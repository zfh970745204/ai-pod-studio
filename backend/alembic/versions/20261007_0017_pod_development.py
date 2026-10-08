"""Add the AI POD product-development domain without replacing core image services."""

import sqlalchemy as sa

from alembic import op

revision = "20261007_0017"
down_revision = "20260913_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE pod_blanks (
            id uuid PRIMARY KEY,
            owner_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            name varchar(160) NOT NULL,
            category varchar(100) NOT NULL,
            material varchar(100) NOT NULL,
            confirmed_attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
            suggested_attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
            product_visual_style jsonb NOT NULL DEFAULT '{}'::jsonb,
            status varchar(16) NOT NULL DEFAULT 'active',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_pod_blanks_status CHECK (status IN ('active', 'archived'))
        )
    """)
    op.create_index("ix_pod_blanks_owner_created", "pod_blanks", ["owner_id", "created_at", "id"])

    op.execute("""
        CREATE TABLE pod_blank_references (
            id uuid PRIMARY KEY,
            blank_id uuid NOT NULL REFERENCES pod_blanks(id) ON DELETE RESTRICT,
            asset_id uuid NOT NULL REFERENCES assets(id) ON DELETE RESTRICT,
            reference_role varchar(16) NOT NULL DEFAULT 'primary',
            sort_order integer NOT NULL DEFAULT 0,
            is_supplier_reference boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_pod_blank_references_role CHECK (reference_role IN ('primary', 'detail', 'lifestyle')),
            CONSTRAINT uq_pod_blank_references_asset UNIQUE (blank_id, asset_id)
        )
    """)
    op.create_index(
        "ix_pod_blank_references_blank_order",
        "pod_blank_references",
        ["blank_id", "sort_order", "id"],
    )

    op.execute("""
        CREATE TABLE pod_development_projects (
            id uuid PRIMARY KEY,
            owner_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            blank_id uuid NOT NULL REFERENCES pod_blanks(id) ON DELETE RESTRICT,
            name varchar(160) NOT NULL,
            status varchar(16) NOT NULL DEFAULT 'draft',
            current_stage varchar(32) NOT NULL DEFAULT 'blank',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_pod_development_projects_status CHECK (status IN ('draft', 'active', 'completed', 'archived'))
        )
    """)
    op.create_index(
        "ix_pod_projects_owner_created",
        "pod_development_projects",
        ["owner_id", "created_at", "id"],
    )
    op.create_index(
        "ix_pod_projects_blank_created",
        "pod_development_projects",
        ["blank_id", "created_at", "id"],
    )

    op.execute("""
        CREATE TABLE pod_product_ideas (
            id uuid PRIMARY KEY,
            project_id uuid NOT NULL REFERENCES pod_development_projects(id) ON DELETE RESTRICT,
            generation_job_id uuid REFERENCES image_jobs(id) ON DELETE RESTRICT,
            generation_batch_id uuid NOT NULL,
            idea_name varchar(200) NOT NULL,
            target_audience text NOT NULL,
            use_case text NOT NULL,
            emotional_angle text NOT NULL,
            design_theme text NOT NULL,
            visual_direction text NOT NULL,
            recommended_style text NOT NULL,
            composition_direction text NOT NULL,
            color_direction text NOT NULL,
            core_elements jsonb NOT NULL DEFAULT '[]'::jsonb,
            avoid_elements jsonb NOT NULL DEFAULT '[]'::jsonb,
            rationale text NOT NULL,
            infringement_risk jsonb NOT NULL DEFAULT '{}'::jsonb,
            status varchar(16) NOT NULL DEFAULT 'proposed',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_pod_product_ideas_status CHECK (status IN ('proposed', 'adopted', 'archived'))
        )
    """)
    op.create_index(
        "ix_pod_product_ideas_project_status",
        "pod_product_ideas",
        ["project_id", "status", "created_at", "id"],
    )
    op.create_index(
        "ix_pod_product_ideas_batch",
        "pod_product_ideas",
        ["generation_batch_id", "created_at", "id"],
    )

    op.execute("""
        CREATE TABLE pod_design_concepts (
            id uuid PRIMARY KEY,
            product_idea_id uuid NOT NULL REFERENCES pod_product_ideas(id) ON DELETE RESTRICT,
            generation_job_id uuid REFERENCES image_jobs(id) ON DELETE RESTRICT,
            design_name varchar(200) NOT NULL,
            visual_style text NOT NULL,
            composition text NOT NULL,
            layout text NOT NULL,
            main_subject text NOT NULL,
            secondary_elements jsonb NOT NULL DEFAULT '[]'::jsonb,
            color_palette text NOT NULL,
            typography_direction text NOT NULL,
            pattern_structure text NOT NULL,
            print_method text NOT NULL,
            recommended_print_area text NOT NULL,
            texture_direction text NOT NULL,
            background_direction text NOT NULL,
            negative_elements jsonb NOT NULL DEFAULT '[]'::jsonb,
            design_prompt text NOT NULL,
            status varchar(16) NOT NULL DEFAULT 'proposed',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_pod_design_concepts_status CHECK (status IN ('proposed', 'adopted', 'archived'))
        )
    """)
    op.create_index(
        "ix_pod_design_concepts_idea_status",
        "pod_design_concepts",
        ["product_idea_id", "status", "created_at", "id"],
    )

    op.execute("""
        CREATE TABLE pod_print_candidates (
            id uuid PRIMARY KEY,
            design_concept_id uuid NOT NULL REFERENCES pod_design_concepts(id) ON DELETE RESTRICT,
            asset_id uuid NOT NULL REFERENCES assets(id) ON DELETE RESTRICT,
            generation_job_id uuid NOT NULL REFERENCES image_jobs(id) ON DELETE RESTRICT,
            prompt_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
            status varchar(16) NOT NULL DEFAULT 'generated',
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_pod_print_candidates_status CHECK (status IN ('generated', 'approved', 'rejected'))
        )
    """)
    op.create_index(
        "ix_pod_print_candidates_concept_created",
        "pod_print_candidates",
        ["design_concept_id", "created_at", "id"],
    )

    op.execute("""
        CREATE TABLE pod_print_masters (
            id uuid PRIMARY KEY,
            project_id uuid NOT NULL REFERENCES pod_development_projects(id) ON DELETE RESTRICT,
            print_candidate_id uuid NOT NULL REFERENCES pod_print_candidates(id) ON DELETE RESTRICT,
            asset_id uuid NOT NULL REFERENCES assets(id) ON DELETE RESTRICT,
            version integer NOT NULL,
            status varchar(16) NOT NULL DEFAULT 'active',
            locked_by uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            locked_at timestamptz NOT NULL,
            CONSTRAINT ck_pod_print_masters_status CHECK (status IN ('active', 'superseded')),
            CONSTRAINT uq_pod_print_masters_candidate UNIQUE (print_candidate_id)
        )
    """)
    op.execute(
        "CREATE UNIQUE INDEX uq_pod_print_masters_project_active ON pod_print_masters (project_id) WHERE status = 'active'"
    )

    op.execute("""
        CREATE TABLE pod_products (
            id uuid PRIMARY KEY,
            owner_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            project_id uuid NOT NULL REFERENCES pod_development_projects(id) ON DELETE RESTRICT,
            product_idea_id uuid NOT NULL REFERENCES pod_product_ideas(id) ON DELETE RESTRICT,
            design_concept_id uuid NOT NULL REFERENCES pod_design_concepts(id) ON DELETE RESTRICT,
            print_master_id uuid NOT NULL REFERENCES pod_print_masters(id) ON DELETE RESTRICT,
            primary_visual_asset_id uuid REFERENCES assets(id) ON DELETE RESTRICT,
            primary_visual_job_id uuid REFERENCES image_jobs(id) ON DELETE RESTRICT,
            status varchar(20) NOT NULL DEFAULT 'drafting',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_pod_products_status CHECK (status IN ('drafting', 'visual_ready', 'review_pending', 'approved', 'rejected')),
            CONSTRAINT uq_pod_products_print_master UNIQUE (print_master_id)
        )
    """)
    op.create_index(
        "ix_pod_products_project_created", "pod_products", ["project_id", "created_at", "id"]
    )

    op.execute("""
        CREATE TABLE pod_reviews (
            id uuid PRIMARY KEY,
            owner_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            target_type varchar(32) NOT NULL,
            target_id uuid NOT NULL,
            gate varchar(2) NOT NULL,
            decision varchar(16) NOT NULL,
            note text,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_pod_reviews_gate CHECK (gate IN ('G0', 'G1', 'G2', 'G3')),
            CONSTRAINT ck_pod_reviews_decision CHECK (decision IN ('approved', 'rejected'))
        )
    """)
    op.create_index(
        "ix_pod_reviews_target", "pod_reviews", ["target_type", "target_id", "created_at", "id"]
    )

    for row in (
        (
            "f0000000-0000-4000-8000-000000000019",
            "f0000000-0000-4000-8000-000000000024",
            "pod.blank.analyze",
            "AI 胚件理解",
            2,
            180,
            2,
        ),
        (
            "f0000000-0000-4000-8000-000000000020",
            "f0000000-0000-4000-8000-000000000025",
            "pod.idea.generate",
            "AI 产品创意",
            4,
            240,
            2,
        ),
        (
            "f0000000-0000-4000-8000-000000000021",
            "f0000000-0000-4000-8000-000000000026",
            "pod.design.generate",
            "AI 设计方案",
            4,
            240,
            2,
        ),
        (
            "f0000000-0000-4000-8000-000000000022",
            "f0000000-0000-4000-8000-000000000027",
            "pod.print.generate",
            "AI 印花候选",
            20,
            480,
            2,
        ),
        (
            "f0000000-0000-4000-8000-000000000023",
            "f0000000-0000-4000-8000-000000000028",
            "pod.visual.generate",
            "AI 商品主图",
            20,
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
                SELECT CAST(:price_id AS uuid), id, 1, :points, '{}'::jsonb, now(), 'POD MVP initial price'
                FROM operation_catalog WHERE code = :code
                AND NOT EXISTS (SELECT 1 FROM operation_prices WHERE operation_id = operation_catalog.id)
            """).bindparams(price_id=row[1], points=row[4], code=row[2])
        )
    op.execute(
        sa.text("INSERT INTO schema_migrations (version) VALUES (:version)").bindparams(
            version=revision
        )
    )


def downgrade() -> None:
    op.execute("UPDATE operation_catalog SET enabled = false WHERE code LIKE 'pod.%'")
    op.execute(
        sa.text("DELETE FROM schema_migrations WHERE version = :version").bindparams(
            version=revision
        )
    )
