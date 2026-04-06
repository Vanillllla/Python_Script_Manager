"""Initial schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-07 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "interpreters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("arch", sa.String(length=64), nullable=False),
        sa.Column("python_exe", sa.String(length=2048), nullable=False),
        sa.Column("source_path", sa.String(length=2048), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("python_exe"),
    )
    op.create_table(
        "settings",
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_table(
        "environments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("base_interpreter_id", sa.Integer(), nullable=False),
        sa.Column("env_path", sa.String(length=2048), nullable=False),
        sa.Column("python_exe", sa.String(length=2048), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["base_interpreter_id"], ["interpreters.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("env_path"),
    )
    op.create_table(
        "scripts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("script_path", sa.String(length=2048), nullable=False),
        sa.Column("cwd", sa.String(length=2048), nullable=False),
        sa.Column("interpreter_env_id", sa.Integer(), nullable=True),
        sa.Column("autostart", sa.Boolean(), nullable=False),
        sa.Column("desired_state", sa.String(length=32), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["interpreter_env_id"], ["environments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "module_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("environment_id", sa.Integer(), nullable=False),
        sa.Column("package_name", sa.String(length=255), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("refreshed_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["environment_id"], ["environments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("script_id", sa.Integer(), nullable=False),
        sa.Column("pid", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("pause_state", sa.String(length=32), nullable=False),
        sa.Column("terminal_backend", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["script_id"], ["scripts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "terminal_sessions",
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("pty_backend", sa.String(length=32), nullable=False),
        sa.Column("cols", sa.Integer(), nullable=False),
        sa.Column("rows", sa.Integer(), nullable=False),
        sa.Column("last_output_seq", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"]),
        sa.PrimaryKeyConstraint("run_id"),
    )


def downgrade() -> None:
    op.drop_table("terminal_sessions")
    op.drop_table("runs")
    op.drop_table("module_snapshots")
    op.drop_table("scripts")
    op.drop_table("environments")
    op.drop_table("settings")
    op.drop_table("interpreters")

