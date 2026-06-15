"""Content Factory (Module 5) — real content production + approval-gated publish queue.

Generates real LLM content (reusing money_mode.content_publish_track for artifact
saving), supports multi-platform batches, and stages everything in a publish queue
that NEVER auto-posts — publishing requires explicit human approval (HITL).
"""
from .content_factory import ContentFactory, get_content_factory
from .publish_queue import PublishQueue, get_publish_queue

__all__ = ["ContentFactory", "get_content_factory", "PublishQueue", "get_publish_queue"]
