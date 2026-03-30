"""add device_status table

Revision ID: 20260330_add_device_status_table
Revises: 3a324cf4391b
Create Date: 2026-03-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260330_add_device_status_table"
down_revision = "3a324cf4391b"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "device_status",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "device_id",
            sa.Integer(),
            sa.ForeignKey("devices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("extra", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.CheckConstraint(
            "status in ('online', 'offline')", name="ck_device_status_status"
        ),
    )
    op.create_index("idx_device_status_device_id", "device_status", ["device_id"])
    op.create_index("idx_device_status_changed_at", "device_status", ["changed_at"])


def downgrade():
    op.drop_index("idx_device_status_changed_at", table_name="device_status")
    op.drop_index("idx_device_status_device_id", table_name="device_status")
    op.drop_table("device_status")
