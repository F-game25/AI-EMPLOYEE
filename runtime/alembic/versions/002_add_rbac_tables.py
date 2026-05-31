"""Add RBAC tables for user roles and permissions.

Revision ID: 002
Revises: 001_initial_schema
Create Date: 2026-04-28 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '002'
down_revision = '001_initial_schema'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'user_roles',
        sa.Column('user_id', sa.UUID, sa.ForeignKey('users.user_id', ondelete='CASCADE'), primary_key=True),
        sa.Column('tenant_id', sa.UUID, sa.ForeignKey('tenants.tenant_id', ondelete='CASCADE'), primary_key=True),
        sa.Column('role', sa.String(20), default='viewer', nullable=False),
        sa.Column('assigned_at', sa.DateTime, server_default=sa.func.now()),
        sa.UniqueConstraint('user_id', 'tenant_id', name='uq_user_tenant_role'),
    )
    op.create_index('idx_user_roles_tenant', 'user_roles', ['tenant_id'])
    op.create_index('idx_user_roles_user', 'user_roles', ['user_id'])


def downgrade() -> None:
    op.drop_index('idx_user_roles_user', table_name='user_roles')
    op.drop_index('idx_user_roles_tenant', table_name='user_roles')
    op.drop_table('user_roles')
