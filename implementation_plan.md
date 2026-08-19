# AI-Powered Enterprise Intelligence Platform — Implementation Plan

## Team Split

| Member | Owns | Tech |
|--------|------|------|
| **You** | ML models, embeddings, reranking, document processing, LangChain agents, database schema, vector store, evaluation | TensorFlow, HuggingFace, LangChain, PostgreSQL, Qdrant/Milvus, OpenSearch |
| **Friend** | API layer, ingestion workers, message queue, frontend, auth/RBAC, deployment, observability | FastAPI, Kafka, React/Next.js, Redis, Docker, Kubernetes, Prometheus/Grafana |

---

## Phase 0 — Project Setup & Shared Contracts (Week 1)

> Both members work together to establish the foundation.

### 0.1 Repository & Tooling
- Monorepo structure (or two repos: `platform-core` + `platform-ui`)
- Shared `.env.example`, `docker-compose.yml` for local dev
- Linting, formatting, pre-commit hooks
- CI/CD skeleton (GitHub Actions)

### 0.2 Define Shared Contracts
This is **critical** — both of you must agree on interfaces before splitting off.

```
Contracts to define:
├── Document Schema        → What a "document" looks like after ingestion
├── Chunk Schema           → What a chunk looks like (text, metadata, embedding)
├── Query Schema           → What a search request looks like
├── Response Schema        → What the API returns (answer, citations, scores)
├── Event Schema           → Kafka message formats between services
└── Auth Context           → How tenant_id / user_id / permissions flow
```

#### Suggested Document Schema (agree on this together)
```python
class Document:
    id: str                    # UUID
    tenant_id: str
    source_type: str           # "pdf", "github", "jira", "slack", "email"
    source_id: str             # original ID from source system
    title: str
    content: str               # raw extracted text
    content_hash: str          # for change detection / dedup
    metadata: dict             # source-specific fields
    created_at: datetime
    updated_at: datetime
    permissions: list[str]     # RBAC tags

class Chunk:
    id: str
    document_id: str
    tenant_id: str
    text: str
    embedding: list[float]     # 768 or 1024 dim
    chunk_index: int
    metadata: dict             # page_number, section, etc.
    permissions: list[str]

class SearchRequest:
    query: str
    tenant_id: str
    user_id: str
    filters: dict              # source_type, date_range, etc.
    top_k: int = 20

class SearchResponse:
    answer: str
    confidence: float
    citations: list[Citation]
    sources: list[SourceDoc]
    timelines: list[Event]     # optional
    latency_ms: float
    token_usage: dict
```

### 0.3 Local Dev Environment
```yaml
# docker-compose.yml — both members run this locally
services:
  postgres:       # document metadata, users, tenants
  redis:          # caching, session
  kafka:          # message queue (use KRaft mode, no Zookeeper)
  opensearch:     # BM25 index
  qdrant:         # vector store
  minio:          # S3-compatible object storage for raw files
```

> [!IMPORTANT]
> Agree on the schemas in Phase 0 before splitting off. This prevents integration nightmares later.

---

## Phase 1 — Single-Machine MVP (Weeks 2–5)

### Your Work (ML / LangChain / DB)

#### 1A. Database Schema & Setup `[Week 2]`
- [ ] PostgreSQL schema: `tenants`, `users`, `documents`, `chunks`, `permissions`, `feedback`
- [ ] Alembic migrations setup
- [ ] SQLAlchemy / async SQLAlchemy models
- [ ] Seed data for 2–3 test tenants

