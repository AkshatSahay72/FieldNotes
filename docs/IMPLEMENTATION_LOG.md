# Fieldnote — Implementation Log

## Milestone Status Overview

| Milestone | Description | Status |
| :--- | :--- | :--- |
| **Milestone 0** | Documentation & Minimal Backend Foundation | **COMPLETED** |
| **Milestone 1** | MongoDB Connection & Health Lifecycle | **COMPLETED & FULLY VERIFIED** |
| **Milestone 2** | Research Notes Data Model & CRUD Operations | **COMPLETED & FULLY VERIFIED** |
| **Milestone 3** | Image Attachments with PyMongo GridFS | **COMPLETED & FULLY TESTED** |
| **Milestone 4** | Indexing & Efficient Querying | **COMPLETED & FULLY VERIFIED** |
| **Milestone 5** | Analytics & Aggregation Pipelines | **COMPLETED & FULLY VERIFIED** |
| **Milestone 6A & 6B** | Embedding Service, Vector Schema & Note Lifecycle | **COMPLETED & FULLY VERIFIED** |
| **Milestone 6C** | Semantic Search API (`/api/search/semantic`) | **COMPLETED & FULLY VERIFIED** |
| **Milestone 6D** | Atlas Vector Search Index Provisioning & Live Verifications (6D.1–6D.4) | **COMPLETED & FULLY VERIFIED** |
| **Milestone 7** | Minimal Frontend & Deployment Preparation | **NOT IMPLEMENTED** (Next Milestone) |

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
   - Updated `init_db_indexes(db)` to create multikey index `idx_notes_tags` (`[("tags", ASCENDING)]`), text index `idx_notes_text` (`[("title", TEXT), ("content", TEXT)]`), and compound index `idx_notes_created_at_id_desc` (`[("created_at", DESCENDING), ("_id", DESCENDING)]`) alongside existing indexes.
2. `app/routes/notes.py` *(Modified)*:
   - Added `parse_and_validate_tags(tag, tags)` helper supporting repeatable `?tag=...` and comma-separated `?tags=...`, stripping whitespace and rejecting empty or whitespace-only tags with HTTP `400 Bad Request`.
   - Added `build_notes_query(tags, q)` helper composing tag filtering (`{"tags": {"$in": tags}}`) and native text search (`{"$text": {"$search": q}}`) into a unified MongoDB query filter dict.
   - Updated `GET /api/notes` route handler with query parameters `tag: List[str]`, `tags: Optional[str]`, `q: Optional[str]`, `skip: int = Query(default=0, ge=0)`, and `limit: int = Query(default=20, ge=1, le=100)`.
   - Updated cursor sorting to deterministic compound sort `cursor.sort([("created_at", -1), ("_id", -1)])` to guarantee stable pagination across timestamp ties.
3. `tests/test_db.py` *(Modified)*:
   - Updated `test_init_db_indexes` to verify that `idx_notes_created_at_desc`, `idx_notes_created_at_id_desc`, `idx_notes_tags`, and `idx_notes_text` are initialized on `notes`, and `idx_attachments_note_id` on `attachments`.
4. `tests/test_notes.py` *(Modified)*:
   - Upgraded `FakeCursor` test double to support multi-attribute compound sorting and chained `.skip()` / `.limit()` slicing.
   - Upgraded `FakeCollection.find()` to evaluate MongoDB query filters including `{"tags": {"$in": ...}}` and `{"$text": {"$search": ...}}`.
   - Added unit and integration tests thoroughly testing query composition, edge cases, error conditions, parameter combinations (`tag` and `tags` together), malformed tag values, and pagination.
5. `docs/ARCHITECTURE.md` *(Modified)*:
   - Updated component status table to Milestone 4.
   - Added Section 6.1, 6.2, and 6.3 detailing configured indexes, compound sort index `idx_notes_created_at_id_desc`, query composition, tag OR semantics, pagination rules, deterministic sorting tie-breaker, and transparent documentation of MongoDB text search limitations.
