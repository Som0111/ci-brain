"""CHECK: test_results.duration_seconds must be NULL or >= 0

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-17
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

NAME = "ck_test_results_duration_nonneg"


def upgrade() -> None:
    # The ingestion API has rejected negative/non-finite durations since P0 item 1, so this should
    # touch nothing; it only guarantees the constraint can be added to older data.
    op.execute("UPDATE test_results SET duration_seconds = NULL WHERE duration_seconds < 0")
    with op.batch_alter_table("test_results") as batch:  # batch = also works on SQLite
        batch.create_check_constraint(NAME, "duration_seconds IS NULL OR duration_seconds >= 0")


def downgrade() -> None:
    with op.batch_alter_table("test_results") as batch:
        batch.drop_constraint(NAME, type_="check")
