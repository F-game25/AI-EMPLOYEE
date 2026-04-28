-- Multi-tenant PostgreSQL schema for AI Employee system
-- All tables include tenant_id for complete data isolation
-- Indexes created on frequently-queried columns

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For text search optimization

-- ────────────────────────────────────────────────────────────────────────────
-- Tenants & Users
-- ────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS tenants (
  tenant_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_name VARCHAR(255) NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
  status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'suspended', 'deleted')),
  metadata JSONB DEFAULT '{}',

  -- Rate limiting & quotas
  max_api_calls_per_hour INTEGER DEFAULT 10000,
  max_agents_active INTEGER DEFAULT 56,
  max_storage_gb INTEGER DEFAULT 100,

  INDEX idx_tenants_org_name (org_name),
  INDEX idx_tenants_status (status)
);

CREATE TABLE IF NOT EXISTS users (
  user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  username VARCHAR(50) NOT NULL,
  email VARCHAR(255),
  password_hash VARCHAR(255) NOT NULL,
  role VARCHAR(20) DEFAULT 'member' CHECK (role IN ('admin', 'owner', 'manager', 'member', 'viewer')),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
  last_login TIMESTAMP WITH TIME ZONE,
  is_active BOOLEAN DEFAULT TRUE,

  UNIQUE (tenant_id, username),
  UNIQUE (email),

  INDEX idx_users_tenant_id (tenant_id),
  INDEX idx_users_email (email),
  INDEX idx_users_role (tenant_id, role)
);

-- ────────────────────────────────────────────────────────────────────────────
-- CRM Pipeline (Deals & Leads)
-- ────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS deals (
  deal_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  title VARCHAR(255) NOT NULL,
  company VARCHAR(255),
  value DECIMAL(15, 2),
  stage VARCHAR(50) NOT NULL DEFAULT 'new_lead'
    CHECK (stage IN ('new_lead', 'qualified', 'proposal_sent', 'negotiation', 'closed_won', 'closed_lost')),
  probability_percent INTEGER DEFAULT 0,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
  closed_at TIMESTAMP WITH TIME ZONE,
  owner_id UUID REFERENCES users(user_id) ON DELETE SET NULL,
  notes TEXT,
  metadata JSONB DEFAULT '{}',

  INDEX idx_deals_tenant_id (tenant_id),
  INDEX idx_deals_stage (tenant_id, stage),
  INDEX idx_deals_created_at (tenant_id, created_at DESC),
  INDEX idx_deals_owner_id (tenant_id, owner_id)
);

CREATE TABLE IF NOT EXISTS leads (
  lead_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  name VARCHAR(255) NOT NULL,
  email VARCHAR(255),
  company VARCHAR(255),
  title VARCHAR(255),
  phone VARCHAR(20),
  source VARCHAR(50),
  status VARCHAR(20) DEFAULT 'new' CHECK (status IN ('new', 'contacted', 'qualified', 'lost')),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
  owner_id UUID REFERENCES users(user_id) ON DELETE SET NULL,
  notes TEXT,
  metadata JSONB DEFAULT '{}',

  INDEX idx_leads_tenant_id (tenant_id),
  INDEX idx_leads_email (tenant_id, email),
  INDEX idx_leads_status (tenant_id, status),
  INDEX idx_leads_created_at (tenant_id, created_at DESC)
);

-- ────────────────────────────────────────────────────────────────────────────
-- Tasks & Team Management
-- ────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS tasks (
  task_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  title VARCHAR(255) NOT NULL,
  description TEXT,
  status VARCHAR(20) DEFAULT 'open' CHECK (status IN ('open', 'in_progress', 'completed', 'cancelled')),
  priority VARCHAR(20) DEFAULT 'medium' CHECK (priority IN ('low', 'medium', 'high', 'urgent')),
  assignee_id UUID REFERENCES users(user_id) ON DELETE SET NULL,
  created_by_id UUID REFERENCES users(user_id) ON DELETE SET NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
  due_at TIMESTAMP WITH TIME ZONE,
  completed_at TIMESTAMP WITH TIME ZONE,
  metadata JSONB DEFAULT '{}',

  INDEX idx_tasks_tenant_id (tenant_id),
  INDEX idx_tasks_status (tenant_id, status),
  INDEX idx_tasks_assignee_id (tenant_id, assignee_id),
  INDEX idx_tasks_due_at (tenant_id, due_at)
);

CREATE TABLE IF NOT EXISTS team_members (
  member_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  name VARCHAR(255) NOT NULL,
  role VARCHAR(100),
  capacity_percent INTEGER DEFAULT 100,
  status VARCHAR(20) DEFAULT 'active',
  created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
  metadata JSONB DEFAULT '{}',

  UNIQUE (tenant_id, user_id),

  INDEX idx_team_members_tenant_id (tenant_id),
  INDEX idx_team_members_user_id (user_id)
);

-- ────────────────────────────────────────────────────────────────────────────
-- Knowledge & Content
-- ────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS knowledge_entries (
  entry_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  category VARCHAR(100),
  title VARCHAR(255) NOT NULL,
  content TEXT,
  embedding_vector VECTOR(384),  -- Requires pgvector extension
  created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
  created_by_id UUID REFERENCES users(user_id) ON DELETE SET NULL,
  metadata JSONB DEFAULT '{}',

  INDEX idx_knowledge_tenant_id (tenant_id),
  INDEX idx_knowledge_category (tenant_id, category),
  INDEX idx_knowledge_created_at (tenant_id, created_at DESC)
);

