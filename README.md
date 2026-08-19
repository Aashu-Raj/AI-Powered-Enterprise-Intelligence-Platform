# AI-Powered Enterprise Intelligence Platform

A production-grade internal search & intelligence platform.
Think Glean + GitHub Copilot — built from scratch.

## Team

| Member | Owns |
|--------|------|
| You | ML, LangChain, Database |
| Friend | FastAPI, Kafka, React, Infra |

---

## Quick Start (Local Dev)

### 1. Clone and set up environment

```bash
# Copy env template
cp .env.example .env
# Edit .env with your values (at minimum set OPENAI_API_KEY if using OpenAI)

# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate       # Windows
# source venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt
```

### 2. Start infrastructure

```bash
docker-compose up -d
```

This starts: PostgreSQL, Redis, Qdrant, OpenSearch, Kafka, MinIO

### 3. Run database migrations

```bash
# Generate initial migration (first time only)
alembic revision --autogenerate -m "initial schema"

# Apply migrations
alembic upgrade head
```

### 4. Seed test data

```bash
python -m database.scripts.seed
```

This creates 2 test tenants with users, roles, and sample documents.

### 5. Verify services

| Service | URL |
|---------|-----|
| PostgreSQL | localhost:5432 |
| Redis | localhost:6379 |
| Qdrant Dashboard | http://localhost:6333/dashboard |
| OpenSearch | http://localhost:9200 |
| MinIO Console | http://localhost:9001 (admin/minioadmin) |
| Kafka | localhost:9092 |

---

## Project Structure

```
ai-enterprise-platform/
├── shared/                    # Shared schemas and config
│   ├── config/settings.py     # All env vars (pydantic-settings)
│   └── schemas/document.py    # Pydantic API contracts
│
├── database/                  # YOUR CODE — DB layer
│   ├── base.py                # SQLAlchemy Base + mixins
│   ├── session.py             # Async engine + session factory
│   ├── models/
│   │   ├── tenant.py          # Tenant, User, Role, Permission
│   │   ├── document.py        # Document, Chunk, SourceConnector
│   │   └── query.py           # Query, SearchResult, Feedback
│   ├── vector_store/
│   │   └── qdrant_client.py   # Qdrant async client
│   ├── search_index/
│   │   └── opensearch_client.py  # OpenSearch BM25 client
│   ├── migrations/            # Alembic migrations
│   └── scripts/seed.py        # Dev seed data
│
├── ml/                        # YOUR CODE — ML models
│   ├── document_processing/   # PDF parser, chunker, OCR
│   ├── embeddings/            # TF embedding pipeline
│   ├── retrieval/             # Hybrid BM25 + vector retrieval
│   ├── classification/        # TF document/query classifier
│   ├── ner/                   # Entity extraction + timeline
│   ├── ranking/               # Learning-to-rank (TF)
│   ├── recommendation/        # Personalized ranking (TF)
│   ├── evaluation/            # Recall, MRR, NDCG metrics
│   └── langchain_agent/       # RAG agent + tools
│
├── api/                       # FRIEND'S CODE — FastAPI
├── ingestion/                 # FRIEND'S CODE — Kafka workers
├── frontend/                  # FRIEND'S CODE — Next.js
└── infra/                     # FRIEND'S CODE — Docker/K8s
```

---

## Test Credentials (after seed)

**Tenant: Acme Corp**
- Admin: `admin@acme.com` / `password123`
- Engineer: `engineer@acme.com` / `password123`

**Tenant: TechStart Inc**
- Admin: `admin@techstart.io` / `password123`

---

## Development Commands

```bash
# Run tests
pytest tests/ -v

# Generate new migration
alembic revision --autogenerate -m "add table xyz"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# View migration history
alembic history --verbose
```