6. `README.md` *(Modified)*:
   - Added concise API query parameter examples for listing, tag filtering, text searching, and pagination.

### Key Architectural & Engineering Decisions Made:
- **Compound Index for Stable Pagination**: Added `idx_notes_created_at_id_desc` (`[("created_at", -1), ("_id", -1)]`). Justification: An index on `created_at` alone cannot satisfy a compound sort on `[("created_at", -1), ("_id", -1)]` in MongoDB and results in a `COLLSCAN` + `SORT` stage. The compound index enables index-covered scanning (`IXSCAN -> FETCH`) without an in-memory sort stage for unfiltered pagination.
- **Tag Filtering Semantics (OR via `$in`)**: Filtering by multiple tags uses MongoDB's `$in` operator across the `tags` array field (`{"tags": {"$in": ["soil", "water"]}}`). OR semantics is standard and intuitive for exploratory research notes discovery. Both `tag` and `tags` can be used individually or combined.
- **Multikey Index**: Added `idx_notes_tags` (`[("tags", 1)]`) on `notes`. Justification: Because `tags` is an array of strings, MongoDB automatically indexes each array element in a multikey index, allowing `$in` queries to perform index range scans rather than full collection scans.
- **Native MongoDB Text Index & Search Caveats**: Added `idx_notes_text` (`[("title", "text"), ("content", "text")]`). Text queries require a text index and use `$text: {"$search": q}`. We explicitly document that MongoDB native text search is lexical (word stemming and stop words), allows only one text index per collection, does not optimize chronological sorting (combining `$text` with date ordering requires an in-memory sort stage), and does not provide fuzzy or vector similarity.
- **Deterministic Sort Tie-Breaker**: To prevent pagination drift when multiple notes share the exact same microsecond timestamp, queries sort on `[("created_at", -1), ("_id", -1)]`. `ObjectId`s are strictly ordered by creation timestamp and machine counter, guaranteeing consistent pagination boundaries.
- **Strict Boundary Validation**: Pagination parameters enforce `skip >= 0` and `1 <= limit <= 100` via FastAPI/Pydantic `Query` bounds (HTTP `422 Unprocessable Entity`). Empty search strings (`q=""`) or blank tags (`tag=""` or `tags=""`) return HTTP `400 Bad Request` to catch client errors early.

---

## Milestone 5 Log: MongoDB Aggregation Analytics

- **Date**: 2026-10-13
- **Objective**: Implement a dedicated analytics API (`/api/analytics`) powered by MongoDB aggregation pipelines and counting operations to provide research overview metrics, tag frequency distribution, daily note creation trends, and per-note attachment summaries.
- **Verification Status**:
  - **Automated Test Suite**: 86 tests executed and passing (100% pass rate) with zero failures and zero warnings.
  - **Isolated Unit & Integration Coverage**: 17 tests added in `tests/test_analytics.py` verifying exact pipeline stage construction (`$unwind`, `$match`, `$group`, `$sort`, `$project`, `$dateToString`, `$lookup`, `$size`), overview counts on empty and populated collections, tag counting with deterministic sort (count DESC, tag ASC), case-sensitivity preservation, omission of blank/missing tags, daily activity chronological grouping (UTC), attachment counts with zero-count inclusion/exclusion, and database error safety (503 Service Unavailable).
  - **Live MongoDB Atlas Smoke Verification**: Executed live integration smoke test (`scratch/smoke_test_atlas_analytics.py`) against live MongoDB Atlas cluster (`fieldnote-cluster.maysnkd.mongodb.net`) using disposable test notes and attachments. Confirmed that all 3 aggregation pipelines (`$unwind` tag distribution, `$dateToString` activity timeline, and `$lookup` attachment summary) execute successfully on Atlas with exact counts, followed by 100% cleanup teardown with zero residual records.

### Files Created or Modified:
1. `app/schemas.py` *(Modified)*:
   - Added `AnalyticsOverview` (`total_notes`, `total_attachments`, `notes_with_tags`).
   - Added `TagCount` (`tag`, `count`).
   - Added `DailyActivity` (`date`, `count`).
   - Added `NoteAttachmentSummary` (`note_id`, `title`, `attachment_count`).
