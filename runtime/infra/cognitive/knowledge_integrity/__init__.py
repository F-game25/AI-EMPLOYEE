from .lifecycle_manager import get_lifecycle_manager, register, record_access, quarantine, restore, get_counts, run_decay
from .deduplicator import get_deduplicator, find_duplicates, list_clusters
from .contradiction_scanner import scan as scan_contradictions
from .hallucination_detector import flag as flag_hallucination
from .entropy_reducer import prune_stale, report as entropy_report

__all__ = [
    "get_lifecycle_manager", "get_deduplicator", "register", "record_access",
    "quarantine", "restore", "get_counts", "run_decay", "find_duplicates",
    "list_clusters", "scan_contradictions", "flag_hallucination", "prune_stale",
    "entropy_report"
]
