"""Add WorkOS AuthKit identity mapping foundation.

Revision ID: 0055_workos_identity_mapping
Revises: 0054_account_access_foundation
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0055_workos_identity_mapping"
down_revision: str | None = "0054_account_access_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "external_identity",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("subject_type", sa.Text(), nullable=False),
        sa.Column("subject_id", sa.Text(), nullable=False),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
        ),
        sa.Column("email_snapshot", sa.Text()),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "provider IN ('workos')",
            name="external_identity_provider_ck",
        ),
        sa.CheckConstraint(
            "subject_type IN ('user','organization')",
            name="external_identity_subject_type_ck",
        ),
        sa.CheckConstraint(
            "length(btrim(subject_id)) > 0",
            name="external_identity_subject_id_present_ck",
        ),
        sa.CheckConstraint(
            """
            (
              subject_type = 'organization'
              AND account_id IS NOT NULL
              AND user_id IS NULL
            )
            OR
            (
              subject_type = 'user'
              AND user_id IS NOT NULL
            )
            """,
            name="external_identity_subject_binding_ck",
        ),
        sa.UniqueConstraint(
            "provider",
            "subject_type",
            "subject_id",
            name="external_identity_provider_subject_uq",
        ),
    )
    op.create_index(
        "external_identity_account_uq",
        "external_identity",
        ["provider", "account_id"],
        unique=True,
        postgresql_where=sa.text("subject_type = 'organization' AND account_id IS NOT NULL"),
    )
    op.create_index(
        "external_identity_user_uq",
        "external_identity",
        ["provider", "user_id"],
        unique=True,
        postgresql_where=sa.text("subject_type = 'user' AND user_id IS NOT NULL"),
    )
    op.create_index(
        "external_identity_email_idx",
        "external_identity",
        ["provider", "email_snapshot"],
        postgresql_where=sa.text("email_snapshot IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("external_identity_email_idx", table_name="external_identity")
    op.drop_index("external_identity_user_uq", table_name="external_identity")
    op.drop_index("external_identity_account_uq", table_name="external_identity")
    op.drop_table("external_identity")
