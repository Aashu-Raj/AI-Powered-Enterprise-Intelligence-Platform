"""
database/vector_store/qdrant_client.py

Qdrant vector store client — manages collections and vector operations.

Design:
  - Each tenant gets its own Qdrant collection: enterprise_{tenant_id}
  - Every point stores the embedding + metadata (chunk_id, doc_id, permissions)
  - Permissions are stored as payload fields and filtered at query time
    → RBAC is enforced INSIDE the vector search (not post-filtering)
"""
import uuid
from typing import Any

from loguru import logger
from qdrant_client import AsyncQdrantClient
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    MatchValue,
    PointStruct,
    ScoredPoint,
    VectorParams,
)

from shared.config.settings import settings


class QdrantStore:
    """
    Async Qdrant client wrapper.

    Usage:
        store = QdrantStore()
        await store.init()                          # call once at startup

        # Upsert embeddings
        await store.upsert_chunks(tenant_id, chunks_with_embeddings)

        # Search
        results = await store.search(
            tenant_id, query_vector, user_permissions, top_k=20
        )
    """

    def __init__(self) -> None:
        self._client: AsyncQdrantClient | None = None

    async def init(self) -> None:
        """Initialize the async Qdrant client connection."""
        kwargs: dict[str, Any] = {
            "host": settings.qdrant_host,
            "port": settings.qdrant_port,
            "prefer_grpc": False,
        }
        if settings.qdrant_api_key:
            kwargs["api_key"] = settings.qdrant_api_key

        self._client = AsyncQdrantClient(**kwargs)
        logger.info(f"Qdrant connected at {settings.qdrant_host}:{settings.qdrant_port}")

    async def close(self) -> None:
        if self._client:
            await self._client.close()

    @property
    def client(self) -> AsyncQdrantClient:
        if self._client is None:
            raise RuntimeError("QdrantStore not initialized. Call await store.init() first.")
        return self._client

    # ── Collection Management ─────────────────────────────────────────────────

    def _collection_name(self, tenant_id: str) -> str:
        """Each tenant gets an isolated collection."""
        return f"{settings.qdrant_collection_prefix}_{tenant_id}"

    async def create_tenant_collection(self, tenant_id: str) -> None:
        """
        Create a Qdrant collection for a tenant if it doesn't exist.
        Called when a new tenant is onboarded.
        """
        collection_name = self._collection_name(tenant_id)
        existing = await self.client.collection_exists(collection_name)
        if existing:
            logger.debug(f"Collection '{collection_name}' already exists, skipping.")
            return

        await self.client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=settings.embedding_dim,
                distance=Distance.COSINE,
            ),
        )
        logger.info(f"Created Qdrant collection: '{collection_name}'")

    async def delete_tenant_collection(self, tenant_id: str) -> None:
        """Delete all vectors for a tenant (used when tenant is removed)."""
        collection_name = self._collection_name(tenant_id)
        await self.client.delete_collection(collection_name)
        logger.info(f"Deleted Qdrant collection: '{collection_name}'")

    # ── Upsert ────────────────────────────────────────────────────────────────

    async def upsert_chunks(
        self,
        tenant_id: str,
        chunks: list[dict],
    ) -> None:
        """
        Upsert chunk embeddings into Qdrant.

        Args:
            tenant_id: Tenant identifier.
            chunks: List of dicts with keys:
                - chunk_id (str): UUID of the chunk in PostgreSQL
                - embedding (list[float]): Embedding vector
                - document_id (str)
                - text (str): Chunk text (stored as payload for context)
                - permissions (list[str]): RBAC tags
                - metadata (dict): Any extra metadata
        """
        collection_name = self._collection_name(tenant_id)
        points = []

        for chunk in chunks:
            point_id = str(uuid.uuid4())
            payload = {
                "chunk_id": chunk["chunk_id"],
                "document_id": chunk["document_id"],
                "tenant_id": tenant_id,
                "text": chunk.get("text", ""),
                "permissions": chunk.get("permissions", []),
                **chunk.get("metadata", {}),
            }
            points.append(
                PointStruct(
                    id=point_id,
                    vector=chunk["embedding"],
                    payload=payload,
                )
            )

        await self.client.upsert(
            collection_name=collection_name,
            points=points,
            wait=True,  # wait for indexing to complete
        )
        logger.debug(f"Upserted {len(points)} vectors into '{collection_name}'")

    async def delete_document_chunks(self, tenant_id: str, document_id: str) -> None:
        """
        Delete all vectors for a specific document.
        Called before re-ingesting an updated document.
        """
        collection_name = self._collection_name(tenant_id)
        await self.client.delete(
            collection_name=collection_name,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="document_id",
                        match=MatchValue(value=document_id),
                    )
                ]
            ),
        )
        logger.debug(f"Deleted vectors for document '{document_id}' from '{collection_name}'")

    # ── Search ────────────────────────────────────────────────────────────────

    async def search(
        self,
        tenant_id: str,
        query_vector: list[float],
        user_permissions: list[str],
        top_k: int = 20,
        filters: dict | None = None,
    ) -> list[dict]:
        """
        Vector similarity search with RBAC permission filtering.

        Permission filtering happens INSIDE Qdrant — only documents whose
        permissions overlap with user_permissions are returned.
        This ensures authorization at retrieval time, not post-processing.

        Args:
            tenant_id: Tenant to search within.
            query_vector: Embedded query vector.
            user_permissions: Tags the user has access to (e.g. ["team:eng", "level:public"]).
            top_k: Number of results to return.
            filters: Optional extra filters (source_type, date_range, etc.)

        Returns:
            List of dicts with chunk metadata and scores.
        """
        collection_name = self._collection_name(tenant_id)

        # Build permission filter — user must have at least one matching permission
        must_conditions = []
        if user_permissions:
            must_conditions.append(
                FieldCondition(
                    key="permissions",
                    match=MatchAny(any=user_permissions),
                )
            )

        # Add optional extra filters (e.g., source_type="github")
        if filters:
            for key, value in filters.items():
                must_conditions.append(
                    FieldCondition(
                        key=key,
                        match=MatchValue(value=value),
                    )
                )

        query_filter = Filter(must=must_conditions) if must_conditions else None

        results: list[ScoredPoint] = await self.client.search(
            collection_name=collection_name,
            query_vector=query_vector,
            query_filter=query_filter,
            limit=top_k,
            with_payload=True,
            with_vectors=False,
        )

        return [
            {
                "qdrant_point_id": str(r.id),
                "chunk_id": r.payload.get("chunk_id"),
                "document_id": r.payload.get("document_id"),
                "text": r.payload.get("text", ""),
                "vector_score": r.score,
                "payload": r.payload,
            }
            for r in results
        ]

    async def health_check(self) -> bool:
        """Return True if Qdrant is reachable."""
        try:
            await self.client.get_collections()
            return True
        except Exception as e:
            logger.error(f"Qdrant health check failed: {e}")
            return False


# ── Singleton ─────────────────────────────────────────────────────────────────
qdrant_store = QdrantStore()
