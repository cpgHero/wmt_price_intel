"""Add customer auth provisioning and webhook audit tables.

Revision ID: 0056_customer_auth_provisioning
Revises: 0055_workos_identity_mapping
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0056_customer_auth_provisioning"
down_revision: str | None = "0055_workos_identity_mapping"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid_primary_key() -> sa.Column[object]:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )


def upgrade() -> None:
    op.create_table(
        "customer_account_invitation",
        _uuid_primary_key(),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspace.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text()),
        sa.Column("status", sa.Text(), nullable=False, server_default="prepared"),
        sa.Column(
            "role_keys",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column(
            "entitlement_keys",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("workos_invitation_id", sa.Text()),
        sa.Column("workos_organization_id", sa.Text()),
        sa.Column("workos_user_id", sa.Text()),
        sa.Column(
            "prepared_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id", ondelete="SET NULL"),
        ),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('prepared','sent','accepted','revoked','expired','failed')",
            name="customer_account_invitation_status_ck",
        ),
        sa.CheckConstraint(
            "email = lower(btrim(email)) AND position('@' in email) > 1",
            name="customer_account_invitation_email_ck",
        ),
        sa.UniqueConstraint(
            "account_id",
            "email",
            name="customer_account_invitation_account_email_uq",
        ),
    )
    op.create_index(
        "customer_account_invitation_status_idx",
        "customer_account_invitation",
        ["account_id", "status", "created_at"],
    )
    op.create_index(
        "customer_account_invitation_workos_invitation_idx",
        "customer_account_invitation",
        ["workos_invitation_id"],
        unique=True,
        postgresql_where=sa.text("workos_invitation_id IS NOT NULL"),
    )
    op.create_index(
        "customer_account_invitation_workos_user_idx",
        "customer_account_invitation",
        ["workos_user_id"],
        postgresql_where=sa.text("workos_user_id IS NOT NULL"),
    )

    op.create_table(
        "customer_identity_webhook_event",
        _uuid_primary_key(),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("provider_event_id", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("workos_organization_id", sa.Text()),
        sa.Column("workos_user_id", sa.Text()),
        sa.Column("workos_invitation_id", sa.Text()),
        sa.Column("email_snapshot", sa.Text()),
        sa.Column("processing_status", sa.Text(), nullable=False, server_default="received"),
        sa.Column("processing_error", sa.Text()),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "provider IN ('workos')",
            name="customer_identity_webhook_event_provider_ck",
        ),
        sa.CheckConstraint(
            "processing_status IN ('received','processed','ignored','failed','duplicate')",
            name="customer_identity_webhook_event_processing_status_ck",
        ),
        sa.CheckConstraint(
            "length(btrim(provider_event_id)) > 0",
            name="customer_identity_webhook_event_provider_event_id_ck",
        ),
        sa.UniqueConstraint(
            "provider",
            "provider_event_id",
            name="customer_identity_webhook_event_provider_event_uq",
        ),
    )
    op.create_index(
        "customer_identity_webhook_event_type_idx",
        "customer_identity_webhook_event",
        ["provider", "event_type", "received_at"],
    )
    op.create_index(
        "customer_identity_webhook_event_processing_idx",
        "customer_identity_webhook_event",
        ["processing_status", "received_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "customer_identity_webhook_event_processing_idx",
        table_name="customer_identity_webhook_event",
    )
    op.drop_index(
        "customer_identity_webhook_event_type_idx",
        table_name="customer_identity_webhook_event",
    )
    op.drop_table("customer_identity_webhook_event")
    op.drop_index(
        "customer_account_invitation_workos_user_idx",
        table_name="customer_account_invitation",
    )
    op.drop_index(
        "customer_account_invitation_workos_invitation_idx",
        table_name="customer_account_invitation",
    )
    op.drop_index(
        "customer_account_invitation_status_idx",
        table_name="customer_account_invitation",
    )
    op.drop_table("customer_account_invitation")
