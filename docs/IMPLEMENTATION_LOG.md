# Fieldnote — Implementation Log

## Milestone Status Overview

| Milestone | Description | Status |
| :--- | :--- | :--- |
| **Milestone 0** | Documentation & Minimal Backend Foundation | **COMPLETED** |
| **Milestone 1** | MongoDB Connection & Health Lifecycle | **COMPLETED & FULLY VERIFIED** |
| **Milestone 2** | Research Notes Data Model & CRUD Operations | **COMPLETED & FULLY VERIFIED** |
| **Milestone 3** | Image Attachments with PyMongo GridFS | **COMPLETED & FULLY TESTED** |
| **Milestone 4** | Indexing & Efficient Querying | **COMPLETED & FULLY VERIFIED** |
| **Milestone 5** | Analytics & Aggregation Pipelines | **NOT IMPLEMENTED** (Next Milestone) |
| **Milestone 6** | Semantic Note Retrieval (Atlas Vector Search) | **NOT IMPLEMENTED** |
| **Milestone 7** | Minimal Frontend & Deployment Preparation | **NOT IMPLEMENTED** |

---

## Milestone 0 Log: Backend Foundation & Documentation

- **Date**: 2026-10-13
- **Objective**: Establish documentation, minimal folder hierarchy, environment configuration templates, and dependency definitions for Milestone 0.
- **Verification Status**: Verified clean directory state, documentation created, directory scaffolding initialized. No code or mock implementations created.

### Files Created:
1. `docs/PROJECT_SPEC.md` — Complete specification outlining project purpose, scope, non-goals, technology stack, and acceptance criteria per milestone.
2. `docs/ARCHITECTURE.md` — Layered architectural design, data models for `notes` and `attachments` collections, configuration policy, and error handling.
3. `docs/IMPLEMENTATION_LOG.md` — This file, tracking milestones, decisions, created files, and verification records.
4. `README.md` — Project orientation, milestone-driven workflow instructions, and setup steps.
5. `.gitignore` — Exclusion rules for `.env`, Python cache artifacts, pytest caches, virtual environments, and local IDE metadata.
6. `.env.example` — Placeholder environment variable definitions with no real secrets.
7. `requirements.txt` — Minimal dependencies pinned for FastAPI, PyMongo, Pydantic, and Pytest.
8. `app/__init__.py` — Package initialization for application source.
9. `tests/__init__.py` — Package initialization for test suite.

### Key Architectural & Engineering Decisions Made:
- **No Mock Implementations**: Refrained from writing simulated database adapters or fake CRUD logic. Database logic will be implemented against real PyMongo in Milestone 1.
- **Direct Driver Focus**: Pydantic will be used strictly for HTTP request/response validation and configuration parsing; PyMongo will interface directly with MongoDB Atlas to highlight native document modeling and driver interaction.
- **Separation of Files vs. Metadata**: Binary images will reside on disk/volume while rich metadata and captions reside in the MongoDB `attachments` collection, referenced in `notes`.
- **Zero Automatic Commits**: Adhering strictly to review discipline; Git commits will not be generated automatically.

### Verification Performed:
- Inspected initial workspace directory state via PowerShell (`Get-ChildItem -Force`). Directory confirmed empty prior to file creation.
- Inspected created documentation and directory structure to ensure compliance with academic scope and engineering constraints.

---

## Milestone 1 Log: MongoDB Connection & Health Lifecycle

- **Date**: 2026-10-13
- **Objective**: Implement the smallest working FastAPI backend that loads environment configuration via `pydantic-settings`, manages PyMongo `MongoClient` connection lifecycle, verifies connectivity via the admin `ping` command, exposes `/health` and `/api/health`, and provides offline test coverage.
- **Verification Status**:
  - **Automated Unit / Mocked Test Suite**: Verified with 14 automated pytest tests (all passing).
  - **Live MongoDB Atlas Connectivity**: **VERIFIED & CONFIRMED**. Connected to live cluster (`fieldnote-cluster.maysnkd.mongodb.net`), admin ping executed successfully (`{'ok': 1}`).
  - **Live Health Endpoint Verification**: Both `GET /health` and `GET /api/health` return HTTP `200 OK` with `{"status": "healthy", "app": "ok", "database": "connected", "environment": "development"}`.
  - **Error Safety**: Verified that connection failures return HTTP `503 Service Unavailable` with `status: "unhealthy"`, `app: "ok"`, `database: "disconnected"` without leaking internal details or credentials.

