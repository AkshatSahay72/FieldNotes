# Fieldnote

> **A Personal Memory Archive & Research Notes System using MongoDB**

Fieldnote is a lightweight personal application built with **FastAPI** and **PyMongo** designed to showcase core MongoDB concepts, including native document modeling, indexing, aggregation pipelines, and MongoDB Atlas Vector Search.

Guided by the product principle **"Fieldnote helps you remember your life, not manage your life"**, the system provides low-friction memory capture, chronological timeline exploration, conceptual semantic recall, and structured topic archiving—without AI chatbot bloat or complex multi-tenant workspace clutter.

---

## Academic Focus

This project is tailored for an academic evaluation / viva setting. It deliberately avoids high-level Object-Document Mappers (ODMs) like MongoEngine or Beanie so that direct PyMongo driver usage, queries, indexes, and aggregation stages are transparent and explainable.

### Core Capabilities
1. **Personal Memory & Notes Management**: Idiomatic document CRUD operations with Pydantic validation across five entry classifications: `memory`, `journal`, `idea`, `learning`, and `research`.
2. **Evidence & Attachments**: Image uploads (JPEG, PNG, WebP) with user-provided captions, structured metadata, and binary streaming via PyMongo GridFS.
3. **Optimized Indexing**: Single-field, compound, and native text search indexes with query performance explainability.
4. **Analytics Aggregation Pipelines**: Multi-stage aggregation pipelines for tag analytics, daily activity timelines, and evidence rankings.
5. **Semantic Retrieval**: 384-dimensional vector embeddings and MongoDB Atlas Vector Search (`$vectorSearch`).
6. **Single-Owner Security**: First-party Argon2id password hashing, HTTP-only session cookies, double-submit CSRF defenses, brute-force rate-limiting, and fail-closed database separation.

- [IMPLEMENTATION_LOG.md](docs/IMPLEMENTATION_LOG.md): Current progress, decisions, verification records, and next milestone.

---

## 10-Phase Project Verification & Status Table

The Fieldnote system was implemented and hardened across 10 progressive phases:

