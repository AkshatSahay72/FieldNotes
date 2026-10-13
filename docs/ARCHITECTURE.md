# Fieldnote — Architecture Document

## 1. Architectural Overview

Fieldnote follows a layered, decoupled service architecture designed for straightforward maintenance, testability, and academic evaluation.

```
       +-------------------------------------------------------------+
       |                  Client / Caller Layer                      |
       |  (FastAPI TestClient, cURL / Swagger UI, future Flask Web)  |
       +-------------------------------------------------------------+
                                      │ HTTP (JSON / multipart)
                                      ▼
       +-------------------------------------------------------------+
       |               FastAPI Application Layer                     |
       |  - Route Handlers (REST Endpoints)                         |
       |  - Pydantic Request Validation & Response Serialization     |
       |  - Exception Handlers (HTTP & Database errors)              |
       +-------------------------------------------------------------+
                                      │ In-process Python calls
                                      ▼
       +-------------------------------------------------------------+
       |               Service & Data Access Layer                   |
       |  - Direct PyMongo Database Operations                      |
       |  - Aggregation Pipeline Builders                           |
       |  - Index Management & Verification Routines                |
       +-------------------------------------------------------------+
                                      │ Wire Protocol (mongodb+srv)
                                      ▼
       +-------------------------------------------------------------+
       |                   MongoDB Atlas Cluster                     |
       |  - Collections: notes, attachments                         |
       |  - Secondary Indexes (B-tree & Text)                        |
       |  - Atlas Vector Search Index                                |
       +-------------------------------------------------------------+
```

---

## 2. Distinction: Planned Design vs. Implemented Behavior

| Component / Layer | Planned Design Status | Implemented Behavior Status (Milestone 5) |
| :--- | :--- | :--- |
| **API Framework (FastAPI)** | Modular routers (`/api/health`, `/api/notes`, `/api/analytics`, `/api/search`) | **IMPLEMENTED** (`/health`, `/api/health`, `/api/notes`, `/api/notes/{note_id}/attachments`, `/api/analytics`) |
| **Database Driver (PyMongo)** | Singleton/lifespan-managed `MongoClient` with connection pooling | **IMPLEMENTED** (lifespan management, ping checks, `get_database`, `get_gridfs` dependencies) |
| **Database (MongoDB Atlas)** | Remote Atlas Cluster storing `notes`, `attachments`, and GridFS buckets | **IMPLEMENTED** (`notes`, `attachments`, `fs.files`, `fs.chunks`) |
| **Configuration** | Pydantic Settings reading environment variables | **IMPLEMENTED** (`pydantic-settings` reading `.env` with validation) |
| **Collections & Schemas** | Document validation rules on `notes` and `attachments` | **IMPLEMENTED** (Pydantic schemas + PyMongo BSON serialization) |
| **Index Management** | Compound, unique, and text indexes configured via PyMongo | **IMPLEMENTED** (`idx_notes_created_at_desc`, `idx_notes_created_at_id_desc`, `idx_notes_tags`, `idx_notes_text` on `notes`; `idx_attachments_note_id` on `attachments`) |
| **Querying & Text Search** | Tag filtering (`$in`), native text search (`$text`), pagination, deterministic sort | **IMPLEMENTED** (`GET /api/notes` with `tag`, `tags`, `q`, `skip`, `limit`, and `_id` tie-breaker) |
| **Binary Storage (GridFS)** | PyMongo GridFS binary storage with bounded reading & streaming | **IMPLEMENTED** (`fs.files` & `fs.chunks` managed via PyMongo `GridFS`) |
| **Aggregation Pipelines** | Multi-stage analytical queries | **IMPLEMENTED** (`$unwind`, `$match`, `$group`, `$sort`, `$project`, `$lookup`, `$dateToString`) |
| **Embedding Service & Lifecycle** | In-process vector embeddings & note lifecycle hooks | **IMPLEMENTED** (Milestones 6B, 6D.4: `sentence-transformers/all-MiniLM-L6-v2`, inline `embedding`, `embedding_model`, backfill script verified on live Atlas with dry-run, idempotency, and concurrency protection) |
| **Vector Search API** | Vector search endpoint using `$vectorSearch` | **IMPLEMENTED** (Milestones 6C, 6D.2, 6D.3: verified end-to-end against live MongoDB Atlas cluster; live semantic retrieval confirmed) |
| **Vector Search Index Provisioning** | Atlas Vector Search index `idx_notes_vector` (384-dim, cosine) on `notes` | **IMPLEMENTED** (Milestone 6D.2: provisioned on `fieldnote_db.notes`, status `READY`, queryable `True`) |
| **User Interface (Web)** | Minimal responsive researcher dashboard & analytics UI | **IMPLEMENTED (Phase 2A, 2B, 2C.1 & 2C.2)**: Jinja2 templates, static assets (`/static/*`), accessible mobile navigation drawer, research dashboard with dual text/semantic search, note CRUD modals, Phase 2C.1 Evidence Gallery, and Phase 2C.2 Analytics Visualizations (overview cards, ranked tag bars, UTC activity timeline, evidence ranking with zero-toggle, top-25 limits, independent request-race protection, and fault-tolerant parallel loading) |
| **Public Demo Mode & Seeding** | Read-only demo safety, synthetic seed script, database isolation | **IMPLEMENTED (Phase 2D.1)**: Declarative FastAPI route dependencies rejecting all write operations with HTTP 403 Forbidden; synthetic dataset seed script with Pillow-generated evidence; safety guard preventing accidental targeting of default development database |

