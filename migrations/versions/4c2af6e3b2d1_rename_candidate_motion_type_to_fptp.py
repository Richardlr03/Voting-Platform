"""rename candidate motion type to fptp

Revision ID: 4c2af6e3b2d1
Revises: 8ee6508f8c71
Create Date: 2026-02-04 22:40:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "4c2af6e3b2d1"
down_revision = "8ee6508f8c71"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        sa.text("UPDATE motions SET type = 'FPTP' WHERE type = 'CANDIDATE'")
    )


def downgrade():
    op.execute(
        sa.text("UPDATE motions SET type = 'CANDIDATE' WHERE type = 'FPTP'")
    )
