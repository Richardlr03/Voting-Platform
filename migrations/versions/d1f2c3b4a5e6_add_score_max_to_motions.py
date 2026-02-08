"""add score max to motions

Revision ID: d1f2c3b4a5e6
Revises: c3d2a1f4b6e9
Create Date: 2026-02-06 11:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d1f2c3b4a5e6"
down_revision = "c3d2a1f4b6e9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("motions", sa.Column("score_max", sa.Integer(), nullable=True))


def downgrade():
    op.drop_column("motions", "score_max")
