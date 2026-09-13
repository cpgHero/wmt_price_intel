"""Add CPGHero account, workspace, role, and entitlement foundations.

Revision ID: 0054_account_access_foundation
Revises: 0053_scope_projections
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0054_account_access_foundation"
down_revision: str | None = "0053_scope_projections"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_ORGANIZATION_ID = "00000000-0000-0000-0000-000000000001"
DEFAULT_ACCOUNT_ID = "00000000-0000-0000-0000-000000000101"
DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000201"


def _uuid_primary_key() -> sa.Column[object]:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )


def upgrade() -> None:
    op.create_table(
        "account",
        _uuid_primary_key(),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organization.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("slug", sa.Text(), nullable=False, unique=True),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("account_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "account_type IN ('system','customer','partner','internal')",
            name="account_type_ck",
        ),
        sa.CheckConstraint(
            "status IN ('active','suspended','archived')",
            name="account_status_ck",
        ),
        sa.CheckConstraint(
            "slug ~ '^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$'",
            name="account_slug_ck",
        ),
    )
    op.create_index("account_status_idx", "account", ["status", "account_type"])

    op.create_table(
        "workspace",
        _uuid_primary_key(),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('active','suspended','archived')",
            name="workspace_status_ck",
        ),
        sa.CheckConstraint(
            "slug ~ '^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$'",
            name="workspace_slug_ck",
        ),
        sa.UniqueConstraint("account_id", "slug", name="workspace_account_slug_uq"),
    )
    op.create_index("workspace_account_status_idx", "workspace", ["account_id", "status"])

    op.create_table(
        "platform_permission",
        sa.Column("permission_key", sa.Text(), primary_key=True),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("customer_visible", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "platform_role",
        _uuid_primary_key(),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
        ),
        sa.Column("role_key", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("role_scope", sa.Text(), nullable=False),
        sa.Column("system_managed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "role_scope IN ('system','account','workspace','project')",
            name="platform_role_scope_ck",
        ),
        sa.CheckConstraint(
            "role_key ~ '^[a-z][a-z0-9_]{1,63}$'",
            name="platform_role_key_ck",
        ),
        sa.UniqueConstraint("account_id", "role_key", name="platform_role_account_key_uq"),
    )
    op.create_index(
        "platform_role_system_key_uq",
        "platform_role",
        ["role_key"],
        unique=True,
        postgresql_where=sa.text("account_id IS NULL"),
    )

    op.create_table(
        "platform_role_permission",
        sa.Column(
            "role_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform_role.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "permission_key",
            sa.Text(),
            sa.ForeignKey("platform_permission.permission_key", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint(
            "role_id",
            "permission_key",
            name="platform_role_permission_pk",
        ),
    )

    op.create_table(
        "account_membership",
        _uuid_primary_key(),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('active','invited','suspended','removed')",
            name="account_membership_status_ck",
        ),
        sa.UniqueConstraint("account_id", "user_id", name="account_membership_user_uq"),
    )
    op.create_index(
        "account_membership_user_idx",
        "account_membership",
        ["user_id", "status"],
    )

    op.create_table(
        "account_membership_role",
        sa.Column(
            "account_membership_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("account_membership.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "role_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform_role.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint(
            "account_membership_id",
            "role_id",
            name="account_membership_role_pk",
        ),
    )

    op.create_table(
        "workspace_membership",
        _uuid_primary_key(),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspace.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "account_membership_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("account_membership.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('active','invited','suspended','removed')",
            name="workspace_membership_status_ck",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "account_membership_id",
            name="workspace_membership_user_uq",
        ),
    )

    op.create_table(
        "workspace_membership_role",
        sa.Column(
            "workspace_membership_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspace_membership.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "role_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform_role.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint(
            "workspace_membership_id",
            "role_id",
            name="workspace_membership_role_pk",
        ),
    )

    op.create_table(
        "account_entitlement",
        _uuid_primary_key(),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entitlement_key", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("configuration", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("limits", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("starts_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column(
            "granted_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('active','paused','expired','revoked')",
            name="account_entitlement_status_ck",
        ),
        sa.CheckConstraint(
            "entitlement_key ~ '^[a-z][a-z0-9_.]{1,95}$'",
            name="account_entitlement_key_ck",
        ),
        sa.UniqueConstraint(
            "account_id",
            "entitlement_key",
            name="account_entitlement_key_uq",
        ),
    )
    op.create_index(
        "account_entitlement_status_idx",
        "account_entitlement",
        ["account_id", "status", "entitlement_key"],
    )

    op.add_column(
        "audit_event",
        sa.Column("account_id", postgresql.UUID(as_uuid=True)),
    )
    op.add_column(
        "audit_event",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True)),
    )
    op.add_column("audit_event", sa.Column("actor_type", sa.Text()))
    op.add_column("audit_event", sa.Column("request_id", sa.Text()))
    op.add_column("audit_event", sa.Column("ip_hash", sa.String(length=64)))
    op.add_column("audit_event", sa.Column("user_agent_hash", sa.String(length=64)))
    op.create_foreign_key(
        "audit_event_account_fk",
        "audit_event",
        "account",
        ["account_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "audit_event_workspace_fk",
        "audit_event",
        "workspace",
        ["workspace_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("audit_event_account_idx", "audit_event", ["account_id", "created_at"])
    op.create_index("audit_event_workspace_idx", "audit_event", ["workspace_id", "created_at"])

    op.execute(
        """
        INSERT INTO account (id, organization_id, slug, display_name, account_type, metadata)
        VALUES (
          '00000000-0000-0000-0000-000000000101',
          '00000000-0000-0000-0000-000000000001',
          'cpghero-system',
          'CPGHero System',
          'system',
          '{"migration":"0054_account_access_foundation"}'::jsonb
        )
        ON CONFLICT (organization_id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO workspace (id, account_id, slug, display_name, metadata)
        VALUES (
          '00000000-0000-0000-0000-000000000201',
          '00000000-0000-0000-0000-000000000101',
          'default',
          'Default workspace',
          '{"migration":"0054_account_access_foundation"}'::jsonb
        )
        ON CONFLICT (account_id, slug) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO platform_permission (permission_key, category, description, customer_visible)
        VALUES
          (
            'users.manage',
            'account',
            'Invite, suspend, and manage account users.',
            true
          ),
          (
            'roles.manage',
            'account',
            'Manage account roles and permission assignments.',
            true
          ),
          (
            'api_keys.manage',
            'live_api',
            'Create, rotate, and revoke customer API keys.',
            true
          ),
          (
            'projects.create',
            'bulk_projects',
            'Create Bulk Project drafts.',
            true
          ),
          (
            'projects.manage',
            'bulk_projects',
            'Manage Bulk Project configuration and status.',
            true
          ),
          (
            'projects.approve_paid_run',
            'bulk_projects',
            'Approve paid collection work.',
            true
          ),
          (
            'exports.download',
            'data',
            'Download permitted datasets and report artifacts.',
            true
          ),
          (
            'analytics.view',
            'analytics',
            'View entitled analytics modules and reports.',
            true
          ),
          (
            'analytics.share',
            'analytics',
            'Create governed report shares.',
            true
          ),
          (
            'billing.view',
            'billing',
            'View usage, credit consumption, and billing exports.',
            true
          ),
          (
            'system.admin',
            'system',
            'Administer platform-wide system settings.',
            false
          ),
          (
            'system.provider_admin',
            'system',
            'Administer private source adapters and credentials.',
            false
          ),
          (
            'system.governance',
            'system',
            'Administer Product Packs, matching, and evidence governance.',
            false
          )
        ON CONFLICT (permission_key) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO platform_role (
          account_id, role_key, display_name, description, role_scope, system_managed
        )
        VALUES
          (
            NULL,
            'system_owner',
            'System owner',
            'Full platform owner access.',
            'system',
            true
          ),
          (
            NULL,
            'system_admin',
            'System admin',
            'Platform operations and support access.',
            'system',
            true
          ),
          (
            NULL,
            'system_analyst',
            'System analyst',
            'Internal analytics and governance support.',
            'system',
            true
          ),
          (
            '00000000-0000-0000-0000-000000000101',
            'account_owner',
            'Account owner',
            'Owns account settings, users, usage, and all projects.',
            'account',
            true
          ),
          (
            '00000000-0000-0000-0000-000000000101',
            'account_admin',
            'Account admin',
            'Manages users, projects, and delivery settings.',
            'account',
            true
          ),
          (
            '00000000-0000-0000-0000-000000000101',
            'project_owner',
            'Project owner',
            'Creates and manages assigned projects.',
            'project',
            true
          ),
          (
            '00000000-0000-0000-0000-000000000101',
            'analyst',
            'Analyst',
            'Explores analytics and downloads permitted evidence.',
            'workspace',
            true
          ),
          (
            '00000000-0000-0000-0000-000000000101',
            'viewer',
            'Viewer',
            'Views permitted reports and dashboards.',
            'workspace',
            true
          ),
          (
            '00000000-0000-0000-0000-000000000101',
            'developer',
            'Developer',
            'Uses developer docs, API keys, and integration diagnostics.',
            'account',
            true
          ),
          (
            '00000000-0000-0000-0000-000000000101',
            'billing_user',
            'Billing user',
            'Views usage and billing exports.',
            'account',
            true
          )
        ON CONFLICT DO NOTHING
        """
    )
    op.execute(
        """
        WITH role_permissions(role_key, permission_key) AS (
          VALUES
            ('system_owner', 'system.admin'),
            ('system_owner', 'system.provider_admin'),
            ('system_owner', 'system.governance'),
            ('system_admin', 'system.admin'),
            ('system_admin', 'system.governance'),
            ('system_analyst', 'system.governance'),
            ('account_owner', 'users.manage'),
            ('account_owner', 'roles.manage'),
            ('account_owner', 'api_keys.manage'),
            ('account_owner', 'projects.create'),
            ('account_owner', 'projects.manage'),
            ('account_owner', 'projects.approve_paid_run'),
            ('account_owner', 'exports.download'),
            ('account_owner', 'analytics.view'),
            ('account_owner', 'analytics.share'),
            ('account_owner', 'billing.view'),
            ('account_admin', 'users.manage'),
            ('account_admin', 'api_keys.manage'),
            ('account_admin', 'projects.create'),
            ('account_admin', 'projects.manage'),
            ('account_admin', 'projects.approve_paid_run'),
            ('account_admin', 'exports.download'),
            ('account_admin', 'analytics.view'),
            ('account_admin', 'analytics.share'),
            ('project_owner', 'projects.create'),
            ('project_owner', 'projects.manage'),
            ('project_owner', 'projects.approve_paid_run'),
            ('project_owner', 'exports.download'),
            ('project_owner', 'analytics.view'),
            ('project_owner', 'analytics.share'),
            ('analyst', 'exports.download'),
            ('analyst', 'analytics.view'),
            ('analyst', 'analytics.share'),
            ('viewer', 'analytics.view'),
            ('developer', 'api_keys.manage'),
            ('developer', 'billing.view'),
            ('billing_user', 'billing.view')
        )
        INSERT INTO platform_role_permission (role_id, permission_key)
        SELECT role.id, role_permissions.permission_key
        FROM role_permissions
        JOIN platform_role role ON role.role_key = role_permissions.role_key
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("audit_event_workspace_idx", table_name="audit_event")
    op.drop_index("audit_event_account_idx", table_name="audit_event")
    op.drop_constraint("audit_event_workspace_fk", "audit_event", type_="foreignkey")
    op.drop_constraint("audit_event_account_fk", "audit_event", type_="foreignkey")
    op.drop_column("audit_event", "user_agent_hash")
    op.drop_column("audit_event", "ip_hash")
    op.drop_column("audit_event", "request_id")
    op.drop_column("audit_event", "actor_type")
    op.drop_column("audit_event", "workspace_id")
    op.drop_column("audit_event", "account_id")
    op.drop_index("account_entitlement_status_idx", table_name="account_entitlement")
    op.drop_table("account_entitlement")
    op.drop_table("workspace_membership_role")
    op.drop_table("workspace_membership")
    op.drop_table("account_membership_role")
    op.drop_index("account_membership_user_idx", table_name="account_membership")
    op.drop_table("account_membership")
    op.drop_table("platform_role_permission")
    op.drop_index("platform_role_system_key_uq", table_name="platform_role")
    op.drop_table("platform_role")
    op.drop_table("platform_permission")
    op.drop_index("workspace_account_status_idx", table_name="workspace")
    op.drop_table("workspace")
    op.drop_index("account_status_idx", table_name="account")
    op.drop_table("account")
