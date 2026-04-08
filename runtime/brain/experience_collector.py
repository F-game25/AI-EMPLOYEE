"""experience_collector.py — Smart online/offline experience collector.

Detects internet connectivity and routes experience collection to the
appropriate source:

  Online  → GitHub Issues / PRs / Commit messages (via GitHub REST API)
  Offline → Local logs (JSONL), JSON state files, self-simulated experiences

The collector runs inside the brain's background thread and periodically
pushes new experiences into the central replay buffer.
"""
from __future__ import annotations

import json
import logging
import os
import random
import socket
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional

import torch

logger = logging.getLogger("brain.collector")

# ── Project root ─────────────────────────────────────────────────────────────
_AI_HOME = Path(os.environ.get("AI_HOME", Path.home() / ".ai-employee"))
_PROJECT_ROOT = Path(__file__).resolve().parents[2]  # runtime/brain → repo root

# ── GitHub settings (read from env — same as auto_updater.py) ─────────────────
_REPO   = os.environ.get("AI_EMPLOYEE_REPO",   "F-game25/AI-EMPLOYEE")
_BRANCH = os.environ.get("AI_EMPLOYEE_BRANCH", "main")
_TOKEN  = os.environ.get("GITHUB_TOKEN", "") or os.environ.get("GH_TOKEN", "")
_GH_HEADERS: Dict[str, str] = {
    "Accept":     "application/vnd.github.v3+json",
    "User-Agent": "ai-employee-brain/1.0",
}
if _TOKEN:
    _GH_HEADERS["Authorization"] = f"Bearer {_TOKEN}"


# ═════════════════════════════════════════════════════════════════════════════
# Internet detection
# ═════════════════════════════════════════════════════════════════════════════

def check_internet(host: str = "8.8.8.8", port: int = 53, timeout: float = 2.0) -> bool:
    """Return True if a TCP connection to *host:port* can be established."""
    try:
        socket.setdefaulttimeout(timeout)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((host, port))
        return True
    except OSError:
        return False


# ═════════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════════

