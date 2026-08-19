"""
shared/schemas/document.py

Pydantic v2 schemas for API request/response contracts.
These are shared between the ML layer and the API layer.
"""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# Document Schemas
# ─────────────────────────────────────────────────────────────────────────────

class ChunkSchema(BaseModel):
    chunk_id: str
    document_id: str
    text: str
    chunk_index: int
    page_number: int | None = None
    section_title: str | None = None
    chunk_type: str = "paragraph"
    permissions: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentSchema(BaseModel):
    id: str
    tenant_id: str
    source_type: str
    source_id: str
    title: str
    source_url: str | None = None
    content_hash: str | None = None
    language: str = "en"
    category: str = "unknown"
    permissions: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Search / Query Schemas
# ─────────────────────────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    """Incoming search/chat request from the API layer."""
    query: str = Field(..., min_length=1, max_length=2000)
    tenant_id: str
    user_id: str | None = None
    user_permissions: list[str] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    top_k: int = Field(default=10, ge=1, le=50)
    conversation_id: str | None = None
    turn_index: int = 0


class CitationSchema(BaseModel):
    """A citation linking an answer claim to a source chunk."""
    chunk_id: str
    document_id: str
    document_title: str
    text: str                     # excerpt of the chunk used
    source_type: str
    source_url: str | None = None
    page_number: int | None = None
    relevance_score: float


class SearchResultItem(BaseModel):
    """A single retrieved item in the result set."""
    chunk_id: str
    document_id: str
    document_title: str
    text: str
    source_type: str
    source_url: str | None = None
    bm25_score: float | None = None
    vector_score: float | None = None
    reranker_score: float | None = None
    final_score: float
    rank: int


class TimelineEvent(BaseModel):
    """An extracted timeline event for the query response."""
    event_date: str | None = None
    event_type: str | None = None
    description: str
    source_document_id: str | None = None
    entities: dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    """Full response returned to the user."""
    query_id: str
    answer: str
    confidence: float = Field(ge=0.0, le=1.0)
    citations: list[CitationSchema] = Field(default_factory=list)
    sources: list[SearchResultItem] = Field(default_factory=list)
    timeline: list[TimelineEvent] = Field(default_factory=list)
    # Latency breakdown (ms)
    embedding_latency_ms: float | None = None
    retrieval_latency_ms: float | None = None
    reranking_latency_ms: float | None = None
    llm_latency_ms: float | None = None
    total_latency_ms: float | None = None
    # Token usage
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
