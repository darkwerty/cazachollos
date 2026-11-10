"""raw_messages ids as BIGINT and nullable price_sale

Telegram channel ids (-100...) and message ids do not fit in a 32-bit INTEGER. A message without a price is
stored with price_sale NULL instead of 0, which is reserved for real freebies.

Replaces the old ad-hoc script src/infrastructure/db/migrations/fix_int_overflow.py (running this on a database
where that script was already applied is harmless: the columns are already BIGINT).

Revision ID: a1c3e5f7b9d2
Revises: f23685747e04
Create Date: 2026-11-10 02:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1c3e5f7b9d2"
down_revision: Union[str, None] = "f23685747e04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "raw_messages", "chat_id", type_=sa.BigInteger(), existing_type=sa.Integer(), existing_nullable=False
    )
    op.alter_column(
        "raw_messages", "msg_id", type_=sa.BigInteger(), existing_type=sa.Integer(), existing_nullable=False
    )
    op.alter_column("deals", "price_sale", existing_type=sa.Numeric(precision=10, scale=2), nullable=True)
    # Old rows saved "no price" as 0: they were scored as freebies. They cannot be told apart from real
    # freebies here, so they are left as they are.


def downgrade() -> None:
    op.execute("UPDATE deals SET price_sale = 0 WHERE price_sale IS NULL")
    op.alter_column("deals", "price_sale", existing_type=sa.Numeric(precision=10, scale=2), nullable=False)
    op.alter_column(
        "raw_messages", "msg_id", type_=sa.Integer(), existing_type=sa.BigInteger(), existing_nullable=False
    )
    op.alter_column(
        "raw_messages", "chat_id", type_=sa.Integer(), existing_type=sa.BigInteger(), existing_nullable=False
    )
