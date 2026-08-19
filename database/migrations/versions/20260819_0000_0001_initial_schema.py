"""initial_schema

Revision ID: 0001
Revises:
Create Date: 2026-08-19 00:00:00.000000 UTC

Creates all 13 tables for the Enterprise Intelligence Platform:
  - tenants, users, roles, user_roles, permissions (multi-tenancy + RBAC)
  - source_connectors, documents, chunks, document_tags (document layer)
  - queries, search_results, feedback, query_events (query + evaluation layer)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── ENUMS ────────────────────────────────────────────────────────────────
    tenant_status = sa.Enum("active", "suspended", "trial", name="tenant_status")
    user_status = sa.Enum("active", "inactive", "pending", name="user_status")
    role_type = sa.Enum("admin", "editor", "viewer", "api_key", name="role_type")
    source_type = sa.Enum(
        "pdf", "docx", "pptx", "txt", "html",
        "github", "github_issue", "jira", "slack", "email",
        "confluence", "google_doc", "meeting_transcript", "database",
        name="source_type",
    )
    document_status = sa.Enum(
        "queued", "parsing", "chunking", "embedding", "indexing",
        "ready", "failed", "stale",
        name="document_status",
    )
    document_category = sa.Enum(
        "technical_doc", "policy", "meeting_notes", "code_review",
        "incident_report", "announcement", "knowledge_base",
        "support_ticket", "other", "unknown",
        name="document_category",
    )
    query_type = sa.Enum(
        "factual", "exploratory", "debugging", "comparison",
        "aggregation", "unknown",
        name="query_type",
    )
    query_status = sa.Enum(
        "pending", "processing", "completed", "failed", "timeout",
        name="query_status",
    )
    feedback_type = sa.Enum(
        "thumbs_up", "thumbs_down", "rating", "correction",
        name="feedback_type",
    )

    # Create enums first (PostgreSQL requires this)
    for enum in [
        tenant_status, user_status, role_type, source_type,
        document_status, document_category, query_type, query_status, feedback_type,
    ]:
        enum.create(op.get_bind(), checkfirst=True)

    # ── TENANTS ───────────────────────────────────────────────────────────────
    op.create_table(
        "tenants",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False, unique=True),
        sa.Column("status", sa.Enum("active", "suspended", "trial", name="tenant_status", create_constraint=False), nullable=False, server_default="trial"),
        sa.Column("plan", sa.String(50), nullable=False, server_default="free"),
        sa.Column("settings", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    # ── USERS ─────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("status", sa.Enum("active", "inactive", "pending", name="user_status", create_constraint=False), nullable=False, server_default="pending"),
        sa.Column("avatar_url", sa.String(500), nullable=True),
        sa.Column("is_superuser", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"])
    op.create_index("ix_users_email", "users", ["email"])
    op.create_unique_constraint("uq_user_tenant_email", "users", ["tenant_id", "email"])

    # ── ROLES ─────────────────────────────────────────────────────────────────
    op.create_table(
        "roles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("role_type", sa.Enum("admin", "editor", "viewer", "api_key", name="role_type", create_constraint=False), nullable=False, server_default="viewer"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_roles_tenant_id", "roles", ["tenant_id"])
    op.create_unique_constraint("uq_role_tenant_name", "roles", ["tenant_id", "name"])

    # ── USER_ROLES ─────────────────────────────────────────────────────────────
    op.create_table(
        "user_roles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role_id", sa.String(36), sa.ForeignKey("roles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_user_roles_user_id", "user_roles", ["user_id"])
    op.create_index("ix_user_roles_role_id", "user_roles", ["role_id"])
    op.create_unique_constraint("uq_user_role", "user_roles", ["user_id", "role_id"])

    # ── PERMISSIONS ────────────────────────────────────────────────────────────
    op.create_table(
        "permissions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("role_id", sa.String(36), sa.ForeignKey("roles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resource", sa.String(100), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("scope", sa.String(255), nullable=False, server_default="*"),
    )
    op.create_index("ix_permissions_role_id", "permissions", ["role_id"])

    # ── SOURCE_CONNECTORS ──────────────────────────────────────────────────────
    op.create_table(
        "source_connectors",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("source_type", sa.Enum(
            "pdf", "docx", "pptx", "txt", "html", "github", "github_issue",
            "jira", "slack", "email", "confluence", "google_doc",
            "meeting_transcript", "database", name="source_type", create_constraint=False,
        ), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("config", sa.JSON, nullable=True),
        sa.Column("crawl_schedule", sa.String(100), nullable=True),
        sa.Column("last_crawled_at", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_source_connectors_tenant_id", "source_connectors", ["tenant_id"])

    # ── DOCUMENTS ─────────────────────────────────────────────────────────────
    op.create_table(
        "documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connector_id", sa.String(36), sa.ForeignKey("source_connectors.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_id", sa.String(500), nullable=False),
        sa.Column("source_type", sa.Enum(
            "pdf", "docx", "pptx", "txt", "html", "github", "github_issue",
            "jira", "slack", "email", "confluence", "google_doc",
            "meeting_transcript", "database", name="source_type", create_constraint=False,
        ), nullable=False),
        sa.Column("title", sa.String(1000), nullable=False),
        sa.Column("source_url", sa.String(2000), nullable=True),
        sa.Column("content", sa.Text, nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("language", sa.String(10), nullable=False, server_default="en"),
        sa.Column("file_size_bytes", sa.BigInteger, nullable=True),
        sa.Column("page_count", sa.Integer, nullable=True),
        sa.Column("word_count", sa.Integer, nullable=True),
        sa.Column("s3_key", sa.String(1000), nullable=True),
        sa.Column("category", sa.Enum(
            "technical_doc", "policy", "meeting_notes", "code_review",
            "incident_report", "announcement", "knowledge_base",
            "support_ticket", "other", "unknown",
            name="document_category", create_constraint=False,
        ), nullable=False, server_default="unknown"),
        sa.Column("category_confidence", sa.Float, nullable=True),
        sa.Column("metadata", sa.JSON, nullable=True),
        sa.Column("permissions", sa.JSON, nullable=True),
        sa.Column("status", sa.Enum(
            "queued", "parsing", "chunking", "embedding", "indexing",
            "ready", "failed", "stale", name="document_status", create_constraint=False,
        ), nullable=False, server_default="queued"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("processing_started_at", sa.String(50), nullable=True),
        sa.Column("processing_completed_at", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_documents_tenant_id", "documents", ["tenant_id"])
    op.create_index("ix_documents_status", "documents", ["status"])
    op.create_index("ix_documents_source_type", "documents", ["source_type"])
    op.create_index("ix_documents_content_hash", "documents", ["content_hash"])
    op.create_unique_constraint("uq_doc_tenant_source", "documents", ["tenant_id", "source_id", "connector_id"])

    # ── CHUNKS ────────────────────────────────────────────────────────────────
    op.create_table(
        "chunks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("char_start", sa.Integer, nullable=True),
        sa.Column("char_end", sa.Integer, nullable=True),
        sa.Column("page_number", sa.Integer, nullable=True),
        sa.Column("section_title", sa.String(500), nullable=True),
        sa.Column("chunk_type", sa.String(50), nullable=False, server_default="paragraph"),
        sa.Column("qdrant_point_id", sa.String(36), nullable=True),
        sa.Column("embedding_model", sa.String(100), nullable=True),
        sa.Column("permissions", sa.JSON, nullable=True),
        sa.Column("metadata", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_chunks_document_id", "chunks", ["document_id"])
    op.create_index("ix_chunks_tenant_id", "chunks", ["tenant_id"])
    op.create_index("ix_chunks_qdrant_id", "chunks", ["qdrant_point_id"])

    # ── DOCUMENT_TAGS ──────────────────────────────────────────────────────────
    op.create_table(
        "document_tags",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tag", sa.String(100), nullable=False),
        sa.Column("source", sa.String(50), nullable=False, server_default="ml"),
        sa.Column("confidence", sa.Float, nullable=True),
    )
    op.create_index("ix_document_tags_document_id", "document_tags", ["document_id"])
    op.create_index("ix_document_tags_tag", "document_tags", ["tag"])
    op.create_unique_constraint("uq_doc_tag", "document_tags", ["document_id", "tag"])

    # ── QUERIES ───────────────────────────────────────────────────────────────
    op.create_table(
        "queries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("query_text", sa.Text, nullable=False),
        sa.Column("query_type", sa.Enum(
            "factual", "exploratory", "debugging", "comparison",
            "aggregation", "unknown", name="query_type", create_constraint=False,
        ), nullable=False, server_default="unknown"),
        sa.Column("conversation_id", sa.String(36), nullable=True),
        sa.Column("turn_index", sa.Integer, nullable=False, server_default="0"),
        sa.Column("filters", sa.JSON, nullable=True),
        sa.Column("answer", sa.Text, nullable=True),
        sa.Column("answer_confidence", sa.Float, nullable=True),
        sa.Column("citations", sa.JSON, nullable=True),
        sa.Column("status", sa.Enum(
            "pending", "processing", "completed", "failed", "timeout",
            name="query_status", create_constraint=False,
        ), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("embedding_latency_ms", sa.Float, nullable=True),
        sa.Column("retrieval_latency_ms", sa.Float, nullable=True),
        sa.Column("reranking_latency_ms", sa.Float, nullable=True),
        sa.Column("llm_latency_ms", sa.Float, nullable=True),
        sa.Column("total_latency_ms", sa.Float, nullable=True),
        sa.Column("llm_model", sa.String(100), nullable=True),
        sa.Column("prompt_tokens", sa.Integer, nullable=True),
        sa.Column("completion_tokens", sa.Integer, nullable=True),
        sa.Column("total_tokens", sa.Integer, nullable=True),
        sa.Column("num_candidates", sa.Integer, nullable=True),
        sa.Column("num_results", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_queries_tenant_id", "queries", ["tenant_id"])
    op.create_index("ix_queries_user_id", "queries", ["user_id"])
    op.create_index("ix_queries_status", "queries", ["status"])
    op.create_index("ix_queries_created_at", "queries", ["created_at"])

    # ── SEARCH_RESULTS ─────────────────────────────────────────────────────────
    op.create_table(
        "search_results",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("query_id", sa.String(36), sa.ForeignKey("queries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("chunk_id", sa.String(36), nullable=True),
        sa.Column("rank", sa.Integer, nullable=False),
        sa.Column("bm25_score", sa.Float, nullable=True),
        sa.Column("vector_score", sa.Float, nullable=True),
        sa.Column("reranker_score", sa.Float, nullable=True),
        sa.Column("final_score", sa.Float, nullable=True),
        sa.Column("was_clicked", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("dwell_time_seconds", sa.Float, nullable=True),
        sa.Column("was_cited", sa.Boolean, nullable=False, server_default="false"),
    )
    op.create_index("ix_search_results_query_id", "search_results", ["query_id"])
    op.create_index("ix_search_results_document_id", "search_results", ["document_id"])

    # ── FEEDBACK ──────────────────────────────────────────────────────────────
    op.create_table(
        "feedback",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("query_id", sa.String(36), sa.ForeignKey("queries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("feedback_type", sa.Enum(
            "thumbs_up", "thumbs_down", "rating", "correction",
            name="feedback_type", create_constraint=False,
        ), nullable=False),
        sa.Column("rating", sa.Integer, nullable=True),
        sa.Column("comment", sa.Text, nullable=True),
        sa.Column("corrected_answer", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_feedback_query_id", "feedback", ["query_id"])
    op.create_index("ix_feedback_user_id", "feedback", ["user_id"])

    # ── QUERY_EVENTS ───────────────────────────────────────────────────────────
    op.create_table(
        "query_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("query_id", sa.String(36), sa.ForeignKey("queries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_date", sa.String(50), nullable=True),
        sa.Column("event_type", sa.String(100), nullable=True),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("source_document_id", sa.String(36), nullable=True),
        sa.Column("entities", sa.JSON, nullable=True),
    )
    op.create_index("ix_query_events_query_id", "query_events", ["query_id"])


def downgrade() -> None:
    # Drop tables in reverse FK order
    op.drop_table("query_events")
    op.drop_table("feedback")
    op.drop_table("search_results")
    op.drop_table("queries")
    op.drop_table("document_tags")
    op.drop_table("chunks")
    op.drop_table("documents")
    op.drop_table("source_connectors")
    op.drop_table("permissions")
    op.drop_table("user_roles")
    op.drop_table("roles")
    op.drop_table("users")
    op.drop_table("tenants")

    # Drop enums
    for enum_name in [
        "feedback_type", "query_status", "query_type",
        "document_category", "document_status", "source_type",
        "role_type", "user_status", "tenant_status",
    ]:
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
