"""PostgreSQL backup and retention management."""
import os
import subprocess
import logging
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


class BackupManager:
    """Handle PostgreSQL backups with retention policy."""

    def __init__(self, backup_dir: str = None, retention_days: int = 30):
        self.backup_dir = Path(backup_dir or os.path.expanduser("~/.ai-employee/backups"))
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.retention_days = retention_days
        self.db_url = os.environ.get("DATABASE_URL", "")

    def create_backup(self) -> str:
        """Create a full PostgreSQL backup (custom format)."""
        if not self.db_url:
            logger.error("DATABASE_URL not set")
            return ""

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_file = self.backup_dir / f"ai_employee_{timestamp}.dump"

        try:
            cmd = [
                "pg_dump",
                "-Fc",  # Custom format (compressed)
                "-v",   # Verbose
                self.db_url,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode != 0:
                logger.error(f"Backup failed: {result.stderr}")
                return ""

            with open(backup_file, "wb") as f:
                f.write(result.stdout.encode() if isinstance(result.stdout, str) else result.stdout)

            logger.info(f"Backup created: {backup_file}")
            self._cleanup_old_backups()
            return str(backup_file)

        except subprocess.TimeoutExpired:
            logger.error("Backup timed out")
            return ""
        except Exception as e:
            logger.error(f"Backup error: {e}")
            return ""

    def create_backup_via_shell(self) -> str:
        """Create backup using shell environment (for Docker containers)."""
        if not self.db_url:
            logger.error("DATABASE_URL not set")
            return ""

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_file = self.backup_dir / f"ai_employee_{timestamp}.sql"

        try:
            # Parse DATABASE_URL to extract connection params
            # Format: postgresql://user:password@host:port/database
            import urllib.parse
            parsed = urllib.parse.urlparse(self.db_url)

            env = os.environ.copy()
            env["PGPASSWORD"] = parsed.password or ""

            cmd = [
                "pg_dump",
                "-h", parsed.hostname or "localhost",
                "-U", parsed.username or "postgres",
                "-d", (parsed.path or "/").lstrip("/"),
                "-F", "c",  # Custom format
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, env=env)

            if result.returncode != 0:
                logger.error(f"Backup failed: {result.stderr}")
                return ""

            with open(backup_file, "wb") as f:
                f.write(result.stdout.encode() if isinstance(result.stdout, str) else result.stdout)

            logger.info(f"Backup created: {backup_file} ({backup_file.stat().st_size} bytes)")
            self._cleanup_old_backups()
            return str(backup_file)

        except Exception as e:
            logger.error(f"Backup error: {e}")
            return ""

    def restore_backup(self, backup_file: str) -> bool:
        """Restore from a backup file."""
        if not self.db_url or not Path(backup_file).exists():
            logger.error(f"Invalid backup file: {backup_file}")
            return False

        try:
            # Drop and recreate database before restore
            import psycopg
            conn = psycopg.connect(self.db_url)
            conn.autocommit = True
            cur = conn.cursor()
            cur.execute("DROP DATABASE IF EXISTS ai_employee_restore")
            cur.execute("CREATE DATABASE ai_employee_restore")
            cur.close()
            conn.close()

            cmd = [
                "pg_restore",
                "-h", "localhost",
                "-U", "ai_user",
                "-d", "ai_employee_restore",
                backup_file,
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode == 0:
                logger.info(f"Restored from {backup_file}")
                return True
            else:
                logger.error(f"Restore failed: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"Restore error: {e}")
            return False

    def _cleanup_old_backups(self) -> None:
        """Delete backups older than retention_days."""
        cutoff = datetime.utcnow() - timedelta(days=self.retention_days)

        for backup_file in self.backup_dir.glob("ai_employee_*.dump"):
            mtime = datetime.utcfromtimestamp(backup_file.stat().st_mtime)
            if mtime < cutoff:
                try:
                    backup_file.unlink()
                    logger.info(f"Deleted old backup: {backup_file}")
                except Exception as e:
                    logger.warning(f"Failed to delete {backup_file}: {e}")

    def list_backups(self) -> list[dict]:
        """List all available backups."""
        backups = []
        for backup_file in sorted(self.backup_dir.glob("ai_employee_*.dump"), reverse=True):
            stat = backup_file.stat()
            backups.append({
                "file": backup_file.name,
                "path": str(backup_file),
                "size_mb": stat.st_size / (1024 * 1024),
                "created": datetime.utcfromtimestamp(stat.st_mtime).isoformat()
            })
        return backups


def get_backup_manager() -> BackupManager:
    """Get global backup manager instance."""
    return BackupManager()
