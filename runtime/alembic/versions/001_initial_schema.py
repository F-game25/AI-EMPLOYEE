"""Initial multi-tenant schema.

Revision ID: 001
Revises:
Create Date: 2026-04-28

"""
from alembic import op
import sqlalchemy as sa

revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')

    op.create_table(
        'tenants',
        sa.Column('tenant_id', sa.UUID, primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('org_name', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.Column('status', sa.String(20), default='active'),
        sa.Column('metadata', sa.JSON, default={}),
        sa.Column('max_api_calls_per_hour', sa.Integer, default=10000),
        sa.Column('max_agents_active', sa.Integer, default=56),
        sa.Column('max_storage_gb', sa.Integer, default=100)
    )
    op.create_index('idx_tenants_org_name', 'tenants', ['org_name'])
    op.create_index('idx_tenants_status', 'tenants', ['status'])

    op.create_table(
        'users',
        sa.Column('user_id', sa.UUID, primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', sa.UUID, sa.ForeignKey('tenants.tenant_id', ondelete='CASCADE'), nullable=False),
        sa.Column('username', sa.String(50), nullable=False),
        sa.Column('email', sa.String(255)),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('role', sa.String(20), default='member'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.Column('last_login', sa.DateTime(timezone=True)),
        sa.Column('is_active', sa.Boolean, default=True)
    )
    op.create_index('idx_users_tenant_id', 'users', ['tenant_id'])
    op.create_index('idx_users_email', 'users', ['email'])
    op.create_index('idx_users_tenant_username', 'users', ['tenant_id', 'username'], unique=True)

    op.create_table(
        'deals',
        sa.Column('deal_id', sa.UUID, primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', sa.UUID, sa.ForeignKey('tenants.tenant_id', ondelete='CASCADE'), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('company', sa.String(255)),
        sa.Column('value', sa.Numeric(15, 2)),
        sa.Column('stage', sa.String(50), default='new_lead'),
        sa.Column('probability_percent', sa.Integer, default=0),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.Column('closed_at', sa.DateTime(timezone=True)),
        sa.Column('owner_id', sa.UUID, sa.ForeignKey('users.user_id', ondelete='SET NULL')),
        sa.Column('notes', sa.Text),
        sa.Column('metadata', sa.JSON, default={})
    )
    op.create_index('idx_deals_tenant_id', 'deals', ['tenant_id'])
    op.create_index('idx_deals_stage', 'deals', ['tenant_id', 'stage'])

    op.create_table(
        'tasks',
        sa.Column('task_id', sa.UUID, primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', sa.UUID, sa.ForeignKey('tenants.tenant_id', ondelete='CASCADE'), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('status', sa.String(20), default='open'),
        sa.Column('priority', sa.String(20), default='medium'),
        sa.Column('assignee_id', sa.UUID, sa.ForeignKey('users.user_id', ondelete='SET NULL')),
        sa.Column('created_by_id', sa.UUID, sa.ForeignKey('users.user_id', ondelete='SET NULL')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.Column('due_at', sa.DateTime(timezone=True)),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.Column('metadata', sa.JSON, default={})
    )
    op.create_index('idx_tasks_tenant_id', 'tasks', ['tenant_id'])
    op.create_index('idx_tasks_status', 'tasks', ['tenant_id', 'status'])

    op.create_table(
        'audit_logs',
        sa.Column('log_id', sa.UUID, primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', sa.UUID, sa.ForeignKey('tenants.tenant_id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.UUID, sa.ForeignKey('users.user_id', ondelete='SET NULL')),
        sa.Column('action', sa.String(255), nullable=False),
        sa.Column('resource_type', sa.String(100)),
        sa.Column('resource_id', sa.String(255)),
        sa.Column('changes', sa.JSON),
        sa.Column('ip_address', sa.String(45)),
        sa.Column('user_agent', sa.Text),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp())
    )
    op.create_index('idx_audit_logs_tenant_id', 'audit_logs', ['tenant_id'])

    op.create_table(
        'revenue_events',
        sa.Column('event_id', sa.UUID, primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', sa.UUID, sa.ForeignKey('tenants.tenant_id', ondelete='CASCADE'), nullable=False),
        sa.Column('type', sa.String(50), nullable=False),
        sa.Column('amount', sa.Numeric(15, 2), nullable=False),
        sa.Column('currency', sa.String(3), default='USD'),
        sa.Column('source', sa.String(255)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.Column('metadata', sa.JSON, default={})
    )
    op.create_index('idx_revenue_tenant_id', 'revenue_events', ['tenant_id'])


def downgrade():
    op.drop_table('revenue_events')
    op.drop_table('audit_logs')
    op.drop_table('tasks')
    op.drop_table('deals')
    op.drop_table('users')
    op.drop_table('tenants')
    op.execute('DROP EXTENSION IF EXISTS "pg_trgm"')
    op.execute('DROP EXTENSION IF EXISTS "uuid-ossp"')
