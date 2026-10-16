"""Electricity tariffs used to estimate costs.

Revision ID: 0005_tariffs
Revises: 0004_orphan_alerts
Create Date: 2026-10-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_tariffs"
down_revision: Union[str, None] = "0004_orphan_alerts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PRICES = (
    "energy_price_p1",
    "energy_price_p2",
    "energy_price_p3",
    "power_price_p1",
    "power_price_p2",
    "contracted_power_p1_kw",
    "contracted_power_p2_kw",
)
OPTIONAL = ("export_price", "fixed_daily", "electricity_tax_pct", "vat_pct")


def upgrade() -> None:
    op.create_table(
        "tariffs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("valid_from", sa.Date(), nullable=False),
        *(sa.Column(name, sa.Float(), nullable=False) for name in PRICES),
        *(sa.Column(name, sa.Float(), nullable=False, server_default="0") for name in OPTIONAL),
        sa.UniqueConstraint("valid_from", name="uq_tariff_valid_from"),
    )


def downgrade() -> None:
    op.drop_table("tariffs")