---

## 3. Configuration Approach

The application uses **12-factor configuration** driven entirely by environment variables. No secrets or connection strings are hardcoded in the application repository.

- Configuration is defined in `app.config.Settings` using `pydantic-settings`.
- In local development, values are sourced from a `.env` file (excluded from version control).
- In staging/production (e.g. Render), values will be injected directly via environment variables.

### Key Configuration Variables:
- `MONGODB_URI`: Full MongoDB connection string (e.g., `mongodb+srv://...`).
- `DATABASE_NAME`: Name of the target MongoDB database (default: `fieldnote_db`).
- `APP_ENV`: Application environment (`development`, `testing`, `production`).
- `APP_HOST`: Host interface binding (default: `127.0.0.1`).
- `APP_PORT`: Port binding (default: `8000`).
- `MONGODB_SERVER_SELECTION_TIMEOUT_MS`: Timeout for MongoDB commands before failing fast (default: `2000`).
- `UPLOAD_DIR`: Optional local filesystem storage directory.
- `EMBEDDING_MODEL`: SentenceTransformers model identifier (default: `sentence-transformers/all-MiniLM-L6-v2`).
- `DEMO_MODE`: Boolean flag enforcing read-only public demo mode (default: `false`). Rejects all write endpoints with HTTP 403 Forbidden.

---

## 4. Collection Responsibilities & Schemas

Fieldnote avoids relational tables and instead utilizes idiomatic document modeling across two primary collections (`notes` and `attachments`) alongside MongoDB GridFS buckets (`fs.files` and `fs.chunks`).

### 4.1 Collection: `notes`
Stores the primary research notes, tags, timestamps, and vector embeddings.

- `_id`: `ObjectId` (MongoDB primary key)
- `title`: `str` (required) — Concise title of the observation or finding
- `content`: `str` (required) — Markdown or plain text content of the note
- `tags`: `list[str]` (required, default `[]`) — Categorical tags for classification
- `embedding`: `list[float]` (384 finite floats) — Normalized vector embedding generated from `title + "\n\n" + content`
- `embedding_model`: `str` — Model name tag (e.g. `sentence-transformers/all-MiniLM-L6-v2`)
- `created_at`: `datetime` (UTC timestamp, indexed DESC)
- `updated_at`: `datetime` (UTC timestamp)

### 4.2 Collection: `attachments`
Stores metadata and user-written captions/descriptions for uploaded image evidence.

- `_id`: `ObjectId` (MongoDB primary key)
- `note_id`: `ObjectId` (foreign reference to parent note, indexed ASC)
- `file_id`: `ObjectId` (reference to binary file document in `fs.files`)
- `filename`: `str` — Sanitized display filename (never a raw filesystem path)
- `content_type`: `str` — Verified MIME type (`image/jpeg`, `image/png`, or `image/webp`)
- `file_size`: `int` — Size in bytes (bounded to <= 5 MB)
- `caption`: `Optional[str]` — User-provided short title or caption
- `description`: `Optional[str]` — User-authored contextual description of the evidence
- `created_at`: `datetime` (UTC timestamp)

### 4.3 Binary Storage Model: PyMongo GridFS
Binary image payloads are stored in MongoDB GridFS:
- `fs.files`: Tracks binary file chunks count, chunk size, MD5 hash, upload date, and length.
- `fs.chunks`: Stores binary byte chunks (255 KB default chunk size).

#### Ingestion & Safety Controls:
1. **Bounded Reading & Size Enforcement**: File data is read from FastAPI `UploadFile` in 1 MB incremental chunks up to a hard limit of 5 MB (`5 * 1024 * 1024` bytes). Reading aborts immediately with HTTP `413 Content Too Large` if this bound is crossed, preventing memory exhaustion and denial-of-service from unbounded buffering.
2. **True Format Verification (Magic Bytes)**: File content is sniffed using binary magic numbers rather than trusting client-supplied `Content-Type` headers:
   - JPEG: starts with `\xff\xd8\xff`
   - PNG: starts with `\x89PNG\r\n\x1a\n`
   - WebP: starts with `RIFF` and contains `WEBP` signature at byte offset 8-11.
   MIME spoofing or unallowed image formats return HTTP `415 Unsupported Media Type`.
3. **Filename Sanitization**: Client-supplied filenames are sanitized with `os.path.basename` and regex stripping to prevent directory traversal and header injection. Client filenames are never used as server filesystem paths.
4. **Streaming Downloads**: `GET /api/notes/{note_id}/attachments/{attachment_id}/download` uses FastAPI `StreamingResponse` to stream GridFS binary chunks efficiently, setting the stored `content_type` and `Content-Disposition: inline`.

### 4.4 Cascading Deletion & Partial Failure Safety
MongoDB lacks multi-collection foreign key constraints. When a note is deleted via `DELETE /api/notes/{note_id}`:
1. All child attachment metadata records are queried: `attachments.find({"note_id": note_oid})`.
2. For each attachment, the binary data in GridFS is deleted: `gridfs.delete(file_id)`.
3. The attachment metadata records are purged: `attachments.delete_many({"note_id": note_oid})`.
4. Only upon successful attachment cleanup is the parent note deleted: `notes.delete_one({"_id": note_oid})`.

