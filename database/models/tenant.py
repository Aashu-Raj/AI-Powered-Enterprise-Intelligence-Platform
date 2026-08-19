"""
database/models/tenant.py

Tenant and User models — the foundation of multi-tenancy and RBAC.

Tables:
  tenants        → company / organization accounts
  users          → employees within a tenant
  roles          → named permission bundles (admin, editor, viewer, ...)
  user_roles     → M2M: which user has which role(s)
  permissions    → fine-grained permission entries per role
"""
import enum

from sqlalchemy import (
    Boolean,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base, TimestampMixin, UUIDMixin


# ─────────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────────

class TenantStatus(str, enum.Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    TRIAL = "trial"


class UserStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"          # email not yet verified


class RoleType(str, enum.Enum):
    ADMIN = "admin"              # full access
    EDITOR = "editor"           # can upload / manage documents
    VIEWER = "viewer"           # read-only search
    API_KEY = "api_key"         # service account


# ─────────────────────────────────────────────────────────────────────────────
# Tenant
# ─────────────────────────────────────────────────────────────────────────────

class Tenant(UUIDMixin, TimestampMixin, Base):
    """
    Represents a company / organization.

    All data (documents, users, embeddings) is scoped to a tenant.
    tenant_id is passed through every query to enforce isolation.
    """
    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    status: Mapped[TenantStatus] = mapped_column(
        Enum(TenantStatus, name="tenant_status"),
        default=TenantStatus.TRIAL,
        nullable=False,
    )
    plan: Mapped[str] = mapped_column(String(50), default="free", nullable=False)

    # Settings stored as JSON-like text (use JSON column in Postgres)
    # e.g. {"max_documents": 10000, "allowed_sources": ["pdf", "github"]}
    settings: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Relationships ──────────────────────────────────────────────────────────
    users: Mapped[list["User"]] = relationship(
        "User", back_populates="tenant", cascade="all, delete-orphan"
    )
    roles: Mapped[list["Role"]] = relationship(
        "Role", back_populates="tenant", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Tenant id={self.id} slug={self.slug} status={self.status}>"


# ─────────────────────────────────────────────────────────────────────────────
# User
# ─────────────────────────────────────────────────────────────────────────────

class User(UUIDMixin, TimestampMixin, Base):
    """
    A user belongs to exactly one Tenant.
    Authentication: email + hashed password (JWT issued by API layer).
    Authorization: via UserRole → Role → Permission chain.
    """
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_user_tenant_email"),
        Index("ix_users_tenant_id", "tenant_id"),
        Index("ix_users_email", "email"),
    )

    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, name="user_status"),
        default=UserStatus.PENDING,
        nullable=False,
    )
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # ── Relationships ──────────────────────────────────────────────────────────
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="users")
    user_roles: Mapped[list["UserRole"]] = relationship(
        "UserRole", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email} tenant={self.tenant_id}>"


# ─────────────────────────────────────────────────────────────────────────────
# Role
# ─────────────────────────────────────────────────────────────────────────────

class Role(UUIDMixin, TimestampMixin, Base):
    """
    Named bundle of permissions within a tenant.
    Each tenant can have custom roles on top of the default ones.
    """
    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_role_tenant_name"),
        Index("ix_roles_tenant_id", "tenant_id"),
    )

    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    role_type: Mapped[RoleType] = mapped_column(
        Enum(RoleType, name="role_type"),
        default=RoleType.VIEWER,
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Relationships ──────────────────────────────────────────────────────────
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="roles")
    user_roles: Mapped[list["UserRole"]] = relationship(
        "UserRole", back_populates="role", cascade="all, delete-orphan"
    )
    permissions: Mapped[list["Permission"]] = relationship(
        "Permission", back_populates="role", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Role id={self.id} name={self.name} type={self.role_type}>"


# ─────────────────────────────────────────────────────────────────────────────
# UserRole (M2M join table)
# ─────────────────────────────────────────────────────────────────────────────

class UserRole(UUIDMixin, TimestampMixin, Base):
    """Association table: which users have which roles."""
    __tablename__ = "user_roles"
    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="uq_user_role"),
        Index("ix_user_roles_user_id", "user_id"),
        Index("ix_user_roles_role_id", "role_id"),
    )

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False
    )

    # ── Relationships ──────────────────────────────────────────────────────────
    user: Mapped["User"] = relationship("User", back_populates="user_roles")
    role: Mapped["Role"] = relationship("Role", back_populates="user_roles")


# ─────────────────────────────────────────────────────────────────────────────
# Permission
# ─────────────────────────────────────────────────────────────────────────────

class Permission(UUIDMixin, Base):
    """
    Fine-grained permission entry attached to a Role.

    Examples:
      resource="documents", action="read",  scope="*"
      resource="documents", action="write", scope="source:github"
      resource="queries",   action="run",   scope="*"
      resource="tenants",   action="admin", scope="*"
    """
    __tablename__ = "permissions"
    __table_args__ = (
        Index("ix_permissions_role_id", "role_id"),
    )

    role_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False
    )
    resource: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)   # read | write | admin | run
    scope: Mapped[str] = mapped_column(String(255), default="*", nullable=False)

    # ── Relationships ──────────────────────────────────────────────────────────
    role: Mapped["Role"] = relationship("Role", back_populates="permissions")

    def __repr__(self) -> str:
        return f"<Permission role={self.role_id} {self.resource}:{self.action}:{self.scope}>"