def _gh_get(url: str) -> Optional[Any]:
    """GET request to GitHub API; returns parsed JSON or None on error."""
    try:
        req = urllib.request.Request(url, headers=_GH_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except Exception as exc:
        logger.debug("GitHub API error: %s", exc)
        return None


def _text_to_features(text: str, size: int) -> torch.Tensor:
    """Very lightweight text → fixed-size float feature vector.

    Uses character n-gram hashing (no ML dependencies required).
    """
    vec = [0.0] * size
    if not text:
        return torch.tensor(vec, dtype=torch.float32)
    text = text.lower()
    for i, ch in enumerate(text[:size]):
        vec[i % size] += ord(ch) / 1000.0
    # Normalise
    total = max(sum(abs(v) for v in vec), 1.0)
    vec = [v / total for v in vec]
    return torch.tensor(vec, dtype=torch.float32)


def _label_to_action(label: str) -> int:
    """Map a GitHub issue label / keyword to an action index."""
    _MAP = {
        "bug":          0,
        "enhancement":  1,
        "question":     2,
        "documentation":3,
        "update":       4,
        "security":     5,
        "performance":  6,
    }
    label_lower = label.lower()
    for key, idx in _MAP.items():
        if key in label_lower:
            return idx
    return 7  # "other"


def _issue_to_reward(issue: Dict[str, Any]) -> float:
    """Heuristic reward from an issue: closed with comments → positive."""
    if issue.get("state") == "closed":
        return 1.0
    comments = issue.get("comments", 0)
    if comments > 5:
        return 0.5
    return 0.0


# ═════════════════════════════════════════════════════════════════════════════
# Online collector
# ═════════════════════════════════════════════════════════════════════════════

class OnlineExperienceCollector:
    """Collects experiences from GitHub API (issues, PRs, commits)."""

    def __init__(self, input_size: int, output_size: int) -> None:
        self.input_size = input_size
        self.output_size = output_size
        self._api = f"https://api.github.com/repos/{_REPO}"

    def collect(self, max_items: int = 20) -> List[tuple]:
        """Return a list of (state, action, reward, next_state) tuples."""
        experiences = []

        # ── Issues ────────────────────────────────────────────────────────────
        issues = _gh_get(f"{self._api}/issues?state=all&per_page={max_items}") or []
        for issue in issues[:max_items]:
            if not isinstance(issue, dict):
                continue
            title   = issue.get("title", "")
            body    = issue.get("body",  "") or ""
            labels  = [lbl.get("name", "") for lbl in issue.get("labels", [])]
            label   = labels[0] if labels else "other"

            state      = _text_to_features(title + " " + body[:200], self.input_size)
            action     = _label_to_action(label)
            reward     = _issue_to_reward(issue)
            next_state = _text_to_features(body[-200:], self.input_size)

            experiences.append((state, action, reward, next_state))

        logger.info("Online collector: %d experiences from GitHub.", len(experiences))
        return experiences

    def collect_prs(self, max_items: int = 10) -> List[tuple]:
        """Collect experiences from recently merged pull requests."""
        experiences = []
        prs = _gh_get(f"{self._api}/pulls?state=closed&per_page={max_items}") or []
        for pr in prs[:max_items]:
            if not isinstance(pr, dict):
                continue
            merged = pr.get("merged_at") is not None
            title  = pr.get("title", "")
            body   = pr.get("body",  "") or ""

            state      = _text_to_features(title + " " + body[:200], self.input_size)
            action     = 4  # "update" action for PRs
            reward     = 1.0 if merged else -0.5
            next_state = _text_to_features(body[-200:], self.input_size)

            experiences.append((state, action, reward, next_state))

        return experiences


# ═════════════════════════════════════════════════════════════════════════════
# Offline collector
# ═════════════════════════════════════════════════════════════════════════════

class OfflineExperienceCollector:
    """Collects experiences from local logs, JSON files, and self-simulation."""

    def __init__(self, input_size: int, output_size: int) -> None:
        self.input_size  = input_size
        self.output_size = output_size

        # Directories to search for local data
        self._search_dirs: List[Path] = [
            _AI_HOME / "logs",
            _AI_HOME / "state",
            _PROJECT_ROOT / "runtime" / "improvements",
            _PROJECT_ROOT / "runtime" / "config",
        ]

    # ── JSONL log files ───────────────────────────────────────────────────────

    def _iter_jsonl(self, path: Path) -> Iterator[Dict[str, Any]]:
        try:
            for line in path.read_text(errors="replace").splitlines():
                line = line.strip()
                if line:
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        pass
        except OSError:
            pass

    def collect_from_logs(self, max_items: int = 30) -> List[tuple]:
        """Parse JSONL log files and extract (s, a, r, s') tuples."""
        experiences = []
        for search_dir in self._search_dirs:
            if not search_dir.exists():
                continue
            for log_file in list(search_dir.glob("*.jsonl"))[:5]:
                records = list(self._iter_jsonl(log_file))
                for rec in records[:max_items]:
                    try:
                        # Extract features from whatever is in the log record
                        text  = json.dumps(rec)
                        state = _text_to_features(text[:300], self.input_size)
                        action = rec.get("action", rec.get("agent_action", random.randint(0, self.output_size - 1)))
                        if isinstance(action, str):
                            action = _label_to_action(action)
                        action = int(action) % self.output_size
                        reward = float(rec.get("reward", rec.get("success", 0.0)))
                        next_state = _text_to_features(text[-300:], self.input_size)
                        experiences.append((state, action, reward, next_state))
                    except Exception:
                        continue
                if len(experiences) >= max_items:
                    break

        logger.info("Offline log collector: %d experiences.", len(experiences))
        return experiences

    def collect_from_json_files(self, max_items: int = 20) -> List[tuple]:
        """Extract experiences from JSON state / config files."""
        experiences = []
        for search_dir in self._search_dirs:
            if not search_dir.exists():
                continue
            for json_file in list(search_dir.glob("*.json"))[:10]:
                try:
                    raw = json.loads(json_file.read_text(errors="replace"))
                    items = raw if isinstance(raw, list) else [raw]
                    for item in items[:max_items]:
                        text       = json.dumps(item)[:400]
                        state      = _text_to_features(text, self.input_size)
                        next_state = _text_to_features(text[::-1], self.input_size)
                        action     = random.randint(0, self.output_size - 1)
                        reward     = 0.5  # neutral — we don't know the outcome
                        experiences.append((state, action, reward, next_state))
                except Exception:
                    continue
                if len(experiences) >= max_items:
                    break

        return experiences

    def simulate(self, count: int = 20) -> List[tuple]:
        """Generate synthetic experiences via self-simulation.

        Uses structured random vectors that mimic plausible state distributions,
        allowing the brain to continue learning even with zero external data.
        """
        experiences = []
        patterns = [
            # (state_template, reward)  — action is randomised per output_size
            (torch.ones(self.input_size) * 0.8,  1.0),   # high-signal → positive
            (torch.zeros(self.input_size),        0.0),   # empty state  → neutral
            (torch.randn(self.input_size).abs(),  0.5),   # noisy        → partial
        ]
        for _ in range(count):
            template, reward = random.choice(patterns)
            noise      = torch.randn(self.input_size) * 0.1
            state      = (template + noise).clamp(-1, 1)
            next_state = (state + torch.randn(self.input_size) * 0.05).clamp(-1, 1)
            action     = random.randint(0, self.output_size - 1)
            experiences.append((state, action, reward, next_state))

        logger.debug("Offline simulation: %d synthetic experiences.", count)
        return experiences

    def collect(self, max_items: int = 50) -> List[tuple]:
        """Collect from all offline sources combined."""
        exps: List[tuple] = []
        exps.extend(self.collect_from_logs(max_items // 2))
        exps.extend(self.collect_from_json_files(max_items // 4))
        if len(exps) < 10:
            exps.extend(self.simulate(max_items - len(exps)))
        return exps[:max_items]


# ═════════════════════════════════════════════════════════════════════════════
# Smart dispatcher
# ═════════════════════════════════════════════════════════════════════════════

class ExperienceCollector:
    """Unified collector: uses online sources when internet is available,
    falls back to offline sources otherwise.

    Args:
        input_size:  Feature vector size expected by the brain.
        output_size: Number of actions the brain can choose from.
        push_fn:     Callable(state, action, reward, next_state) that pushes
                     an experience directly into the brain's replay buffer.
    """

    def __init__(
        self,
        input_size: int,
        output_size: int,
        push_fn: Callable[[torch.Tensor, int, float, torch.Tensor], None],
    ) -> None:
        self.online  = OnlineExperienceCollector(input_size, output_size)
        self.offline = OfflineExperienceCollector(input_size, output_size)
        self._push   = push_fn
        self.is_online: bool = False

    def collect_and_push(self, max_items: int = 30) -> int:
        """Detect connectivity, collect, and push experiences.

        Returns:
            Number of experiences pushed.
        """
        self.is_online = check_internet()

        if self.is_online:
            experiences = self.online.collect(max_items)
            experiences += self.online.collect_prs(max_items // 3)
            mode = "online"
        else:
            experiences = self.offline.collect(max_items)
            mode = "offline"

        for state, action, reward, next_state in experiences:
            try:
                self._push(state, action, reward, next_state)
            except Exception as exc:
                logger.debug("push error: %s", exc)

        logger.info(
            "ExperienceCollector [%s]: pushed %d experiences.",
            mode, len(experiences),
        )
        return len(experiences)
