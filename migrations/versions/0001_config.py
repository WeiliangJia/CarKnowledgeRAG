"""Create the configuration store."""

from alembic import op

revision = "0001_config"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE config_snapshots (
            id text PRIMARY KEY CHECK (length(id) = 64),
            bundle_sha256 text NOT NULL CHECK (length(bundle_sha256) = 64),
            model_info_id text NOT NULL,
            model_year_code text NOT NULL,
            source_url text NOT NULL,
            captured_at timestamptz NOT NULL,
            source jsonb NOT NULL,
            footnotes jsonb NOT NULL,
            notices jsonb NOT NULL
        )
    """)
    op.execute("""
        CREATE TABLE config_versions (
            snapshot_id text NOT NULL REFERENCES config_snapshots(id),
            column_index integer NOT NULL CHECK (column_index > 0),
            group_label text,
            label text NOT NULL,
            PRIMARY KEY (snapshot_id, column_index)
        )
    """)
    op.execute("""
        CREATE TABLE config_fields (
            snapshot_id text NOT NULL REFERENCES config_snapshots(id),
            row_index integer NOT NULL CHECK (row_index > 0),
            field_id text NOT NULL,
            name text NOT NULL,
            unit text,
            test_cycle text,
            range_type text,
            definition jsonb NOT NULL,
            PRIMARY KEY (snapshot_id, row_index),
            UNIQUE (snapshot_id, field_id)
        )
    """)
    op.execute("""
        CREATE TABLE config_facts (
            snapshot_id text NOT NULL,
            row_index integer NOT NULL,
            column_index integer NOT NULL,
            raw text NOT NULL,
            number numeric,
            status text NOT NULL CHECK (status IN (
                'standard', 'optional', 'unavailable', 'unknown'
            )),
            qualifier text,
            footnote_ids jsonb NOT NULL,
            pending_reason text,
            review_status text NOT NULL CHECK (review_status IN (
                'not_reviewed', 'confirmed', 'confirmed_conditions', 'insufficient_evidence'
            )),
            review_evidence jsonb,
            PRIMARY KEY (snapshot_id, row_index, column_index),
            FOREIGN KEY (snapshot_id, row_index)
                REFERENCES config_fields(snapshot_id, row_index),
            FOREIGN KEY (snapshot_id, column_index)
                REFERENCES config_versions(snapshot_id, column_index)
        )
    """)
    op.execute(
        "CREATE INDEX config_facts_version_idx ON config_facts(snapshot_id, column_index)"
    )


def downgrade():
    for name in (
        "config_facts",
        "config_fields",
        "config_versions",
        "config_snapshots",
    ):
        op.drop_table(name)
