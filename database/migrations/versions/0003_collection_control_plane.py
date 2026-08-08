"""Create versioned collection definitions, runs, and the durable task queue.

Revision ID: 0003_collection_control_plane
Revises: 0002_location_master
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_collection_control_plane"
down_revision: str | None = "0002_location_master"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_ORGANIZATION_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    organization = op.create_table(
        "organization",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.bulk_insert(
        organization,
        [{"id": DEFAULT_ORGANIZATION_ID, "name": "Standalone RCI"}],
    )
    op.create_table(
        "app_user",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organization.id"),
            nullable=False,
        ),
        sa.Column("email", sa.Text(), nullable=False, unique=True),
        sa.Column("display_name", sa.Text()),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("role IN ('admin', 'analyst', 'viewer')", name="app_user_role_ck"),
    )

    op.create_table(
        "collection_definition",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organization.id"),
            nullable=False,
        ),
        sa.Column("stable_key", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "organization_id",
            "stable_key",
            name="collection_definition_org_key_uq",
        ),
    )
    op.create_table(
        "collection_definition_version",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "definition_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("collection_definition.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("config", postgresql.JSONB(), nullable=False),
        sa.Column("checksum", sa.Text(), nullable=False),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("definition_id", "version", name="collection_definition_version_uq"),
        sa.UniqueConstraint("definition_id", "checksum", name="collection_definition_checksum_uq"),
    )
    op.create_index(
        "collection_definition_version_latest_idx",
        "collection_definition_version",
        ["definition_id", "version"],
    )

    op.create_table(
        "collection_run",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organization.id"),
            nullable=False,
        ),
        sa.Column(
            "definition_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("collection_definition_version.id"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("estimated_pages", sa.Integer(), nullable=False),
        sa.Column("estimated_credits", sa.Integer(), nullable=False),
        sa.Column("actual_success_pages", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("actual_credits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_user.id")),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True)),
        sa.Column("error_summary", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'cancel_requested', 'cancelled', "
            "'succeeded', 'failed')",
            name="collection_run_status_ck",
        ),
    )
    op.create_index("collection_run_status_idx", "collection_run", ["status", "created_at"])

    op.create_table(
        "collection_task",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "collection_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("collection_run.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("retailer_id", sa.Text(), sa.ForeignKey("retailer.id"), nullable=False),
        sa.Column(
            "retailer_location_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("retailer_location.id"),
        ),
        sa.Column("adapter_id", sa.Text(), nullable=False),
        sa.Column("location_scope_key", sa.Text(), nullable=False),
        sa.Column("zipcode", sa.Text(), nullable=False),
        sa.Column("store_number", sa.Text()),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("max_pages", sa.Integer(), nullable=False),
        sa.Column("stop_on_empty", sa.Boolean(), nullable=False),
        sa.Column("stop_on_short_page", sa.Boolean(), nullable=False),
        sa.Column("credits_per_success", sa.Integer(), nullable=False),
        sa.Column("request_payload", postgresql.JSONB(), nullable=False),
        sa.Column("request_fingerprint", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("locked_by", sa.Text()),
        sa.Column("locked_at", sa.DateTime(timezone=True)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("http_status", sa.Integer()),
        sa.Column("result_count", sa.Integer()),
        sa.Column("failure_class", sa.Text()),
        sa.Column("last_error", sa.Text()),
        sa.Column("billable_credits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("page_number BETWEEN 1 AND 10", name="collection_task_page_ck"),
        sa.CheckConstraint("max_pages BETWEEN 1 AND 10", name="collection_task_max_pages_ck"),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed', 'cancelled')",
            name="collection_task_status_ck",
        ),
        sa.UniqueConstraint(
            "collection_run_id",
            "retailer_id",
            "location_scope_key",
            "page_number",
            "request_fingerprint",
            name="collection_task_identity_uq",
        ),
    )
    op.create_index(
        "collection_task_claim_idx",
        "collection_task",
        ["status", "available_at", "lease_expires_at", "priority", "created_at"],
    )
    op.create_index(
        "collection_task_run_idx",
        "collection_task",
        ["collection_run_id", "retailer_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("collection_task_run_idx", table_name="collection_task")
    op.drop_index("collection_task_claim_idx", table_name="collection_task")
    op.drop_table("collection_task")
    op.drop_index("collection_run_status_idx", table_name="collection_run")
    op.drop_table("collection_run")
    op.drop_index(
        "collection_definition_version_latest_idx",
        table_name="collection_definition_version",
    )
    op.drop_table("collection_definition_version")
    op.drop_table("collection_definition")
    op.drop_table("app_user")
    op.drop_table("organization")
