"""add score votes table

Revision ID: c3d2a1f4b6e9
Revises: b9a37b2c71e4
Create Date: 2026-02-06 10:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c3d2a1f4b6e9"
down_revision = "b9a37b2c71e4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "score_votes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("voter_id", sa.Integer(), nullable=False),
        sa.Column("motion_id", sa.Integer(), nullable=False),
        sa.Column("option_id", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["motion_id"], ["motions.id"]),
        sa.ForeignKeyConstraint(["option_id"], ["options.id"]),
        sa.ForeignKeyConstraint(["voter_id"], ["voters.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("score_votes")