**Failure Handling**: If an error occurs during GridFS or metadata cleanup (e.g., database timeout or driver exception), the cascading operation immediately halts, logs the failure, and **does not delete the parent note**. The endpoint returns HTTP `503 Service Unavailable`, preventing orphaned attachments and ensuring the system never falsely reports successful note deletion when underlying cleanup has failed.

---

## 5. Error Handling Strategy

FastAPI provides an exception handler hierarchy:

1. **PyMongo Driver Errors**:
   - `PyMongoError` (base database connection/query exception) mapped to `503 Service Unavailable` with a structured error response, preventing raw database tracebacks, connection strings, or credentials from leaking.
2. **Resource Resolution Errors**:
   - Non-existent `ObjectId` or missing document queries mapped to `404 Not Found`.
   - Malformed `ObjectId` hex strings caught at input validation and mapped to `400 Bad Request`.
3. **Data Validation Errors**:
   - Pydantic validation errors caught by FastAPI and converted to uniform `422 Unprocessable Entity` JSON responses (e.g., negative pagination `skip`, `limit <= 0`, or `limit > 100`).
   - Query validation errors (e.g., empty search query `?q=` or blank tag filter `?tag=`) mapped to deliberate `400 Bad Request`.
4. **Payload & Format Errors**:
   - Oversized uploads return HTTP `413 Content Too Large`.
   - Disallowed or spoofed file types return HTTP `415 Unsupported Media Type`.
   - Empty files return HTTP `400 Bad Request`.

---

## 6. Indexing & Query Strategy

To ensure queries remain efficient and demonstrate database fundamentals during academic evaluation:

### 6.1 Configured Indexes
1. **`notes.created_at` (DESCENDING)**: Single-field descending index (`idx_notes_created_at_desc`, `[("created_at", -1)]`) retained for backwards-compatibility.
2. **`notes (created_at DESC, _id DESC)` (COMPOUND)**: Compound B-tree index (`idx_notes_created_at_id_desc`, `[("created_at", -1), ("_id", -1)]`) specifically satisfies deterministic pagination sorting. While single-field `created_at` cannot satisfy a compound sort without an in-memory `SORT` stage, this compound index enables MongoDB to scan index entries in exact sort order (`IXSCAN -> FETCH`), eliminating in-memory sorting and collection scans for unfiltered list queries.
3. **`notes.tags` (ASCENDING / MULTIKEY)**: Multikey B-tree index (`idx_notes_tags`, `[("tags", 1)]`) indexes individual string elements of the `tags` array, accelerating tag filtering queries using `$in`.
4. **`notes` Text Index (`title: "text"`, `content: "text"`)**: Compound native text index (`idx_notes_text`) enables keyword searches across both the note title and body via `$text: {"$search": q}`.
5. **`attachments.note_id` (ASCENDING)**: Single-field index (`idx_attachments_note_id`, `[("note_id", 1)]`) supports fast attachment listing (`GET /api/notes/{note_id}/attachments`) and cascading cleanup lookups without full-collection scans.
6. **Vector Index (Atlas)** (Planned): Configured on `embedding` field with cosine similarity for Milestone 6.

### 6.2 Query Composition & Semantics
- **Tag Filtering Semantics**: Tag queries accept one or multiple tags via repeated `?tag=...` parameters, comma-separated `?tags=...`, or both parameters supplied together (e.g. `?tag=soil&tags=water,canopy`). Multiple requested tags use **OR semantics** via MongoDB's `$in` operator:
  ```json
  {"tags": {"$in": ["soil", "water", "canopy"]}}
  ```
  A note matches if its `tags` array contains at least one of the queried tags. Any blank or whitespace-only tag values across either parameter return HTTP `400 Bad Request`.
- **Query Composition**: When both text search and tag filters are supplied, they are composed in a single MongoDB query document with implicit AND semantics:
  ```json
  {
    "tags": {"$in": ["soil", "water"]},
    "$text": {"$search": "nitrogen"}
  }
  ```
- **Pagination**: Supports `skip` (default 0, `ge=0`) and `limit` (default 20, `ge=1`, `le=100`), enforced at request validation (`422 Unprocessable Entity` on invalid bounds). Responses maintain the existing list response format (`List[NoteResponse]`) without altering the contract.
- **Deterministic Sort Tie-Breaker**: To ensure pagination stability when multiple notes share identical `created_at` timestamps, queries use a deterministic compound sort:
  ```python
  cursor.sort([("created_at", -1), ("_id", -1)])
  ```
  Since `_id` values are monotonically generated and unique `ObjectId`s, this tie-breaker prevents page drift or skipped notes across pagination boundaries.

