"""Promote the untouched default branding to AI POD Studio."""

from alembic import op

revision = "20261010_0020"
down_revision = "20261007_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Preserve customer-managed names. Only replace the upstream default on the
    # currently active branding version so the live product matches its POD scope.
    op.execute("""
        UPDATE config_versions AS version
        SET "values" = jsonb_set(
            version."values", '{site_name}', '"AI POD Studio"'::jsonb
        )
        FROM config_groups AS config_group
        WHERE config_group.code = 'branding'
          AND version.group_id = config_group.id
          AND version.version = config_group.active_version
          AND version."values"->>'site_name' = 'Sub2Image'
    """)
    op.execute("INSERT INTO schema_migrations (version) VALUES ('20261010_0020')")


def downgrade() -> None:
    op.execute("""
        UPDATE config_versions AS version
        SET "values" = jsonb_set(
            version."values", '{site_name}', '"Sub2Image"'::jsonb
        )
        FROM config_groups AS config_group
        WHERE config_group.code = 'branding'
          AND version.group_id = config_group.id
          AND version.version = config_group.active_version
          AND version."values"->>'site_name' = 'AI POD Studio'
    """)
    op.execute("DELETE FROM schema_migrations WHERE version = '20261010_0020'")
