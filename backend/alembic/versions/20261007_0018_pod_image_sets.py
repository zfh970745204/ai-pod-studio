"""Add versioned POD image sets and image slots."""

import sqlalchemy as sa

from alembic import op

revision = "20261007_0018"
down_revision = "20261007_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE pod_image_sets (
            id uuid PRIMARY KEY,
            product_id uuid NOT NULL REFERENCES pod_products(id) ON DELETE RESTRICT,
            generation_job_id uuid REFERENCES image_jobs(id) ON DELETE RESTRICT,
            version integer NOT NULL,
            strategy_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
            status varchar(16) NOT NULL DEFAULT 'active',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_pod_image_sets_status CHECK (status IN ('active', 'archived')),
            CONSTRAINT uq_pod_image_sets_product_version UNIQUE (product_id, version)
        )
    """)
    op.execute(
        "CREATE UNIQUE INDEX uq_pod_image_sets_product_active "
        "ON pod_image_sets (product_id) WHERE status = 'active'"
    )
    op.create_index(
        "ix_pod_image_sets_product_created", "pod_image_sets", ["product_id", "created_at", "id"]
    )

    op.execute("""
        CREATE TABLE pod_image_slots (
            id uuid PRIMARY KEY,
            image_set_id uuid NOT NULL REFERENCES pod_image_sets(id) ON DELETE RESTRICT,
            code varchar(64) NOT NULL,
            title varchar(160) NOT NULL,
            scope varchar(32) NOT NULL,
            requires_print boolean NOT NULL DEFAULT true,
            scene_prompt text NOT NULL,
            composition_prompt text NOT NULL,
            style_prompt text NOT NULL,
            sort_order integer NOT NULL,
            asset_id uuid REFERENCES assets(id) ON DELETE RESTRICT,
            generation_job_id uuid REFERENCES image_jobs(id) ON DELETE RESTRICT,
            prompt_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
            status varchar(16) NOT NULL DEFAULT 'planned',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_pod_image_slots_scope CHECK (scope IN ('product_specific', 'generic')),
            CONSTRAINT ck_pod_image_slots_status CHECK (status IN ('planned', 'generated', 'approved', 'rejected')),
            CONSTRAINT uq_pod_image_slots_set_code UNIQUE (image_set_id, code)
        )
    """)
    op.create_index("ix_pod_image_slots_set_order", "pod_image_slots", ["image_set_id", "sort_order", "id"])
    op.create_index("ix_pod_image_slots_generation_job", "pod_image_slots", ["generation_job_id"])

    for row in (
        (
            "f0000000-0000-4000-8000-000000000029",
            "f0000000-0000-4000-8000-000000000030",
            "pod.image.strategy.generate",
            "AI 图片套组规划",
            3,
            240,
            2,
        ),
        (
            "f0000000-0000-4000-8000-000000000031",
            "f0000000-0000-4000-8000-000000000032",
            "pod.visual.generic",
            "AI 通用商品视觉",
            15,
            480,
            2,
        ),
    ):
        op.execute(
            sa.text("""
                INSERT INTO operation_catalog (id, code, name, engine_type, queue_name, enabled, timeout_seconds, max_attempts)
                VALUES (CAST(:id AS uuid), :code, :name, 'sub2api', 'image-jobs', true, :timeout, :attempts)
                ON CONFLICT (code) DO NOTHING
            """).bindparams(id=row[0], code=row[2], name=row[3], timeout=row[5], attempts=row[6])
        )
        op.execute(
            sa.text("""
                INSERT INTO operation_prices (id, operation_id, version, base_points, parameter_rules, effective_from, reason)
                SELECT CAST(:price_id AS uuid), id, 1, :points, '{}'::jsonb, now(), 'POD image set initial price'
                FROM operation_catalog WHERE code = :code
                AND NOT EXISTS (SELECT 1 FROM operation_prices WHERE operation_id = operation_catalog.id)
            """).bindparams(price_id=row[1], points=row[4], code=row[2])
        )
    op.execute(sa.text("INSERT INTO schema_migrations (version) VALUES (:version)").bindparams(version=revision))


def downgrade() -> None:
    op.execute("UPDATE operation_catalog SET enabled = false WHERE code IN ('pod.image.strategy.generate', 'pod.visual.generic')")
    op.execute(sa.text("DELETE FROM schema_migrations WHERE version = :version").bindparams(version=revision))
