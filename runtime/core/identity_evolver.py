"""
Identity evolver — background daemon that grows identity based on usage patterns.
Runs every 5 minutes, reads audit logs, updates favorite_agents, vocabulary, work_pattern.
Suggests capability enablement at interaction milestones.
"""
import json
import asyncio
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from collections import Counter


class IdentityEvolver:
    """Evolve identity based on usage patterns."""

    def __init__(self, identity_file: Optional[Path] = None, audit_db: Optional[Path] = None):
        self.identity_file = identity_file or (Path.home() / ".ai-employee" / "identity.json")
        self.audit_db = audit_db or (Path.home() / ".ai-employee" / "state" / "audit.db")
        self.check_interval_seconds = 300  # 5 minutes

    def load_identity(self) -> Optional[Dict]:
        """Load current identity."""
        if not self.identity_file.exists():
            return None
        with open(self.identity_file) as f:
            return json.load(f)

    def save_identity(self, identity: Dict):
        """Save updated identity."""
        self.identity_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.identity_file, 'w') as f:
            json.dump(identity, f, indent=2)

    def get_audit_logs(self, since: Optional[datetime] = None) -> List[Dict]:
        """Fetch recent audit logs from audit.db."""
        if not self.audit_db.exists():
            return []

        if since is None:
            since = datetime.utcnow() - timedelta(minutes=5)

        try:
            conn = sqlite3.connect(self.audit_db)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Fetch logs since the given time
            cursor.execute(
                "SELECT * FROM audit_logs WHERE timestamp > ? ORDER BY timestamp DESC",
                (since.isoformat(),)
            )
            rows = cursor.fetchall()
            conn.close()
            return [dict(row) for row in rows]
        except Exception as e:
            print(f"Failed to read audit logs: {e}")
            return []

    def extract_favorite_agents(self, logs: List[Dict]) -> List[str]:
        """Extract top 5 agent IDs by interaction count."""
        agent_counts = Counter()
        for log in logs:
            agent_id = log.get("agent_id")
            if agent_id:
                agent_counts[agent_id] += 1

        # Return top 5
        return [agent for agent, count in agent_counts.most_common(5)]

    def extract_vocabulary_signature(self, logs: List[Dict]) -> List[str]:
        """Extract common words from user messages (simple bag-of-words)."""
        # Simple approach: just collect message keywords (real version would do NLP)
        keywords = Counter()
        stopwords = {"the", "a", "an", "is", "are", "was", "be", "to", "of", "and", "or", "in", "on"}

        for log in logs:
            message = log.get("message", "").lower()
            if message:
                words = [w for w in message.split() if w not in stopwords and len(w) > 3]
                keywords.update(words)

        # Return top 10 keywords
        return [word for word, count in keywords.most_common(10)]

    def infer_work_pattern(self, logs: List[Dict]) -> Optional[str]:
        """Infer work pattern from timestamp distribution (morning/evening/burst)."""
        if not logs:
            return None

        hours = []
        for log in logs:
            try:
                ts = datetime.fromisoformat(log.get("timestamp", "").replace("Z", "+00:00"))
                hours.append(ts.hour)
            except Exception:
                pass

        if not hours:
            return None

        avg_hour = sum(hours) / len(hours)

        # Simple heuristic
        if 6 <= avg_hour < 12:
            return "morning"
        elif 12 <= avg_hour < 17:
            return "afternoon"
        elif 17 <= avg_hour < 22:
            return "evening"
        else:
            return "late_night"

    def suggest_capabilities(self, logs: List[Dict], identity: Dict) -> List[str]:
        """Suggest capabilities to enable based on usage patterns."""
        suggestions = []
        interaction_count = len(logs)

        # Milestone thresholds
        if interaction_count >= 200 and "postgres" not in [c for c in identity.get("enabled_capabilities", [])]:
            suggestions.append("postgres")
        if interaction_count >= 50 and "mailchimp" not in identity.get("enabled_capabilities", []):
            # Check if user has asked about email/newsletter
            if any("email" in log.get("message", "").lower() for log in logs[-20:]):
                suggestions.append("mailchimp")
        if interaction_count >= 10 and "tracing" not in identity.get("enabled_capabilities", []):
            suggestions.append("tracing")

        return suggestions

    def evolve(self) -> Dict:
        """Run one evolution cycle."""
        identity = self.load_identity()
        if not identity:
            print("No identity found; skipping evolution")
            return {}

        # Get recent audit logs
        last_evolution = identity.get("evolution_log", [])
        since = None
        if last_evolution:
            try:
                since = datetime.fromisoformat(last_evolution[-1].get("timestamp", "").replace("Z", "+00:00"))
            except Exception:
                since = datetime.utcnow() - timedelta(minutes=5)
        else:
            since = datetime.utcnow() - timedelta(minutes=5)

        logs = self.get_audit_logs(since)
        if not logs:
            return {}

        # Extract insights
        favorite_agents = self.extract_favorite_agents(logs)
        vocabulary = self.extract_vocabulary_signature(logs)
        work_pattern = self.infer_work_pattern(logs)
        suggestions = self.suggest_capabilities(logs, identity)

        # Update identity
        identity["emergent"]["favorite_agents"] = favorite_agents
        identity["emergent"]["vocabulary_signature"] = vocabulary
        if work_pattern:
            identity["emergent"]["work_pattern"] = work_pattern

        # Log evolution event
        identity["evolution_log"].append({
            "event": "evolution_cycle",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "logs_processed": len(logs),
            "favorite_agents": favorite_agents,
            "vocabulary_words": len(vocabulary),
            "work_pattern": work_pattern,
            "capability_suggestions": suggestions
        })

        # Cap evolution_log to last 100 entries to prevent unbounded growth
        if len(identity["evolution_log"]) > 100:
            identity["evolution_log"] = identity["evolution_log"][-100:]

        self.save_identity(identity)

        return {
            "favorite_agents": favorite_agents,
            "vocabulary_words": len(vocabulary),
            "work_pattern": work_pattern,
            "capability_suggestions": suggestions
        }

    async def run_forever(self):
        """Run evolution loop forever (one cycle every 5 minutes)."""
        print(f"[IdentityEvolver] Starting evolution daemon (check interval: {self.check_interval_seconds}s)")
        while True:
            try:
                result = self.evolve()
                if result:
                    print(f"[IdentityEvolver] Evolved: {result}")
            except Exception as e:
                print(f"[IdentityEvolver] Cycle failed: {e}")

            await asyncio.sleep(self.check_interval_seconds)

    def run_sync(self):
        """Synchronous version (for non-async contexts)."""
        print(f"[IdentityEvolver] Running evolution cycle")
        try:
            result = self.evolve()
            if result:
                print(f"[IdentityEvolver] Evolved: {result}")
            return result
        except Exception as e:
            print(f"[IdentityEvolver] Cycle failed: {e}")
            return {}


# Convenience functions
def evolve_identity() -> Dict:
    """Run one evolution cycle (sync)."""
    evolver = IdentityEvolver()
    return evolver.run_sync()


async def run_evolution_daemon():
    """Start the async evolution daemon."""
    evolver = IdentityEvolver()
    await evolver.run_forever()


if __name__ == "__main__":
    # Quick test
    evolver = IdentityEvolver()
    result = evolver.run_sync()
    print(f"Evolution result: {result}")
