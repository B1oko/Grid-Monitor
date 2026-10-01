"""Alerts and web push subscriptions.

Revision ID: 0002_alerts
Revises: 0001_initial
Create Date: 2026-10-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_alerts"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("endpoint", sa.String(length=1024), nullable=False),
        sa.Column("p256dh", sa.String(length=255), nullable=False),
        sa.Column("auth", sa.String(length=255), nullable=False),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("endpoint", name="uq_push_subscription_endpoint"),
    )
    op.create_table(
        "alert_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("inverter_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("peak_value", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["inverter_id"], ["inverters.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_alert_events_inverter_id", "alert_events", ["inverter_id"])
    op.create_index("ix_alert_events_notified_at", "alert_events", ["notified_at"])


def downgrade() -> None:
    op.drop_index("ix_alert_events_notified_at", table_name="alert_events")
    op.drop_index("ix_alert_events_inverter_id", table_name="alert_events")
    op.drop_table("alert_events")
    op.drop_table("push_subscriptions")
