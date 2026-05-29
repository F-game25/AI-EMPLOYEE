#!/usr/bin/env python3
"""Migrate existing single-tenant state to multi-tenant model.

This script:
1. Creates a default tenant for existing data
2. Converts all state files to tenant-segregated format
3. Creates backup of original files
4. Validates migration success
"""
import json
import shutil
import sys
from pathlib import Path
from datetime import datetime

AI_HOME = Path.home() / ".ai-employee"
STATE_DIR = AI_HOME / "state"
BACKUP_DIR = AI_HOME / "backups" / f"pre-multitenant-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

STATE_FILES = [
    "deals.json",
    "tasks.json",
    "team-roster.json",
    "knowledge_store.json",
    "team-tasks.json",
    "leads.json",
    "revenue.json",
    "chatlog.jsonl",
    "activity_log.jsonl",
    "improvements.json",
    "metrics.json",
    "guardrails.json",
    "memory.json",
    "doctor_actions.json",
]


def create_backup():
    """Create backup of all state files."""
    print("🔄 Creating backup...")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    for fname in STATE_FILES:
        src = STATE_DIR / fname
        if src.exists():
            dst = BACKUP_DIR / fname
            shutil.copy2(src, dst)
            print(f"  ✓ Backed up {fname}")

    # Backup the entire state dir
    shutil.copytree(STATE_DIR, BACKUP_DIR / "full-state", dirs_exist_ok=True)
    print(f"✓ Full backup saved to {BACKUP_DIR}")


def migrate_json_file(file_path: Path, tenant_id: str) -> bool:
    """Convert single-tenant JSON file to multi-tenant format."""
    try:
        if not file_path.exists():
            return True

        with open(file_path) as f:
            original_data = json.load(f)

        # Create tenant-segregated structure
        tenant_data = {
            "_tenant_data": {
                tenant_id: original_data if isinstance(original_data, (dict, list)) else []
            },
            "_migrated_at": datetime.now().isoformat(),
            "_default_tenant": tenant_id,
        }

        with open(file_path, 'w') as f:
            json.dump(tenant_data, f, indent=2, ensure_ascii=False)

        return True
    except Exception as e:
        print(f"  ✗ Error migrating {file_path.name}: {e}")
        return False


def migrate_jsonl_file(file_path: Path, tenant_id: str) -> bool:
    """Convert JSONL file (line-delimited) to multi-tenant format."""
    try:
        if not file_path.exists():
            return True

        # Read all lines
        lines = []
        with open(file_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        lines.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

        # Write back with tenant_id on each line
        with open(file_path, 'w') as f:
            for entry in lines:
                if isinstance(entry, dict):
                    entry["_tenant_id"] = tenant_id
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')

        return True
    except Exception as e:
        print(f"  ✗ Error migrating {file_path.name}: {e}")
        return False


def main():
    """Execute migration."""
    print("=" * 60)
    print("Multi-Tenancy Migration")
    print("=" * 60)

    # Create default tenant ID from existing installation
    default_tenant_id = "default-tenant"
    print(f"\n📌 Default tenant ID: {default_tenant_id}")

    # Step 1: Backup
    if not STATE_DIR.exists():
        print("\n⚠️  No state directory found. Creating fresh multi-tenant setup...")
        STATE_DIR.mkdir(parents=True, exist_ok=True)
    else:
        create_backup()

    # Step 2: Migrate JSON files
    print("\n🔄 Migrating JSON state files...")
    json_migrated = 0
    for fname in STATE_FILES:
        if fname.endswith('.jsonl'):
            continue
        file_path = STATE_DIR / fname
        if migrate_json_file(file_path, default_tenant_id):
            print(f"  ✓ {fname}")
            json_migrated += 1
        else:
            print(f"  ✗ {fname} (skipped)")

    # Step 3: Migrate JSONL files
    print("\n🔄 Migrating JSONL log files...")
    jsonl_migrated = 0
    for fname in STATE_FILES:
        if not fname.endswith('.jsonl'):
            continue
        file_path = STATE_DIR / fname
        if migrate_jsonl_file(file_path, default_tenant_id):
            print(f"  ✓ {fname}")
            jsonl_migrated += 1
        else:
            print(f"  ✗ {fname} (skipped)")

    # Step 4: Verify
    print("\n✓ Verification:")
    for fname in STATE_FILES:
        file_path = STATE_DIR / fname
        if file_path.exists():
            try:
                if fname.endswith('.jsonl'):
                    with open(file_path) as f:
                        first_line = f.readline()
                        if first_line:
                            entry = json.loads(first_line)
                            has_tenant = "_tenant_id" in entry
                            status = "✓" if has_tenant else "⚠"
                            print(f"  {status} {fname} (has _tenant_id: {has_tenant})")
                else:
                    with open(file_path) as f:
                        data = json.load(f)
                        has_tenant_data = "_tenant_data" in data
                        status = "✓" if has_tenant_data else "⚠"
                        print(f"  {status} {fname} (has _tenant_data: {has_tenant_data})")
            except Exception as e:
                print(f"  ✗ {fname} (error: {e})")

    print("\n" + "=" * 60)
    print("✓ Migration complete!")
    print(f"  Migrated JSON files: {json_migrated}")
    print(f"  Migrated JSONL files: {jsonl_migrated}")
    print(f"  Backup location: {BACKUP_DIR}")
    print(f"  Default tenant: {default_tenant_id}")
    print("\nNext steps:")
    print("  1. Update JWT tokens to include tenant_id claim")
    print("  2. Update all routes to accept/use tenant_id from token")
    print("  3. Test with: curl -H 'Authorization: Bearer <token>' http://localhost:8787/api/agents")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Migration cancelled. Backup is safe at:", BACKUP_DIR)
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        print(f"Backup is safe at: {BACKUP_DIR}")
        sys.exit(1)
