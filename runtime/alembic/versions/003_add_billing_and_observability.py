"""Add billing and observability tables for Phase 4.

Revision ID: 003
Revises: 002_add_rbac_tables
Create Date: 2026-04-28 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '003'
down_revision = '002_add_rbac_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Billing events table
    op.create_table(
        'billing_events',
        sa.Column('event_id', sa.UUID, server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('tenant_id', sa.UUID, sa.ForeignKey('tenants.tenant_id', ondelete='CASCADE'), nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False),  # api_call, agent_execution, database_query, error
        sa.Column('event_data', sa.JSON, default={}),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index('idx_billing_events_tenant', 'billing_events', ['tenant_id'])
    op.create_index('idx_billing_events_type', 'billing_events', ['event_type'])
    op.create_index('idx_billing_events_created', 'billing_events', ['created_at'])

    # Audit logs for security/compliance
    op.create_table(
        'audit_logs',
        sa.Column('log_id', sa.UUID, server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('tenant_id', sa.UUID, sa.ForeignKey('tenants.tenant_id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.UUID, sa.ForeignKey('users.user_id', ondelete='SET NULL')),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('resource', sa.String(100)),
        sa.Column('resource_id', sa.String(255)),
        sa.Column('status', sa.String(20), default='success'),  # success, failure
        sa.Column('details', sa.JSON, default={}),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index('idx_audit_logs_tenant', 'audit_logs', ['tenant_id'])
    op.create_index('idx_audit_logs_user', 'audit_logs', ['user_id'])
    op.create_index('idx_audit_logs_action', 'audit_logs', ['action'])
    op.create_index('idx_audit_logs_created', 'audit_logs', ['created_at'])

    # Rate limiting / quota tracking
    op.create_table(
        'quota_usage',
        sa.Column('usage_id', sa.UUID, server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('tenant_id', sa.UUID, sa.ForeignKey('tenants.tenant_id', ondelete='CASCADE'), nullable=False),
        sa.Column('metric', sa.String(50), nullable=False),  # requests_per_minute, agents_per_hour, api_calls_per_day
        sa.Column('current_usage', sa.Integer, default=0),
        sa.Column('quota_limit', sa.Integer, nullable=False),
        sa.Column('period_start', sa.DateTime, nullable=False),
        sa.Column('period_end', sa.DateTime, nullable=False),
        sa.Column('last_reset', sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index('idx_quota_usage_tenant', 'quota_usage', ['tenant_id'])
    op.create_index('idx_quota_usage_metric', 'quota_usage', ['metric'])

    # Vector embeddings for semantic search
    op.create_table(
        'embeddings',
        sa.Column('embedding_id', sa.UUID, server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('tenant_id', sa.UUID, sa.ForeignKey('tenants.tenant_id', ondelete='CASCADE'), nullable=False),
        sa.Column('text', sa.Text, nullable=False),
        sa.Column('vector', sa.JSON, nullable=False),  # 384-dim embedding as JSON array
        sa.Column('metadata', sa.JSON, default={}),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index('idx_embeddings_tenant', 'embeddings', ['tenant_id'])
    op.create_index('idx_embeddings_created', 'embeddings', ['created_at'])


def downgrade() -> None:
    op.drop_index('idx_embeddings_created', table_name='embeddings')
    op.drop_index('idx_embeddings_tenant', table_name='embeddings')
    op.drop_table('embeddings')

    op.drop_index('idx_quota_usage_metric', table_name='quota_usage')
    op.drop_index('idx_quota_usage_tenant', table_name='quota_usage')
    op.drop_table('quota_usage')

    op.drop_index('idx_audit_logs_created', table_name='audit_logs')
    op.drop_index('idx_audit_logs_action', table_name='audit_logs')
    op.drop_index('idx_audit_logs_user', table_name='audit_logs')
    op.drop_index('idx_audit_logs_tenant', table_name='audit_logs')
    op.drop_table('audit_logs')

    op.drop_index('idx_billing_events_created', table_name='billing_events')
    op.drop_index('idx_billing_events_type', table_name='billing_events')
    op.drop_index('idx_billing_events_tenant', table_name='billing_events')
    op.drop_table('billing_events')
