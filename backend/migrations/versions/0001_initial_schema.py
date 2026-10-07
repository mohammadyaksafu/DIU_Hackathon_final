"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-07 08:50:46.672747
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('alerts',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('tx_id', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.Float(), nullable=False),
    sa.Column('tx_ts', sa.Float(), nullable=False),
    sa.Column('tx_type', sa.String(length=32), nullable=False),
    sa.Column('sender', sa.String(length=32), nullable=False),
    sa.Column('receiver', sa.String(length=32), nullable=False),
    sa.Column('amount', sa.Float(), nullable=False),
    sa.Column('decision', sa.String(length=16), nullable=False),
    sa.Column('risk_score', sa.Float(), nullable=False),
    sa.Column('reason_codes', sa.JSON(), nullable=False),
    sa.Column('signals', sa.JSON(), nullable=False),
    sa.Column('features', sa.JSON(), nullable=False),
    sa.Column('model_version', sa.String(length=64), nullable=False),
    sa.Column('policy_version', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('label', sa.String(length=16), nullable=True),
    sa.Column('customer_action', sa.String(length=16), nullable=True),
    sa.Column('source', sa.String(length=16), nullable=False),
    sa.Column('scenario_tag', sa.String(length=32), nullable=True),
    sa.Column('opened_at', sa.Float(), nullable=True),
    sa.Column('decided_at', sa.Float(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('alerts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_alerts_decision'), ['decision'], unique=False)
        batch_op.create_index(batch_op.f('ix_alerts_receiver'), ['receiver'], unique=False)
        batch_op.create_index(batch_op.f('ix_alerts_risk_score'), ['risk_score'], unique=False)
        batch_op.create_index(batch_op.f('ix_alerts_sender'), ['sender'], unique=False)
        batch_op.create_index(batch_op.f('ix_alerts_status'), ['status'], unique=False)
        batch_op.create_index('ix_alerts_status_risk', ['status', 'risk_score'], unique=False)
        batch_op.create_index(batch_op.f('ix_alerts_tx_id'), ['tx_id'], unique=False)

    op.create_table('audit_log',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('ts', sa.Float(), nullable=False),
    sa.Column('actor', sa.String(length=64), nullable=False),
    sa.Column('event', sa.String(length=48), nullable=False),
    sa.Column('tx_id', sa.String(length=64), nullable=True),
    sa.Column('alert_id', sa.Integer(), nullable=True),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('audit_log', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_audit_log_event'), ['event'], unique=False)
        batch_op.create_index(batch_op.f('ix_audit_log_ts'), ['ts'], unique=False)
        batch_op.create_index(batch_op.f('ix_audit_log_tx_id'), ['tx_id'], unique=False)

    op.create_table('feedback',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('alert_id', sa.Integer(), nullable=False),
    sa.Column('analyst', sa.String(length=64), nullable=False),
    sa.Column('label', sa.String(length=16), nullable=False),
    sa.Column('notes', sa.Text(), nullable=False),
    sa.Column('created_at', sa.Float(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('feedback', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_feedback_alert_id'), ['alert_id'], unique=False)

    op.create_table('idempotency',
    sa.Column('key', sa.String(length=128), nullable=False),
    sa.Column('created_at', sa.Float(), nullable=False),
    sa.Column('response', sa.JSON(), nullable=False),
    sa.PrimaryKeyConstraint('key')
    )
    op.create_table('narratives',
    sa.Column('evidence_hash', sa.String(length=64), nullable=False),
    sa.Column('alert_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.Float(), nullable=False),
    sa.Column('provider', sa.String(length=32), nullable=False),
    sa.Column('content', sa.JSON(), nullable=False),
    sa.PrimaryKeyConstraint('evidence_hash')
    )
    with op.batch_alter_table('narratives', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_narratives_alert_id'), ['alert_id'], unique=False)

    op.create_table('scored_transactions',
    sa.Column('tx_id', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.Float(), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('decision', sa.String(length=16), nullable=False),
    sa.Column('risk_score', sa.Float(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('alert_id', sa.Integer(), nullable=True),
    sa.Column('latency_ms', sa.Float(), nullable=False),
    sa.PrimaryKeyConstraint('tx_id')
    )
    with op.batch_alter_table('scored_transactions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_scored_transactions_decision'), ['decision'], unique=False)
        batch_op.create_index(batch_op.f('ix_scored_transactions_status'), ['status'], unique=False)



def downgrade() -> None:
    with op.batch_alter_table('scored_transactions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_scored_transactions_status'))
        batch_op.drop_index(batch_op.f('ix_scored_transactions_decision'))

    op.drop_table('scored_transactions')
    with op.batch_alter_table('narratives', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_narratives_alert_id'))

    op.drop_table('narratives')
    op.drop_table('idempotency')
    with op.batch_alter_table('feedback', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_feedback_alert_id'))

    op.drop_table('feedback')
    with op.batch_alter_table('audit_log', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_audit_log_tx_id'))
        batch_op.drop_index(batch_op.f('ix_audit_log_ts'))
        batch_op.drop_index(batch_op.f('ix_audit_log_event'))

    op.drop_table('audit_log')
    with op.batch_alter_table('alerts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_alerts_tx_id'))
        batch_op.drop_index('ix_alerts_status_risk')
        batch_op.drop_index(batch_op.f('ix_alerts_status'))
        batch_op.drop_index(batch_op.f('ix_alerts_sender'))
        batch_op.drop_index(batch_op.f('ix_alerts_risk_score'))
        batch_op.drop_index(batch_op.f('ix_alerts_receiver'))
        batch_op.drop_index(batch_op.f('ix_alerts_decision'))

    op.drop_table('alerts')