### Files Created or Modified:
1. `app/config.py` *(Created)* — Implements `Settings` using `pydantic-settings` to load `MONGODB_URI`, `DATABASE_NAME`, `APP_ENV`, `APP_HOST`, `APP_PORT`, `MONGODB_SERVER_SELECTION_TIMEOUT_MS`, and `UPLOAD_DIR`. Enforces non-empty `MONGODB_URI`.
2. `app/db.py` *(Created)* — Implements `create_mongo_client` with explicit `serverSelectionTimeoutMS` (default 2000ms), `ping_database` using `client.admin.command("ping")` wrapped in safe exception handling, and `close_mongo_client`.
3. `app/schemas.py` *(Created)* — Implements `HealthResponse` schema returning `status`, `app`, `database`, and `environment`.
4. `app/main.py` *(Created)* — Implements FastAPI application factory `create_app()`, async `lifespan` context manager managing single client lifecycle across app state, dependency provider `get_db_client`, and health endpoints (`GET /health` and `GET /api/health`).
5. `requirements.txt` *(Modified)* — Added explicit `dnspython>=2.7.0` alongside `pymongo>=4.10.0` to eliminate pip extra warning.
6. `tests/test_config.py` *(Created)* — 3 tests validating settings loading, missing `MONGODB_URI` validation failure, and empty string rejection.
7. `tests/test_db.py` *(Created)* — 6 tests verifying client option timeout configuration, `ping_database` success (`{"ok": 1.0}`), failure handling on `ConnectionFailure`, `ServerSelectionTimeoutError`, `None` client handling, and clean client disposal.
8. `tests/test_health.py` *(Created)* — 5 tests verifying 200 OK responses on healthy database, 503 Service Unavailable responses on database disconnection, `None` client handling, and application lifespan initialization.
9. `.env` *(Updated)* — Corrected URI delimiter syntax (`@@` -> `@`).

---

## Milestone 2 Log: Research Notes Data Model & CRUD Operations

- **Date**: 2026-10-13
- **Objective**: Implement a minimal REST API for creating, listing, retrieving, updating, and deleting research notes using FastAPI, PyMongo, and MongoDB Atlas.
- **Verification Status**:
  - **Automated Test Suite**: 32 tests executed and passing (100% pass rate).
  - **Live Atlas CRUD Test**: End-to-end verified against MongoDB Atlas cluster: `POST /api/notes` (201), `GET /api/notes/{id}` (200), `PUT /api/notes/{id}` (200), `DELETE /api/notes/{id}` (204), subsequent `GET` (404).
  - **Index Verification**: Verified descending index `idx_notes_created_at_desc` (`created_at: -1`) exists on MongoDB Atlas `notes` collection.

### Files Created or Modified:
1. `app/schemas.py` *(Modified)* — Added `NoteCreate` (title non-empty validator, content, tags default empty), `NoteUpdate`, and `NoteResponse` (exposing string `id` from MongoDB `ObjectId`).
2. `app/db.py` *(Modified)* — Added `init_db_indexes(db)` creating descending index on `created_at`, and `get_database(request)` dependency returning active database with HTTP 503 fallback if uninitialized.
3. `app/routes/__init__.py` *(Created)* — Package initialization for API routes.
4. `app/routes/notes.py` *(Created)* — Implemented direct PyMongo note CRUD endpoints with ObjectId validation (`400 Bad Request` for malformed hex strings, `404 Not Found` for missing notes, `503 Service Unavailable` on driver errors):
   - `POST /api/notes` (201 Created)
   - `GET /api/notes` (200 OK, sorted newest first via `created_at` DESC)
   - `GET /api/notes/{note_id}` (200 OK)
   - `PUT /api/notes/{note_id}` (200 OK, atomic `find_one_and_update`)
   - `DELETE /api/notes/{note_id}` (204 No Content)
5. `app/main.py` *(Modified)* — Registered `notes_router` and wired `init_db_indexes` into lifespan startup.
6. `tests/test_notes.py` *(Created)* — 17 unit/integration tests using an in-memory database double covering all success and failure paths, sorting, validations, malformed IDs, missing IDs, and database error handling.
7. `tests/test_db.py` *(Modified)* — Added unit test `test_init_db_indexes`.

