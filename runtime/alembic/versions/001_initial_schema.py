"""
001_initial_schema.py

Create initial PostgreSQL schema from runtime/db/schema.sql

This migration sets up:
- Tenant and user management tables
- CRM pipeline (deals, leads)
- Task and team management
- Knowledge base and content storage
- Revenue tracking and billing
- Audit logging
- Job queue for background tasks

Revision ID: 001
Revises: (none)
Create Date: 2026-05-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# Revision identifiers
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply migration."""
    
    # Create extensions
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')
    
    # ────────────────────────────────────────────────────────────────────
    # Tenants & Users
    # ────────────────────────────────────────────────────────────────────
    
    op.create_table(
        'tenants',
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column('org_name', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.Column('status', sa.String(20), default='active', server_default='active'),
        sa.Column('metadata', postgresql.JSONB, default='{}', server_default='{}'),
        sa.Column('max_api_calls_per_hour', sa.Integer, default=10000),
        sa.Column('max_agents_active', sa.Integer, default=56),
        sa.Column('max_storage_gb', sa.Integer, default=100),
        sa.CheckConstraint("status IN ('active', 'suspended', 'deleted')"),
    )
    
    op.create_index('idx_tenants_org_name', 'tenants', ['org_name'])
    op.create_index('idx_tenants_status', 'tenants', ['status'])
    
    op.create_table(
        'users',
        sa.Column('user_id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('username', sa.String(50), nullable=False),
        sa.Column('email', sa.String(255)),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('role', sa.String(20), default='member'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.Column('last_login', sa.DateTime(timezone=True)),
        sa.Column('is_active', sa.Boolean, default=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.tenant_id'], ondelete='CASCADE'),
        sa.UniqueConstraint('tenant_id', 'username'),
        sa.UniqueConstraint('email'),
        sa.CheckConstraint("role IN ('admin', 'owner', 'manager', 'member', 'viewer')"),
    )
    
    op.create_index('idx_users_tenant_id', 'users', ['tenant_id'])
    op.create_index('idx_users_email', 'users', ['email'])
    op.create_index('idx_users_role', 'users', ['tenant_id', 'role'])
    op.create_index('idx_users_tenant_username', 'users', ['tenant_id', 'username'])
    
    # ────────────────────────────────────────────────────────────────────
    # CRM Pipeline (Deals & Leads)
    # ────────────────────────────────────────────────────────────────────
    
    op.create_table(
        'deals',
        sa.Column('deal_id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('company', sa.String(255)),
        sa.Column('value', sa.Numeric(15, 2)),
        sa.Column('stage', sa.String(50), default='new_lead'),
        sa.Column('probability_percent', sa.Integer, default=0),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.Column('closed_at', sa.DateTime(timezone=True)),
        sa.Column('owner_id', postgresql.UUID(as_uuid=True)),
        sa.Column('notes', sa.Text()),
        sa.Column('metadata', postgresql.JSONB, default='{}', server_default='{}'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.tenant_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['owner_id'], ['users.user_id'], ondelete='SET NULL'),
        sa.CheckConstraint("stage IN ('new_lead', 'qualified', 'proposal_sent', 'negotiation', 'closed_won', 'closed_lost')"),
    )
    
    op.create_index('idx_deals_tenant_id', 'deals', ['tenant_id'])
    op.create_index('idx_deals_stage', 'deals', ['tenant_id', 'stage'])
    op.create_index('idx_deals_created_at', 'deals', ['tenant_id', 'created_at'], postgresql_using='DESC')
    op.create_index('idx_deals_owner_id', 'deals', ['tenant_id', 'owner_id'])
    op.create_index('idx_deals_tenant_value', 'deals', ['tenant_id', 'value'], postgresql_using='DESC')
    
    op.create_table(
        'leads',
        sa.Column('lead_id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('email', sa.String(255)),
        sa.Column('company', sa.String(255)),
        sa.Column('title', sa.String(255)),
        sa.Column('phone', sa.String(20)),
        sa.Column('source', sa.String(50)),
        sa.Column('status', sa.String(20), default='new'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.Column('owner_id', postgresql.UUID(as_uuid=True)),
        sa.Column('notes', sa.Text()),
        sa.Column('metadata', postgresql.JSONB, default='{}', server_default='{}'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.tenant_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['owner_id'], ['users.user_id'], ondelete='SET NULL'),
        sa.CheckConstraint("status IN ('new', 'contacted', 'qualified', 'lost')"),
    )
    
    op.create_index('idx_leads_tenant_id', 'leads', ['tenant_id'])
    op.create_index('idx_leads_email', 'leads', ['tenant_id', 'email'])
    op.create_index('idx_leads_status', 'leads', ['tenant_id', 'status'])
    op.create_index('idx_leads_created_at', 'leads', ['tenant_id', 'created_at'], postgresql_using='DESC')
    
    # ────────────────────────────────────────────────────────────────────
    # Tasks & Team Management
    # ────────────────────────────────────────────────────────────────────
    
    op.create_table(
        'tasks',
        sa.Column('task_id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('status', sa.String(20), default='open'),
        sa.Column('priority', sa.String(20), default='medium'),
        sa.Column('assignee_id', postgresql.UUID(as_uuid=True)),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.Column('due_at', sa.DateTime(timezone=True)),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.Column('metadata', postgresql.JSONB, default='{}', server_default='{}'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.tenant_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['assignee_id'], ['users.user_id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.user_id'], ondelete='SET NULL'),
        sa.CheckConstraint("status IN ('open', 'in_progress', 'completed', 'cancelled')"),
        sa.CheckConstraint("priority IN ('low', 'medium', 'high', 'urgent')"),
    )
    
    op.create_index('idx_tasks_tenant_id', 'tasks', ['tenant_id'])
    op.create_index('idx_tasks_status', 'tasks', ['tenant_id', 'status'])
    op.create_index('idx_tasks_assignee_id', 'tasks', ['tenant_id', 'assignee_id'])
    op.create_index('idx_tasks_due_at', 'tasks', ['tenant_id', 'due_at'])
    
    op.create_table(
        'team_members',
        sa.Column('member_id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('role', sa.String(100)),
        sa.Column('capacity_percent', sa.Integer, default=100),
        sa.Column('status', sa.String(20), default='active'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.Column('metadata', postgresql.JSONB, default='{}', server_default='{}'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.tenant_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE'),
        sa.UniqueConstraint('tenant_id', 'user_id'),
    )
    
    op.create_index('idx_team_members_tenant_id', 'team_members', ['tenant_id'])
    op.create_index('idx_team_members_user_id', 'team_members', ['user_id'])
    
    # ────────────────────────────────────────────────────────────────────
    # Knowledge & Content
    # ────────────────────────────────────────────────────────────────────
    
    op.create_table(
        'knowledge_entries',
        sa.Column('entry_id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('category', sa.String(100)),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('content', sa.Text()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True)),
        sa.Column('metadata', postgresql.JSONB, default='{}', server_default='{}'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.tenant_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.user_id'], ondelete='SET NULL'),
    )
    
    op.create_index('idx_knowledge_tenant_id', 'knowledge_entries', ['tenant_id'])
    op.create_index('idx_knowledge_category', 'knowledge_entries', ['tenant_id', 'category'])
    op.create_index('idx_knowledge_created_at', 'knowledge_entries', ['tenant_id', 'created_at'], postgresql_using='DESC')
    
    # ────────────────────────────────────────────────────────────────────
    # Revenue & Billing
    # ────────────────────────────────────────────────────────────────────
    
    op.create_table(
        'revenue_events',
        sa.Column('event_id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('type', sa.String(50), nullable=False),
        sa.Column('amount', sa.Numeric(15, 2), nullable=False),
        sa.Column('currency', sa.String(3), default='USD'),
        sa.Column('source', sa.String(255)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.Column('metadata', postgresql.JSONB, default='{}', server_default='{}'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.tenant_id'], ondelete='CASCADE'),
        sa.CheckConstraint("type IN ('content', 'outreach', 'data_sale', 'manual')"),
    )
    
    op.create_index('idx_revenue_tenant_id', 'revenue_events', ['tenant_id'])
    op.create_index('idx_revenue_type', 'revenue_events', ['tenant_id', 'type'])
    op.create_index('idx_revenue_created_at', 'revenue_events', ['tenant_id', 'created_at'], postgresql_using='DESC')
    op.create_index('idx_revenue_tenant_amount', 'revenue_events', ['tenant_id', 'amount'], postgresql_using='DESC')
    
    # ────────────────────────────────────────────────────────────────────
    # Audit & Compliance
    # ────────────────────────────────────────────────────────────────────
    
    op.create_table(
        'audit_logs',
        sa.Column('log_id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True)),
        sa.Column('action', sa.String(255), nullable=False),
        sa.Column('resource_type', sa.String(100)),
        sa.Column('resource_id', sa.String(255)),
        sa.Column('changes', postgresql.JSONB),
        sa.Column('ip_address', postgresql.INET),
        sa.Column('user_agent', sa.Text()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.tenant_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='SET NULL'),
    )
    
    op.create_index('idx_audit_logs_tenant_id', 'audit_logs', ['tenant_id'])
    op.create_index('idx_audit_logs_user_id', 'audit_logs', ['tenant_id', 'user_id'])
    op.create_index('idx_audit_logs_created_at', 'audit_logs', ['tenant_id', 'created_at'], postgresql_using='DESC')
    op.create_index('idx_audit_logs_action', 'audit_logs', ['tenant_id', 'action'])
    op.create_index('idx_audit_logs_compound', 'audit_logs', ['tenant_id', 'action', 'created_at'], postgresql_using='DESC')
    
    # ────────────────────────────────────────────────────────────────────
    # Task Queue (Job Queue)
    # ────────────────────────────────────────────────────────────────────
    
    op.create_table(
        'job_queue',
        sa.Column('job_id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('agent_id', sa.String(100), nullable=False),
        sa.Column('status', sa.String(20), default='pending'),
        sa.Column('payload', postgresql.JSONB),
        sa.Column('result', postgresql.JSONB),
        sa.Column('error_message', sa.Text()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.Column('started_at', sa.DateTime(timezone=True)),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.tenant_id'], ondelete='CASCADE'),
        sa.CheckConstraint("status IN ('pending', 'running', 'completed', 'failed', 'cancelled')"),
    )
    
    op.create_index('idx_job_queue_tenant_id', 'job_queue', ['tenant_id'])
    op.create_index('idx_job_queue_status', 'job_queue', ['tenant_id', 'status'])
    op.create_index('idx_job_queue_agent_id', 'job_queue', ['tenant_id', 'agent_id'])
    op.create_index('idx_job_queue_created_at', 'job_queue', ['tenant_id', 'created_at'], postgresql_using='DESC')
    
    # ────────────────────────────────────────────────────────────────────
    # Billing & Subscriptions
    # ────────────────────────────────────────────────────────────────────
    
    op.create_table(
        'subscriptions',
        sa.Column('subscription_id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column('stripe_subscription_id', sa.String(255)),
        sa.Column('stripe_customer_id', sa.String(255)),
        sa.Column('plan', sa.String(50), default='free'),
        sa.Column('status', sa.String(20), default='active'),
        sa.Column('billing_cycle_start', sa.Date()),
        sa.Column('billing_cycle_end', sa.Date()),
        sa.Column('usage_limit_api_calls', sa.Integer, default=1000),
        sa.Column('usage_limit_storage_gb', sa.Integer, default=10),
        sa.Column('monthly_cost', sa.Numeric(10, 2)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.tenant_id'], ondelete='CASCADE'),
        sa.CheckConstraint("plan IN ('free', 'starter', 'business', 'enterprise')"),
        sa.CheckConstraint("status IN ('active', 'paused', 'cancelled')"),
    )
    
    op.create_index('idx_subscriptions_plan', 'subscriptions', ['plan'])
    op.create_index('idx_subscriptions_status', 'subscriptions', ['status'])
    
    op.create_table(
        'usage_metrics',
        sa.Column('metric_id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('metric_type', sa.String(100), nullable=False),
        sa.Column('value', sa.Integer, default=0),
        sa.Column('period_start', sa.Date(), nullable=False),
        sa.Column('period_end', sa.Date(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.tenant_id'], ondelete='CASCADE'),
        sa.UniqueConstraint('tenant_id', 'metric_type', 'period_start', 'period_end'),
    )
    
    op.create_index('idx_usage_metrics_tenant_id', 'usage_metrics', ['tenant_id'])
    op.create_index('idx_usage_metrics_period', 'usage_metrics', ['period_start', 'period_end'])
    
    # ────────────────────────────────────────────────────────────────────
    # Triggers for auto-updating updated_at timestamps
    # ────────────────────────────────────────────────────────────────────
    
    op.execute("""
    CREATE OR REPLACE FUNCTION update_updated_at_column()
    RETURNS TRIGGER AS $$
    BEGIN
      NEW.updated_at = CURRENT_TIMESTAMP;
      RETURN NEW;
    END;
    $$ language 'plpgsql';
    """)
    
    tables_with_update = [
        'tenants', 'users', 'deals', 'leads', 'tasks',
        'knowledge_entries', 'subscriptions'
    ]
    
    for table in tables_with_update:
        op.execute(f"""
        CREATE TRIGGER update_{table}_updated_at BEFORE UPDATE ON {table}
          FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """)


def downgrade() -> None:
    """Revert migration."""
    
    # Drop triggers and function
    tables_with_update = [
        'tenants', 'users', 'deals', 'leads', 'tasks',
        'knowledge_entries', 'subscriptions'
    ]
    
    for table in tables_with_update:
        op.execute(f"DROP TRIGGER IF EXISTS update_{table}_updated_at ON {table}")
    
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column()")
    
    # Drop tables in reverse order of foreign key dependencies
    tables = [
        'usage_metrics', 'subscriptions', 'job_queue', 'audit_logs',
        'revenue_events', 'knowledge_entries', 'team_members', 'tasks',
        'leads', 'deals', 'users', 'tenants'
    ]
    
    for table in tables:
        op.drop_table(table, if_exists=True)
    
    # Drop extensions
    op.execute('DROP EXTENSION IF EXISTS "pg_trgm"')
    op.execute('DROP EXTENSION IF EXISTS "uuid-ossp"')
