"""users and telegram_links: Google accounts of the web and the Telegram chat each one receives alerts in

Revision ID: e7a9c1d3f5b8
Revises: d5f7b9c1e3a6
Create Date: 2026-11-11 01:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e7a9c1d3f5b8"
down_revision: Union[str, None] = "d5f7b9c1e3a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=64), primary_key=True),  # sha256 of the Google sub
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("name", sa.String(length=60), nullable=True),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=True, unique=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "telegram_links",
        sa.Column("code", sa.String(length=32), primary_key=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("telegram_links")
    op.drop_table("users")
