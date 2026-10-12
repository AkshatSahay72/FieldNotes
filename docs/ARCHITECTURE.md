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

| Component / Layer | Planned Design Status | Implemented Behavior Status (Milestone 4) |
| :--- | :--- | :--- |
| **API Framework (FastAPI)** | Modular routers (`/api/health`, `/api/notes`, `/api/analytics`, `/api/search`) | **IMPLEMENTED** (`/health`, `/api/health`, `/api/notes`, `/api/notes/{note_id}/attachments`) |
| **Database Driver (PyMongo)** | Singleton/lifespan-managed `MongoClient` with connection pooling | **IMPLEMENTED** (lifespan management, ping checks, `get_database`, `get_gridfs` dependencies) |
| **Database (MongoDB Atlas)** | Remote Atlas Cluster storing `notes`, `attachments`, and GridFS buckets | **IMPLEMENTED** (`notes`, `attachments`, `fs.files`, `fs.chunks`) |
| **Configuration** | Pydantic Settings reading environment variables | **IMPLEMENTED** (`pydantic-settings` reading `.env` with validation) |
| **Collections & Schemas** | Document validation rules on `notes` and `attachments` | **IMPLEMENTED** (Pydantic schemas + PyMongo BSON serialization) |
| **Index Management** | Compound, unique, and text indexes configured via PyMongo | **IMPLEMENTED** (`idx_notes_created_at_desc`, `idx_notes_tags`, `idx_notes_text` on `notes`; `idx_attachments_note_id` on `attachments`) |
| **Querying & Text Search** | Tag filtering (`$in`), native text search (`$text`), pagination, deterministic sort | **IMPLEMENTED** (`GET /api/notes` with `tag`, `tags`, `q`, `skip`, `limit`, and `_id` tie-breaker) |
| **Binary Storage (GridFS)** | PyMongo GridFS binary storage with bounded reading & streaming | **IMPLEMENTED** (`fs.files` & `fs.chunks` managed via PyMongo `GridFS`) |
| **Aggregation Pipelines** | Multi-stage analytical queries | **NOT IMPLEMENTED** (Milestone 5) |
| **Vector Search** | Vector index query using `$vectorSearch` | **NOT IMPLEMENTED** (Milestone 6) |

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

---

## 4. Collection Responsibilities & Schemas

Fieldnote avoids relational tables and instead utilizes idiomatic document modeling across two primary collections (`notes` and `attachments`) alongside MongoDB GridFS buckets (`fs.files` and `fs.chunks`).

### 4.1 Collection: `notes`
Stores the primary research notes, tags, and timestamps.

- `_id`: `ObjectId` (MongoDB primary key)
- `title`: `str` (required) — Concise title of the observation or finding
- `content`: `str` (required) — Markdown or plain text content of the note
- `tags`: `list[str]` (required, default `[]`) — Categorical tags for classification
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
1. **`notes.created_at` (DESCENDING)**: Single-field descending index (`idx_notes_created_at_desc`) supports default `GET /api/notes` ordering newest first without in-memory sort stages.
2. **`notes.tags` (ASCENDING / MULTIKEY)**: Multikey B-tree index (`idx_notes_tags`, `[("tags", 1)]`) indexes individual string elements of the `tags` array, accelerating tag filtering queries using `$in`.
3. **`notes` Text Index (`title: "text"`, `content: "text"`)**: Compound native text index (`idx_notes_text`) enables keyword searches across both the note title and body via `$text: {"$search": q}`.
4. **`attachments.note_id` (ASCENDING)**: Single-field index (`idx_attachments_note_id`, `[("note_id", 1)]`) supports fast attachment listing (`GET /api/notes/{note_id}/attachments`) and cascading cleanup lookups without full-collection scans.
5. **Vector Index (Atlas)** (Planned): Configured on `embedding` field with cosine similarity for Milestone 6.

### 6.2 Query Composition & Semantics
- **Tag Filtering Semantics**: Tag queries accept one or multiple tags (`?tag=soil&tag=water` or comma-separated `?tags=soil,water`). Multiple requested tags use **OR semantics** via MongoDB's `$in` operator:
  ```json
  {"tags": {"$in": ["soil", "water"]}}
  ```
  A note matches if its `tags` array contains at least one of the queried tags. Blank or whitespace-only tag parameters return HTTP `400 Bad Request`.
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
1. **Single Text Index per Collection**: MongoDB allows at most **one** text index per collection. Adding a second text index throws an error.
2. **Text Index & Sort Key Restrictions**: Unlike standard B-tree compound indexes, MongoDB text indexes cannot have trailing sort keys. When querying with `$text` and sorting by `[("created_at", -1), ("_id", -1)]`, MongoDB uses `idx_notes_text` to select matching documents and then executes an **in-memory sort stage** (`SORT`). For high-throughput chronological searches on massive datasets, text relevance score (`metaTextScore`) or specialized search engines (Atlas Search) would be evaluated.
3. **No Fuzzy or Typo-Tolerant Matching**: Native MongoDB `$text` search relies on word tokenization, stemming (e.g. "runs" -> "run"), and stop-word removal for supported languages (default: English). It does **not** support fuzzy Levenshtein distance, partial substring regex matching, or typo tolerance.
4. **No Semantic or Vector Understanding**: Native `$text` performs exact lexical/stemmed matching. It does not understand synonyms, context, or embeddings. Semantic retrieval is reserved for Milestone 6 using MongoDB Atlas Vector Search.

