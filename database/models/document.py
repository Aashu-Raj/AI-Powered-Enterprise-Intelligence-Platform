"""
database/models/document.py

Document and Chunk models — the core data units of the platform.

Tables:
  source_connectors  → configured data sources per tenant (GitHub repo, Jira project, ...)
  documents          → one ingested document (PDF, code file, Jira ticket, Slack thread, ...)
  chunks             → text chunks derived from a document (what gets embedded + indexed)
  document_tags      → M2M: tag labels per document (classification output)
"""
import enum

from sqlalchemy import (
    BigInteger,
    Boolean,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base, TimestampMixin, UUIDMixin


# ─────────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────────

class SourceType(str, enum.Enum):
    """Supported data source types."""
    PDF = "pdf"
    DOCX = "docx"
    PPTX = "pptx"
    TXT = "txt"
    HTML = "html"
    GITHUB = "github"          # code file or README from a repo
    GITHUB_ISSUE = "github_issue"
    JIRA = "jira"
    SLACK = "slack"
    EMAIL = "email"
    CONFLUENCE = "confluence"
    GOOGLE_DOC = "google_doc"
    MEETING_TRANSCRIPT = "meeting_transcript"
    DATABASE = "database"


class DocumentStatus(str, enum.Enum):
    """Processing pipeline status of a document."""
    QUEUED = "queued"           # received, awaiting processing
    PARSING = "parsing"         # text extraction in progress
    CHUNKING = "chunking"       # splitting into chunks
    EMBEDDING = "embedding"     # generating embeddings
    INDEXING = "indexing"       # writing to search indexes
    READY = "ready"             # fully processed and searchable
    FAILED = "failed"           # permanent failure
    STALE = "stale"             # source changed, needs re-processing


class DocumentCategory(str, enum.Enum):
    """ML-classified document category (set by document classifier)."""
    TECHNICAL_DOC = "technical_doc"
    POLICY = "policy"
    MEETING_NOTES = "meeting_notes"
    CODE_REVIEW = "code_review"
    INCIDENT_REPORT = "incident_report"
    ANNOUNCEMENT = "announcement"
    KNOWLEDGE_BASE = "knowledge_base"
    SUPPORT_TICKET = "support_ticket"
    OTHER = "other"
    UNKNOWN = "unknown"         # not yet classified


# ─────────────────────────────────────────────────────────────────────────────
# SourceConnector
# ─────────────────────────────────────────────────────────────────────────────

class SourceConnector(UUIDMixin, TimestampMixin, Base):
    """
    A configured data source connection for a tenant.

    Examples:
      - GitHub repo: github.com/company/backend
      - Jira project: PROJ-* tickets
      - Slack workspace channel: #engineering
      - Local folder: /uploads/hr-policies

    The crawler/ingestion workers (owned by friend) use this table
    to know what to crawl and how often.
    """
    __tablename__ = "source_connectors"
    __table_args__ = (
        Index("ix_source_connectors_tenant_id", "tenant_id"),
    )

    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)        # human-readable label
    source_type: Mapped[SourceType] = mapped_column(
        Enum(SourceType, name="source_type"),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Connection config (stored encrypted in production)
    # e.g. {"repo_url": "...", "token": "..."} for GitHub
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Crawl schedule (cron expression, e.g. "0 */6 * * *" = every 6 hours)
    crawl_schedule: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_crawled_at: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # ── Relationships ──────────────────────────────────────────────────────────
    documents: Mapped[list["Document"]] = relationship(
        "Document", back_populates="connector"
    )

    def __repr__(self) -> str:
        return f"<SourceConnector id={self.id} type={self.source_type} tenant={self.tenant_id}>"


# ─────────────────────────────────────────────────────────────────────────────
# Document
# ─────────────────────────────────────────────────────────────────────────────

class Document(UUIDMixin, TimestampMixin, Base):
    """
    One ingested document — a PDF, a GitHub file, a Jira ticket, etc.

    Key design decisions:
    - content_hash enables change detection (reprocess only if hash changed)
    - s3_key stores the raw file path in MinIO/S3 for re-processing
    - permissions is a JSON list of tags used at retrieval time for RBAC
    - category is set by the ML document classifier
    """
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("tenant_id", "source_id", "connector_id", name="uq_doc_tenant_source"),
        Index("ix_documents_tenant_id", "tenant_id"),
        Index("ix_documents_status", "status"),
        Index("ix_documents_source_type", "source_type"),
        Index("ix_documents_content_hash", "content_hash"),
    )

    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    connector_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("source_connectors.id", ondelete="SET NULL"), nullable=True
    )

    # ── Identity ──────────────────────────────────────────────────────────────
    source_id: Mapped[str] = mapped_column(String(500), nullable=False)
    # ^ Original ID in source system (file path, Jira ticket key, GitHub SHA, etc.)

    source_type: Mapped[SourceType] = mapped_column(
        Enum(SourceType, name="source_type", create_constraint=False),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    # ── Content ───────────────────────────────────────────────────────────────
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    # ^ Extracted raw text (may be large; move to S3 for very large docs)

    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # ^ SHA-256 or xxHash of content — used for change detection

    language: Mapped[str] = mapped_column(String(10), default="en", nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    word_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── Storage ───────────────────────────────────────────────────────────────
    s3_key: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    # ^ Path of the raw file in MinIO/S3 — used for re-processing

    # ── ML Outputs ───────────────────────────────────────────────────────────
    category: Mapped[DocumentCategory] = mapped_column(
        Enum(DocumentCategory, name="document_category"),
        default=DocumentCategory.UNKNOWN,
        nullable=False,
    )
    category_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Source-specific metadata (author, repo, project, channel, etc.)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    # RBAC: list of permission tags that control who can see this document
    # Example: ["team:engineering", "level:public", "source:github"]
    # Retriever checks user's permission tags vs this list at query time.
    permissions: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)

    # ── Processing State ─────────────────────────────────────────────────────
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="document_status"),
        default=DocumentStatus.QUEUED,
        nullable=False,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    processing_started_at: Mapped[str | None] = mapped_column(String(50), nullable=True)
    processing_completed_at: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # ── Relationships ──────────────────────────────────────────────────────────
    connector: Mapped["SourceConnector | None"] = relationship(
        "SourceConnector", back_populates="documents"
    )
    chunks: Mapped[list["Chunk"]] = relationship(
        "Chunk", back_populates="document", cascade="all, delete-orphan"
    )
    tags: Mapped[list["DocumentTag"]] = relationship(
        "DocumentTag", back_populates="document", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Document id={self.id} title={self.title[:40]!r} status={self.status}>"


# ─────────────────────────────────────────────────────────────────────────────
# Chunk
# ─────────────────────────────────────────────────────────────────────────────

class Chunk(UUIDMixin, TimestampMixin, Base):
    """
    A text chunk derived from a Document.

    This is the atomic unit for:
    - embedding generation (vector store)
    - BM25 indexing (OpenSearch)
    - retrieval and citation

    The actual embedding vector is stored in Qdrant (not here).
    We store the chunk text + metadata here for citation lookup.
    """
    __tablename__ = "chunks"
    __table_args__ = (
        Index("ix_chunks_document_id", "document_id"),
        Index("ix_chunks_tenant_id", "tenant_id"),
        Index("ix_chunks_qdrant_id", "qdrant_point_id"),
    )

    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    # ^ Denormalized for fast retrieval filtering without JOIN

    # ── Content ───────────────────────────────────────────────────────────────
    text: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    # ^ Position of this chunk within the document (0-indexed)

    char_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # ^ Character offsets in original document content (for highlighting)

    # ── Location Metadata ─────────────────────────────────────────────────────
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    chunk_type: Mapped[str] = mapped_column(
        String(50), default="paragraph", nullable=False
    )
    # ^ paragraph | table | code_block | list | header | image_caption

    # ── Embedding Reference ───────────────────────────────────────────────────
    qdrant_point_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # ^ UUID of the corresponding point in Qdrant vector store

    embedding_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # ^ Which embedding model generated this chunk's vector

    # ── RBAC (inherited from parent document) ─────────────────────────────────
    permissions: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)

    # ── Extra Metadata ────────────────────────────────────────────────────────
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    # ── Relationships ──────────────────────────────────────────────────────────
    document: Mapped["Document"] = relationship("Document", back_populates="chunks")

    def __repr__(self) -> str:
        return f"<Chunk id={self.id} doc={self.document_id} idx={self.chunk_index}>"


# ─────────────────────────────────────────────────────────────────────────────
# DocumentTag
# ─────────────────────────────────────────────────────────────────────────────

class DocumentTag(UUIDMixin, Base):
    """
    Tags applied to a document (by ML classifier or manually).
    Examples: "finance", "incident", "deployment", "api-gateway"
    """
    __tablename__ = "document_tags"
    __table_args__ = (
        UniqueConstraint("document_id", "tag", name="uq_doc_tag"),
        Index("ix_document_tags_document_id", "document_id"),
        Index("ix_document_tags_tag", "tag"),
    )

    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    tag: Mapped[str] = mapped_column(String(100), nullable=False)
    source: Mapped[str] = mapped_column(
        String(50), default="ml", nullable=False
    )
    # ^ "ml" (auto-classified) | "manual" (human-added)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ── Relationships ──────────────────────────────────────────────────────────
    document: Mapped["Document"] = relationship("Document", back_populates="tags")
