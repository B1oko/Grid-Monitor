"""Per-device notification language and language-neutral alert parameters.

Revision ID: 0003_i18n
Revises: 0002_alerts
Create Date: 2026-10-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_i18n"
down_revision: Union[str, None] = "0002_alerts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("push_subscriptions") as batch:
        batch.add_column(
            sa.Column("language", sa.String(length=16), nullable=False, server_default="en")
        )
    with op.batch_alter_table("alert_events") as batch:
        batch.add_column(sa.Column("params", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("alert_events") as batch:
        batch.drop_column("params")
    with op.batch_alter_table("push_subscriptions") as batch:
        batch.drop_column("language")