#### 1B. Document Processing Pipeline `[Week 2–3]`
- [ ] **PDF Parser** — `PyMuPDF` / `pdfplumber` for text extraction
- [ ] **Text Chunking** — Recursive character splitter with overlap (LangChain's `RecursiveCharacterTextSplitter` or custom)
- [ ] **Content Hashing** — SHA-256 of content for change detection / dedup
- [ ] **Metadata Extraction** — title, author, dates, source-specific fields
- [ ] Output: `Document` + list of `Chunk` objects

#### 1C. CNN-Based Document Layout Analysis `[Week 3–4]`
This is where TensorFlow + CNN is used **meaningfully**:
```
PDF page (image)
    ↓
TensorFlow CNN model (e.g., fine-tuned EfficientNet or custom)
    ↓
Layout detection: [table | image | paragraph | header | footer]
    ↓
Region extraction
    ↓
Tables → structured data (pandas DataFrame)
Images → caption / OCR
Paragraphs → text chunks
```
- [ ] Page rendering: PDF → images (using `pdf2image`)
- [ ] Layout detection model in TensorFlow/Keras
  - Option A: Use a pre-trained model (LayoutLM via HuggingFace, or Detectron2-equivalent in TF)
  - Option B: Fine-tune EfficientDet / custom CNN on document layout datasets (PubLayNet, DocLayNet)
- [ ] Region classifier: table / image / paragraph / header
- [ ] Table extraction pipeline (detected table region → OCR → structured output)
- [ ] OCR integration (`Tesseract` or `EasyOCR`) for scanned documents

#### 1D. Embedding Pipeline `[Week 3]`
- [ ] Embedding model selection — `sentence-transformers` (works with TF backend via `tf-keras` or use ONNX export)
  - Recommended: `all-MiniLM-L6-v2` (384 dim, fast) for MVP, `bge-large-en-v1.5` (1024 dim) for production
- [ ] Batch embedding generation
- [ ] Qdrant collection setup with proper distance metric (cosine)
- [ ] Index chunks into Qdrant with metadata + permission filters
- [ ] OpenSearch index setup for BM25

#### 1E. Hybrid Retrieval `[Week 4]`
```
Query
  ├── BM25 search (OpenSearch) → candidate set A
  ├── Vector search (Qdrant) → candidate set B
  ↓
  Merge (Reciprocal Rank Fusion or weighted combination)
  ↓
  Candidate set (top 50–100)
  ↓
  Reranker (cross-encoder model in TensorFlow)
  ↓
  Top K results (10–20)
```
- [ ] BM25 retriever (OpenSearch client)
- [ ] Vector retriever (Qdrant client)
- [ ] Reciprocal Rank Fusion (RRF) merger
- [ ] **Reranker** — TensorFlow cross-encoder model
  - Load a cross-encoder (e.g., `ms-marco-MiniLM-L-6-v2`) and run in TF via ONNX or saved model
  - Input: (query, passage) pairs → relevance score
- [ ] Permission filtering at retrieval time (pass `tenant_id` + `user_permissions` as Qdrant/OpenSearch filters)

#### 1F. LangChain RAG Agent `[Week 4–5]`
```
User Query
    ↓
Query Router (LangChain)
    ├── tool: search_documents(query, filters)
    ├── tool: search_code(query, repo)
    ├── tool: search_jira(query, project)
    ├── tool: search_conversations(query, channel)
    └── tool: sql_query(question)
    ↓
Retrieved context (with sources)
    ↓
LLM (OpenAI API / open-source via Ollama)
    ↓
Answer + Citations + Confidence
```
- [ ] LangChain tool definitions for each retrieval source
- [ ] Query classification — route to appropriate tools
- [ ] Prompt template with citation enforcement
- [ ] Citation extraction — map each claim to source chunk
- [ ] Confidence scoring — based on retrieval scores + LLM logprobs
- [ ] Streaming response support

---

### Friend's Work (API / Infra / Frontend)

#### 1G. FastAPI Backend `[Week 2–3]`
- [ ] Project structure: routers, services, models, middleware
- [ ] Auth system: JWT tokens, tenant isolation
- [ ] RBAC middleware: check permissions on every request
- [ ] API endpoints:
  - `POST /api/search` — main search/chat endpoint
  - `POST /api/documents/upload` — manual document upload
  - `GET /api/documents/{id}` — get document details
  - `POST /api/feedback` — user feedback on results
  - `GET /api/health` — health check
- [ ] Request validation, error handling, rate limiting
- [ ] CORS, security headers

#### 1H. Ingestion System `[Week 3–4]`
- [ ] Kafka topics: `documents.raw`, `documents.parsed`, `documents.embedded`, `documents.indexed`
- [ ] Source connectors (start with 2–3):
  - File upload connector (PDF, DOCX, TXT)
  - GitHub connector (clone repo → extract code + docs + issues)
  - Mock Jira/Slack connector (for demo)
- [ ] Change detection: compare `content_hash` before re-processing
- [ ] Kafka consumer workers that call **your** processing pipeline
- [ ] Dead letter queue for failed documents
- [ ] Status tracking: document processing state in PostgreSQL

#### 1I. Frontend `[Week 4–5]`
- [ ] Next.js app with:
  - Search bar (main interface)
  - Chat-style results display
  - Source cards (document, code, Jira, Slack — with icons)
  - Citation highlights (click citation → see source)
  - Confidence/relevance scores visualization
  - Filter sidebar (source type, date, team)
  - Document viewer (preview PDFs, code files)
- [ ] Auth pages: login, register
- [ ] Admin panel: manage tenants, users, permissions, data sources
- [ ] Dark mode

---

## Phase 2 — Production Hardening (Weeks 6–8)

### Your Work

#### 2A. Evaluation System `[Week 6]`
- [ ] Build evaluation dataset:
  ```
  [
    {
      "query": "Why did payment service fail after March deploy?",
      "expected_doc_ids": ["doc_123", "doc_456"],
      "expected_answer_contains": ["timeout", "config change"],
      "source_type_expected": ["jira", "github", "slack"]
    }
  ]
  ```
- [ ] Implement metrics:
  - **Retrieval**: Recall@K, Precision@K, MRR, NDCG
  - **Answer quality**: Faithfulness (is answer grounded in sources?), Citation accuracy
  - **Performance**: Latency (p50, p95, p99), Token consumption
- [ ] Automated evaluation pipeline: run nightly against test set
- [ ] Results dashboard (can be a simple HTML report or Grafana)

#### 2B. Entity Extraction `[Week 6–7]`
- [ ] NER model in TensorFlow (or use spaCy + custom entities)
  - Entities: person, team, service, deployment, date, ticket_id, PR number
- [ ] Entity linking: connect extracted entities to knowledge graph
- [ ] Timeline generation: extract events with dates → build timeline

#### 2C. Document Classification `[Week 7]`
- [ ] TensorFlow text classifier:
  - Categories: technical_doc, policy, meeting_notes, code_review, incident_report, etc.
- [ ] Train on labeled subset, use for auto-tagging
- [ ] Classification confidence → if low, flag for human review

#### 2D. Learning-to-Rank (Advanced) `[Week 8]`
- [ ] Collect implicit feedback (clicks, dwell time, explicit thumbs up/down)
- [ ] Feature engineering: BM25 score, vector similarity, recency, source type, user history
- [ ] TensorFlow ranking model (listwise or pairwise loss)
- [ ] A/B testing framework: serve old ranker vs. new ranker

---

### Friend's Work

#### 2E. Distributed Processing `[Week 6–7]`
- [ ] Multiple Kafka consumer workers (parser, embedder, indexer)
- [ ] Worker autoscaling based on queue depth
- [ ] Retry logic with exponential backoff
- [ ] Poison message handling

#### 2F. Observability `[Week 7]`
- [ ] OpenTelemetry instrumentation across all services
- [ ] Prometheus metrics:
  - Query latency (retrieval, reranking, LLM)
  - Document processing throughput
  - Queue depth, consumer lag
  - Error rates by source type
- [ ] Grafana dashboards
- [ ] Structured logging (JSON logs)
- [ ] Alerting rules

#### 2G. Caching & Performance `[Week 7–8]`
- [ ] Redis caching:
  - Embedding cache (same query → skip re-embedding)
  - Result cache (same query + same tenant → cached response, with TTL)
  - Popular document cache
- [ ] Connection pooling for all databases
- [ ] Rate limiting per tenant

#### 2H. Multi-Tenancy Hardening `[Week 8]`
- [ ] Row-level security in PostgreSQL
- [ ] Tenant-scoped Qdrant collections (or metadata filtering)
- [ ] Tenant-scoped OpenSearch indices
- [ ] Data isolation audit tests

---

## Phase 3 — Scale & Polish (Weeks 9–12)

### Your Work

#### 3A. ML Recommendation Layer `[Week 9–10]`
```
User interaction data:
  - queries issued
  - documents clicked
  - time spent on each doc
  - feedback given
        ↓
Feature engineering
        ↓
TensorFlow model: P(user finds doc useful | user, query, doc)
        ↓
Personalized re-ranking
```
- [ ] Interaction logging schema
- [ ] Feature pipeline
- [ ] TensorFlow recommendation model
- [ ] Online serving: merge ML scores with retrieval scores

#### 3B. Advanced Document Understanding `[Week 10–11]`
- [ ] Improve CNN layout model with more training data
- [ ] Handle complex tables (merged cells, nested headers)
- [ ] Image captioning for figures in documents
- [ ] Code understanding: AST parsing + semantic chunking for code files

#### 3C. Query Understanding `[Week 11–12]`
- [ ] Query expansion (synonyms, related terms)
- [ ] Query classification (factual, exploratory, debugging, comparison)
- [ ] Conversational context (multi-turn: remember previous queries)
- [ ] Auto-suggest / query completion

---

### Friend's Work

#### 3D. Deployment `[Week 9–10]`
- [ ] Dockerfiles for all services
- [ ] Kubernetes manifests / Helm charts
- [ ] Horizontal pod autoscaling
- [ ] Health checks, readiness/liveness probes

#### 3E. Additional Connectors `[Week 10–11]`
- [ ] Real Jira connector (REST API)
- [ ] Real Slack connector (Events API)
- [ ] Email connector (IMAP / Gmail API)
- [ ] Confluence / Google Docs connector

#### 3F. Frontend Polish `[Week 11–12]`
- [ ] Knowledge graph visualization (D3.js / vis.js)
- [ ] Analytics dashboard for admins
- [ ] Mobile responsive design
- [ ] Accessibility (WCAG)
- [ ] Onboarding flow for new tenants

---

## Folder Structure

```
ai-enterprise-platform/
├── docker-compose.yml
├── .env.example
├── shared/
│   ├── schemas/              # Pydantic models shared between services
│   ├── config/               # Shared configuration
│   └── utils/                # Common utilities
│
├── ml/                       # ← YOUR CODE
│   ├── document_processing/
│   │   ├── pdf_parser.py
│   │   ├── chunker.py
│   │   ├── dedup.py
│   │   └── layout_cnn/
│   │       ├── model.py      # TensorFlow CNN for layout detection
│   │       ├── train.py
│   │       └── inference.py
│   ├── embeddings/
│   │   ├── embedder.py       # Batch embedding generation
│   │   └── model_config.py
│   ├── retrieval/
│   │   ├── bm25_retriever.py
│   │   ├── vector_retriever.py
│   │   ├── hybrid.py         # RRF merger
│   │   └── reranker.py       # TF cross-encoder reranker
│   ├── classification/
│   │   ├── doc_classifier.py # TF text classifier
│   │   └── query_classifier.py
│   ├── ner/
│   │   ├── entity_extractor.py
│   │   └── timeline.py
│   ├── ranking/
│   │   ├── ltr_model.py      # Learning-to-rank in TF
│   │   └── features.py
│   ├── recommendation/
│   │   ├── model.py
│   │   └── features.py
│   ├── evaluation/
│   │   ├── metrics.py        # Recall, Precision, MRR, NDCG
│   │   ├── faithfulness.py
│   │   ├── eval_dataset.json
│   │   └── run_eval.py
│   └── langchain_agent/
│       ├── agent.py           # Main RAG agent
│       ├── tools.py           # Search tools
│       ├── prompts.py         # Prompt templates
│       └── citations.py       # Citation extraction
│
├── database/                  # ← YOUR CODE
│   ├── migrations/            # Alembic
│   ├── models.py              # SQLAlchemy models
│   ├── vector_store.py        # Qdrant client
│   └── search_index.py        # OpenSearch client
│
├── api/                       # ← FRIEND'S CODE
│   ├── main.py                # FastAPI app
│   ├── routers/
│   ├── middleware/
│   ├── services/
│   └── auth/
│
├── ingestion/                 # ← FRIEND'S CODE (calls your ML pipeline)
│   ├── connectors/
│   ├── workers/
│   └── kafka_config.py
│
├── frontend/                  # ← FRIEND'S CODE
│   └── (Next.js app)
│
├── infra/                     # ← FRIEND'S CODE
│   ├── docker/
│   ├── k8s/
│   └── monitoring/
│
└── tests/
    ├── ml/
    ├── api/
    ├── integration/
    └── e2e/
```

---

## Integration Points (Where Your Work Meets Friend's Work)

These are the **handoff interfaces** — define them clearly to avoid blocking each other.

| # | Your Side (produces) | Friend's Side (consumes) | Interface |
|---|---------------------|-------------------------|-----------|
| 1 | `process_document(raw_bytes, source_type) → Document + Chunks` | Kafka worker calls this function | Python function |
| 2 | `embed_chunks(chunks) → chunks_with_embeddings` | Kafka worker calls this after parsing | Python function |
| 3 | `search(query, tenant_id, user_perms, filters) → SearchResponse` | FastAPI endpoint calls this | Python function |
| 4 | `run_agent(query, context) → AgentResponse` | FastAPI endpoint calls this for chat | Python function |
| 5 | DB models + migrations | API layer imports and uses them | SQLAlchemy models |
| 6 | Evaluation metrics | Grafana dashboards display them | Prometheus metrics / JSON |

---

## Week-by-Week Summary

| Week | You | Friend |
|------|-----|--------|
| 1 | Shared: schemas, docker-compose, contracts | Shared: schemas, docker-compose, contracts |
| 2 | DB schema + PDF parser + chunker | FastAPI skeleton + auth + Kafka setup |
| 3 | CNN layout model + embedding pipeline | Ingestion connectors + Kafka workers |
| 4 | Hybrid retrieval + reranker | Frontend search UI |
| 5 | LangChain RAG agent | Frontend chat UI + integration |
| 6 | Evaluation system + entity extraction | Distributed workers + scaling |
| 7 | Document classification | Observability + caching |
| 8 | Learning-to-rank | Multi-tenancy hardening |
| 9–10 | ML recommendation layer | Docker/K8s deployment |
| 11–12 | Query understanding + advanced doc processing | More connectors + frontend polish |

---

## Key Decisions to Make Together

> [!IMPORTANT]
> Discuss and decide these before starting Phase 1:

1. **LLM Choice**: OpenAI API (faster to start) vs. open-source via Ollama (no API costs, full control)?
2. **Embedding Model**: `all-MiniLM-L6-v2` (fast, 384 dim) vs. `bge-large` (better quality, 1024 dim)?
3. **Vector DB**: Qdrant (simpler) vs. Milvus (more features)?
4. **TensorFlow version**: TF 2.x with Keras 3 (recommended)?
5. **Monorepo vs. multi-repo**: Single repo is easier for two people, recommended for now.
6. **Demo data**: What sample documents will you use for development? (Suggest: arXiv papers + mock Jira/Slack data)