| Phase | Phase Name | Implemented Functionality | Tests & Verification Performed | Remaining Limitations | Final Status |
| :---: | :--- | :--- | :--- | :--- | :---: |
| **01** | Documentation & Backend Foundation | FastAPI lifespan, PyMongo connection management, `/health` endpoint with live database ping and timeout controls. | `tests/test_health.py` (3 tests): ping response, timeout handling, connection lifespan. | Requires reachable MongoDB instance. | **Complete** |
| **02** | Personal Memory & Notes Data Model | Direct PyMongo CRUD (`POST/GET/PUT/DELETE /api/notes`), BSON ObjectId validation, 5 entry types (`journal`, `memory`, `idea`, `learning`, `research`), fail-safe error handling. | `tests/test_notes.py`, `tests/test_notes_edge_cases.py` (28 tests): CRUD, pagination, edge cases. | Single-owner / public demo records; no multi-tenant sharing. | **Complete** |
| **03** | PyMongo GridFS Evidence & Image Attachments | Binary chunk streaming (255 KB), cascading deletion on note deletion, magic byte + Pillow validation (JPEG, PNG, WebP ≤ 5 MB), safe filename sanitization. | `tests/test_attachments.py` (22 tests): upload bounds, MIME validation, streaming, cascading delete. | Non-image files (.pdf, .zip) intentionally rejected. | **Complete** |
| **04** | Indexing, Multikey Filtering & Text Search | Compound sort index `idx_notes_created_at_id_desc`, compound text index `idx_notes_text`, multikey tag filtering with `$in` OR semantics. | `tests/test_indexes.py` (8 tests): compound sorting, explain plans, text search stem matching. | Full-text search requires pre-built text index. | **Complete** |
| **05** | Aggregation Analytics Pipelines | Multi-stage aggregation pipelines: `$unwind` & `$group` for tags, `$dateToString` for daily activity, `$lookup` & `$size` for child attachment rankings. | `tests/test_analytics.py` (16 tests): aggregation correctness, empty DB states, ranking limits. | Bound by MongoDB aggregation memory limits. | **Complete** |
| **06** | Vector Embeddings & Atlas Vector Search | Dense vector embeddings (384-dim, `all-MiniLM-L6-v2`), `$vectorSearch` pipeline, bounded candidate pool (`calculate_num_candidates`), graceful fallback on index unavailability (HTTP 503). | `tests/test_search.py`, `tests/test_embedding.py` (24 tests): vector similarity, dimension validation, fallback error handling. | Requires MongoDB Atlas Search index (`idx_notes_vector`) for vector execution; keyword search fallback active when unavailable. | **Complete** |
| **07** | Researcher Dashboard & Public Demo Mode | Responsive Jinja2/CSS/JS interface (`/` and `/analytics`), accessible dialogs (`role="dialog"`), image lightbox, fail-closed read-only demo mode (`DEMO_MODE=true` rejects writes with 403), synthetic dataset seeder (`scripts/seed_demo_data.py`). | `tests/test_ui.py`, `tests/test_demo_mode.py`, `tests/test_deployment.py` (42 tests): UI shells, demo mode guards, seed cleanup. | Demo mode is globally read-only across all visitors. | **Complete** |
| **08** | Single-Owner Auth & Route Protection | Argon2id password hashing, HTTP-only secure session cookies, double-submit CSRF tokens, sliding-window rate limiting, strict query scoping by `user_id`. | `tests/test_auth.py`, `tests/test_authorization.py`, `tests/test_modes_and_separation.py` (72 tests): hashing, CSRF rejections, route protection matrix. | Single-owner architecture deliberately rejects public user registration. | **Complete** |
| **09** | Product Identity & Personal Memory Workflows | Dedicated Capture, Timeline (chronological day dividers), Recall (semantic match badges), Archive (tag & type filters), minimal calm visual identity (#14263D, #0D9488, #F4F7FA). | UI regression inspection, browser verification recording (`release_gate_browser_test_1791918847545.webp`), CSS/JS contract checks. | No task boards, Kanban, or project management widgets (by design). | **Complete** |
| **10** | Final Audit, Public Access Fix & Atlas Hardening | Public unauthenticated access verified for all read/browse/recall/archive/analytics/attachments; demo seeded data protected; least-privilege Atlas database user roles documented; full test suite passes (243 tests); Git diff audited and cleanly committed. | Full pytest suite (243 passed in ~12s), `git diff --check`, `python -m compileall app scripts tests` (0 errors). | Atlas role changes must be applied manually by cluster admin in Atlas console. | **Complete** |

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

### 3. MongoDB Atlas Least-Privilege Database User Hardening

In shared multi-environment clusters, database users should adhere strictly to the principle of least privilege. Overly broad administrative roles (such as `atlasAdmin@admin` or `readWriteAnyDatabase@admin`) must never be assigned to application workloads.

#### Recommended Role Scoping Matrix

| Database User | Intended Scope | Recommended MongoDB Atlas Built-in Role | Unnecessary Roles to Revoke |
| :--- | :--- | :--- | :--- |
| **`fieldnote_demo`** | Public Web Showcase (Render) | `readWrite@fieldnote_demo` | Revoke `readWriteAnyDatabase@admin` |
| **`fieldnote_app`** | Private Single-Owner Instance | `readWrite@fieldnote_private` | Revoke `readWriteAnyDatabase@admin` |
| **`akshatsahay19_db_user`** | Cluster Administrator | `atlasAdmin@admin` (Console only) | NEVER use in `.env` or application configs |

#### Manual Step-by-Step Atlas Permission Hardening Procedure

1. **Log in to MongoDB Atlas**: Navigate to [cloud.mongodb.com](https://cloud.mongodb.com) and select your project.
2. **Access Database Access**:
   - In the left sidebar under **Security**, click **Database Access**.
3. **Harden `fieldnote_demo`**:
   - Locate user `fieldnote_demo` and click **Edit**.
   - Under **Database User Privileges**, change **Built-in Role** from `readWriteAnyDatabase` to **Specific Privileges** / **Built-in Roles**.
   - Add privilege: Role `readWrite` on Database `fieldnote_demo`.
   - Ensure NO privileges exist for `fieldnote_private`, `fieldnote_db`, or `admin`.
   - Click **Update User**.
4. **Harden `fieldnote_app`**:
   - Locate user `fieldnote_app` and click **Edit**.
   - Change role to `readWrite` on Database `fieldnote_private` only.
   - Click **Update User**.
5. **Secure Administrative Credentials**:
   - Retain `akshatsahay19_db_user` purely for browser-based cluster management. Do not place its password in repository code or hosting environments.

#### Atlas Vector Search Index Definition (`idx_notes_vector`)

To support semantic vector recall on `fieldnote_demo`:
1. In Atlas, click **Database** > **Browse Collections**.
2. Select database `fieldnote_demo` and collection `notes`.
3. Click the **Atlas Search** tab > **Create Search Index** > **JSON Editor**.
4. Select database `fieldnote_demo` and collection `notes`, name the index `idx_notes_vector`, and paste the following definition:
   ```json
   {
     "fields": [
       {
         "numDimensions": 384,
         "path": "embedding",
         "similarity": "cosine",
         "type": "vector"
       }
     ]
   }
   ```
5. Click **Next** and **Create Search Index**. The index will show status `READY` once synchronization completes.

### 4. Render Operational Constraints & Mitigations

| Constraint | Operational Impact | Architectural Mitigation in Fieldnote |
| :--- | :--- | :--- |
| **Build Timeout & Bandwidth** | Standard PyTorch CUDA wheels are ~2.5 GB and exceed build limits. | Build command installs CPU-only wheel (`download.pytorch.org/whl/cpu`, ~180 MB) before `requirements.txt`. |
| **Memory Ceiling (512 MB)** | Free PaaS instances enforce strict memory caps. | Single worker `--workers 1` in `startCommand` prevents multi-process memory multiplication. |
| **Inactivity Spin-down** | Free instances spin down after 15 minutes of inactivity. | First request incurs ~30s cold start; subsequent requests run at low latency. Keep `/health` lightweight. |
| **Ephemeral Filesystem** | Local disk storage is discarded on dyno restart or redeployment. | Image attachments stream directly to/from PyMongo GridFS in MongoDB Atlas. |

---

## Local Development & Test Execution

### 1. Local Environment Setup

```bash
# 1. Clone repository
git clone https://github.com/AkshatSahay72/FieldNotes.git
cd FieldNotes

# 2. Create virtual environment
python -m venv .venv
# On Windows (PowerShell):
.venv\Scripts\Activate.ps1
# On Linux/macOS:
source .venv/bin/activate

# 3. Install CPU-only PyTorch and project dependencies
pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt

# 4. Configure local environment
cp .env.example .env
# Edit .env with your local settings:
# APP_ENV=development
# MONGODB_URI=mongodb://localhost:27017
# DATABASE_NAME=fieldnote_db
```

### 2. Running Automated Tests

Fieldnote includes an extensive automated test suite of 243 tests covering authentication, route authorization, CRUD, GridFS streaming, Atlas search, analytics, and fail-closed demo mode:

```bash
# Run complete test suite (executes isolated offline via tests/conftest.py):
pytest -v

# Run targeted test suites:
pytest tests/test_notes.py tests/test_attachments.py
pytest tests/test_auth.py tests/test_authorization.py
pytest tests/test_demo_mode.py tests/test_modes_and_separation.py
pytest tests/test_deployment.py

# Python syntax compilation check:
python -m compileall app scripts tests

# Whitespace and formatting check:
git diff --check
```

### 3. Manual Smoke-Test Checklist

Use this checklist to verify a local instance or the live public deployment (`https://fieldnote-jzvx.onrender.com`):

- [ ] **Health Check (`/health`)**: Returns HTTP 200 with `{"status": "healthy", "database": "connected"}`.
- [ ] **Public Dashboard Browsing (`/`)**: Page loads with Navy/Teal/Off-white theme without prompting for login.
- [ ] **Timeline Feed**: Seeded notes render chronologically with date badges and classification pills (`Journal`, `Idea`, etc.).
- [ ] **Tag Filtering**: Clicking tag pills filters observation cards using MongoDB `$in` OR semantics.
- [ ] **Text Search**: Typing in search bar and pressing Enter executes `$text` search; zero matches show clean empty state.
- [ ] **Recall (Semantic Search)**: Switching to Semantic Search queries Atlas Vector Search; results display similarity percentage badges.
- [ ] **Evidence Lightbox**: Clicking `📷 Evidence` on a note opens the gallery; clicking a thumbnail opens the full-size image lightbox.
- [ ] **Analytics View (`/analytics`)**: Overview counters, tag frequency bars, daily activity timeline, and evidence ranking cards render correctly.
- [ ] **Demo Mode Write Protection**: Clicking `+ New Entry` or submitting a form in demo mode triggers an informative toast explaining that the demo is read-only.
- [ ] **Responsive Navigation**: Resizing to mobile viewport reveals hamburger menu; opening drawer displays all navigation links with accessible focus trap.

---

## Academic Evaluation & Viva Guide

This section summarizes key technical talking points and suggested presentation materials for the academic defense:

### 1. MongoDB Proficiency Matrix (Viva Defense Points)

| Evaluated Concept | Implementation Location | Viva Explanation / Demonstration |
| :--- | :--- | :--- |
| **Direct PyMongo Usage** | `app/db.py`, `app/routes/notes.py` | Explain avoiding ORM/ODM impedance mismatches: queries use raw BSON documents and explicit driver methods (`insert_one`, `find`, `find_one_and_update`, `delete_one`). |
| **Secondary & Compound Indexes** | `app/db.py:init_db_indexes` | Explain `idx_notes_created_at_id_desc`: compound B-tree index on `[("created_at", -1), ("_id", -1)]` satisfying deterministic pagination sorting without memory-intensive sort stages. |
| **Native Text Search** | `app/routes/notes.py:build_notes_query` | Explain compound text index `idx_notes_text` on `{title: "text", content: "text"}` and `$text` / `$search` operator with stem matching. |
| **Aggregation Pipelines** | `app/routes/analytics.py` | Explain multi-stage pipelines: `$unwind` on multikey tags, `$group` with `$sum`, `$dateToString` for chronological bucketing, and `$lookup` for child attachment counts. |
| **Vector Search (`$vectorSearch`)** | `app/routes/search.py` | Explain 384-dimensional cosine similarity embeddings (`sentence-transformers/all-MiniLM-L6-v2`), Atlas vector index definition, and candidate bounding (`numCandidates`). |
| **Chunked Binary Storage (GridFS)** | `app/routes/attachments.py` | Explain storing binary image streams in `fs.files` and `fs.chunks` (255 KB chunks), cascading deletion, and keeping large binaries out of BSON 16 MB document limits. |

### 2. Suggested Screenshots for Academic Report & Slides

1. **Figure 1 — Personal Memory Journal & Timeline**:
   - Screenshot of the main dashboard (`/`) displaying the timeline with date headers ("Today", "Yesterday"), entry classification badges (`Journal`, `Idea`, `Memory`), and tag pills.
2. **Figure 2 — Semantic Vector Recall in Action**:
   - Screenshot of Recall view showing natural-language query matching (e.g. searching for emotional or conceptual phrases) with transparent similarity match badges (`89% match`).
3. **Figure 3 — PyMongo GridFS Evidence Lightbox**:
   - Screenshot of an open photo evidence modal and full-size lightbox streaming directly from GridFS with MIME metadata.
4. **Figure 4 — MongoDB Aggregation Analytics Dashboard (`/analytics`)**:
   - Screenshot of the analytics page displaying overview cards, ranked tag frequency bars, and chronological activity trends.
5. **Figure 5 — MongoDB Atlas Search Index Configuration**:
   - Screenshot from MongoDB Atlas UI showing `idx_notes_vector` in `READY` status on `notes.embedding`.
6. **Figure 6 — Automated Test Suite Pass**:
   - Terminal screenshot of `pytest -v` completing 240+ tests across authentication, CRUD, GridFS, search, and mode separation in ~12 seconds.