### Key Architectural & Engineering Decisions Made:
- **Direct PyMongo Driver Usage**: Operations use native PyMongo collection methods (`insert_one`, `find().sort()`, `find_one`, `find_one_and_update`, `delete_one`) without introducing an ODM or repository layer.
- **Document Model**: Documents store `title` (str), `content` (str), `tags` (list[str]), `created_at` (UTC datetime), and `updated_at` (UTC datetime). `_id` is stored as BSON `ObjectId` and converted to string `id` in API responses.
- **Index Justification**: Added a single descending B-tree index on `created_at` (`[("created_at", -1)]`). Justification: The notes listing endpoint explicitly sorts newest first (`created_at: -1`); having a descending index enables index-covered sorted scans and prevents memory-intensive in-memory sort stages.
- **Input Validation & Safety**: Pydantic validates input schemas, strips whitespace, and rejects empty titles with HTTP `422`. Hex string format for `ObjectId` is verified before database queries, returning HTTP `400 Bad Request` for malformed IDs.
- **Isolated Testing**: Automated tests use an in-memory PyMongo test double, preventing dependence on or modification of real research data in Atlas.

---

## Milestone 3 Log: Image Attachments with PyMongo GridFS

- **Date**: 2026-10-13
- **Objective**: Implement image attachments linked to existing research notes using FastAPI `UploadFile`, PyMongo `GridFS` for binary chunks, and a MongoDB `attachments` collection for metadata.
- **Verification Status**:
  - **Automated Test Suite**: 55 tests executed and passing (100% pass rate) with zero failures and zero warnings.
  - **Isolated Test Doubles**: In-memory `FakeCollection`, `FakeDatabase`, and `FakeGridFS` test doubles verify upload validation, format checking, bounded chunk reading, structural validation, downloads, deletions, upload failure cleanup, and cascading failure safety without mutating Atlas data.
  - **Live MongoDB Atlas Smoke Verification**: Verified on live MongoDB Atlas cluster using disposable test records and a tiny 1x1 JPEG fixture (`scratch/smoke_test_atlas_attachments.py`). Confirmed GridFS storage (`fs.put`), metadata insertion, reading back, and complete cleanup teardown with zero residual records. Real research data was completely untouched.
  - **Index Verification**: Added ascending index `idx_attachments_note_id` on `attachments` collection (`note_id: 1`).

### Files Created or Modified:
1. `requirements.txt` *(Modified)* — Added `pillow>=10.0.0` for structural image payload verification.
2. `app/schemas.py` *(Modified)* — Added `AttachmentResponse` schema returning `id`, `note_id`, `file_id`, `filename`, `content_type`, `file_size`, `caption`, `description`, and UTC `created_at`.
3. `app/db.py` *(Modified)* — Added `get_gridfs(db)` dependency returning `gridfs.GridFS(db)`, and added index `idx_attachments_note_id` (`[("note_id", ASCENDING)]`) to `init_db_indexes`.
4. `app/routes/attachments.py` *(Created)* — Implemented image attachment endpoints:
   - `POST /api/notes/{note_id}/attachments` (201 Created): Uploads image via bounded streaming (up to 5 MB), checks true magic bytes, performs structural validation with Pillow, writes binary data to GridFS, stores metadata in `attachments` collection. Cleans up orphaned GridFS binary if metadata insertion fails.
   - `GET /api/notes/{note_id}/attachments` (200 OK): Lists attachments for a note.
   - `GET /api/notes/{note_id}/attachments/{attachment_id}` (200 OK): Retrieves attachment metadata.
   - `GET /api/notes/{note_id}/attachments/{attachment_id}/download` (200 OK): Streams binary chunks from GridFS with verified `Content-Type`, `Content-Disposition: inline`, and safe `grid_out.close()` in generator `finally`.
   - `DELETE /api/notes/{note_id}/attachments/{attachment_id}` (204 No Content): Deletes binary chunks from GridFS and document from `attachments`.
5. `app/routes/notes.py` *(Modified)* — Updated `delete_note` (`DELETE /api/notes/{note_id}`) to implement cascading deletion: removes linked GridFS files and attachment metadata sequentially per attachment before deleting the parent note document. Includes partial failure protection: if cleanup fails, the parent note is preserved (NOT deleted), HTTP 503 is returned, and subsequent retries can proceed safely without falsely claiming all attachments remain intact.
6. `app/main.py` *(Modified)* — Registered `attachments_router` and incremented app version to `0.3.0`.
7. `tests/test_attachments.py` *(Created)* — 16 isolated unit/integration tests covering upload success (JPEG, PNG, WebP), invalid MIME type rejection (415), fake MIME header sniffing rejection (415), corrupted structural payload rejection (415), empty file rejection (400), 5 MB bounded reading rejection (413), missing note (404), malformed note ID (400), filename sanitization, listing, metadata retrieval, binary streaming download, attachment deletion (204), orphaned GridFS cleanup on upload failure (503), cascading note deletion, cascading failure safety (503), and cascading delete retry after partial failure.
8. `tests/test_notes.py` *(Modified)* — Added `get_gridfs` to `app.db` import and dependency overrides.
9. `tests/test_db.py` *(Modified)* — Updated `test_init_db_indexes` to verify indexes on both `notes` and `attachments` collections.
10. `docs/ARCHITECTURE.md` *(Modified)* — Documented GridFS binary storage architecture, `attachments` schema, bounded reading, Pillow structural verification, safe streaming, and cascading cleanup failure handling.

