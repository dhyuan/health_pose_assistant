"""empty message

Revision ID: 838c4238bf2d
Revises: 01c518217659, 20260330_add_device_status_table
Create Date: 2026-03-31 21:39:05.185773

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '838c4238bf2d'
down_revision: Union[str, Sequence[str], None] = ('01c518217659', '20260330_add_device_status_table')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
