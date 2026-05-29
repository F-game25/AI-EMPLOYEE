"""PostgreSQL backup and retention management."""
import os
import subprocess
import logging
import time
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
        """List local backup files with size, age, and creation time."""
        now = datetime.utcnow()
        backups = []
        for f in sorted(self.backup_dir.glob("ai_employee_*"), reverse=True):
            if f.suffix not in (".dump", ".sql"):
                continue
            stat = f.stat()
            created_at = datetime.utcfromtimestamp(stat.st_mtime)
            backups.append({
                "file": f.name,
                "path": str(f),
                "size_mb": round(stat.st_size / (1024 * 1024), 3),
                "age_days": (now - created_at).days,
                "created_at": created_at.isoformat(),
            })
        return backups

    # ── Cloud upload methods ──────────────────────────────────────────────────

    def upload_to_s3(self, backup_file: str) -> bool:
        """Upload backup to S3. Returns False gracefully if boto3 absent or bucket unset."""
        bucket = os.environ.get("S3_BACKUP_BUCKET", "")
        if not bucket:
            logger.warning("S3_BACKUP_BUCKET not set — skipping S3 upload")
            return False
        try:
            import boto3  # type: ignore
        except ImportError:
            logger.warning("boto3 not installed — skipping S3 upload")
            return False
        try:
            path = Path(backup_file)
            key = f"backups/{path.name}"
            s3 = boto3.client("s3")
            s3.upload_file(str(path), bucket, key)
            logger.info(f"Uploaded to s3://{bucket}/{key}")
            return True
        except Exception as e:
            logger.error(f"S3 upload failed: {e}")
            return False

    def upload_to_backblaze(self, backup_file: str) -> bool:
        """Upload backup to Backblaze B2. Returns False gracefully if b2sdk absent or creds unset."""
        key_id = os.environ.get("B2_APPLICATION_KEY_ID", "")
        app_key = os.environ.get("B2_APPLICATION_KEY", "")
        bucket_name = os.environ.get("B2_BUCKET_NAME", "")
        if not all([key_id, app_key, bucket_name]):
            logger.warning("B2_APPLICATION_KEY_ID / B2_APPLICATION_KEY / B2_BUCKET_NAME not fully set — skipping B2 upload")
            return False
        try:
            from b2sdk.v2 import InMemoryAccountInfo, B2Api  # type: ignore
        except ImportError:
            logger.warning("b2sdk not installed — skipping Backblaze upload")
            return False
        try:
            info = InMemoryAccountInfo()
            api = B2Api(info)
            api.authorize_account("production", key_id, app_key)
            bucket = api.get_bucket_by_name(bucket_name)
            path = Path(backup_file)
            bucket.upload_local_file(
                local_file=str(path),
                file_name=f"backups/{path.name}",
            )
            logger.info(f"Uploaded to b2://{bucket_name}/backups/{path.name}")
            return True
        except Exception as e:
            logger.error(f"Backblaze upload failed: {e}")
            return False

    def full_backup_cycle(self, upload: bool = True) -> dict:
        """Run create_backup + optional cloud uploads. Returns result summary dict."""
        start = time.monotonic()
        backup_file = self.create_backup()
        if not backup_file:
            return {"file": "", "size_mb": 0.0, "s3_ok": False, "b2_ok": False, "duration_s": round(time.monotonic() - start, 2)}

        size_mb = round(Path(backup_file).stat().st_size / (1024 * 1024), 3)
        s3_ok = self.upload_to_s3(backup_file) if upload else False
        b2_ok = self.upload_to_backblaze(backup_file) if upload else False

        return {
            "file": backup_file,
            "size_mb": size_mb,
            "s3_ok": s3_ok,
            "b2_ok": b2_ok,
            "duration_s": round(time.monotonic() - start, 2),
        }


def get_backup_manager() -> BackupManager:
    """Get global backup manager instance."""
    return BackupManager()
