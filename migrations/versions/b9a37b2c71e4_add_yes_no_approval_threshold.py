"""add yes/no approval threshold

Revision ID: b9a37b2c71e4
Revises: 4c2af6e3b2d1
Create Date: 2026-02-04 23:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b9a37b2c71e4"
down_revision = "4c2af6e3b2d1"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "motions",
        sa.Column("approved_threshold_pct", sa.Float(), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE motions
            SET approved_threshold_pct = 50
            WHERE type = 'YES_NO' AND approved_threshold_pct IS NULL
            """
        )
    )


def downgrade():
    op.drop_column("motions", "approved_threshold_pct")
