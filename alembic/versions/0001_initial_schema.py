"""initial schema: repos, test_cases, test_runs, test_results

Revision ID: 0001
Revises:
Create Date: 2026-08-15
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "repos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_repos_name", "repos", ["name"], unique=True)

    op.create_table(
        "test_cases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("repo_id", sa.Integer(), sa.ForeignKey("repos.id"), nullable=False),
        sa.Column("node_id", sa.String(length=1000), nullable=False),
        sa.Column("file_path", sa.String(length=1000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("repo_id", "node_id", name="uq_test_case_repo_node"),
    )
    op.create_index("ix_test_cases_repo_id", "test_cases", ["repo_id"])

    op.create_table(
        "test_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("repo_id", sa.Integer(), sa.ForeignKey("repos.id"), nullable=False),
        sa.Column("commit_sha", sa.String(length=40), nullable=True),
        sa.Column("branch", sa.String(length=255), nullable=True),
        sa.Column("source", sa.Enum("junit", "coverage", name="run_source"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("coverage_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_test_runs_repo_id", "test_runs", ["repo_id"])

    op.create_table(
        "test_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("test_run_id", sa.Integer(), sa.ForeignKey("test_runs.id"), nullable=False),
        sa.Column("test_case_id", sa.Integer(), sa.ForeignKey("test_cases.id"), nullable=False),
        sa.Column(
            "status",
            sa.Enum("passed", "failed", "skipped", "error", name="test_status"),
            nullable=False,
        ),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_test_results_test_run_id", "test_results", ["test_run_id"])
    op.create_index("ix_test_results_test_case_id", "test_results", ["test_case_id"])


def downgrade() -> None:
    op.drop_table("test_results")
    op.drop_table("test_runs")
    op.drop_table("test_cases")
    op.drop_table("repos")
    sa.Enum(name="run_source").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="test_status").drop(op.get_bind(), checkfirst=True)