2. `app/routes/analytics.py` *(Created)*:
   - Implemented pipeline builders: `build_tag_distribution_pipeline()`, `build_note_activity_pipeline()`, and `build_attachment_counts_pipeline()`.
   - Implemented `GET /api/analytics/overview` (counts for notes, attachments, and notes containing tags).
   - Implemented `GET /api/analytics/tags` (tag frequency via `$unwind` and `$group`).
   - Implemented `GET /api/analytics/activity` (chronological note counts by UTC date via `$dateToString`).
   - Implemented `GET /api/analytics/attachments` (attachment counts per note via `$lookup` and `$size` with `include_zero` parameter).
3. `app/main.py` *(Modified)*:
   - Registered `analytics_router` on application instance.
   - Incremented application version to `0.5.0`.
4. `tests/test_analytics.py` *(Created)*:
   - 17 isolated tests validating pipeline definitions, empty collections, populated collections, case-sensitivity, date formatting, lookup joining, and error handling.
5. `docs/ARCHITECTURE.md` *(Modified)*:
   - Updated component status table to Milestone 5.
   - Added Section 7 detailing analytics endpoints, aggregation pipeline definitions, semantics, and performance considerations.
6. `README.md` *(Modified)*:
   - Added API usage examples for all 4 analytics endpoints.

### Key Architectural & Engineering Decisions Made:
- **Efficient Counts for Overview**: Used native PyMongo `count_documents` (`{}` and `{"tags.0": {"$exists": True}}`) for the overview endpoint rather than forcing an expensive aggregation pipeline where simple index-backed counts provide superior clarity and performance.
- **Defensive Tag Grouping**: The tag distribution pipeline uses `$unwind: "$tags"` followed by `{"$match": {"tags": {"$nin": ["", None]}}}` to ensure notes with empty tag arrays or missing tags are excluded, preventing fabricated blank tags from being counted. Tags are grouped case-sensitively as stored, respecting user input without silent mutation.
- **Deterministic Sorting**: All aggregation pipelines enforce deterministic ordering: tag distribution sorts by `count` DESC then tag ASC; activity sorts by date ASC; attachment summaries sort by `attachment_count` DESC then title ASC then `note_id` ASC.
- **Explicit UTC Date Formatting**: Daily note creation activity uses `$dateToString` with `format: "%Y-%m-%d"` and explicit `timezone: "UTC"` to eliminate server timezone discrepancies. Missing calendar days are not fabricated.
- **Memory-Safe Multi-Collection Join**: Attachment counts use `$lookup` joining `notes._id` to `attachments.note_id` (accelerated by `idx_attachments_note_id`) and calculate `{"$size": "$attachments"}` inside the database engine. Binary GridFS chunks and attachment documents are never loaded into Python RAM.

---

## Milestone 6B Log: Embedding Service & Note Lifecycle Integration

- **Date**: 2026-10-13
- **Objective**: Implement the vector embedding service (`app/services/embedding.py`), integrate embedding generation into note creation and updates, build an idempotent concurrency-safe backfill script (`scripts/backfill_embeddings.py`), and test all functionality in isolation.
- **Verification Status**: Verified clean test execution across 113 pytest tests (87 existing + 26 new embedding/lifecycle/backfill tests). Verified dry-run and error handling semantics without network downloads during test execution.

### Files Created:
1. `app/services/__init__.py` — Application services package marker.
2. `app/services/embedding.py` — `EmbeddingService` implementation with lazy-loaded singleton `sentence-transformers/all-MiniLM-L6-v2`, explicit empty-input validation, 384-dimensional finite vector verification, unit normalization, and sanitized exception handling.
3. `scripts/__init__.py` — Scripts package marker.
4. `scripts/backfill_embeddings.py` — Idempotent batch backfill CLI with cursor streaming, concurrency guard matching on `_id` and `updated_at`, `--dry-run` simulation mode, sanitized summary output, and non-zero exit codes on error.
5. `tests/test_embedding.py` — 11 isolated unit tests validating text formatting, non-empty validation, normalization, dimension checking, finite-value verification, exception wrapping, and dependency singleton behavior.
6. `tests/test_backfill.py` — 8 isolated tests validating backfill updates, idempotency on up-to-date notes, outdated model detection, dry-run simulation, concurrency conflicts, fault tolerance, and CLI exit codes.

