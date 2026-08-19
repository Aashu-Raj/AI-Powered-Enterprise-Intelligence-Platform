"""
database/scripts/seed.py

Seed the database with initial test data for development.

Creates:
  - 2 Tenants (Acme Corp, TechStart Inc)
  - 2 Users per tenant
  - Default roles (admin, editor, viewer) per tenant
  - Sample SourceConnectors

Usage:
    python -m database.scripts.seed
    (Run with venv activated from project root)
"""
import asyncio
import uuid
from passlib.context import CryptContext

from sqlalchemy.ext.asyncio import AsyncSession

from database.session import AsyncSessionLocal
from database.models import (
    Chunk,
    Document,
    DocumentCategory,
    DocumentStatus,
    Permission,
    Role,
    RoleType,
    SourceConnector,
    SourceType,
    Tenant,
    TenantStatus,
    User,
    UserRole,
    UserStatus,
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


# ─────────────────────────────────────────────────────────────────────────────
# Seed Data
# ─────────────────────────────────────────────────────────────────────────────

async def seed(session: AsyncSession) -> None:
    print("🌱 Seeding database...")

    # ── Tenant 1: Acme Corp ───────────────────────────────────────────────────
    acme_id = str(uuid.uuid4())
    acme = Tenant(
        id=acme_id,
        name="Acme Corp",
        slug="acme-corp",
        status=TenantStatus.ACTIVE,
        plan="enterprise",
    )
    session.add(acme)

    # ── Tenant 2: TechStart ───────────────────────────────────────────────────
    techstart_id = str(uuid.uuid4())
    techstart = Tenant(
        id=techstart_id,
        name="TechStart Inc",
        slug="techstart-inc",
        status=TenantStatus.TRIAL,
        plan="free",
    )
    session.add(techstart)

    await session.flush()  # flush so FKs resolve

    # ── Roles for Acme ────────────────────────────────────────────────────────
    acme_roles: dict[str, Role] = {}
    for role_type in [RoleType.ADMIN, RoleType.EDITOR, RoleType.VIEWER]:
        role = Role(
            id=str(uuid.uuid4()),
            tenant_id=acme_id,
            name=role_type.value.capitalize(),
            role_type=role_type,
            description=f"Default {role_type.value} role for Acme Corp",
        )
        session.add(role)
        acme_roles[role_type.value] = role

    # ── Permissions for Acme Roles ────────────────────────────────────────────
    await session.flush()

    # Admin gets everything
    for resource, action in [
        ("documents", "read"), ("documents", "write"), ("documents", "admin"),
        ("queries", "run"), ("tenants", "admin"), ("users", "admin"),
    ]:
        session.add(Permission(
            id=str(uuid.uuid4()),
            role_id=acme_roles["admin"].id,
            resource=resource,
            action=action,
            scope="*",
        ))

    # Editor: read + write documents, run queries
    for resource, action in [
        ("documents", "read"), ("documents", "write"),
        ("queries", "run"),
    ]:
        session.add(Permission(
            id=str(uuid.uuid4()),
            role_id=acme_roles["editor"].id,
            resource=resource,
            action=action,
            scope="*",
        ))

    # Viewer: read documents + run queries only
    for resource, action in [("documents", "read"), ("queries", "run")]:
        session.add(Permission(
            id=str(uuid.uuid4()),
            role_id=acme_roles["viewer"].id,
            resource=resource,
            action=action,
            scope="*",
        ))

    # ── Users for Acme ────────────────────────────────────────────────────────
    acme_admin = User(
        id=str(uuid.uuid4()),
        tenant_id=acme_id,
        email="admin@acme.com",
        full_name="Alice Admin",
        hashed_password=hash_password("password123"),
        status=UserStatus.ACTIVE,
        is_superuser=True,
    )
    acme_user = User(
        id=str(uuid.uuid4()),
        tenant_id=acme_id,
        email="engineer@acme.com",
        full_name="Bob Engineer",
        hashed_password=hash_password("password123"),
        status=UserStatus.ACTIVE,
    )
    session.add_all([acme_admin, acme_user])
    await session.flush()

    # Assign roles
    session.add(UserRole(
        id=str(uuid.uuid4()),
        user_id=acme_admin.id,
        role_id=acme_roles["admin"].id,
    ))
    session.add(UserRole(
        id=str(uuid.uuid4()),
        user_id=acme_user.id,
        role_id=acme_roles["editor"].id,
    ))

    # ── Roles for TechStart ────────────────────────────────────────────────────
    ts_roles: dict[str, Role] = {}
    for role_type in [RoleType.ADMIN, RoleType.VIEWER]:
        role = Role(
            id=str(uuid.uuid4()),
            tenant_id=techstart_id,
            name=role_type.value.capitalize(),
            role_type=role_type,
        )
        session.add(role)
        ts_roles[role_type.value] = role

    ts_admin = User(
        id=str(uuid.uuid4()),
        tenant_id=techstart_id,
        email="admin@techstart.io",
        full_name="Carol Founder",
        hashed_password=hash_password("password123"),
        status=UserStatus.ACTIVE,
        is_superuser=True,
    )
    session.add(ts_admin)

    # ── Source Connectors for Acme ────────────────────────────────────────────
    await session.flush()

    connectors = [
        SourceConnector(
            id=str(uuid.uuid4()),
            tenant_id=acme_id,
            name="Acme Backend GitHub Repo",
            source_type=SourceType.GITHUB,
            is_active=True,
            config={
                "repo_url": "https://github.com/acme/backend",
                "branch": "main",
            },
            crawl_schedule="0 */6 * * *",
        ),
        SourceConnector(
            id=str(uuid.uuid4()),
            tenant_id=acme_id,
            name="HR Policy Documents",
            source_type=SourceType.PDF,
            is_active=True,
            config={"folder": "uploads/hr-policies"},
            crawl_schedule="0 0 * * 1",  # weekly
        ),
        SourceConnector(
            id=str(uuid.uuid4()),
            tenant_id=acme_id,
            name="Jira Engineering Board",
            source_type=SourceType.JIRA,
            is_active=True,
            config={
                "base_url": "https://acme.atlassian.net",
                "project_key": "ENG",
            },
            crawl_schedule="0 */2 * * *",
        ),
    ]
    session.add_all(connectors)

    await session.flush()

    # ── Sample Document (for testing retrieval) ────────────────────────────────
    sample_doc = Document(
        id=str(uuid.uuid4()),
        tenant_id=acme_id,
        connector_id=connectors[0].id,
        source_id="acme/backend/README.md@main",
        source_type=SourceType.GITHUB,
        title="Backend Service README",
        source_url="https://github.com/acme/backend/blob/main/README.md",
        content="This is the backend service for Acme Corp. It handles payment processing, user authentication, and order management.",
        content_hash="abc123def456",
        language="en",
        word_count=200,
        category=DocumentCategory.TECHNICAL_DOC,
        category_confidence=0.95,
        status=DocumentStatus.READY,
        permissions=["team:engineering", "level:internal"],
        metadata_={"repo": "acme/backend", "branch": "main", "author": "Bob Engineer"},
    )
    session.add(sample_doc)
    await session.flush()

    # Sample chunk
    sample_chunk = Chunk(
        id=str(uuid.uuid4()),
        document_id=sample_doc.id,
        tenant_id=acme_id,
        text="This is the backend service for Acme Corp. It handles payment processing, user authentication, and order management.",
        chunk_index=0,
        char_start=0,
        char_end=120,
        page_number=1,
        section_title="Overview",
        chunk_type="paragraph",
        embedding_model="all-MiniLM-L6-v2",
        permissions=["team:engineering", "level:internal"],
    )
    session.add(sample_chunk)

    await session.commit()
    print("✅ Seed complete!")
    print("\nTest credentials:")
    print("  Tenant: Acme Corp")
    print("  Admin:    admin@acme.com / password123")
    print("  Engineer: engineer@acme.com / password123")
    print("\n  Tenant: TechStart Inc")
    print("  Admin:    admin@techstart.io / password123")


async def main() -> None:
    async with AsyncSessionLocal() as session:
        await seed(session)


if __name__ == "__main__":
    asyncio.run(main())