### 6.3 MongoDB Text Search Limitations (Academic & Viva Focus)
1. **Requires Text Index**: Native `$text` queries strictly require a text index to exist on the collection; executing `$text` without a text index results in a database execution error.
2. **Text Index Does Not Optimize Chronological Sorting**: In MongoDB, text indexes cannot include trailing B-tree keys for sorting. A text index does **not** optimize chronological sorting. When querying with `$text` and sorting by `[("created_at", -1), ("_id", -1)]`, MongoDB uses `idx_notes_text` for document filtering and then requires an additional **in-memory sort stage** (`SORT`). For high-throughput chronological searches on massive datasets, relevance score sorting (`metaTextScore`) or specialized search engines (Atlas Search) would be evaluated.
3. **Single Text Index per Collection**: MongoDB allows at most **one** text index per collection. Adding a second text index throws an error.
4. **No Fuzzy or Typo-Tolerant Matching**: Native MongoDB `$text` search relies on word tokenization, stemming (e.g. "runs" -> "run"), and stop-word removal for supported languages (default: English). It does **not** support fuzzy Levenshtein distance, partial substring regex matching, or typo tolerance.
5. **No Semantic or Vector Understanding**: Native `$text` performs exact lexical/stemmed matching. It does not understand synonyms, context, or embeddings. Semantic retrieval is reserved for Milestone 6 using MongoDB Atlas Vector Search.

---

## 7. MongoDB Aggregation Pipelines & Analytics Strategy

Fieldnote provides analytics via dedicated read-only aggregation pipelines in `app/routes/analytics.py`. These endpoints demonstrate multi-stage document transformations, grouping, date formatting, and relational-style collection joins in an academic viva setting.

### 7.1 Analytics Endpoints Summary
- `GET /api/analytics/overview`: Fast high-level counts across notes and attachments.
- `GET /api/analytics/tags`: Tag frequency distribution via `$unwind` and `$group`.
- `GET /api/analytics/activity`: Daily note creation timeline via `$dateToString` and `$group`.
- `GET /api/analytics/attachments`: Per-note attachment counts via `$lookup` and `$size`.

### 7.2 Aggregation Pipeline Definitions & Semantics

#### 1. Tag Frequency Distribution (`/api/analytics/tags`)
```python
[
    {"$unwind": "$tags"},
    {"$match": {"tags": {"$type": "string", "$regex": r"\S"}}},
    {"$group": {"_id": "$tags", "count": {"$sum": 1}}},
    {"$sort": {"count": -1, "_id": 1}},
    {"$project": {"_id": 0, "tag": "$_id", "count": 1}},
]
```
- **Semantics**:
  - `$unwind` splits the `tags` array into separate stream documents. Empty arrays (`[]`) and missing fields are automatically omitted.
  - `$match` strictly requires tags to be non-empty strings with at least one non-whitespace character (excluding nulls, empty strings, and whitespace-only strings), perfectly aligning with `notes_with_tags` in the overview endpoint.
  - `$group` computes the frequency of each tag. Stored tags are case-sensitive as stored (e.g. `"Soil"` and `"soil"` are grouped separately; stored user data is not mutated).
  - Deterministic sort orders by `count` descending, then tag name alphabetically ascending.
  - Returns `[]` when no tagged notes exist.

#### 2. Note Creation Over Time (`/api/analytics/activity`)
```python
[
    {"$match": {"created_at": {"$type": "date"}}},
    {
        "$group": {
            "_id": {
                "$dateToString": {
                    "format": "%Y-%m-%d",
                    "date": "$created_at",
                    "timezone": "UTC",
                }
            },
            "count": {"$sum": 1},
        }
    },
    {"$sort": {"_id": 1}},
    {"$project": {"_id": 0, "date": "$_id", "count": 1}},
]
```
- **Semantics**:
  - `$dateToString` with `timezone: "UTC"` truncates BSON `created_at` datetimes to calendar dates (`YYYY-MM-DD`).
  - Dates with zero notes created are not artificially fabricated.
  - Deterministic sort orders chronologically ascending by calendar date.
  - Returns `[]` when no notes exist.

#### 3. Attachment Counts by Note (`/api/analytics/attachments`)
```python
[
    {
        "$lookup": {
            "from": "attachments",
            "localField": "_id",
            "foreignField": "note_id",
            "as": "attachments",
        }
    },
    {
        "$project": {
            "_id": 0,
            "note_id": {"$toString": "$_id"},
            "title": "$title",
            "attachment_count": {"$size": "$attachments"},
        }
    },
    # (Optional) {"$match": {"attachment_count": {"$gt": 0}}},
    {"$sort": {"attachment_count": -1, "title": 1, "note_id": 1}},
]
```
- **Semantics & Performance**:
  - `$lookup` performs a left outer join from `notes` to `attachments`. The query planner leverages the existing `idx_attachments_note_id` index on `attachments`.
  - `$project` evaluates `{"$size": "$attachments"}` directly inside the MongoDB database engine. **Crucially, attachment documents and binary GridFS chunks are never transmitted to Python**, preventing memory exhaustion.
  - Notes with 0 attachments yield an empty array from `$lookup` and are accurately counted with `attachment_count: 0`. The query parameter `?include_zero=false` allows filtering to notes with at least one attachment.
  - Deterministic sort orders by `attachment_count` descending, then title ascending, then `note_id` ascending.

---

## 8. Vector Search Architecture & Semantic Retrieval (`/api/search/semantic`)

Milestone 6C introduces the dedicated semantic search route (`app/routes/search.py`) providing natural language similarity search over research notes.

### 8.1 Retrieval Flow
1. **Query Validation**:
   - `q`: Required string parameter. Empty or whitespace-only inputs are rejected immediately with HTTP `400 Bad Request`.
   - `limit`: Integer parameter bounded between 1 and 50 (default: 10). Out-of-bounds or non-integer values return HTTP `422 Unprocessable Entity`.
