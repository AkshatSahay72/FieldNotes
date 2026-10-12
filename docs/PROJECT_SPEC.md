# Fieldnote — Project Specification

## 1. Project Purpose

Fieldnote is a lightweight **Research Notes and Evidence Management System** built with **FastAPI** and **MongoDB (PyMongo)**. 

The project is designed for an academic viva / evaluation setting. Its primary academic objective is to demonstrate proficiency with core MongoDB concepts without the obfuscation of heavy Object-Document Mappers (ODMs) or bloated enterprise architectures.

Key technical proficiencies demonstrated:
- Raw PyMongo usage and idiomatic document modeling.
- Document validation and structured data integrity in MongoDB.
- Index design (single field, compound, text index) and query optimization.
- Complex data aggregation using MongoDB Aggregation Pipelines.
- Semantic document retrieval using MongoDB Atlas Vector Search.

The application remains intentionally compact, readable, and direct so every design decision can be clearly articulated during examination.

---

## 2. Project Scope

The project scope encompasses:
1. **Research Notes Management**: Structured CRUD operations for academic/field notes with tags, timestamps, and rich metadata.
2. **Evidence & Attachments**: Image attachment support accompanied by user-authored captions and contextual descriptions.
3. **Querying & Indexing**: Deterministic MongoDB queries, compound filtering, text search, and index optimization.
4. **Analytics via Aggregations**: Insight generation (e.g., tag frequency distributions, note creation timelines, evidence statistics) using MongoDB Aggregation Pipelines.
5. **Vector Search**: Semantic similarity matching across notes using MongoDB Atlas Vector Search.
6. **API Interface**: A clean RESTful API built on FastAPI with OpenAPI documentation.

---

## 3. Explicit Non-Goals

To maintain academic clarity, avoid scope creep, and keep the codebase auditable, the following are strictly out of scope:
- **Authentication & User Management**: No multi-tenant accounts, JWT/OAuth auth flows, or permission hierarchies.
- **Multi-user Workspaces & Collaboration**: No collaborative editing or team workspaces.
- **Task Management & Scheduling**: No calendar integrations, task boards, reminders, or schedulers.
- **Autonomous Agents & LLM Tool Execution**: No agentic loops, background bots, or autonomous reasoning pipelines.
- **Heavy Image Processing & OCR**: No computer vision models, automated OCR pipelines, or image transformations.
- **ODMs / ORMs**: No MongoEngine, Beanie, or SQLAlchemy. PyMongo is used directly to showcase database driver interaction.
- **Secondary Databases**: No standalone vector databases (Pinecone, Weaviate, Chroma, Milvus) or secondary relational stores (PostgreSQL, SQLite). MongoDB Atlas provides all document and vector search storage.
- **CI/CD & Container Orchestration**: No premature Docker or Kubernetes setups unless specifically requested for deployment later.

---

## 4. Technology Stack & Rationale

| Layer | Technology | Rationale |
| :--- | :--- | :--- |
| **Language** | Python 3.10+ | Clean syntax, native typing, strong scientific/data ecosystem. |
| **Backend Framework** | FastAPI | High performance, automatic OpenAPI documentation, clean dependency injection. |
| **Database Driver** | PyMongo | Direct MongoDB driver exposure; transparent control over queries, indexes, and aggregation pipelines without ODM abstraction layers. |
| **Database Engine** | MongoDB Atlas | Managed cloud MongoDB supporting flexible document schemas, aggregation pipelines, and Atlas Vector Search. |
| **Validation / Schemas** | Pydantic v2 | Robust input/output schema validation for API boundaries; distinct from MongoDB internal collection schemas. |
| **Testing** | pytest & HTTPX | Standard testing framework for unit and API integration testing. |
| **Configuration** | Environment Variables (`python-dotenv` / `pydantic-settings`) | 12-factor application configuration decoupled from codebase. |

---

## 5. Milestone Breakdown & Acceptance Criteria

### Milestone 0: Documentation & Minimal Backend Foundation (Current)
- **Scope**: Project specification, architecture, implementation log, minimal repository configuration, empty structure.
- **Acceptance Criteria**:
  - `docs/PROJECT_SPEC.md`, `docs/ARCHITECTURE.md`, `docs/IMPLEMENTATION_LOG.md` exist and are consistent.
  - `.gitignore`, `.env.example`, `requirements.txt`, and minimal `app/` and `tests/` folders exist.
  - No speculative features, mock implementations, or auto-commits created.

### Milestone 1: MongoDB Connection & Health Lifecycle
- **Scope**: Environment configuration loading, PyMongo client lifecycle management (startup/shutdown), database connectivity check.
- **Acceptance Criteria**:
  - Dedicated database module managing `MongoClient` connection lifecycle.
  - Health check endpoint (`GET /api/health`) verifying database connectivity via `db.command("ping")`.
  - Integration test verifying health check status.

### Milestone 2: Research Notes Data Model & CRUD Operations
- **Scope**: PyMongo CRUD operations for research notes, schema validation at both API (Pydantic) and database levels, REST routes.
- **Acceptance Criteria**:
  - Pydantic models for note creation, update, and response.
  - PyMongo repository/service implementing: Create, Read (by ID and list with pagination), Update, Delete.
  - Standard error handling for missing documents (`404`) and invalid ObjectIds (`400`).
  - Unit/integration tests covering all CRUD operations.

### Milestone 3: Image Attachments & Evidence Metadata
- **Scope**: File upload handling for image attachments, storing attachment metadata and user descriptions/captions, linking attachments to notes.
- **Acceptance Criteria**:
  - Attachment upload endpoint handling file storage (local filesystem or storage volume) and capturing user caption/description.
  - Attachment metadata document stored and linked to note records.
  - Ability to retrieve, list, and delete attachments associated with a note.

### Milestone 4: Indexing & Efficient Querying
- **Scope**: Explicit index management (single field, compound, text search), query performance demonstration.
- **Acceptance Criteria**:
  - Index creation script / startup routines for created_at, tags, and text search over title/body.
  - Search endpoint using MongoDB text search (`$text`, `$search`).
  - Query explainability documentation (`explain("executionStats")`) for viva demonstration.

### Milestone 5: Analytics & MongoDB Aggregation Pipelines
- **Scope**: Analytics endpoints using multi-stage MongoDB aggregation pipelines (`$match`, `$unwind`, `$group`, `$project`, `$sort`).
- **Acceptance Criteria**:
  - Aggregation pipeline for tag frequency distribution.
  - Aggregation pipeline for note activity timeline / creation trends.
  - Aggregation pipeline for attachment evidence summaries.
  - Automated tests validating pipeline output against known test datasets.

### Milestone 6: Semantic Note Retrieval (Atlas Vector Search)
- **Scope**: Generating embeddings for research notes, storing vector embeddings in MongoDB documents, querying with `$vectorSearch`.
- **Acceptance Criteria**:
  - Embeddings generation service for note content.
  - Vector search index definition for MongoDB Atlas.
  - Semantic search endpoint returning semantically related notes based on query embedding.

### Milestone 7: Minimal Frontend & Deployment Preparation (Future, if approved)
- **Scope**: Lightweight Flask frontend interface for interacting with the FastAPI backend, configuration for deployment on Render.
- **Acceptance Criteria**:
  - Simple, clean web interface for browsing and searching notes.
  - Working deployment configuration.
