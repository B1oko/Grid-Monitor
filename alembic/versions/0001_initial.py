"""Initial schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "inverters",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("driver_id", sa.String(length=64), nullable=False),
        sa.Column("host", sa.String(length=255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False, server_default="502"),
        sa.Column("unit_id", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("timeout_seconds", sa.Float(), nullable=False, server_default="3"),
        sa.Column("poll_interval_s", sa.Float(), nullable=False, server_default="2"),
        sa.Column("battery_capacity_kwh", sa.Float(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("extra", sa.JSON(), nullable=True),
    )
    op.create_table(
        "inverter_samples",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("inverter_id", sa.Integer(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pv_power_w", sa.Integer(), nullable=True),
        sa.Column("battery_power_w", sa.Integer(), nullable=True),
        sa.Column("grid_power_w", sa.Integer(), nullable=True),
        sa.Column("load_power_w", sa.Integer(), nullable=True),
        sa.Column("inverter_power_w", sa.Integer(), nullable=True),
        sa.Column("battery_soc_pct", sa.Float(), nullable=True),
        sa.Column("battery_temp_c", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["inverter_id"], ["inverters.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("inverter_id", "ts", name="uq_inverter_sample_ts"),
    )
    op.create_index("ix_inverter_samples_inverter_id", "inverter_samples", ["inverter_id"])
    op.create_index("ix_inverter_samples_ts", "inverter_samples", ["ts"])
    op.create_table(
        "settings",
        sa.Column("key", sa.String(length=64), primary_key=True),
        sa.Column("value", sa.JSON(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("settings")
    op.drop_index("ix_inverter_samples_ts", table_name="inverter_samples")
    op.drop_index("ix_inverter_samples_inverter_id", table_name="inverter_samples")
    op.drop_table("inverter_samples")
    op.drop_table("inverters")