2. **Query Vector Generation**:
   - Converts the natural language query into a 384-dimensional dense vector using the singleton `EmbeddingService` (`sentence-transformers/all-MiniLM-L6-v2`).
   - The query text is encoded directly without title fabrication or ad-hoc preprocessing, matching the training characteristics of the model.
3. **Atlas Vector Search Pipeline**:
   The aggregation pipeline executes on the `notes` collection:
   ```python
   [
       {
           "$vectorSearch": {
               "index": "idx_notes_vector",
               "path": "embedding",
               "queryVector": query_vector,
               "numCandidates": min(max(limit * 10, 20), 500),
               "limit": limit,
           }
       },
       {
           "$project": {
               "_id": 1,
               "title": 1,
               "content": 1,
               "tags": 1,
               "created_at": 1,
               "updated_at": 1,
               "score": {"$meta": "vectorSearchScore"},
           }
       },
   ]
   ```

### 8.2 Architectural Invariants & Safety
- **Candidate Pool Sizing**: `numCandidates` dynamically scales as `10 * limit`, bounded between a minimum of 20 and a maximum of 500. This balances HNSW graph recall with cluster latency and RAM usage.
- **Score Semantics**: The `score` field is populated with `{"$meta": "vectorSearchScore"}`. This is an approximate cosine similarity ranking signal, not a probability or absolute guarantee of relevance.
- **Zero Vector Leakage**: Stored note embeddings and intermediate query vectors are strictly excluded from projection and API response models (`SemanticSearchResult`).
- **Sanitized Failure Handling**:
  - Model loading/inference failures return HTTP `503 Service Unavailable` with clean messages.
  - Recognizable index-not-found / unready index failures from MongoDB return HTTP `503` explaining that the vector search index is unavailable.
  - Unrelated database errors return standard HTTP `503` without leaking credentials or stack traces.
- **Live Verification**: Live semantic query validation verified on Atlas in Milestone 6D.3; live embedding backfill (dry-run, idempotency, concurrency protection) verified on Atlas in Milestone 6D.4.

### 8.3 Atlas Vector Search Index Provisioning (`idx_notes_vector`)

Milestone 6D.2 provisioned and verified the official Atlas Vector Search index on MongoDB Atlas:

- **Target Database & Collection**: `fieldnote_db.notes`
- **Index Name**: `idx_notes_vector`
- **Index Type**: `vectorSearch`
- **Index Definition**:
  ```json
  {
    "fields": [
      {
        "type": "vector",
        "path": "embedding",
        "numDimensions": 384,
        "similarity": "cosine"
      }
    ]
  }
  ```
- **Provisioning Mechanism**: Executed via the safe, auditable CLI script `scripts/provision_vector_index.py` using PyMongo's `SearchIndexModel` API (`collection.create_search_index()`). The script:
  - Validates Atlas connectivity via ping.
  - Refuses duplicate creation if `idx_notes_vector` already exists.
  - Polls Atlas index metadata at 5-second intervals with a 300-second timeout until `status == "READY"` and `queryable == True`.
  - Confirms zero notes were modified or inserted.
- **Current Operational Status**:
  - Atlas Status: `READY`
  - Queryable: `True`
  - Notes Document Count: `0`
  - *Note*: Live semantic query retrieval and live embedding backfill verified end-to-end on MongoDB Atlas in Milestones 6D.3 and 6D.4; baseline collection state verified restored to 0 documents.

---

## 9. User Interface Layer Architecture (Milestone 7 — Phase 2A Foundation)

Fieldnote includes a server-rendered, responsive web interface built directly on top of FastAPI and Jinja2 without external JavaScript frameworks:

```
               +-------------------------------------------------+
               |              Client Browser Request             |
               +-------------------------------------------------+
                                       │
                      ┌────────────────┴────────────────┐
                      ▼                                 ▼
             Browser Route (HTML)              API Route (/api/*)
                      │                                 │
                      ▼                                 ▼
         +──────────────────────────+      +──────────────────────────+
         |      app.routes.ui       |      |    app.routes.{notes,    |
         |  - GET / (Dashboard)     |      |    attachments,search,   |
         |  - GET /analytics        |      |    analytics}            |
         |  - GET /favicon.ico      |      |  - JSON Responses        |
         +──────────────────────────+      +──────────────────────────+
                      │
                      ▼
         +──────────────────────────+
         |     Jinja2 Templates     |
         |  - base.html (Layout)    |
         |  - index.html (Shell)    |
         |  - analytics.html (Shell)|
         |  - 404.html (Custom Err) |
         +──────────────────────────+
                      │
                      ▼
         +──────────────────────────+
         |   Static Assets (/static)|
         |  - css/style.css         |
         |  - js/app.js             |
         |  - favicon.svg           |
         +──────────────────────────+
```

### 9.1 Architectural Principles
- **Zero Framework Bloat**: Uses Vanilla CSS with CSS custom properties (variables) and lightweight Vanilla JS for accessibility and mobile navigation.
- **Mobile-First & Overflow-Safe**: Root elements enforce `overflow-x: hidden` and `box-sizing: border-box`. All containers use fluid sizing and flexible grid definitions.
- **Dual-Mode 404 Exception Handler**:
  - Unmapped browser navigation (`Accept: text/html` without `/api/` prefix) renders `404.html` with a working return link.
  - API endpoints and JSON requests (`/api/*` or `Accept: application/json`) preserve standard JSON error structures (`{"detail": "..."}`) without disruption.
