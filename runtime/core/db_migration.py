"""JSON to PostgreSQL migration utilities."""
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime
import os

from core.database import get_database
from core.file_lock import read_json_safe

logger = logging.getLogger(__name__)


class JSONToPGMigrator:
    """Migrate JSON state files to PostgreSQL tables."""

    def __init__(self, ai_home: str):
        self.ai_home = ai_home
        self.state_dir = Path(ai_home) / 'state'
        self.db = get_database()

    def migrate_deals(self, tenant_id: str) -> int:
        """Migrate deals.json to deals table."""
        deals = read_json_safe(self.state_dir / 'deals.json', default=[])
        if not deals:
            return 0

        count = 0
        for deal in deals:
            try:
                deal['tenant_id'] = tenant_id
                deal['created_at'] = deal.get('created_at') or datetime.utcnow().isoformat()
                deal['updated_at'] = datetime.utcnow().isoformat()

                self.db.insert('deals', deal, tenant_id=tenant_id)
                count += 1
            except Exception as e:
                logger.warning(f"Failed to migrate deal {deal.get('id')}: {e}")

        logger.info(f"Migrated {count} deals to PostgreSQL")
        return count

    def migrate_tasks(self, tenant_id: str) -> int:
        """Migrate tasks.json to tasks table."""
        tasks = read_json_safe(self.state_dir / 'tasks.json', default=[])
        if not tasks:
            return 0

        count = 0
        for task in tasks:
            try:
                task['tenant_id'] = tenant_id
                task['created_at'] = task.get('created_at') or datetime.utcnow().isoformat()
                task['updated_at'] = datetime.utcnow().isoformat()

                self.db.insert('tasks', task, tenant_id=tenant_id)
                count += 1
            except Exception as e:
                logger.warning(f"Failed to migrate task {task.get('id')}: {e}")

        logger.info(f"Migrated {count} tasks to PostgreSQL")
        return count

    def migrate_leads(self, tenant_id: str) -> int:
        """Migrate leads.json to leads table."""
        leads = read_json_safe(self.state_dir / 'leads.json', default=[])
        if not leads:
            return 0

        count = 0
        for lead in leads:
            try:
                lead['tenant_id'] = tenant_id
                lead['created_at'] = lead.get('created_at') or datetime.utcnow().isoformat()
                lead['updated_at'] = datetime.utcnow().isoformat()

                # Handle leads table structure
                data = {
                    'tenant_id': tenant_id,
                    'name': lead.get('name'),
                    'email': lead.get('email'),
                    'company': lead.get('company'),
                    'title': lead.get('title'),
                    'phone': lead.get('phone'),
                    'source': lead.get('source'),
                    'status': lead.get('status', 'new'),
                    'notes': lead.get('notes'),
                    'metadata': lead.get('metadata', {}),
                    'created_at': lead['created_at'],
                    'updated_at': lead['updated_at']
                }

                self.db.insert('leads', data, tenant_id=tenant_id)
                count += 1
            except Exception as e:
                logger.warning(f"Failed to migrate lead {lead.get('id')}: {e}")

        logger.info(f"Migrated {count} leads to PostgreSQL")
        return count

    def migrate_revenue_events(self, tenant_id: str) -> int:
        """Migrate revenue tracking to revenue_events table."""
        # Try multiple possible JSON file locations
        possible_paths = [
            self.state_dir / 'revenue.json',
            self.state_dir / 'revenue_events.json',
            self.state_dir / 'money_mode.json'
        ]

        revenue_data = {}
        for path in possible_paths:
            data = read_json_safe(path, default={})
            if data:
                revenue_data = data
                break

        if not revenue_data:
            return 0

        count = 0
        events = revenue_data.get('events', [])

        for event in events:
            try:
                data = {
                    'tenant_id': tenant_id,
                    'type': event.get('type', 'manual'),
                    'amount': float(event.get('amount', 0)),
                    'currency': event.get('currency', 'USD'),
                    'source': event.get('source'),
                    'metadata': event.get('metadata', {}),
                    'created_at': event.get('created_at', datetime.utcnow().isoformat())
                }

                self.db.insert('revenue_events', data, tenant_id=tenant_id)
                count += 1
            except Exception as e:
                logger.warning(f"Failed to migrate revenue event: {e}")

        logger.info(f"Migrated {count} revenue events to PostgreSQL")
        return count

    def migrate_audit_logs(self, tenant_id: str) -> int:
        """Migrate audit logs to audit_logs table."""
        audit_file = self.state_dir / 'audit.jsonl'
        if not audit_file.exists():
            return 0

        count = 0
        try:
            with open(audit_file, 'r') as f:
                for line in f:
                    if not line.strip():
                        continue

                    try:
                        log_entry = json.loads(line)
                        data = {
                            'tenant_id': tenant_id,
                            'action': log_entry.get('action'),
                            'resource_type': log_entry.get('resource_type'),
                            'resource_id': log_entry.get('resource_id'),
                            'user_id': log_entry.get('user_id'),
                            'changes': log_entry.get('changes'),
                            'ip_address': log_entry.get('ip_address'),
                            'user_agent': log_entry.get('user_agent'),
                            'created_at': log_entry.get('created_at', datetime.utcnow().isoformat())
                        }

                        self.db.insert('audit_logs', data, tenant_id=tenant_id)
                        count += 1
                    except json.JSONDecodeError:
                        logger.warning(f"Skipping invalid audit log line: {line[:50]}")
        except FileNotFoundError:
            pass

        logger.info(f"Migrated {count} audit logs to PostgreSQL")
        return count

    def migrate_all(self, tenant_id: str) -> Dict[str, int]:
        """Migrate all JSON files to PostgreSQL."""
        results = {
            'deals': self.migrate_deals(tenant_id),
            'tasks': self.migrate_tasks(tenant_id),
            'leads': self.migrate_leads(tenant_id),
            'revenue_events': self.migrate_revenue_events(tenant_id),
            'audit_logs': self.migrate_audit_logs(tenant_id)
        }

        total = sum(results.values())
        logger.info(f"Total records migrated: {total}")

        return results


def migrate_json_to_postgres(ai_home: str, tenant_id: str) -> Dict[str, int]:
    """Public API for JSON to PostgreSQL migration."""
    migrator = JSONToPGMigrator(ai_home)
    return migrator.migrate_all(tenant_id)