### Files Modified:
1. `app/config.py`:
   - Added `embedding_model: str = Field(default="sentence-transformers/all-MiniLM-L6-v2", alias="EMBEDDING_MODEL")` to `Settings`.
2. `.env.example`:
   - Documented `EMBEDDING_MODEL` setting.
3. `requirements.txt`:
   - Declared `sentence-transformers>=3.0.0` dependency.
4. `app/routes/notes.py`:
   - Integrated `EmbeddingService` dependency into `create_note` (inserts inline `embedding` and `embedding_model`).
   - Integrated `EmbeddingService` into `update_note` (recomputes embedding if `title` or `content` changed, skips if tag-only, atomic update).
   - Preserved `NoteResponse` contract (vector is never exposed in normal CRUD API responses).
5. `tests/test_notes.py`:
   - Injected deterministic `FakeEmbeddingService` test double into fixtures.
   - Added 6 lifecycle integration tests covering inline persistence, API response contract preservation, 503 inference rollback, title change recomputation, content change recomputation, and tag-only skipping.
6. `tests/test_config.py`:
   - Added tests verifying default and environment-variable overridden `EMBEDDING_MODEL` setting.

### Key Architectural & Engineering Decisions Made:
- **Cosine Similarity via Unit Normalization**: Used `SentenceTransformer.encode(..., normalize_embeddings=True)` ensuring dot product equals cosine similarity, matching MongoDB Atlas Vector Search `cosine` metric configuration.
- **Strict Input Validation**: The embedding service rejects empty or whitespace-only inputs, preventing silent substitution of zero vectors or garbage representations.
- **Contract Compatibility**: `NoteResponse` schemas remain untouched. The embedding vector and model tag remain private storage concerns inline within the note document and are never returned in CRUD responses.
- **Atomicity on Update**: Note content and embedding vector are written together in a single MongoDB `$set` update operation via `find_one_and_update`. If inference fails, no partial updates or stale embeddings are saved.
- **Tag-Only Skip Optimization**: Note updates that modify only tags bypass inference entirely, saving CPU and GPU compute cycles.
- **Concurrency-Safe Backfill**: Backfill uses conditional updates matching `_id` and existing `updated_at`. If a note was modified concurrently during inference, the update matches 0 documents, records a skip, and never overwrites newer user revisions.
- **Offline Test Isolation**: Tests use deterministic test doubles (`FakeEmbeddingService`, `DummyModel`) preventing slow Hugging Face model downloads and ensuring consistent, reproducible test runs.

---

## Milestone 6C Log: Semantic Search API Implementation

- **Date**: 2026-10-13
- **Objective**: Implement the dedicated semantic search endpoint (`GET /api/search/semantic`), convert natural language queries into embeddings via the existing `EmbeddingService`, execute an Atlas Vector Search aggregation pipeline with score projection, and implement sanitized error handling.
- **Verification Status**: Verified clean test execution across 126 pytest tests (114 existing + 12 new search tests). Verified input validation, parameter boundaries, candidate pool sizing, pipeline construction, response schema serialization, and fault isolation.

### Files Created:
1. `app/routes/search.py` — Dedicated semantic search route (`GET /api/search/semantic`), query validation (`q` non-empty, `limit` 1..50), pipeline execution with `$vectorSearch` and `{"$meta": "vectorSearchScore"}` projection, and differentiated database/index error handling.
2. `tests/test_search.py` — 12 focused unit and integration tests covering pipeline verification, candidate bounds, limit validation, empty results, inference error handling, index-not-ready error handling, and router registration.

