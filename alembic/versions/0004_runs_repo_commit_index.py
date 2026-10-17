"""index test_runs (repo_id, commit_sha) for flakiness / dependency-graph filters

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-17
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

NAME = "ix_test_runs_repo_commit"


def upgrade() -> None:
    op.create_index(NAME, "test_runs", ["repo_id", "commit_sha"])


def downgrade() -> None:
    op.drop_index(NAME, table_name="test_runs")
