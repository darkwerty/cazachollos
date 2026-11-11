"""deals: image_url and post_url (picture of the post and link to the original message)

Revision ID: d5f7b9c1e3a6
Revises: c3e5a7b9d1f4
Create Date: 2026-11-11 01:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d5f7b9c1e3a6"
down_revision: Union[str, None] = "c3e5a7b9d1f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("deals", sa.Column("image_url", sa.Text(), nullable=True))
    op.add_column("deals", sa.Column("post_url", sa.Text(), nullable=True))
    op.create_index("ix_deals_created_at", "deals", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_deals_created_at", table_name="deals")
    op.drop_column("deals", "post_url")
    op.drop_column("deals", "image_url")
