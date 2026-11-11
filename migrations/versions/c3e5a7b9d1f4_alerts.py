"""alerts: searches saved from the Telegram bot that trigger a message when a matching deal arrives

Revision ID: c3e5a7b9d1f4
Revises: b7d1f3a5c9e2
Create Date: 2026-11-11 00:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c3e5a7b9d1f4"
down_revision: Union[str, None] = "b7d1f3a5c9e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=False, index=True),
        sa.Column("query", sa.String(length=200), nullable=False),
        sa.Column("max_price", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("alerts")