- **Accessible Navigation**: The mobile menu toggle implements explicit ARIA attributes (`aria-expanded`, `aria-controls`), focus management, backdrop dismissal, and `Escape`-key closure.

### 9.2 Research Dashboard & Note Explorer Architecture (Milestone 7 — Phase 2B)

Phase 2B implements the interactive research dashboard controller in `app/static/js/app.js` and Jinja2 template in `app/templates/index.html`:

- **Client State Management**:
  - `searchMode`: Explicitly toggled between `"text"` and `"semantic"`.
  - `searchQuery`: Current active search term.
  - `tagFilter`: Active comma-separated or multi-tag filter string.
  - `skip` & `limit`: Deterministic pagination state (default `skip: 0`, `limit: 20`).
  - `pendingDeleteId`: Target note ID staged for deletion confirmation.

- **Explicit API Endpoint Integration**:
  - **Text Search & Listing**: Calls `GET /api/notes?skip={skip}&limit={limit}`. When query is present, appends `&q={query}`. When tags are present, appends `&tags={tags}` (preserving backend MongoDB `$in` OR semantics).
  - **Atlas Semantic Search**: Calls `GET /api/search/semantic?q={query}&limit={limit}`. Never falls back silently to text search; displays error banner if semantic search or vector index fails.
  - **Note Creation**: Calls `POST /api/notes` with JSON `{title, content, tags}`.
  - **Note Modification**: Calls `GET /api/notes/{id}` to populate modal inputs, then submits `PUT /api/notes/{id}` with updated JSON payload.
  - **Note Deletion**: Accessible confirmation dialog (`role="alertdialog"`) invokes `DELETE /api/notes/{id}` upon user confirmation.

- **Defensive UI & Security Practices**:
  - **XSS Prevention**: Note titles, contents, tags, and dates are strictly rendered using DOM `textContent` and `document.createElement`. Raw user input is never injected into `innerHTML`.
  - **Honest Error Handling**: API error responses (`422`, `404`, `500`, `503`) are surfaced directly with descriptive messaging and contextual retry controls.
  - **Live Notifications**: Toast notification container (`#toast-container`) with `aria-live="polite"` announces async outcomes (creation, update, deletion, search errors).
  - **Accessibility**: Modals manage `aria-modal="true"`, focus trapping, `Escape`-key dismissal, and focus restoration to the triggering button.

### 9.3 Evidence Gallery & Attachment Management Architecture (Milestone 7 — Phase 2C.1)

Phase 2C.1 integrates research evidence attachment viewing and upload directly into the research notes workflow:

- **Note Card Integration**:
  - Each note card in the explorer displays an accessible `📷 Evidence` action button.
  - Clicking opens the Evidence Gallery modal for the targeted note without triggering note editor opening or deletion.

- **Client State & Direct Endpoint Integration**:
  - `activeEvidenceNote`: `{ id, title }` tracking the parent note context.
  - `evidenceList`: In-memory list of `AttachmentResponse` objects fetched from `GET /api/notes/{note_id}/attachments`.
  - `attachmentToDelete`: `{ id, noteId, filename, caption }` staged for deletion confirmation.
  - **Upload Endpoint**: Submits `POST /api/notes/{note_id}/attachments` via `multipart/form-data` with `file`, optional `caption`, and optional `description`. The client omits manual `Content-Type` headers so the browser sets the multipart boundary.
  - **Thumbnail & Full-Size Image Source**: Loads directly from `GET /api/notes/{note_id}/attachments/{attachment_id}/download` (backend returns `Content-Disposition: inline` with genuine image MIME type).
  - **Deletion Endpoint**: Calls `DELETE /api/notes/{note_id}/attachments/{attachment_id}`. On HTTP 204 No Content, updates the UI and refreshes the gallery without attempting to parse JSON.

- **Defensive Design & Accessibility**:
  - **Client File Validation**: Pre-validates 5.0 MB file size limit and MIME types (`image/jpeg`, `image/png`, `image/webp`) for immediate feedback while backend Pillow validation remains authoritative.
  - **Broken Image Grace**: Prevents infinite retry loops by detaching `onerror` and rendering an accessible fallback indicator.
  - **Stacked Modal Accessibility**: Supports stacked dialogs (Evidence Modal -> Lightbox / Delete Confirmation), trapping `Tab` and `Shift+Tab` focus in the topmost active dialog and restoring focus to the specific triggering button upon closure.
  - **Safe Rendering**: All user-authored captions, descriptions, and filenames are rendered exclusively via DOM `textContent` and `document.createElement`.

### 9.4 Analytics Visualizations Architecture (Milestone 7 — Phase 2C.2)

Phase 2C.2 implements the interactive analytics visualizations on `/analytics` powered by multi-stage MongoDB aggregation pipelines:

- **Client State & Independent Race-Condition Protection**:
  - `reqIds`: Monotonically increasing independent request sequence counters per section (`overview`, `tags`, `activity`, `attachments`).
  - Stale network responses in one section cannot overwrite newer results or disrupt other sections.
  - Toggling the zero-attachments checkbox increments only `reqIds.attachments`, maintaining complete isolation from overview, tag, and activity panels.