-- ────────────────────────────────────────────────────────────────────────────
-- Revenue & Billing
-- ────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS revenue_events (
  event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  type VARCHAR(50) NOT NULL CHECK (type IN ('content', 'outreach', 'data_sale', 'manual')),
  amount DECIMAL(15, 2) NOT NULL,
  currency VARCHAR(3) DEFAULT 'USD',
  source VARCHAR(255),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
  metadata JSONB DEFAULT '{}',

  INDEX idx_revenue_tenant_id (tenant_id),
  INDEX idx_revenue_type (tenant_id, type),
  INDEX idx_revenue_created_at (tenant_id, created_at DESC)
);

-- ────────────────────────────────────────────────────────────────────────────
-- Audit & Compliance
-- ────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS audit_logs (
  log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  user_id UUID REFERENCES users(user_id) ON DELETE SET NULL,
  action VARCHAR(255) NOT NULL,
  resource_type VARCHAR(100),
  resource_id VARCHAR(255),
  changes JSONB,
  ip_address INET,
  user_agent TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

  INDEX idx_audit_logs_tenant_id (tenant_id),
  INDEX idx_audit_logs_user_id (tenant_id, user_id),
  INDEX idx_audit_logs_created_at (tenant_id, created_at DESC),
  INDEX idx_audit_logs_action (tenant_id, action)
);

-- ────────────────────────────────────────────────────────────────────────────
-- Task Queue (Replacing SQLite forge_queue)
-- ────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS job_queue (
  job_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  agent_id VARCHAR(100) NOT NULL,
  status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),
  payload JSONB,
  result JSONB,
  error_message TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
  started_at TIMESTAMP WITH TIME ZONE,
  completed_at TIMESTAMP WITH TIME ZONE,

  INDEX idx_job_queue_tenant_id (tenant_id),
  INDEX idx_job_queue_status (tenant_id, status),
  INDEX idx_job_queue_agent_id (tenant_id, agent_id),
  INDEX idx_job_queue_created_at (tenant_id, created_at DESC)
);

-- ────────────────────────────────────────────────────────────────────────────
-- Billing & Subscriptions
-- ────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS subscriptions (
  subscription_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL UNIQUE REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  stripe_subscription_id VARCHAR(255),
  stripe_customer_id VARCHAR(255),
  plan VARCHAR(50) DEFAULT 'free' CHECK (plan IN ('free', 'starter', 'business', 'enterprise')),
  status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'paused', 'cancelled')),
  billing_cycle_start DATE,
  billing_cycle_end DATE,
  usage_limit_api_calls INTEGER DEFAULT 1000,
  usage_limit_storage_gb INTEGER DEFAULT 10,
  monthly_cost DECIMAL(10, 2),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

  INDEX idx_subscriptions_plan (plan),
  INDEX idx_subscriptions_status (status)
);

CREATE TABLE IF NOT EXISTS usage_metrics (
  metric_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  metric_type VARCHAR(100) NOT NULL,
  value INTEGER DEFAULT 0,
  period_start DATE NOT NULL,
  period_end DATE NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

  UNIQUE (tenant_id, metric_type, period_start, period_end),

  INDEX idx_usage_metrics_tenant_id (tenant_id),
  INDEX idx_usage_metrics_period (period_start, period_end)
);

-- ────────────────────────────────────────────────────────────────────────────
-- Create indexes for common queries
-- ────────────────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_users_tenant_username ON users(tenant_id, username);
CREATE INDEX IF NOT EXISTS idx_deals_tenant_value ON deals(tenant_id, value DESC);
CREATE INDEX IF NOT EXISTS idx_revenue_tenant_amount ON revenue_events(tenant_id, amount DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_compound ON audit_logs(tenant_id, action, created_at DESC);

-- ────────────────────────────────────────────────────────────────────────────
-- Create updated_at triggers (auto-update timestamp on row modification)
-- ────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = CURRENT_TIMESTAMP;
  RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_tenants_updated_at BEFORE UPDATE ON tenants
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_deals_updated_at BEFORE UPDATE ON deals
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_leads_updated_at BEFORE UPDATE ON leads
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_tasks_updated_at BEFORE UPDATE ON tasks
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_knowledge_entries_updated_at BEFORE UPDATE ON knowledge_entries
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_subscriptions_updated_at BEFORE UPDATE ON subscriptions
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ────────────────────────────────────────────────────────────────────────────
-- Verify multi-tenancy enforcement
-- ────────────────────────────────────────────────────────────────────────────

-- Every user must belong to a tenant
ALTER TABLE users ADD CONSTRAINT fk_users_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id) ON DELETE CASCADE;

-- Every data row must have a tenant_id (enforced at application layer, but useful for audits)
CREATE VIEW tenant_data_summary AS
SELECT
  t.tenant_id,
  t.org_name,
  COUNT(DISTINCT u.user_id) as user_count,
  COUNT(DISTINCT d.deal_id) as deal_count,
  COUNT(DISTINCT l.lead_id) as lead_count,
  COUNT(DISTINCT tk.task_id) as task_count,
  COALESCE(SUM(re.amount), 0) as total_revenue
FROM tenants t
LEFT JOIN users u ON t.tenant_id = u.tenant_id
LEFT JOIN deals d ON t.tenant_id = d.tenant_id
LEFT JOIN leads l ON t.tenant_id = l.tenant_id
LEFT JOIN tasks tk ON t.tenant_id = tk.tenant_id
LEFT JOIN revenue_events re ON t.tenant_id = re.tenant_id
GROUP BY t.tenant_id, t.org_name;
