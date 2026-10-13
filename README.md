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
- **Milestone 6**: Semantic Note Retrieval (Atlas Vector Search) *(Completed & Fully Verified)*
- **Milestone 7**: Minimal Frontend & Deployment Preparation *(In Progress — Phase 2D.1 Demo Safety & Seeding Complete)*

Documentation files in `docs/` serve as the source of truth:
- [PROJECT_SPEC.md](docs/PROJECT_SPEC.md): Scope, non-goals, and milestone acceptance criteria.
- [ARCHITECTURE.md](docs/ARCHITECTURE.md): Architectural decisions, schemas, and design constraints.
- [IMPLEMENTATION_LOG.md](docs/IMPLEMENTATION_LOG.md): Current progress, decisions, verification records, and next milestone.

---

## Web Interface

Fieldnote serves a mobile-ready, accessible researcher interface built with FastAPI, Jinja2, Vanilla CSS, and Vanilla JavaScript:
- **Research Observations Dashboard (`/`)**:
  - Live observation feed with pagination controls (`skip`, `limit`).
  - Dual-mode search toggle: Native MongoDB text search (`$text`) vs. Atlas Vector Search (`$vectorSearch`).
  - Categorical tag filtering preserving MongoDB `$in` OR semantics.
  - Interactive note authoring and editing modal dialogs with client validation.
  - Accessible delete confirmation modal dialogs (`role="alertdialog"`).
  - Responsive layout, accessible live toast feedback, and full keyboard navigation.
  - **Evidence Gallery & Attachment Management**:
    - Note-card action (`📷 Evidence`) opens dedicated attachment modal per note.
    - Multipart image upload form (JPEG, PNG, WebP up to 5 MB) with client validation and loading states.
    - Responsive thumbnail gallery streaming directly from PyMongo GridFS.
    - Accessible full-size image lightbox modal with image metadata and keyboard navigation.
- **Analytics & Pipeline Insights (`/analytics`)**:
  - Live research overview cards (Total notes, attachments, tagged notes).
  - Categorical tag distribution rendered as ranked horizontal bars via `$unwind` & `$group`.
  - Chronological daily note creation timeline via `$dateToString` (UTC).
  - Per-note evidence attachment rankings via `$lookup` & `$size`, with toggleable zero-count inclusion and top-25 limits.
  - Section-level loading, error, retry, and empty states with independent request-race protection and parallel fetch via `Promise.allSettled`.
- **Interactive Swagger API Documentation (`/docs`)**: OpenAPI schema and interactive endpoint testing.

---

## Public Demo Mode & Synthetic Dataset Seeding

To prepare Fieldnote for public demonstration without risking mutation of primary development data or exposing open write endpoints, Fieldnote supports a strictly enforced read-only demo mode backed by synthetic data isolation.

### 1. Enabling Demo Mode & Fail-Closed Validation
Configure the demo mode setting in your environment or `.env` file:
```env
DEMO_MODE=true
DATABASE_NAME=fieldnote_demo
```
- **Fail-Closed Validation**: If `DEMO_MODE=true` is enabled, the application will **refuse to start up** unless `DATABASE_NAME` is explicitly supplied and points to a dedicated demo database. Omitting `DATABASE_NAME` or targeting the default development database (`fieldnote_db`) raises a configuration validation error at startup.

### 2. Server-Side Protection
When `DEMO_MODE=true` is set:
- **Rejected Operations**: All write-capable API endpoints (`POST /api/notes`, `PUT /api/notes/{id}`, `DELETE /api/notes/{id}`, `POST /api/notes/{id}/attachments`, `DELETE /api/notes/{id}/attachments/{id}`) are rejected server-side before request processing with **HTTP 403 Forbidden** and response `{"detail": "Operation not permitted in demo mode."}`.
- **Read Operations Preserved**: Note listing, categorical tag filtering, text search, semantic vector search, analytics overview, tag charts, activity timeline, attachment rankings, attachment listing, and image downloads remain completely accessible.
- **UI Indication**: A non-intrusive status banner (`.demo-banner`) is displayed across all pages alerting viewers that mutations are disabled. Attempting a mutation through the UI triggers an immediate, non-sensitive toast notification explaining the restriction.

### 3. Database Isolation & Controlled Seeding
To isolate demonstration records from development data:
1. Specify a dedicated demo database using `DATABASE_NAME` (e.g. `fieldnote_demo`).
2. Populate the demo database using the controlled CLI seed script:
   ```bash
   # Explicit demo database selection via environment variable:
   DATABASE_NAME=fieldnote_demo python scripts/seed_demo_data.py

   # Or explicit CLI argument:
   python scripts/seed_demo_data.py --database-name fieldnote_demo

   # Dry-run inspection without database writes:
   python scripts/seed_demo_data.py --database-name fieldnote_demo --dry-run
   ```
3. **Safety Guards**:
   - **Production Guard**: The seed script unconditionally refuses to run if `APP_ENV=production`.
   - **Development Guard**: If the target database is the default development database (`fieldnote_db`), the seed script will automatically abort unless the explicit flag `--allow-default-db` is provided.
