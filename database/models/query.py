"""
database/models/query.py

Query, SearchResult, and Feedback models — tracking every search interaction.

Tables:
  queries          → every search/chat request made by a user
  search_results   → documents returned for a query (for evaluation + feedback)
  feedback         → explicit user feedback (thumbs up/down, rating)
  query_events     → timeline events generated for a query (e.g. deployment, incident)

These tables power:
  - Evaluation system (Recall@K, Precision@K, MRR, NDCG)
  - ML recommendation layer (personalized ranking)
  - Observability (latency tracking, token usage)
"""
import enum

from sqlalchemy import (
    Boolean,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base, TimestampMixin, UUIDMixin


# ─────────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────────

class QueryType(str, enum.Enum):
    """Query intent classification (set by query classifier ML model)."""
    FACTUAL = "factual"               # "What is the rate limit for the payments API?"
    EXPLORATORY = "exploratory"       # "Tell me about the auth service architecture"
    DEBUGGING = "debugging"           # "Why did X fail after Y deployment?"
    COMPARISON = "comparison"         # "Difference between service A and B"
    AGGREGATION = "aggregation"       # "How many incidents last month?"
    UNKNOWN = "unknown"


class QueryStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


class FeedbackType(str, enum.Enum):
    THUMBS_UP = "thumbs_up"
    THUMBS_DOWN = "thumbs_down"
    RATING = "rating"                 # 1–5 stars
    CORRECTION = "correction"         # user provided better answer


# ─────────────────────────────────────────────────────────────────────────────
# Query
# ─────────────────────────────────────────────────────────────────────────────

class Query(UUIDMixin, TimestampMixin, Base):
    """
    Every search or chat request submitted by a user.

    Stores the full pipeline latency breakdown for observability:
      - embedding_latency_ms  → time to embed the query
      - retrieval_latency_ms  → BM25 + vector search time
      - reranking_latency_ms  → reranker inference time
      - llm_latency_ms        → LLM generation time
      - total_latency_ms      → end-to-end

    Also stores token usage and LLM model used (for cost tracking).
    """
    __tablename__ = "queries"
    __table_args__ = (
        Index("ix_queries_tenant_id", "tenant_id"),
        Index("ix_queries_user_id", "user_id"),
        Index("ix_queries_status", "status"),
        Index("ix_queries_created_at", "created_at"),
    )

    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # ^ nullable for API-key based access (no user session)

    # ── Query Content ─────────────────────────────────────────────────────────
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    query_type: Mapped[QueryType] = mapped_column(
        Enum(QueryType, name="query_type"),
        default=QueryType.UNKNOWN,
        nullable=False,
    )
    conversation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # ^ Groups multi-turn chat queries into a conversation session
    turn_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # ^ Position within conversation (0 = first turn)

    # ── Applied Filters ───────────────────────────────────────────────────────
    filters: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # ^ e.g. {"source_type": "github", "date_from": "2024-01-01"}

    # ── Response ──────────────────────────────────────────────────────────────
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    citations: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # ^ [{"chunk_id": "...", "document_id": "...", "text": "...", "score": 0.9}]

    status: Mapped[QueryStatus] = mapped_column(
        Enum(QueryStatus, name="query_status"),
        default=QueryStatus.PENDING,
        nullable=False,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Latency Breakdown (ms) ────────────────────────────────────────────────
    embedding_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    retrieval_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    reranking_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    llm_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ── LLM Token Usage ───────────────────────────────────────────────────────
    llm_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── Retrieval Stats ───────────────────────────────────────────────────────
    num_candidates: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # ^ Total candidates before reranking
    num_results: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # ^ Final results returned to user

    # ── Relationships ──────────────────────────────────────────────────────────
    search_results: Mapped[list["SearchResult"]] = relationship(
        "SearchResult", back_populates="query", cascade="all, delete-orphan"
    )
    feedback: Mapped[list["Feedback"]] = relationship(
        "Feedback", back_populates="query", cascade="all, delete-orphan"
    )
    events: Mapped[list["QueryEvent"]] = relationship(
        "QueryEvent", back_populates="query", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Query id={self.id} text={self.query_text[:40]!r} status={self.status}>"


# ─────────────────────────────────────────────────────────────────────────────
# SearchResult
# ─────────────────────────────────────────────────────────────────────────────

class SearchResult(UUIDMixin, Base):
    """
    Documents returned for a query, with their retrieval scores.

    Stored for:
    - Evaluation metrics (Recall@K, Precision@K, MRR, NDCG)
    - Training the learning-to-rank model
    - Showing "what was retrieved" in the UI
    """
    __tablename__ = "search_results"
    __table_args__ = (
        Index("ix_search_results_query_id", "query_id"),
        Index("ix_search_results_document_id", "document_id"),
    )

    query_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("queries.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    chunk_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # ── Scores ────────────────────────────────────────────────────────────────
    rank: Mapped[int] = mapped_column(Integer, nullable=False)           # 1-indexed rank
    bm25_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    vector_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    reranker_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    final_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ── User interaction signals (for L2R training) ───────────────────────────
    was_clicked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    dwell_time_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    was_cited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # ^ Whether this document appeared in final answer citations

    # ── Relationships ──────────────────────────────────────────────────────────
    query: Mapped["Query"] = relationship("Query", back_populates="search_results")
    document: Mapped["Document | None"] = relationship("Document")


# ─────────────────────────────────────────────────────────────────────────────
# Feedback
# ─────────────────────────────────────────────────────────────────────────────

class Feedback(UUIDMixin, TimestampMixin, Base):
    """
    Explicit user feedback on a query response.
    Used for evaluation and improving the ranking model.
    """
    __tablename__ = "feedback"
    __table_args__ = (
        Index("ix_feedback_query_id", "query_id"),
        Index("ix_feedback_user_id", "user_id"),
    )

    query_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("queries.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    feedback_type: Mapped[FeedbackType] = mapped_column(
        Enum(FeedbackType, name="feedback_type"),
        nullable=False,
    )
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)     # 1–5
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrected_answer: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Relationships ──────────────────────────────────────────────────────────
    query: Mapped["Query"] = relationship("Query", back_populates="feedback")

    def __repr__(self) -> str:
        return f"<Feedback query={self.query_id} type={self.feedback_type}>"


# ─────────────────────────────────────────────────────────────────────────────
# QueryEvent
# ─────────────────────────────────────────────────────────────────────────────

class QueryEvent(UUIDMixin, Base):
    """
    Timeline events extracted for a query response.
    Example: "Payment service deployed v2.3.1 on 2024-03-15".

    Used to build the timeline view in the UI.
    Entity extraction (NER) populates this table.
    """
    __tablename__ = "query_events"
    __table_args__ = (
        Index("ix_query_events_query_id", "query_id"),
    )

    query_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("queries.id", ondelete="CASCADE"), nullable=False
    )
    event_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    event_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # ^ deployment | incident | config_change | release | alert
    description: Mapped[str] = mapped_column(Text, nullable=False)
    source_document_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    entities: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # ^ {"service": "payment-svc", "version": "v2.3.1", "team": "payments"}

    # ── Relationships ──────────────────────────────────────────────────────────
    query: Mapped["Query"] = relationship("Query", back_populates="events")
