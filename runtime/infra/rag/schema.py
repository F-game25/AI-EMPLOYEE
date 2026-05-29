"""RAG document and chunk schemas."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SourceType(str, Enum):
    SHAREPOINT  = "sharepoint"
    GOOGLE_DRIVE = "google_drive"
    SLACK       = "slack"
    GMAIL       = "gmail"
    JIRA        = "jira"
    CONFLUENCE  = "confluence"
    CRM         = "crm"
    FILE        = "file"
    WEB         = "web"


class ChunkStrategy(str, Enum):
    FIXED       = "fixed"        # fixed token window
    SEMANTIC    = "semantic"     # sentence-boundary aware
    HIERARCHICAL = "hierarchical" # section → paragraph → sentence


@dataclass
class SourceDocument:
    id: str
    source_type: SourceType
    source_id: str              # connector-native ID (e.g. drive file ID)
    tenant_id: str
    title: str
    url: str
    content_hash: str           # SHA-256 of raw content
    raw_text: str
    metadata: dict[str, Any]    # author, modified_at, permissions, labels
    permissions: list[str]      # list of user/group principals who can see this
    ingested_at: float
    modified_at: float
    language: str = "en"
    content_type: str = "text/plain"


@dataclass
class DocumentChunk:
    id: str                     # "{doc_id}::chunk::{n}"
    doc_id: str
    tenant_id: str
    source_type: SourceType
    text: str
    token_count: int
    chunk_index: int
    total_chunks: int
    embedding: list[float] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    permissions: list[str] = field(default_factory=list)
    confidence: float = 1.0


@dataclass
class RetrievalResult:
    chunk: DocumentChunk
    score: float                # 0-1 relevance
    rerank_score: float = 0.0
    source_attribution: str = ""
    graph_boosted: bool = False
