"""
database/models/__init__.py

Central import point for all SQLAlchemy models.
Import from here so Alembic autogenerate can discover all tables.
"""
from database.models.document import (
    Chunk,
    Document,
    DocumentCategory,
    DocumentStatus,
    DocumentTag,
    SourceConnector,
    SourceType,
)
from database.models.query import (
    Feedback,
    FeedbackType,
    Query,
    QueryEvent,
    QueryStatus,
    QueryType,
    SearchResult,
)
from database.models.tenant import (
    Permission,
    Role,
    RoleType,
    Tenant,
    TenantStatus,
    User,
    UserRole,
    UserStatus,
)

__all__ = [
    # Tenant / Auth
    "Tenant", "TenantStatus",
    "User", "UserStatus",
    "Role", "RoleType",
    "UserRole",
    "Permission",
    # Documents
    "SourceConnector", "SourceType",
    "Document", "DocumentStatus", "DocumentCategory",
    "Chunk",
    "DocumentTag",
    # Queries
    "Query", "QueryType", "QueryStatus",
    "SearchResult",
    "Feedback", "FeedbackType",
    "QueryEvent",
]