- **Direct Backend Aggregation Endpoint Integration**:
  - **Overview Cards**: Calls `GET /api/analytics/overview` returning `{total_notes, total_attachments, notes_with_tags}`. Correctly displays zero values (`0`, never blank); avoids synthesizing unsubstantiated percentages or ratios.
  - **Tag Frequency Distribution**: Calls `GET /api/analytics/tags` returning `{tag, count}` ordered deterministically by count descending and tag ascending. Renders horizontal CSS progress bars with ARIA progressbar attributes and safe text wrapping for long tag names.
  - **Research Activity Timeline**: Calls `GET /api/analytics/activity` returning `{date, count}` in UTC chronological order. Plots actual `YYYY-MM-DD (UTC)` dates without fabricating artificial zero-activity calendar entries.
  - **Evidence Distribution**: Calls `GET /api/analytics/attachments?include_zero={true|false}`. Supports toggling zero-attachment notes. Implements a maximum display limit of 25 records with explicit count messaging (`Showing top 25 of X research notes` vs. `Showing X of X research notes`). Long titles are visually truncated with CSS ellipsis while preserving full accessible text via `title` and `aria-label` attributes.

- **Fault-Tolerant Parallel Loading & Per-Section Retries**:
  - Uses `Promise.allSettled` for concurrent section fetching; individual endpoint failures (e.g. 503 Service Unavailable) do not suppress or break successful panels.
  - Each section features dedicated loading (`aria-live="polite"`), error (`role="alert"`), empty, and retry hooks.
  - Global `#btn-refresh-analytics` refreshes all panels concurrently, while section-specific retry buttons retry only their corresponding panel.

- **Security & Accessibility**:
  - **Zero Charting Dependencies**: Built entirely with Vanilla JavaScript and CSS design tokens; no external visualization libraries.
  - **XSS Immunity**: User-controlled tags, titles, dates, and counts are rendered exclusively using `document.createElement` and `textContent`.
  - **Responsive Design**: Fluid CSS grid and flexbox layouts maintain full usability down to 320px viewport width without horizontal page scroll.

---

## 10. Public Demo Mode & Database Isolation Architecture (Phase 2D.1)

Phase 2D.1 prepares Fieldnote for public demonstration using synthetic data with anonymous read-only access and server-side write rejection.

### 10.1 Declarative Route Protection Layer
- **Dependency Guard**: Implements `check_demo_mode` in `app/config.py` as a FastAPI route-level dependency (`dependencies=[Depends(check_demo_mode)]`).
- **Pre-execution Interception**: When `DEMO_MODE=true` is active, write-capable routes (`POST /api/notes`, `PUT /api/notes/{id}`, `DELETE /api/notes/{id}`, `POST /api/notes/{id}/attachments`, `DELETE /api/notes/{id}/attachments/{id}`) abort immediately with **HTTP 403 Forbidden** prior to request body parsing, file stream consumption, or database access.
- **Consistent Error Structure**: Emits standard non-sensitive JSON payload:
  ```json
  {"detail": "Operation not permitted in demo mode."}
  ```
- **Preserved Development Mode**: When `DEMO_MODE=false` (default), the guard passes silently, leaving all development workflows and tests unaffected.

### 10.2 Preserved Anonymous Read-Only Surface
All query, retrieval, and visualization endpoints remain open and fully functional:
- Research observation feeds: `GET /api/notes` (with pagination, sort, and tag filtering).
- Single note inspection: `GET /api/notes/{id}`.
- Native MongoDB text search: `GET /api/notes?q=...` (`$text`).
- Semantic vector search: `GET /api/search/semantic?query=...` (`$vectorSearch`).
- Analytics pipelines: `GET /api/analytics/overview`, `/tags`, `/activity`, `/attachments`.
- Evidence attachments: `GET /api/notes/{note_id}/attachments` and binary streaming `GET /api/notes/{note_id}/attachments/{id}/download`.
- Web UI: HTML endpoints `/` and `/analytics` display a polite demo banner (`.demo-banner`) informing visitors that persistent modifications are disabled.

### 10.3 Database Isolation & Fail-Closed Startup Strategy
- **Explicit Database Selection**: Uses the 12-factor configuration setting `DATABASE_NAME` (e.g. `DATABASE_NAME=fieldnote_demo`).
- **Fail-Closed Application Startup Validation**: In `app/config.py`, a Pydantic `@model_validator(mode="after")` enforces that when `DEMO_MODE=true`:
  - `DATABASE_NAME` must be explicitly configured rather than relying on the default.
  - `DATABASE_NAME` cannot target the default development database (`fieldnote_db`).
  - If violated, the application refuses to start up with a clear configuration validation error.
- **Non-destructive Isolation**: The primary development database (`fieldnote_db`) is untouched and retains its distinct document state.
- **Seeding Development Guard**: Seeding utilities verify the target database name and automatically abort if targeting `fieldnote_db` without an explicit `--allow-default-db` override flag.

