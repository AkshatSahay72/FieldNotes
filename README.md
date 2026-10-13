# Fieldnote

> **A Research Notes & Evidence Management System using MongoDB**

Fieldnote is a lightweight backend system built with **FastAPI** and **PyMongo** designed to showcase core MongoDB concepts, including native document modeling, indexing, aggregation pipelines, and MongoDB Atlas Vector Search.

---

## Academic Focus

This project is tailored for an academic evaluation / viva setting. It deliberately avoids high-level Object-Document Mappers (ODMs) like MongoEngine or Beanie so that direct PyMongo driver usage, queries, indexes, and aggregation stages are transparent and explainable.

### Core Capabilities (Planned Across Milestones)
1. **Research Notes CRUD**: Idiomatic document CRUD operations with Pydantic validation.
2. **Evidence & Attachments**: Image uploads with user-provided captions and structured metadata.
3. **Optimized Indexing**: Single-field, compound, and native text search indexes with query performance explainability.
4. **Analytics Aggregation Pipelines**: Multi-stage aggregation pipelines for tag analytics and research timeline statistics.
5. **Semantic Retrieval**: Vector embeddings and MongoDB Atlas Vector Search.

---

## Technical Stack

- **Language**: Python 3.10+
- **Framework**: FastAPI
- **Database Driver**: PyMongo
- **Database**: MongoDB Atlas
- **Testing**: pytest & HTTPX
- **Configuration**: Environment variables (`.env`)

---

## Milestone-Driven Development Workflow

The project is built incrementally in strict, reviewable milestones:

- **Milestone 0**: Documentation & Minimal Backend Foundation *(Completed)*
- **Milestone 1**: MongoDB Connection & Health Lifecycle *(Completed)*
- **Milestone 2**: Research Notes Data Model & CRUD Operations *(Completed)*
- **Milestone 3**: Image Attachments & Evidence Metadata with GridFS *(Completed)*
- **Milestone 4**: Indexing, Tag Filtering, & Native Text Search *(Completed)*
- **Milestone 5**: Analytics & MongoDB Aggregation Pipelines *(Completed)*
- **Milestone 6**: Semantic Note Retrieval (Atlas Vector Search) *(Next Milestone)*
- **Milestone 7**: Minimal Frontend & Deployment Preparation *(Future)*

Documentation files in `docs/` serve as the source of truth:
- [PROJECT_SPEC.md](docs/PROJECT_SPEC.md): Scope, non-goals, and milestone acceptance criteria.
- [ARCHITECTURE.md](docs/ARCHITECTURE.md): Architectural decisions, schemas, and design constraints.
- [IMPLEMENTATION_LOG.md](docs/IMPLEMENTATION_LOG.md): Current progress, decisions, verification records, and next milestone.

---

## API Usage Examples

### 1. Research Notes & Querying (`/api/notes`)

- **Create a Note**:
  ```bash
  curl -X POST http://127.0.0.1:8000/api/notes \
    -H "Content-Type: application/json" \
    -d '{"title": "Soil Sample 4A", "content": "Observed high nitrogen levels near plot B.", "tags": ["soil", "nitrogen", "field"]}'
  ```

- **List All Notes (Unfiltered, Newest First)**:
  ```bash
  curl http://127.0.0.1:8000/api/notes
  ```

- **Filter by Tags (OR Semantics)**:
  ```bash
  # Repeated parameter convention:
  curl "http://127.0.0.1:8000/api/notes?tag=soil&tag=water"

  # Or comma-separated alias:
  curl "http://127.0.0.1:8000/api/notes?tags=soil,water"
  ```

- **MongoDB Native Text Search**:
  ```bash
  curl "http://127.0.0.1:8000/api/notes?q=nitrogen"
  ```

- **Combined Text Search & Tag Filtering**:
  ```bash
  curl "http://127.0.0.1:8000/api/notes?q=sample&tag=soil"
  ```

- **Deterministic Pagination**:
  ```bash
  # Fetch second page of 10 notes (default skip=0, limit=20; max limit=100)
  curl "http://127.0.0.1:8000/api/notes?skip=10&limit=10"
  ```

### 2. Evidence Attachments (`/api/notes/{note_id}/attachments`)

- **Upload Image Evidence (JPEG, PNG, WebP up to 5 MB)**:
  ```bash
  curl -X POST http://127.0.0.1:8000/api/notes/{note_id}/attachments \
    -F "file=@specimen.jpg;type=image/jpeg" \
    -F "caption=Specimen Macro Photo" \
    -F "description=Close-up of rock layer crystal structure"
  ```

- **List Attachments for a Note**:
  ```bash
  curl http://127.0.0.1:8000/api/notes/{note_id}/attachments
  ```

- **Download / Stream Attachment Image**:
  ```bash
  curl -O http://127.0.0.1:8000/api/notes/{note_id}/attachments/{attachment_id}/download
  ```

### 3. Aggregation Analytics (`/api/analytics`)

- **Research Overview Summary**:
  ```bash
  curl http://127.0.0.1:8000/api/analytics/overview
  ```
  *Response:* `{"total_notes": 12, "total_attachments": 4, "notes_with_tags": 10}`

- **Tag Frequency Distribution (`$unwind` + `$group`)**:
  ```bash
  curl http://127.0.0.1:8000/api/analytics/tags
  ```
  *Response:* `[{"tag": "soil", "count": 6}, {"tag": "nitrogen", "count": 4}]`

- **Daily Note Creation Trends (`$dateToString` in UTC)**:
  ```bash
  curl http://127.0.0.1:8000/api/analytics/activity
  ```
  *Response:* `[{"date": "2026-10-12", "count": 3}, {"date": "2026-10-13", "count": 9}]`

- **Per-Note Attachment Counts (`$lookup` + `$size`)**:
  ```bash
  # Includes notes with 0 attachments by default:
  curl http://127.0.0.1:8000/api/analytics/attachments

  # Or filter to only notes having attachments:
  curl "http://127.0.0.1:8000/api/analytics/attachments?include_zero=false"
  ```

### 4. Semantic Search (`/api/search/semantic`)

- **Semantic Query Retrieval via Vector Search**:
  ```bash
  curl "http://127.0.0.1:8000/api/search/semantic?q=soil+moisture+anomalies&limit=10"
  ```
  *Response:* Returns ranked notes with `score` from `$meta: vectorSearchScore` (relative similarity ranking signal). Note: Atlas Vector Search index provisioning and live cluster validation are deferred to Milestone 6D.

- **Atlas Vector Search Index Provisioning CLI**:
  ```bash
  # Inspect current search index status without creating
  python scripts/provision_vector_index.py --check-only

  # Idempotently provision idx_notes_vector on MongoDB Atlas (polls until READY)
  python scripts/provision_vector_index.py
  ```

- **Offline Vector Backfill CLI**:
  ```bash
  # Dry-run inspection
  python scripts/backfill_embeddings.py --dry-run

  # Idempotent batch execution
  python scripts/backfill_embeddings.py --batch-size 50
  ```

---

## Quickstart

### 1. Prerequisites
- Python 3.10+
- Virtual environment tool (`venv`)

### 2. Environment Setup
```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# On macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Environment Variables
Copy `.env.example` to `.env` and fill in your MongoDB Atlas connection details:
```bash
cp .env.example .env
```
*(Never commit `.env` containing actual credentials).*

### 4. Running Tests
```bash
pytest -v
```

