"""customer appeals and WARN user-study responses

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-07
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('alerts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('appealed_at', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('appeal_note', sa.Text(), nullable=True))
        batch_op.create_index(batch_op.f('ix_alerts_appealed_at'), ['appealed_at'], unique=False)

    op.create_table('study_responses',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.Float(), nullable=False),
    sa.Column('participant', sa.String(length=32), nullable=False),
    sa.Column('arm', sa.String(length=1), nullable=False),
    sa.Column('scenario', sa.String(length=32), nullable=False),
    sa.Column('is_scam', sa.Integer(), nullable=False),
    sa.Column('action', sa.String(length=16), nullable=False),
    sa.Column('seconds', sa.Float(), nullable=False),
    sa.Column('trust', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('study_responses', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_study_responses_arm'), ['arm'], unique=False)
        batch_op.create_index(batch_op.f('ix_study_responses_participant'), ['participant'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('study_responses', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_study_responses_participant'))
        batch_op.drop_index(batch_op.f('ix_study_responses_arm'))
    op.drop_table('study_responses')
    with op.batch_alter_table('alerts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_alerts_appealed_at'))
        batch_op.drop_column('appeal_note')
        batch_op.drop_column('appealed_at')
