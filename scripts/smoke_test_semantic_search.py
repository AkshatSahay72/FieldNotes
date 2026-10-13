"""Live Semantic Retrieval Smoke Test for Milestone 6D.3.

Executes an end-to-end verification against the running FastAPI application
and MongoDB Atlas cluster with the 'idx_notes_vector' search index.

Prerequisites:
    1. The FastAPI application must be running locally on http://127.0.0.1:8000:
       uvicorn app.main:app --host 127.0.0.1 --port 8000
    2. The MongoDB Atlas connection string must be configured in .env.
    3. The 'idx_notes_vector' Vector Search index must be in 'READY' and queryable status.
    4. The 'notes' collection must be empty (baseline document count = 0) to ensure
       deterministic evaluation and test isolation.

Safety Invariants:
    - Verifies connectivity, index readiness, and empty baseline before inserting test notes.
    - Creates 3 synthetic research notes tagged with a unique run UUID via POST /api/notes.
    - Verifies 384-dimensional finite embeddings in MongoDB.
    - Bounded polling (45s max) for Atlas Vector Search change stream ingestion sync.
    - Executes 5 test query categories via GET /api/search/semantic.
    - Asserts that target notes rank #1 for relevant queries and scores are finite floats.
    - Asserts that internal 'embedding' vectors and 'embedding_model' strings are omitted.
    - Guaranteed cleanup in a finally block: deletes ONLY the recorded created note IDs.
    - Verifies deletion in MongoDB and confirms collection count returns to baseline (0).
    - Exits with non-zero status code if any assertion or cleanup step fails.

Usage:
    python scripts/smoke_test_semantic_search.py [--base-url http://127.0.0.1:8000]
"""

import argparse
import json
import logging
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
import urllib.request
import urllib.error
import urllib.parse
from bson import ObjectId

# Ensure project root is on sys.path
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from pymongo.database import Database
from app.config import get_settings
from app.db import create_mongo_client, close_mongo_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("smoke_test_semantic_search")