### Files Modified:
1. `app/schemas.py`:
   - Added `SemanticSearchResult` model inheriting from `NoteResponse`, adding documented `score: float` field ($meta: `vectorSearchScore`).
2. `app/main.py`:
   - Registered `search_router` on application instance.
3. `docs/ARCHITECTURE.md`:
   - Updated component status table to Milestone 6C.
   - Added Section 8 detailing Vector Search Architecture, pipeline stages, score semantics, and error handling.
4. `README.md`:
   - Documented `GET /api/search/semantic` endpoint usage, example JSON response, and offline backfill CLI instructions.

### Key Architectural & Engineering Decisions Made:
- **Direct Query Encoding Without Title Fabrication**: Natural language query strings are encoded directly via `embedding_service.generate_embedding(trimmed_q)` without prepending fabricated titles or altered prefixes, matching model behavior.
- **Bounded Candidate Pool Scaling**: Implemented `calculate_num_candidates(limit) = min(max(limit * 10, 20), 500)`. Ensures candidate pool is always >= limit (at least 20), provides 10x recall multiplier, and caps at 500 to protect cluster RAM and query latency.
- **Score Semantics & Zero Leakage**: The `score` field represents a relative similarity ranking signal (`vectorSearchScore`), explicitly documented as not a probability. Stored note embedding vectors and intermediate query vectors are strictly omitted from projection and API responses.
- **Recognizable Index Error Handling**: Differentiated `OperationFailure` caused specifically by missing or unready vector search indexes (`"idx_notes_vector not found / not ready"`) from general database failures, providing clear 503 diagnostics without exposing internal connection strings or stack traces.
- **Explicit Scope Boundary**: Index definition provisioning on MongoDB Atlas and live Atlas cluster verification are explicitly deferred to **Milestone 6D**. Semantic search is not claimed to work on live Atlas until verified.

---

## Milestone 6D.2 Log: Provision Atlas Vector Search Index

- **Date**: 2026-10-13
- **Objective**: Provision the official Atlas Vector Search index `idx_notes_vector` on `fieldnote_db.notes`, poll until confirmed `READY` and queryable, verify that zero documents were modified, and ensure duplicate prevention.
- **Verification Status**: Verified index provisioned on Atlas cluster. Status is `READY`, `queryable` is `True`, index ID is `6acdcfb758189810955f17de`. Confirmed document count in `notes` collection remains strictly 0. Confirmed 10 unit tests for `scripts/provision_vector_index.py` passed. Live semantic retrieval has NOT yet been run.

### Files Created:
1. `scripts/provision_vector_index.py` — Dedicated, idempotent CLI script to inspect and provision the `idx_notes_vector` Atlas Vector Search index using PyMongo's `SearchIndexModel` API. Features connectivity verification via ping, duplicate creation refusal, polling loop with timeout, and clean logging without credential leakage.
2. `tests/test_provision_vector_index.py` — 10 unit tests covering index discovery, duplicate prevention, readiness polling, timeout handling, error reporting, and `--check-only` mode.

### Files Modified:
1. `docs/ARCHITECTURE.md` — Updated component status table and added Section 8.3 documenting index definition, provisioning script, and operational readiness.
2. `docs/IMPLEMENTATION_LOG.md` — Logged Milestone 6D.2 provisioning details, verified index metadata, and updated remaining milestones.
3. `README.md` — Added CLI instructions for `scripts/provision_vector_index.py`.

### Actual Provisioned Index Details on MongoDB Atlas:
- **Target Database**: `fieldnote_db`
- **Target Collection**: `notes`
- **Index Name**: `idx_notes_vector`
- **Index ID**: `6acdcfb758189810955f17de`
- **Index Type**: `vectorSearch`
- **Definition**:
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
- **Observed Lifecycle**:
  - Initial request: `create_search_index` returned `'idx_notes_vector'`.
  - Initial poll (0.0s): `status: PENDING`, `queryable: False`.
  - Final poll (40.5s): `status: READY`, `queryable: True`.
