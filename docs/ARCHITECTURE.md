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
| **User Interface (Web)** | Minimal responsive researcher dashboard & analytics UI | **IMPLEMENTED (Phase 2A, 2B & 2C.1)**: Jinja2 templates, static assets (`/static/*`), accessible mobile navigation drawer, research dashboard with dual text/semantic search, note CRUD modals, and Phase 2C.1 Evidence Gallery (GridFS image upload, thumbnail grid, full-size lightbox, attachment deletion) |

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
