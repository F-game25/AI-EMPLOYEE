"""
004_json_state_tables.py

Migrate JSON state files to PostgreSQL.

Creates dedicated tables for all runtime state that previously lived in
state/*.json files, enabling proper querying, tenant isolation, and
concurrent access without file-lock contention.

Tables added:
- agent_tasks         — task tracking (state/tasks.json)
- knowledge_entries2  — knowledge base (state/knowledge_store.json, supplement to 001)
- agents_status       — agent registry/heartbeat (state/agents.json)
- learning_sessions   — learning engine sessions (state/learning_engine.json)
- memory_index        — memory index entries (state/memory_index.json)
- research_budget     — per-day research page budget (state/research_budget.json)
- vector_entries      — lightweight vector store (state/vector_store.json)

Revision ID: 004
Revises: 003
Create Date: 2026-05-19
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply migration."""

    # ────────────────────────────────────────────────────────────────────
    # Agent Tasks  (state/tasks.json)
    # ────────────────────────────────────────────────────────────────────

    op.create_table(
        'agent_tasks',
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('tenant_id', sa.Text(), nullable=False),
        sa.Column('title', sa.Text()),
        sa.Column('description', sa.Text()),
        sa.Column('status', sa.Text(), server_default='pending'),
        sa.Column('priority', sa.Text(), server_default='medium'),
        sa.Column('agent_id', sa.Text()),
        sa.Column('result', postgresql.JSONB()),
        sa.Column('meta', postgresql.JSONB(), server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
    )

    op.create_index('idx_agent_tasks_tenant', 'agent_tasks', ['tenant_id'])
    op.create_index('idx_agent_tasks_status', 'agent_tasks', ['tenant_id', 'status'])
    op.create_index('idx_agent_tasks_agent', 'agent_tasks', ['tenant_id', 'agent_id'])

    # ────────────────────────────────────────────────────────────────────
    # Knowledge Store  (state/knowledge_store.json)
    # knowledge_entries was created in 001 with a UUID PK tied to the
    # users FK — this table uses a plain TEXT id to hold migrated data
    # from the JSON store without requiring a tenant UUID.
    # ────────────────────────────────────────────────────────────────────

    op.create_table(
        'knowledge_store',
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('tenant_id', sa.Text(), nullable=False),
        sa.Column('topic', sa.Text()),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('source', sa.Text()),
        sa.Column('confidence', sa.Float(), server_default='1.0'),
        sa.Column('tags', postgresql.JSONB(), server_default='[]'),
        sa.Column('embedding_id', sa.Text()),
        sa.Column('meta', postgresql.JSONB(), server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
    )

    op.create_index('idx_knowledge_store_tenant', 'knowledge_store', ['tenant_id'])
    op.create_index('idx_knowledge_store_topic', 'knowledge_store', ['tenant_id', 'topic'])

    # ────────────────────────────────────────────────────────────────────
    # Agents Status  (state/agents.json)
    # ────────────────────────────────────────────────────────────────────

    op.create_table(
        'agents_status',
        sa.Column('agent_id', sa.Text(), nullable=False),
        sa.Column('tenant_id', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), server_default='idle'),
        sa.Column('last_heartbeat', sa.DateTime(timezone=True)),
        sa.Column('meta', postgresql.JSONB(), server_default='{}'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.PrimaryKeyConstraint('agent_id', 'tenant_id'),
    )

    op.create_index('idx_agents_status_tenant', 'agents_status', ['tenant_id'])
    op.create_index('idx_agents_status_status', 'agents_status', ['tenant_id', 'status'])

    # ────────────────────────────────────────────────────────────────────
    # Learning Sessions  (state/learning_engine.json)
    # ────────────────────────────────────────────────────────────────────

    op.create_table(
        'learning_sessions',
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('tenant_id', sa.Text(), nullable=False),
        sa.Column('topic', sa.Text()),
        sa.Column('status', sa.Text(), server_default='pending'),
        sa.Column('sources_consulted', sa.Integer(), server_default='0'),
        sa.Column('result', postgresql.JSONB()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
    )

    op.create_index('idx_learning_sessions_tenant', 'learning_sessions', ['tenant_id'])
    op.create_index('idx_learning_sessions_topic', 'learning_sessions', ['tenant_id', 'topic'])

    # ────────────────────────────────────────────────────────────────────
    # Memory Index  (state/memory_index.json)
    # Embeddings stored as JSONB array; upgrade to pgvector when available.
    # ────────────────────────────────────────────────────────────────────

    op.create_table(
        'memory_index',
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('tenant_id', sa.Text(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('embedding', postgresql.JSONB(), server_default='[]'),
        sa.Column('meta', postgresql.JSONB(), server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
    )

    op.create_index('idx_memory_index_tenant', 'memory_index', ['tenant_id'])

    # ────────────────────────────────────────────────────────────────────
    # Research Budget  (state/research_budget.json)
    # ────────────────────────────────────────────────────────────────────

    op.create_table(
        'research_budget',
        sa.Column('id', sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column('tenant_id', sa.Text(), nullable=False),
        sa.Column('date', sa.Text(), nullable=False),
        sa.Column('pages_used', sa.Integer(), server_default='0'),
        sa.Column('pages_limit', sa.Integer(), server_default='200'),
        sa.UniqueConstraint('tenant_id', 'date', name='uq_research_budget_tenant_date'),
    )

    op.create_index('idx_research_budget_tenant', 'research_budget', ['tenant_id'])
    op.create_index('idx_research_budget_date', 'research_budget', ['tenant_id', 'date'])

    # ────────────────────────────────────────────────────────────────────
    # Vector Entries  (state/vector_store.json)
    # Lightweight vector store; embeddings kept as JSONB until pgvector.
    # ────────────────────────────────────────────────────────────────────

    op.create_table(
        'vector_entries',
        sa.Column('key', sa.Text(), nullable=False),
        sa.Column('tenant_id', sa.Text(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('embedding', postgresql.JSONB(), server_default='[]'),
        sa.Column('meta', postgresql.JSONB(), server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.PrimaryKeyConstraint('key', 'tenant_id'),
    )

    op.create_index('idx_vector_entries_tenant', 'vector_entries', ['tenant_id'])

    # ────────────────────────────────────────────────────────────────────
    # Auto-update triggers for updated_at columns
    # (reuse function created in 001_initial_schema)
    # ────────────────────────────────────────────────────────────────────

    tables_with_update = [
        'agent_tasks',
        'knowledge_store',
        'agents_status',
        'learning_sessions',
        'memory_index',
        'vector_entries',
    ]

    for table in tables_with_update:
        op.execute(f"""
        CREATE TRIGGER update_{table}_updated_at BEFORE UPDATE ON {table}
          FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """)


def downgrade() -> None:
    """Revert migration — drop tables in reverse creation order."""

    tables_with_update = [
        'agent_tasks',
        'knowledge_store',
        'agents_status',
        'learning_sessions',
        'memory_index',
        'vector_entries',
    ]

    for table in tables_with_update:
        op.execute(f"DROP TRIGGER IF EXISTS update_{table}_updated_at ON {table}")

    # Drop in reverse dependency order
    for table in reversed([
        'agent_tasks',
        'knowledge_store',
        'agents_status',
        'learning_sessions',
        'memory_index',
        'research_budget',
        'vector_entries',
    ]):
        op.drop_table(table)