### Key Architectural & Engineering Decisions Made:
- **PyMongo GridFS Storage**: Binary data is stored directly in MongoDB via GridFS (`fs.files` and `fs.chunks`), keeping binary chunks partitioned in 255 KB chunks while metadata resides in the `attachments` collection. Multi-document operations are explicitly handled as non-atomic with resilient cleanup logic.
- **Bounded Reading (Doops / Memory Exhaustion Defense)**: Uploads are read incrementally in 64 KB chunks up to a strict 5 MB limit. If the stream exceeds 5 MB, it aborts immediately with HTTP `413 Content Too Large` without buffering the entire file into server RAM.
- **Structural Image Validation (Pillow Dependency)**: Beyond sniffing header magic bytes (JPEG `\xff\xd8\xff`, PNG `\x89PNG\r\n\x1a\n`, WebP `RIFF....WEBP`), complete structural integrity is verified via `Image.open().verify()` using the lightweight, standard `Pillow` dependency. Corrupted payloads or executables disguised with valid image headers are rejected with HTTP `415 Unsupported Media Type`.
- **Upload Failure Cleanup (Orphan Prevention)**: If `fs.put` succeeds but writing metadata to `db["attachments"]` fails, the newly written GridFS file is immediately purged in the exception handler.
- **Filename Path Traversal Prevention**: Filenames are sanitized via `pathlib.Path().name` and regex alphanumeric filtering before storage, preventing path traversal attacks and header injection. Client filenames are never used as server filesystem paths.
- **Cascading Deletion Failure Safety & Safe Retries**: Deleting a parent note purges child GridFS binaries and metadata records sequentially per attachment. If any step fails, the operation halts, logs an error, preserves the parent note, and returns HTTP `503 Service Unavailable`. Deleting per attachment ensures that partial failures do not falsely claim all attachments are still intact, and allows the delete operation to be safely retried.
- **Index Justification**: Added `idx_attachments_note_id` (`[("note_id", 1)]`) on `attachments`. Justification: All attachment operations (listing, metadata lookups, and cascading deletion) filter by parent `note_id`. Indexing this field ensures fast index scans without full-collection scans.

---

## Milestone 4 Log: MongoDB Querying, Tag Filtering, and Native Text Search

- **Date**: 2026-10-13
- **Objective**: Implement tag filtering (single & multiple tags with OR semantics), native MongoDB text search across title and content (`$text`), pagination (`skip` & `limit`), deterministic sorting with `_id` tie-breaker, and text/multikey index creation on the `notes` collection.
- **Verification Status**:
  - **Automated Test Suite**: 69 tests executed and passing (100% pass rate) with zero failures and zero warnings.
  - **Isolated Unit / Integration Coverage**: 14 new tests added in `tests/test_notes.py` and `tests/test_db.py` verifying unfiltered listing, single tag filtering, multiple tags with OR semantics (`$in`), query parameter aliasing (`tag` and `tags`), empty tag validation error (400), empty search query validation error (400), title search, content search, no-match search, combined tag + text search, default pagination (skip=0, limit=20), custom skip and limit, out-of-range pagination validation (422), deterministic sorting tie-breaker on identical timestamps, query builder correctness, and index initialization.
  - **Live MongoDB Atlas Smoke Verification**: Executed live integration check against MongoDB Atlas cluster (`fieldnote-cluster.maysnkd.mongodb.net`) using disposable test records (`scratch/smoke_test_atlas_queries.py`). Confirmed index presence (`idx_notes_tags`, `idx_notes_text`), tag filtering matching `$in`, native text search matching `$text`, combined text + tag query, deterministic tie-breaking, and complete teardown of disposable documents without touching real data.

### Files Created or Modified:
1. `app/db.py` *(Modified)*:
   - Added PyMongo `TEXT` import.
   - Updated `init_db_indexes(db)` to create multikey index `idx_notes_tags` (`[("tags", ASCENDING)]`) and text index `idx_notes_text` (`[("title", TEXT), ("content", TEXT)]`) alongside existing indexes.