### 10.4 Idempotent Synthetic Data Seeding (`scripts/seed_demo_data.py`)
- **Academic Synthetic Data**: Populates clearly fictional research observations spanning multiple domains (subterranean mycology, lacustrine sediment stratigraphy, cryogenics, marine bioacoustics, drone telemetry, and synthetic polymer kinetics).
- **Synthetic Evidence Images**: Generates deterministic, lightweight scientific charts and spectrograms in-memory using Pillow (`PIL.Image`, `ImageDraw`) without external image downloads or file system dependencies.
- **Compensating GridFS Cleanup**: If inserting attachment metadata fails after an image chunk is uploaded to GridFS, the newly uploaded GridFS file is automatically cleaned up, preventing orphaned GridFS chunks while keeping pre-existing files intact.
- **Production Environment Guard**: The seed script unconditionally refuses to execute if `APP_ENV=production`.
- **Strict Idempotency**: Notes are matched on `title`; attachments are matched on `(note_id, filename)`. Existing documents are safely skipped, making repeated script execution zero-mutation and duplicate-free.
- **No Public Seeding Endpoints**: Seeding is strictly an operator CLI command; no HTTP endpoints exist for seeding, resetting, or wiping data.

### 10.5 Security Boundaries & Limitations
- **Application-Layer Enforcement**: Demo protection is enforced within the FastAPI application layer. It is suited for academic viva demonstrations and public portfolio hosting.
- **Non-Goals Preserved**: It deliberately does not implement user authentication, multi-tenancy, or MongoDB Atlas user role revocation. Database connections from the server still use authenticated connection strings configured via environment variables.

### 10.6 Automated Test Suite Isolation (`tests/conftest.py`)
- **Guaranteed Offline Execution**: Root pytest configuration (`tests/conftest.py`) forces `APP_ENV=testing` and injects dummy loopback settings (`mongodb://localhost:27017`) before test suite collection.
- **Lifespan Protection**: Prevents the application `lifespan` hook from executing index checks against remote clusters during test startup even when a local `.env` contains live credentials.

---

## 11. Production Deployment Architecture (Render Web Service — Phase 2D.2)

Fieldnote is engineered to deploy cleanly as a containerized web service on cloud PaaS providers, specifically tailored for Render.

### 11.1 Infrastructure as Code Specification (`render.yaml`)
Deployment topology is defined declaratively using Render's Infrastructure-as-Code Blueprint format:
- **Service Type**: `web` (FastAPI ASGI application).
- **Runtime**: `python` with `PYTHON_VERSION: 3.11.9`.
- **Plan**: `free` (512 MB RAM, shared CPU).
- **Health Check Path**: `/health` (probes ASGI availability and MongoDB Atlas ping response before routing live traffic).
- **Binding**: Uses dynamic `$PORT` environment variable provided by Render.

### 11.2 Process Model & Memory Optimization
- **Single Uvicorn Worker**: The start command explicitly configures:
  ```bash
  uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1
  ```
- **Memory Footprint Breakdown**:
  - Base Python + FastAPI + PyMongo + Jinja2: ~80–100 MB.
  - PyTorch (CPU) + SentenceTransformers + `all-MiniLM-L6-v2` weights: ~200–250 MB.
  - Total Resident Memory: ~280–350 MB.
- **Out-of-Memory (OOM) Prevention**: Multi-worker configurations (`--workers 2+`) replicate the heavy PyTorch runtime across worker processes, exceeding the Render free tier's 512 MB memory limit and causing kernel OOM kills (`Exit Code 137`). Enforcing `--workers 1` ensures continuous stability within memory ceilings.

### 11.3 CPU-Only PyTorch Build Optimization
Standard PyPI wheels for `torch` default to CUDA-bundled packages exceeding 2.5 GB in download and disk space. To prevent build timeouts and excessive disk utilization on Render, the build command explicitly pre-installs the official CPU-only PyTorch wheel:
```bash
pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && pip install --no-cache-dir -r requirements.txt
```
When `sentence-transformers>=3.0.0` is subsequently installed from `requirements.txt`, its PyTorch dependency is already satisfied by the lightweight CPU wheel (~180 MB), cutting build duration to ~1–2 minutes.

### 11.4 Embedding Model Caching & Deployment Lifecycle
- **Dynamic Hub Loading**: The service relies on SentenceTransformers' native download resolution against the Hugging Face Hub (`sentence-transformers/all-MiniLM-L6-v2`).
- **No Local Artifact Couplings**: The codebase does not depend on local developer model caches or large binary files committed to Git.
- **Cache Persistence**: Cached weights are stored under Hugging Face's default cache structure and loaded into memory lazily upon the first semantic search request.

### 11.5 Network Boundaries & MongoDB Atlas Security
Render free and individual web services utilize dynamic outbound IPs without dedicated static allocations:
- **Atlas Network Access**: Configuring `0.0.0.0/0` ("Allow Access from Anywhere") is required for dynamic IP routing on free tiers.
- **Compensating Security Controls**:
  - The database user account configured via `MONGODB_URI` must be restricted to `readWrite` strictly on the dedicated demo database (`fieldnote_demo`).
  - Strict password entropy (32+ characters) and mandatory TLS encryption over SCRAM-SHA-256.
  - Time-limited access entries in Atlas Network Access for evaluation windows.
  - Upgrading to Render Team plans enables **Static Outbound IPs**, allowing exact IP whitelisting in Atlas.

### 11.6 Operational Seeding Architecture
- **Air-Gapped Seeding**: No seed or reset HTTP endpoints are exposed on the public web service.
- **Out-of-Band Operator Execution**: Seeding is executed exclusively by an authorized operator from a trusted administrative environment targeting `DATABASE_NAME=fieldnote_demo` with `APP_ENV != production`.
- **Production Guard Enforcement**: The seed script refuses execution if `APP_ENV=production`.