4. **Idempotency & Compensating Cleanup**: The script is safe to rerun at any time without duplicating notes or attachments. If a metadata record insertion fails after uploading an image chunk to GridFS, the newly uploaded GridFS file is automatically cleaned up.
5. **No Public Seed/Reset Endpoints**: Seeding is exclusively an operator CLI tool; no public endpoints exist to trigger seeding, resets, or deletions.

### 4. Security Limitations
- Demo mode is an application-layer write protection mechanism intended for academic evaluations and portfolio demonstrations.
- It does not introduce authentication, user registration, multi-tenancy, or MongoDB Atlas user role modifications.


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

---

## Deployment to Render

Fieldnote is configured for deployment as a Render Web Service using the blueprint [`render.yaml`](file:///d:/Coding/Major%20Project/FieldNotes/render.yaml).

### 1. Step-by-Step Operator Deployment

1. **Push Repository**: Ensure the latest code is on your GitHub repository.
2. **Create Web Service on Render**:
   - In the [Render Dashboard](https://dashboard.render.com), click **New +** > **Blueprint** (or **New +** > **Web Service**).
   - Select your Fieldnote repository.
   - If using Blueprints, Render detects `render.yaml` automatically.
   - If creating manually:
     - **Environment**: Python
     - **Build Command**: `pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && pip install --no-cache-dir -r requirements.txt`
     - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1`
     - **Health Check Path**: `/health`
3. **Configure Environment Variables in Render Dashboard**:
   - `APP_ENV`: `production`
   - `DEMO_MODE`: `true`
   - `MONGODB_URI`: Your MongoDB Atlas connection URI (`mongodb+srv://...`)
   - `DATABASE_NAME`: Dedicated demo database (e.g. `fieldnote_demo`). *Must not be `fieldnote_db`.*
   - `EMBEDDING_MODEL`: `sentence-transformers/all-MiniLM-L6-v2`
   - `PYTHON_VERSION`: `3.11.9`
4. **Deploy**: Trigger the initial build. The health check at `/health` verifies that the web service and database connection are operational.

### 2. Seeding Synthetic Demo Data

The public Render service runs in read-only demo mode and exposes **no** public seeding or reset endpoints. Seeding must be performed by the operator from a trusted environment:

```bash
# Set environment variables pointing to the dedicated demo database
export MONGODB_URI="mongodb+srv://<user>:<password>@<cluster>.mongodb.net/?retryWrites=true&w=majority"
export DATABASE_NAME="fieldnote_demo"
export APP_ENV="development" # or "demo" — NEVER "production"

# Run idempotent seed script with --force to confirm the demo database
python scripts/seed_demo_data.py --force
```

- **Production Guard**: The seed script unconditionally refuses execution if `APP_ENV=production`.
- **Compensating Cleanup**: If any GridFS metadata insertion fails during upload, the newly uploaded binary chunks are automatically deleted.
- **Idempotency**: Rerunning the seed script performs zero duplicate insertions.

### 3. MongoDB Atlas Network Access & Security Trade-offs

Render web services on free and individual starter plans use dynamic outbound IP addresses that change across builds and container restarts.

- **The `0.0.0.0/0` ("Allow Access from Anywhere") Trade-off**:
  - Setting `0.0.0.0/0` in MongoDB Atlas Network Access is commonly used for dynamic hosts, but it exposes the database cluster port to the entire internet.
  - **Security Mitigation**:
    1. Create a dedicated Atlas database user with credentials scoped strictly to `readWrite` on `fieldnote_demo` only (not cluster admin or access to other databases).
    2. Use a high-entropy, auto-generated password (32+ characters).
    3. Use TLS and SCRAM-SHA-256 (default in MongoDB Atlas).
    4. For temporary evaluations, utilize Atlas's "Temporary IP Access" feature with auto-expiration (e.g. 6 or 24 hours).
    5. On Render Team/Enterprise plans, utilize Render's **Static Outbound IP** feature to whitelist specific IPs in Atlas Network Access, avoiding `0.0.0.0/0` entirely.

### 4. Render Free-Tier Resource Limitations & Mitigations

| Limitation | Impact | Mitigation in Fieldnote |
| :--- | :--- | :--- |
| **512 MB RAM Limit** | PyTorch + SentenceTransformers can exceed RAM with multiple workers. | Enforce `--workers 1` in start command. Runtime memory is ~280-350 MB. |
| **Inactivity Spin-down** | Free instances sleep after 15 minutes of inactivity. | 30-60s cold start latency on first request. Health check `/health` verifies availability once warm. |
| **Ephemeral Filesystem** | Files written to local disk are lost on container restart. | All demo evidence attachments are stored in MongoDB GridFS; demo mode rejects local uploads. |
| **Build Timeout & Bandwidth** | Standard PyTorch CUDA wheels are ~2.5 GB and can exceed build limits. | Build command installs the CPU-only PyTorch wheel (`https://download.pytorch.org/whl/cpu`, ~180 MB) prior to `requirements.txt`. |
