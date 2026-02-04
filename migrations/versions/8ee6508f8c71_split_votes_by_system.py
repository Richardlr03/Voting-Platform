"""split votes by system

Revision ID: 8ee6508f8c71
Revises: 
Create Date: 2026-02-03 23:38:17.326473

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '8ee6508f8c71'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    op.create_table('candidate_votes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('voter_id', sa.Integer(), nullable=False),
    sa.Column('motion_id', sa.Integer(), nullable=False),
    sa.Column('option_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['motion_id'], ['motions.id'], ),
    sa.ForeignKeyConstraint(['option_id'], ['options.id'], ),
    sa.ForeignKeyConstraint(['voter_id'], ['voters.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('preference_votes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('voter_id', sa.Integer(), nullable=False),
    sa.Column('motion_id', sa.Integer(), nullable=False),
    sa.Column('option_id', sa.Integer(), nullable=False),
    sa.Column('preference_rank', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['motion_id'], ['motions.id'], ),
    sa.ForeignKeyConstraint(['option_id'], ['options.id'], ),
    sa.ForeignKeyConstraint(['voter_id'], ['voters.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('yes_no_votes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('voter_id', sa.Integer(), nullable=False),
    sa.Column('motion_id', sa.Integer(), nullable=False),
    sa.Column('option_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['motion_id'], ['motions.id'], ),
    sa.ForeignKeyConstraint(['option_id'], ['options.id'], ),
    sa.ForeignKeyConstraint(['voter_id'], ['voters.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    if "votes" in existing_tables:
        op.execute(
            sa.text(
                """
                INSERT INTO yes_no_votes (voter_id, motion_id, option_id)
                SELECT v.voter_id, v.motion_id, v.option_id
                FROM votes v
                JOIN motions m ON m.id = v.motion_id
                WHERE m.type = 'YES_NO'
                """
            )
        )
        op.execute(
            sa.text(
                """
                INSERT INTO candidate_votes (voter_id, motion_id, option_id)
                SELECT v.voter_id, v.motion_id, v.option_id
                FROM votes v
                JOIN motions m ON m.id = v.motion_id
                WHERE m.type = 'CANDIDATE'
                """
            )
        )
        op.execute(
            sa.text(
                """
                INSERT INTO preference_votes (voter_id, motion_id, option_id, preference_rank)
                SELECT v.voter_id, v.motion_id, v.option_id, v.preference_rank
                FROM votes v
                JOIN motions m ON m.id = v.motion_id
                WHERE m.type = 'PREFERENCE' AND v.preference_rank IS NOT NULL
                """
            )
        )
        op.drop_table('votes')


def downgrade():
    op.create_table(
    'votes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('voter_id', sa.Integer(), nullable=False),
    sa.Column('motion_id', sa.Integer(), nullable=False),
    sa.Column('option_id', sa.Integer(), nullable=False),
    sa.Column('preference_rank', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['motion_id'], ['motions.id']),
    sa.ForeignKeyConstraint(['option_id'], ['options.id']),
    sa.ForeignKeyConstraint(['voter_id'], ['voters.id']),
    sa.PrimaryKeyConstraint('id')
    )
    op.execute(
        sa.text(
            """
            INSERT INTO votes (voter_id, motion_id, option_id, preference_rank)
            SELECT voter_id, motion_id, option_id, NULL FROM yes_no_votes
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO votes (voter_id, motion_id, option_id, preference_rank)
            SELECT voter_id, motion_id, option_id, NULL FROM candidate_votes
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO votes (voter_id, motion_id, option_id, preference_rank)
            SELECT voter_id, motion_id, option_id, preference_rank FROM preference_votes
            """
        )
    )
    op.drop_table('yes_no_votes')
    op.drop_table('preference_votes')
    op.drop_table('candidate_votes')
