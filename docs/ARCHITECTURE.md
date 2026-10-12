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

| Component / Layer | Planned Design Status | Implemented Behavior Status (Milestone 0) |
| :--- | :--- | :--- |
| **API Framework (FastAPI)** | Modular routers (`/api/health`, `/api/notes`, `/api/analytics`, `/api/search`) | **NOT IMPLEMENTED** (Directories created only) |
| **Database Driver (PyMongo)** | Singleton/lifespan-managed `MongoClient` with connection pooling | **NOT IMPLEMENTED** |
| **Database (MongoDB Atlas)** | Remote Atlas Cluster storing `notes` and `attachments` | **NOT IMPLEMENTED** (Connection string template in `.env.example`) |
| **Configuration** | Pydantic Settings reading environment variables | **NOT IMPLEMENTED** |
| **Collections & Schemas** | Document validation rules on `notes` and `attachments` | **NOT IMPLEMENTED** |
| **Index Management** | Compound, unique, and text indexes configured via PyMongo | **NOT IMPLEMENTED** |
| **Aggregation Pipelines** | Multi-stage analytical queries | **NOT IMPLEMENTED** |
| **Vector Search** | Vector index query using `$vectorSearch` | **NOT IMPLEMENTED** |

---

## 3. Configuration Approach

The application uses **12-factor configuration** driven entirely by environment variables. No secrets or connection strings are hardcoded in the application repository.

- Configuration will be defined in a centralized settings module using `pydantic-settings`.
- In local development, values will be sourced from a `.env` file (excluded from version control).
- In staging/production (e.g. Render), values will be injected directly via environment variables.

### Key Configuration Variables:
- `MONGODB_URI`: Full MongoDB connection string (e.g., `mongodb+srv://...`).
- `DATABASE_NAME`: Name of the target MongoDB database (default: `fieldnote_db`).
- `APP_ENV`: Application environment (`development`, `testing`, `production`).
- `APP_HOST`: Host interface binding (default: `127.0.0.1`).
- `APP_PORT`: Port binding (default: `8000`).
- `UPLOAD_DIR`: Local filesystem directory for storing binary attachments.

---

## 4. Planned Collection Responsibilities & Schemas

Fieldnote avoids relational tables and instead utilizes idiomatic document modeling across two primary collections: `notes` and `attachments`.

### 4.1 Collection: `notes`
Stores the primary research notes, tags, metadata, and references to attachments.

- `_id`: `ObjectId` (MongoDB primary key)
- `title`: `str` (required, indexed) — Concise title of the observation or finding
- `body`: `str` (required) — Markdown or plain text content of the note
- `tags`: `list[str]` (required, default `[]`, multikey indexed) — Categorical tags for classification
- `attachment_ids`: `list[ObjectId]` (default `[]`) — Explicit references to documents in the `attachments` collection
- `created_at`: `datetime` (UTC timestamp, indexed)
- `updated_at`: `datetime` (UTC timestamp)
- `embedding`: `list[float]` (optional, planned for Milestone 6) — High-dimensional vector embedding for semantic search

**Modeling rationale**: Embedding attachment references (`attachment_ids`) inside the note keeps note retrieval fast, while keeping heavy binary metadata out of the main document to respect MongoDB document size limits and optimize working set memory.

### 4.2 Collection: `attachments`
Stores metadata and descriptions for uploaded evidence/images.

- `_id`: `ObjectId` (MongoDB primary key)
- `note_id`: `ObjectId` (indexed reference to parent note)
- `filename`: `str` — Sanitized stored filename
- `original_filename`: `str` — Original name uploaded by user
- `file_path`: `str` — Relative storage path on disk / volume
- `mime_type`: `str` — Media type (e.g., `image/jpeg`, `image/png`)
- `file_size`: `int` — Size in bytes
- `caption`: `str` — User-written short title or caption
- `description`: `str` — User-authored contextual description of the evidence
- `created_at`: `datetime` (UTC timestamp)

**Binary file storage strategy**: Binary image contents are stored on the filesystem / persistent volume, and only metadata and descriptive context are stored in MongoDB. This is the recommended practice for files over small thumbnails to prevent database cache churn.

---

## 5. Error Handling Strategy

FastAPI provides an exception handler hierarchy. Planned strategy:

1. **PyMongo Driver Errors**:
   - `PyMongoError` (base database connection/query exception) mapped to `503 Service Unavailable` with a structured error response, preventing raw database tracebacks from leaking.
   - `DuplicateKeyError` mapped to `409 Conflict`.
2. **Resource Resolution Errors**:
   - Non-existent `ObjectId` or missing document queries mapped to `404 Not Found`.
   - Malformed `ObjectId` hex strings caught at input validation and mapped to `422 Unprocessable Entity` or `400 Bad Request`.
3. **Data Validation Errors**:
   - Pydantic validation errors caught by FastAPI and converted to uniform `422 Unprocessable Entity` JSON responses.

---

## 6. Indexing & Query Strategy (Planned)

To ensure queries remain efficient and demonstrate database fundamentals during the viva:
1. **Single-field index on `created_at`** (descending) for fast reverse-chronological retrieval.
2. **Multikey index on `tags`** for tag-based filtering.
3. **Compound index on `(tags, created_at)`** for filtered chronological feeds.
4. **Text index on `title` and `body`** to support native MongoDB full-text search with relevance scoring (`$meta: "textScore"`).
5. **Vector Index (Atlas)**: Configured on `embedding` field with cosine similarity for Milestone 6.