2. `app/routes/notes.py` *(Modified)*:
   - Added `parse_and_validate_tags(tag, tags)` helper supporting repeatable `?tag=...` and comma-separated `?tags=...`, stripping whitespace and rejecting empty or whitespace-only tags with HTTP `400 Bad Request`.
   - Added `build_notes_query(tags, q)` helper composing tag filtering (`{"tags": {"$in": tags}}`) and native text search (`{"$text": {"$search": q}}`) into a unified MongoDB query filter dict.
   - Updated `GET /api/notes` route handler with query parameters `tag: List[str]`, `tags: Optional[str]`, `q: Optional[str]`, `skip: int = Query(default=0, ge=0)`, and `limit: int = Query(default=20, ge=1, le=100)`.
   - Updated cursor sorting to deterministic compound sort `cursor.sort([("created_at", -1), ("_id", -1)])` to guarantee stable pagination across timestamp ties.
3. `tests/test_db.py` *(Modified)*:
   - Updated `test_init_db_indexes` to verify that `idx_notes_created_at_desc`, `idx_notes_tags`, and `idx_notes_text` are initialized on `notes`, and `idx_attachments_note_id` on `attachments`.
4. `tests/test_notes.py` *(Modified)*:
   - Upgraded `FakeCursor` test double to support multi-attribute compound sorting and chained `.skip()` / `.limit()` slicing.
   - Upgraded `FakeCollection.find()` to evaluate MongoDB query filters including `{"tags": {"$in": ...}}` and `{"$text": {"$search": ...}}`.
   - Added 14 unit and integration tests thoroughly testing query composition, edge cases, error conditions, and pagination.
5. `docs/ARCHITECTURE.md` *(Modified)*:
   - Updated component status table to Milestone 4.
   - Added Section 6.1, 6.2, and 6.3 detailing configured indexes, query composition, tag OR semantics, pagination rules, deterministic sorting tie-breaker, and transparent documentation of MongoDB text search limitations.
6. `README.md` *(Modified)*:
   - Added concise API query parameter examples for listing, tag filtering, text searching, and pagination.

### Key Architectural & Engineering Decisions Made:
- **Tag Filtering Semantics (OR via `$in`)**: Filtering by multiple tags uses MongoDB's `$in` operator across the `tags` array field (`{"tags": {"$in": ["soil", "water"]}}`). OR semantics is standard and intuitive for exploratory research notes discovery.
- **Multikey Index**: Added `idx_notes_tags` (`[("tags", 1)]`) on `notes`. Justification: Because `tags` is an array of strings, MongoDB automatically indexes each array element in a multikey index, allowing `$in` queries to perform index range scans rather than full collection scans.
- **Native MongoDB Text Index & Search**: Added `idx_notes_text` (`[("title", "text"), ("content", "text")]`). Text queries use `$text: {"$search": q}`. We explicitly document that MongoDB native text search is lexical (word stemming and stop words), allows only one text index per collection, requires an in-memory sort when combined with date ordering, and does not provide fuzzy or vector similarity.
- **Deterministic Sort Tie-Breaker**: To prevent pagination drift when multiple notes share the exact same microsecond timestamp, queries sort on `[("created_at", -1), ("_id", -1)]`. `ObjectId`s are strictly ordered by creation timestamp and machine counter, guaranteeing consistent pagination boundaries.
- **Strict Boundary Validation**: Pagination parameters enforce `skip >= 0` and `1 <= limit <= 100` via FastAPI/Pydantic `Query` bounds (HTTP `422 Unprocessable Entity`). Empty search strings (`q=""`) or blank tags (`tag=""`) return HTTP `400 Bad Request` to catch client errors early.

---

## Unimplemented Features (Strictly Marked)

The following capabilities remain explicitly **NOT IMPLEMENTED**:
- [NOT IMPLEMENTED] MongoDB aggregation pipelines for analytics (`/analytics`, Milestone 5).
- [NOT IMPLEMENTED] Vector embeddings generation and Atlas Vector Search queries (`/search`, Milestone 6).
- [NOT IMPLEMENTED] Frontend templates or Flask web server (Milestone 7).
- [NOT IMPLEMENTED] Authentication, authorization, or user accounts.
- [NOT IMPLEMENTED] OCR, computer vision, or AI-generated captions.

---

## Next Approved Milestone

- **Milestone 5**: Analytics & Aggregation Pipelines
  - Focus: Multi-stage MongoDB aggregation pipelines for research tag frequency, activity timelines, and summary metrics (`/api/analytics`).
  - Required before starting: Explicit user approval to proceed.