- **Collection State**: Confirmed note document count is exactly `0` before and after provisioning.
- **Secondary Indexes**: All 5 existing secondary indexes (`_id_`, `idx_notes_created_at_desc`, `idx_notes_tags`, `idx_notes_text`, `idx_notes_created_at_id_desc`) remain intact and untouched.

### Key Architectural & Engineering Decisions Made:
- **Dedicated Out-of-Band Script**: Index creation is handled via `scripts/provision_vector_index.py` rather than on FastAPI startup or lifespan. Application startup remains fast and completely independent of Atlas Search index provisioning.
- **Duplicate Prevention**: The script checks `list_search_indexes()` prior to creation. If `idx_notes_vector` already exists, it warns and safely refuses to recreate or overwrite.
- **Bounded Polling**: Employs an elapsed-time loop polling every 5.0s up to a configurable timeout (default 300s). Fails fast if the index reports `FAILED` status.
- **Zero Vector or Data Mutation**: The provisioning script operates strictly on index metadata and performs zero document inserts, updates, or deletes.
- **Strict Scope Boundary**: Live semantic query execution (`$vectorSearch`), test note seeding, and embedding backfills are strictly deferred to subsequent milestones.

---

## Milestone 6D.3 Log: Live Semantic Retrieval Verification

- **Date**: 2026-10-13
- **Objective**: Execute an end-to-end live semantic retrieval smoke test against the running FastAPI application and MongoDB Atlas cluster (`fieldnote_db.notes`) using the provisioned `idx_notes_vector` index.
- **Verification Status**: **VERIFIED LIVE AGAINST ATLAS**. Confirmed 100% correct semantic similarity retrieval across all 5 test query categories. Confirmed zero internal vector leakage in response payloads. Confirmed exact cleanup of all temporary test notes, restoring the collection baseline count to strictly 0.

### Test Execution Details:
- **Test Run Identifier**: `test-6d3-5d7675b5`
- **Atlas Database**: `fieldnote_db`
- **Target Collection**: `notes`
- **Search Index**: `idx_notes_vector` (verified `READY`, `queryable: True`)
- **Baseline Document Count**: `0`

### Temporary Test Data Created:
Created 3 synthetic research notes via `POST /api/notes`:
1. **Note 1** (`6acdd563a481632cbe31cda7`):
   - Title: *"Orbital Mechanics and Satellite Trajectory Calculations"*
   - Content: *"Calculated Hohmann transfer orbits, delta-v budgets, and gravitational perturbations for Low Earth Orbit satellite stationkeeping."*
   - Tags: `["orbital-mechanics", "aerospace", "test-6d3-5d7675b5"]`
   - Embedding verification: 384 finite numeric floats, model `sentence-transformers/all-MiniLM-L6-v2`.
2. **Note 2** (`6acdd563a481632cbe31cda8`):
   - Title: *"Plant Root Architecture and Soil Moisture Uptake"*
   - Content: *"Analyzed xylem water transport, hydraulic redistribution, and root depth profiles under variable soil moisture deficit conditions."*
   - Tags: `["botany", "soil-moisture", "test-6d3-5d7675b5"]`
   - Embedding verification: 384 finite numeric floats, model `sentence-transformers/all-MiniLM-L6-v2`.
3. **Note 3** (`6acdd563a481632cbe31cda9`):
   - Title: *"Database Indexing and B-Tree Query Optimization"*
   - Content: *"Evaluated compound index selectivity, execution plans, and write overhead for high-concurrency database queries."*
   - Tags: `["databases", "indexing", "test-6d3-5d7675b5"]`
   - Embedding verification: 384 finite numeric floats, model `sentence-transformers/all-MiniLM-L6-v2`.

### Query Categories Tested & Observed Live Results:

