"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-09-13
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Tables are created by SQLAlchemy metadata on startup for v1.
    # This revision exists so `alembic upgrade head` is a documented no-op
    # after create_all, and future deltas can be added here.
    op.execute("SELECT 1")


def downgrade() -> None:
    pass
