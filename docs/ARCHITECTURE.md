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

| Component / Layer | Planned Design Status | Implemented Behavior Status (Milestone 3B) |
| :--- | :--- | :--- |
| **API Framework (FastAPI)** | Modular routers (`/api/health`, `/api/notes`, `/api/analytics`, `/api/search`) | **IMPLEMENTED** (`/health`, `/api/health`, `/api/notes`, `/api/notes/{note_id}/attachments`) |
| **Database Driver (PyMongo)** | Singleton/lifespan-managed `MongoClient` with connection pooling | **IMPLEMENTED** (lifespan management, ping checks, `get_database`, `get_gridfs` dependencies) |
| **Database (MongoDB Atlas)** | Remote Atlas Cluster storing `notes`, `attachments`, and GridFS buckets | **IMPLEMENTED** (`notes`, `attachments`, `fs.files`, `fs.chunks`) |
| **Configuration** | Pydantic Settings reading environment variables | **IMPLEMENTED** (`pydantic-settings` reading `.env` with validation) |
| **Collections & Schemas** | Document validation rules on `notes` and `attachments` | **IMPLEMENTED** (Pydantic schemas + PyMongo BSON serialization) |
| **Index Management** | Compound, unique, and text indexes configured via PyMongo | **IMPLEMENTED** (`idx_notes_created_at_desc` on `notes`, `idx_attachments_note_id` on `attachments`) |
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
   - Pydantic validation errors caught by FastAPI and converted to uniform `422 Unprocessable Entity` JSON responses.
4. **Payload & Format Errors**:
   - Oversized uploads return HTTP `413 Content Too Large`.
   - Disallowed or spoofed file types return HTTP `415 Unsupported Media Type`.
   - Empty files return HTTP `400 Bad Request`.

---

## 6. Indexing & Query Strategy

To ensure queries remain efficient and demonstrate database fundamentals during academic evaluation:
1. **`notes.created_at` (DESCENDING)**: Single-field descending index (`idx_notes_created_at_desc`) supports `GET /api/notes` ordering newest first without in-memory sort stages.
2. **`attachments.note_id` (ASCENDING)**: Single-field index (`idx_attachments_note_id`) supports fast attachment listing (`GET /api/notes/{note_id}/attachments`) and cascading cleanup lookups without full-collection scans.
3. **Multikey index on `notes.tags`** (Planned): Tag-based filtering for Milestone 4.
4. **Text index on `title` and `content`** (Planned): MongoDB native full-text search with relevance scoring for Milestone 4.
5. **Vector Index (Atlas)** (Planned): Configured on `embedding` field with cosine similarity for Milestone 6.

