"""
database/search_index/opensearch_client.py

OpenSearch client for BM25 full-text search.

Design:
  - Each tenant gets its own index: enterprise_docs_{tenant_id}
  - Documents are indexed at the CHUNK level (same as vector store)
  - Permissions stored in the index document → filtered at query time (RBAC)
  - Custom analyzer with English stemming + stop words for better BM25 recall
"""
from typing import Any

from loguru import logger
from opensearchpy._async.client import AsyncOpenSearch
from opensearchpy.exceptions import NotFoundError

from shared.config.settings import settings


# ── Index Mapping Template ────────────────────────────────────────────────────

CHUNK_INDEX_MAPPING = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,  # 0 for single-node dev; set to 1 in production
        "analysis": {
            "analyzer": {
                "enterprise_analyzer": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": [
                        "lowercase",
                        "english_stop",
                        "english_stemmer",
                        "asciifolding",
                    ],
                }
            },
            "filter": {
                "english_stop": {
                    "type": "stop",
                    "stopwords": "_english_",
                },
                "english_stemmer": {
                    "type": "stemmer",
                    "language": "english",
                },
            },
        },
    },
    "mappings": {
        "properties": {
            # ── Identifiers ───────────────────────────────────────────────────
            "chunk_id": {"type": "keyword"},
            "document_id": {"type": "keyword"},
            "tenant_id": {"type": "keyword"},
            # ── Searchable content ────────────────────────────────────────────
            "text": {
                "type": "text",
                "analyzer": "enterprise_analyzer",
                "fields": {
                    "keyword": {"type": "keyword", "ignore_above": 512},
                },
            },
            "title": {
                "type": "text",
                "analyzer": "enterprise_analyzer",
                "boost": 2.0,   # title matches weighted 2x
                "fields": {
                    "keyword": {"type": "keyword", "ignore_above": 512},
                },
            },
            # ── Metadata ──────────────────────────────────────────────────────
            "source_type": {"type": "keyword"},
            "chunk_type": {"type": "keyword"},
            "page_number": {"type": "integer"},
            "chunk_index": {"type": "integer"},
            "language": {"type": "keyword"},
            "category": {"type": "keyword"},
            "tags": {"type": "keyword"},
            # ── RBAC ──────────────────────────────────────────────────────────
            "permissions": {"type": "keyword"},
            # ── Dates ────────────────────────────────────────────────────────
            "created_at": {"type": "date"},
            "updated_at": {"type": "date"},
            # ── Source-specific ───────────────────────────────────────────────
            "source_url": {"type": "keyword", "index": False},
            "author": {"type": "keyword"},
            "repo": {"type": "keyword"},
            "jira_project": {"type": "keyword"},
            "slack_channel": {"type": "keyword"},
        }
    },
}