| # | Query Category | Query String | Rank 1 Title | Rank 1 Score | Expected Match | Result |
| :- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1** | Closely matching Note 1 | *"Orbital mechanics and satellite trajectories"* | Note 1 (*Orbital Mechanics...*) | `0.842941` | Note 1 | **PASS** (Clear separation: Note 2 score `0.514885`, Note 3 score `0.494934`) |
| **2** | Paraphrased Note 1 | *"Keeping satellites on course in space"* | Note 1 (*Orbital Mechanics...*) | `0.728458` | Note 1 | **PASS** (Clear separation: Note 2 score `0.512492`, Note 3 score `0.489841`) |
| **3** | Botany / soil matching Note 2 | *"Plant roots obtaining water from soil"* | Note 2 (*Plant Root Architecture...*) | `0.828912` | Note 2 | **PASS** (Clear separation: Note 1 score `0.506615`, Note 3 score `0.468635`) |
| **4** | Database matching Note 3 | *"Speeding up database lookups"* | Note 3 (*Database Indexing...*) | `0.743207` | Note 3 | **PASS** (Clear separation: Note 1 score `0.516626`, Note 2 score `0.466987`) |
| **5** | Unrelated topic | *"Renaissance oil painting techniques and pigments"* | Note 3 (*Database Indexing...*) | `0.539252` | Nearest neighbor | **PASS** (All scores low: `0.539252`, `0.476900`, `0.447430`; no false confidence) |

### Payload Safety Verification:
- Internal `embedding` vector (384 floats) was strictly **omitted** from all API response payloads.
- Internal `embedding_model` identifier was strictly **omitted** from all API response payloads.
- All returned `score` fields were finite floating-point values representing relative similarity ranking signals (`vectorSearchScore`).

### Cleanup & Baseline Restoration:
- Targeted deletion executed via `DELETE /api/notes/{id}` for exactly the 3 recorded test IDs (`6acdd563a481632cbe31cda7`, `6acdd563a481632cbe31cda8`, `6acdd563a481632cbe31cda9`).
- Each note verified as non-existent in MongoDB following deletion.
- Final collection document count: **0** (strictly returned to baseline count of 0).
- Secondary indexes: All 5 indexes remained intact.

### Architectural & Operational Insights:
- **Change Stream Indexing Latency**: Observed ~3–6 seconds between document insertion in MongoDB and Lucene/Atlas Search ingestion by the background mongot process. Applications performing immediate vector search following note creation must account for this asynchronous ingestion model.
- **Score Semantics**: Vector search scores reflect approximate cosine similarity ranking signals rather than calibrated probabilities; unrelated queries still retrieve nearest neighbors, confirming why the API must project the score transparently to client callers.

---

## Milestone 6D.4 Log: Live Atlas Embedding Backfill Verification

- **Date**: 2026-10-13
- **Objective**: Verify the live embedding backfill script (`scripts/backfill_embeddings.py`) against MongoDB Atlas (`fieldnote_db.notes`), confirming dry-run safety, live batch backfill, idempotency, deterministic concurrency protection, and complete cleanup back to zero baseline documents.
- **Verification Status**: **VERIFIED & CONFIRMED ON LIVE ATLAS**. All preflight checks passed, 4 synthetic legacy notes processed, dry-run mutated 0 documents, live backfill populated 384-dimensional embeddings matching the active model, second run updated 0 documents, concurrency protection rejected stale writes, and all test documents were cleanly removed.

### Preflight Verification:
- **Git Branch & HEAD**: `main` at `4412fef` (working tree clean).
- **Atlas Connectivity**: Admin ping succeeded (`{"ok": 1.0}`).
- **Baseline Document Count**: `0` in `fieldnote_db.notes`.
- **Search Index Status**: `idx_notes_vector` status `READY`, `queryable: True`.
- **Embedding Model**: `sentence-transformers/all-MiniLM-L6-v2` loaded and verified locally.

