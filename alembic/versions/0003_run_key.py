"""test_runs.run_key: optional idempotency key, unique per repo

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-17
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

NAME = "uq_test_run_repo_run_key"


def upgrade() -> None:
    with op.batch_alter_table("test_runs") as batch:  # batch = also works on SQLite
        batch.add_column(sa.Column("run_key", sa.String(length=128), nullable=True))
        batch.create_unique_constraint(NAME, ["repo_id", "run_key"])


def downgrade() -> None:
    with op.batch_alter_table("test_runs") as batch:
        batch.drop_constraint(NAME, type_="unique")
        batch.drop_column("run_key")
