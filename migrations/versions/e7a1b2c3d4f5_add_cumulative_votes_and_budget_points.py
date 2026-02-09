"""add cumulative votes and budget points

Revision ID: e7a1b2c3d4f5
Revises: d1f2c3b4a5e6
Create Date: 2026-02-09 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e7a1b2c3d4f5"
down_revision = "d1f2c3b4a5e6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("motions", sa.Column("budget_points", sa.Integer(), nullable=True))
    op.create_table(
        "cumulative_votes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("voter_id", sa.Integer(), sa.ForeignKey("voters.id"), nullable=False),
        sa.Column("motion_id", sa.Integer(), sa.ForeignKey("motions.id"), nullable=False),
        sa.Column("option_id", sa.Integer(), sa.ForeignKey("options.id"), nullable=False),
        sa.Column("points", sa.Float(), nullable=False),
    )


def downgrade():
    op.drop_table("cumulative_votes")
    op.drop_column("motions", "budget_points")