### Script Code Audit Findings (`scripts/backfill_embeddings.py`):
- **Candidate Filter**: Correctly targets notes missing `embedding`, having `embedding: None`, or with `embedding_model != target_model`.
- **Dry-Run Mode**: Simulates processing and counts candidates without executing any database mutations.
- **Batching**: Streams documents in configurable chunk sizes (default 100, tested at 10) to control memory overhead.
- **Deterministic Concurrency Protection**: Updates are conditioned on `{"_id": doc["_id"], "updated_at": original_updated_at}`, preventing overwrites if a concurrent researcher edits the document during inference.
- **Error Handling & Exit Codes**: Per-document exceptions are captured and counted; exit code is `0` on zero failures, `1` if any document fails.

### Synthetic Disposable Test Fixtures (Run ID: `test-6d4-8d9e6345`):
Inserted 4 synthetic notes directly via PyMongo:
1. `6acdd9ec580d4f0a8b30f7d7`: Missing `embedding` and `embedding_model` ("Glacial Flow Measurements").
2. `6acdd9ed580d4f0a8b30f7d8`: Missing `embedding` and `embedding_model` ("Volcanic Ash Spectroscopy").
3. `6acdd9ed580d4f0a8b30f7d9`: Explicit `embedding: None`, missing `embedding_model` ("Deep Sea Hydrothermal Vents").
4. `6acdd9ed580d4f0a8b30f7da`: Obsolete `embedding_model: "sentence-transformers/legacy-v1-obsolete"`, dummy 128-dim vector ("Atmospheric Ozone Depletion").

### Step-by-Step Live Execution Results:

| Phase | Executed Command | Exit Code | Reported Summary | Direct Atlas Verification | Result |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Dry-Run** | `python scripts/backfill_embeddings.py --dry-run` | `0` | Processed: 4, Updated: 4 (simulated), Failed: 0 | All 4 documents in MongoDB remained bit-for-bit identical to pre-test state; 0 writes performed | **PASS** |
| **Live Backfill** | `python scripts/backfill_embeddings.py --batch-size 10` | `0` | Processed: 4, Updated: 4, Failed: 0 | All 4 documents verified with 384 finite floats, model `sentence-transformers/all-MiniLM-L6-v2`, max delta from reference < 1e-4; non-embedding fields untouched | **PASS** |
| **Idempotency** | `python scripts/backfill_embeddings.py --batch-size 10` | `0` | Processed: 0, Updated: 0, Failed: 0 | Documents verified completely unmodified across both database reads; 0 updates performed | **PASS** |
| **Concurrency Protection** | Controlled update test on 5th disposable note (`6acdda35580d4f0a8b30f7db`) | `N/A` | Conditional update with stale `updated_at` | `matched_count: 0`, `modified_count: 0`. Newer user content was preserved; stale embedding was rejected | **PASS** |

### Mandatory Cleanup & Baseline Restoration:
- Targeted deletion executed in a reliable `try/finally` block for all 5 recorded ObjectIds (`6acdd9ec580d4f0a8b30f7d7`, `6acdd9ed580d4f0a8b30f7d8`, `6acdd9ed580d4f0a8b30f7d9`, `6acdd9ed580d4f0a8b30f7da`, `6acdda35580d4f0a8b30f7db`).
- Every ID verified as non-existent in MongoDB following deletion.
- Final collection document count: **0** (strictly returned to baseline count of 0).
- Secondary indexes: All 5 indexes remained intact.

---

## Unimplemented Features (Strictly Marked)

The following capabilities remain explicitly **NOT IMPLEMENTED**:
- [NOT IMPLEMENTED] Automatic index creation or index polling on application startup.
- [NOT IMPLEMENTED] Frontend templates or web user interface (Milestone 7).
- [NOT IMPLEMENTED] Deployment to external hosting platforms (Milestone 7).
- [NOT IMPLEMENTED] Authentication, authorization, or multi-tenant user accounts.
- [NOT IMPLEMENTED] OCR, computer vision, or AI-generated captions.

---

## Next Approved Milestone

- **Milestone 7**: Minimal Frontend & Deployment Preparation
  - Focus: Minimal, responsive researcher web interface (dashboard, note authoring, image attachment viewer, semantic search UI) and production deployment configuration (e.g. Render / Docker).
  - Required before starting: Explicit user approval to proceed.