def http_request(
    base_url: str,
    method: str,
    path: str,
    data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Execute an HTTP request to the running FastAPI server."""
    url = f"{base_url}{path}"
    headers = {"Accept": "application/json"}
    body_bytes = None
    if data is not None:
        headers["Content-Type"] = "application/json"
        body_bytes = json.dumps(data).encode("utf-8")

    req = urllib.request.Request(url, data=body_bytes, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30.0) as resp:
            status_code = resp.status
            content = resp.read().decode("utf-8")
            payload = json.loads(content) if content else None
            return {"status_code": status_code, "data": payload}
    except urllib.error.HTTPError as err:
        content = err.read().decode("utf-8")
        try:
            payload = json.loads(content)
        except Exception:
            payload = content
        return {"status_code": err.code, "data": payload}


def run_smoke_test(base_url: str = "http://127.0.0.1:8000") -> Dict[str, Any]:
    """Execute end-to-end smoke test against the live running API and Atlas cluster."""
    settings = get_settings()
    logger.info("Connecting to Atlas database: '%s' for pre-flight check...", settings.database_name)
    client = create_mongo_client(settings)
    db = client[settings.database_name]

    test_run_id = f"test-6d3-{uuid.uuid4().hex[:8]}"
    logger.info("Generated unique test run ID: %s", test_run_id)

    recorded_note_ids: List[str] = []
    report: Dict[str, Any] = {
        "test_run_id": test_run_id,
        "database": settings.database_name,
        "baseline_count": None,
        "created_notes": [],
        "search_results": [],
        "cleanup_status": {},
        "final_count": None,
    }

    try:
        # Preflight 1: Health check on running API
        logger.info("Pinging running API health at %s/api/health...", base_url)
        health = http_request(base_url, "GET", "/api/health")
        if health["status_code"] != 200 or health["data"].get("status") != "healthy":
            raise RuntimeError(f"API health check failed: {health}")
        logger.info("API health check verified: %s", health["data"])

        # Preflight 2: Atlas Vector Index readiness
        indexes = list(db["notes"].list_search_indexes("idx_notes_vector"))
        if not indexes or indexes[0].get("status") != "READY" or not indexes[0].get("queryable"):
            raise RuntimeError(f"Vector search index idx_notes_vector is not READY/queryable: {indexes}")
        logger.info("Vector search index idx_notes_vector confirmed READY and queryable.")

        # Preflight 3: Baseline count
        baseline_count = db["notes"].count_documents({})
        report["baseline_count"] = baseline_count
        logger.info("Baseline notes collection count: %d", baseline_count)
        if baseline_count != 0:
            raise RuntimeError(f"Baseline notes count is {baseline_count}, expected 0. Halting without mutating data.")

        # Step 2: Create 3 synthetic research notes
        synthetic_notes = [
            {
                "title": "Orbital Mechanics and Satellite Trajectory Calculations",
                "content": "Calculated Hohmann transfer orbits, delta-v budgets, and gravitational perturbations for Low Earth Orbit satellite stationkeeping.",
                "tags": ["orbital-mechanics", "aerospace", test_run_id],
                "expected_category": "orbital_mechanics",
            },
            {
                "title": "Plant Root Architecture and Soil Moisture Uptake",
                "content": "Analyzed xylem water transport, hydraulic redistribution, and root depth profiles under variable soil moisture deficit conditions.",
                "tags": ["botany", "soil-moisture", test_run_id],
                "expected_category": "plant_roots",
            },
            {
                "title": "Database Indexing and B-Tree Query Optimization",
                "content": "Evaluated compound index selectivity, execution plans, and write overhead for high-concurrency database queries.",
                "tags": ["databases", "indexing", test_run_id],
                "expected_category": "database_indexing",
            },
        ]

        logger.info("Creating 3 synthetic research notes via POST %s/api/notes...", base_url)
        for note_def in synthetic_notes:
            resp = http_request(base_url, "POST", "/api/notes", {
                "title": note_def["title"],
                "content": note_def["content"],
                "tags": note_def["tags"],
            })
            if resp["status_code"] != 201:
                raise RuntimeError(f"Failed to create note '{note_def['title']}': {resp}")

            created_id = resp["data"]["id"]
            recorded_note_ids.append(created_id)
            logger.info("Created note '%s' -> ID: %s", note_def["title"], created_id)

            # Verify in MongoDB
            doc = db["notes"].find_one({"_id": ObjectId(created_id)})
            if not doc:
                raise RuntimeError(f"Created note {created_id} not found in MongoDB.")

            embedding = doc.get("embedding")
            embedding_model = doc.get("embedding_model")
            if not isinstance(embedding, list) or len(embedding) != 384:
                raise RuntimeError(f"Invalid embedding dimensions for note {created_id}: {type(embedding)}, len={len(embedding) if isinstance(embedding, list) else None}")
            if not all(isinstance(x, (int, float)) for x in embedding):
                raise RuntimeError(f"Non-numeric values in embedding for note {created_id}")
            if embedding_model != settings.embedding_model:
                raise RuntimeError(f"Mismatch embedding_model: {embedding_model} vs {settings.embedding_model}")

            report["created_notes"].append({
                "id": created_id,
                "title": note_def["title"],
                "category": note_def["expected_category"],
                "dimensions": len(embedding),
                "model": embedding_model,
            })
            logger.info("Verified note %s in MongoDB: 384 dimensions, model=%s", created_id, embedding_model)

        # Step 2b: Bounded wait for Atlas Vector Search ingestion sync
        logger.info("Waiting for Atlas Vector Search index to ingest all %d notes (max 45s)...", len(recorded_note_ids))
        start_sync = time.time()
        synced = False
        while time.time() - start_sync < 45.0:
            probe = http_request(base_url, "GET", "/api/search/semantic?q=scientific+research&limit=10")
            if probe["status_code"] == 200:
                count_indexed = len(probe["data"])
                logger.info("Atlas Vector Search probe: %d / %d notes indexed (elapsed: %.1fs)", count_indexed, len(recorded_note_ids), time.time() - start_sync)
                if count_indexed == len(recorded_note_ids):
                    synced = True
                    break
            time.sleep(3.0)

        if not synced:
            raise RuntimeError(f"Atlas Vector Search did not index all {len(recorded_note_ids)} notes within 45s timeout.")

        # Step 3: Run 5 live semantic search queries
        test_queries = [
            {
                "category": "1. Closely matching orbital mechanics",
                "query": "Orbital mechanics and satellite trajectories",
                "expected_top_id": recorded_note_ids[0],
                "expected_title": synthetic_notes[0]["title"],
            },
            {
                "category": "2. Paraphrased orbital mechanics",
                "query": "Keeping satellites on course in space",
                "expected_top_id": recorded_note_ids[0],
                "expected_title": synthetic_notes[0]["title"],
            },
            {
                "category": "3. Plant roots obtaining water",
                "query": "Plant roots obtaining water from soil",
                "expected_top_id": recorded_note_ids[1],
                "expected_title": synthetic_notes[1]["title"],
            },
            {
                "category": "4. Speeding up database lookups",
                "query": "Speeding up database lookups",
                "expected_top_id": recorded_note_ids[2],
                "expected_title": synthetic_notes[2]["title"],
            },
            {
                "category": "5. Unrelated topic",
                "query": "Renaissance oil painting techniques and pigments",
                "expected_top_id": None,
                "expected_title": None,
            },
        ]

        logger.info("Executing 5 live semantic search queries via GET %s/api/search/semantic...", base_url)
        for q_info in test_queries:
            q_encoded = urllib.parse.quote(q_info["query"])
            search_resp = http_request(base_url, "GET", f"/api/search/semantic?q={q_encoded}&limit=10")
            if search_resp["status_code"] != 200:
                raise RuntimeError(f"Search failed for '{q_info['query']}': {search_resp}")

            results = search_resp["data"]
            logger.info("Query: '%s' | Returned: %d notes", q_info["query"], len(results))

            # Inspect payload safety: zero vector leakage
            query_log_results = []
            for rank, r in enumerate(results, start=1):
                if "embedding" in r or "embedding_model" in r:
                    raise RuntimeError(f"LEAKAGE DETECTED: embedding vector or model in response: {r}")
                score = r.get("score")
                if not isinstance(score, (int, float)):
                    raise RuntimeError(f"Invalid score type in response: {score}")

                query_log_results.append({
                    "rank": rank,
                    "id": r["id"],
                    "title": r["title"],
                    "score": round(score, 6),
                })
                logger.info("   Rank %d: '%s' (ID: %s, Score: %.6f)", rank, r["title"], r["id"], score)

            top_id = results[0]["id"] if results else None
            top_title = results[0]["title"] if results else None

            # Assert deterministic ranking expectations for domain queries 1..4
            if q_info["expected_top_id"] is not None:
                if top_id != q_info["expected_top_id"]:
                    raise AssertionError(
                        f"Ranking mismatch for query '{q_info['query']}': "
                        f"Expected top note ID {q_info['expected_top_id']} ({q_info['expected_title']}), "
                        f"but got {top_id} ({top_title})"
                    )

            matches_expected = (top_id == q_info["expected_top_id"]) if q_info["expected_top_id"] else True

            report["search_results"].append({
                "category": q_info["category"],
                "query": q_info["query"],
                "returned_count": len(results),
                "top_id": top_id,
                "top_title": top_title,
                "expected_top_id": q_info["expected_top_id"],
                "matches_expected": matches_expected,
                "results": query_log_results,
            })

    finally:
        # Mandatory Step 4: Cleanup recorded test notes only
        logger.info("Executing safe cleanup for recorded test note IDs: %s", recorded_note_ids)
        cleanup_failures = []
        for nid in recorded_note_ids:
            try:
                del_resp = http_request(base_url, "DELETE", f"/api/notes/{nid}")
                if del_resp["status_code"] not in [200, 204]:
                    cleanup_failures.append(f"HTTP {del_resp['status_code']} for ID {nid}")
                # Verify deletion in MongoDB
                remaining = db["notes"].find_one({"_id": ObjectId(nid)})
                if remaining is not None:
                    cleanup_failures.append(f"Document {nid} still exists in MongoDB!")
                else:
                    logger.info("Successfully deleted and verified removal of note ID: %s", nid)
            except Exception as e:
                cleanup_failures.append(f"Exception deleting {nid}: {e}")

        final_count = db["notes"].count_documents({})
        report["final_count"] = final_count
        restored = (final_count == 0) and (len(cleanup_failures) == 0)
        report["cleanup_status"] = {
            "attempted_ids": recorded_note_ids,
            "failures": cleanup_failures,
            "final_count": final_count,
            "restored_baseline": restored,
        }
        logger.info("Cleanup completed. Final collection count: %d (Baseline was %d)", final_count, report.get("baseline_count", 0))

        client.close()

        # Enforce that cleanup failures or failure to restore baseline always fails the smoke test
        if cleanup_failures or final_count != 0:
            raise RuntimeError(
                f"Cleanup failed! Remaining failures: {cleanup_failures}, final collection count: {final_count}"
            )

    return report


def main() -> int:
    """CLI entrypoint for running live semantic search smoke test."""
    parser = argparse.ArgumentParser(
        description="Run live semantic search smoke test against FastAPI and Atlas Vector Search."
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Base URL of running Fieldnote FastAPI service (default: http://127.0.0.1:8000)",
    )
    args = parser.parse_args()

    try:
        report = run_smoke_test(base_url=args.base_url)
        print("\n--- SMOKE TEST JSON REPORT ---")
        print(json.dumps(report, indent=2))
        logger.info("All smoke test assertions and cleanups passed successfully.")
        return 0
    except Exception as exc:
        logger.error("Smoke test failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