class OpenSearchIndex:
    """
    Async OpenSearch client wrapper for BM25 full-text search.

    Usage:
        idx = OpenSearchIndex()
        await idx.init()

        # Index chunks
        await idx.index_chunks(tenant_id, chunks)

        # BM25 search
        results = await idx.search(tenant_id, query_text, user_permissions, top_k=50)
    """

    def __init__(self) -> None:
        self._client: AsyncOpenSearch | None = None

    async def init(self) -> None:
        """Initialize the async OpenSearch client."""
        self._client = AsyncOpenSearch(
            hosts=[{
                "host": settings.opensearch_host,
                "port": settings.opensearch_port,
            }],
            http_auth=(settings.opensearch_user, settings.opensearch_password),
            use_ssl=settings.opensearch_use_ssl,
            verify_certs=False,
            ssl_show_warn=False,
        )
        logger.info(
            f"OpenSearch connected at {settings.opensearch_host}:{settings.opensearch_port}"
        )

    async def close(self) -> None:
        if self._client:
            await self._client.close()

    @property
    def client(self) -> AsyncOpenSearch:
        if self._client is None:
            raise RuntimeError("OpenSearchIndex not initialized. Call await idx.init() first.")
        return self._client

    # ── Index Management ──────────────────────────────────────────────────────

    def _index_name(self, tenant_id: str) -> str:
        return f"{settings.opensearch_index_prefix}_{tenant_id}"

    async def create_tenant_index(self, tenant_id: str) -> None:
        """Create the BM25 index for a tenant if it doesn't exist."""
        index_name = self._index_name(tenant_id)
        exists = await self.client.indices.exists(index=index_name)
        if exists:
            logger.debug(f"Index '{index_name}' already exists, skipping.")
            return

        await self.client.indices.create(
            index=index_name,
            body=CHUNK_INDEX_MAPPING,
        )
        logger.info(f"Created OpenSearch index: '{index_name}'")

    async def delete_tenant_index(self, tenant_id: str) -> None:
        """Delete the entire index for a tenant."""
        index_name = self._index_name(tenant_id)
        try:
            await self.client.indices.delete(index=index_name)
            logger.info(f"Deleted OpenSearch index: '{index_name}'")
        except NotFoundError:
            logger.debug(f"Index '{index_name}' not found, nothing to delete.")

    # ── Indexing ──────────────────────────────────────────────────────────────

    async def index_chunks(self, tenant_id: str, chunks: list[dict]) -> None:
        """
        Index chunk documents into OpenSearch.

        Args:
            tenant_id: Tenant identifier.
            chunks: List of dicts with chunk data. Expected keys:
                chunk_id, document_id, text, title, source_type,
                chunk_type, permissions, metadata, ...
        """
        index_name = self._index_name(tenant_id)
        operations: list[dict] = []

        for chunk in chunks:
            # Bulk API: alternating action + document pairs
            operations.append({
                "index": {
                    "_index": index_name,
                    "_id": chunk["chunk_id"],  # use chunk_id as OpenSearch doc ID
                }
            })
            operations.append({
                "chunk_id": chunk["chunk_id"],
                "document_id": chunk["document_id"],
                "tenant_id": tenant_id,
                "text": chunk.get("text", ""),
                "title": chunk.get("title", ""),
                "source_type": chunk.get("source_type", ""),
                "chunk_type": chunk.get("chunk_type", "paragraph"),
                "page_number": chunk.get("page_number"),
                "chunk_index": chunk.get("chunk_index", 0),
                "language": chunk.get("language", "en"),
                "category": chunk.get("category", "unknown"),
                "tags": chunk.get("tags", []),
                "permissions": chunk.get("permissions", []),
                "created_at": chunk.get("created_at"),
                "updated_at": chunk.get("updated_at"),
                "source_url": chunk.get("source_url"),
                "author": chunk.get("author"),
                "repo": chunk.get("repo"),
                "jira_project": chunk.get("jira_project"),
                "slack_channel": chunk.get("slack_channel"),
            })

        if operations:
            response = await self.client.bulk(body=operations, refresh=True)
            errors = [item for item in response["items"] if "error" in item.get("index", {})]
            if errors:
                logger.error(f"Bulk index errors: {errors}")
            else:
                logger.debug(f"Indexed {len(chunks)} chunks into '{index_name}'")

    async def delete_document_chunks(self, tenant_id: str, document_id: str) -> None:
        """Delete all chunks for a document from the index (for incremental re-ingestion)."""
        index_name = self._index_name(tenant_id)
        await self.client.delete_by_query(
            index=index_name,
            body={
                "query": {"term": {"document_id": document_id}}
            },
            refresh=True,
        )
        logger.debug(f"Deleted OpenSearch chunks for document '{document_id}'")

    # ── BM25 Search ───────────────────────────────────────────────────────────

    async def search(
        self,
        tenant_id: str,
        query_text: str,
        user_permissions: list[str],
        top_k: int = 50,
        filters: dict[str, Any] | None = None,
    ) -> list[dict]:
        """
        BM25 full-text search with RBAC permission filtering.

        Uses multi-match across text (title boosted 2x) with permission
        filtering applied as a filter clause (not affecting relevance score).

        Args:
            tenant_id: Tenant to search within.
            query_text: Natural language query.
            user_permissions: Tags the user has access to.
            top_k: Max results to return.
            filters: Optional extra filters (source_type, date_range, etc.)

        Returns:
            List of dicts with chunk data and BM25 scores.
        """
        index_name = self._index_name(tenant_id)

        # Build filter clauses (RBAC + optional extra filters)
        filter_clauses: list[dict] = []
        if user_permissions:
            filter_clauses.append({"terms": {"permissions": user_permissions}})
        if filters:
            if source_type := filters.get("source_type"):
                filter_clauses.append({"term": {"source_type": source_type}})
            if date_from := filters.get("date_from"):
                filter_clauses.append({"range": {"created_at": {"gte": date_from}}})
            if date_to := filters.get("date_to"):
                filter_clauses.append({"range": {"created_at": {"lte": date_to}}})
            if category := filters.get("category"):
                filter_clauses.append({"term": {"category": category}})

        body = {
            "size": top_k,
            "query": {
                "bool": {
                    "must": [
                        {
                            "multi_match": {
                                "query": query_text,
                                "fields": ["text", "title^2"],
                                "type": "best_fields",
                                "fuzziness": "AUTO",
                            }
                        }
                    ],
                    "filter": filter_clauses,
                }
            },
            "_source": True,
        }

        response = await self.client.search(index=index_name, body=body)
        hits = response["hits"]["hits"]

        return [
            {
                "chunk_id": hit["_source"]["chunk_id"],
                "document_id": hit["_source"]["document_id"],
                "text": hit["_source"].get("text", ""),
                "bm25_score": hit["_score"],
                "source": hit["_source"],
            }
            for hit in hits
        ]

    async def health_check(self) -> bool:
        """Return True if OpenSearch is reachable."""
        try:
            health = await self.client.cluster.health()
            return health.get("status") in ("green", "yellow")
        except Exception as e:
            logger.error(f"OpenSearch health check failed: {e}")
            return False


# ── Singleton ─────────────────────────────────────────────────────────────────
opensearch_index = OpenSearchIndex()
