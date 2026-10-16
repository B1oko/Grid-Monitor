"""Remove alert events left behind by inverters that were deleted.

Revision ID: 0004_orphan_alerts
Revises: 0003_i18n
Create Date: 2026-10-16
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0004_orphan_alerts"
down_revision: Union[str, None] = "0003_i18n"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DELETE FROM alert_events WHERE inverter_id NOT IN (SELECT id FROM inverters)")


def downgrade() -> None:
    pass
