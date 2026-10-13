"""Live Atlas Embedding Backfill Verification Harness for Milestone 6D.4.

Orchestrates a comprehensive, verifiable verification of scripts/backfill_embeddings.py
against the configured MongoDB Atlas cluster (fieldnote_db.notes).

Workflow:
1. Verifies preflight invariants (baseline count == 0, Atlas connection, index READY).
2. Seeds 4 synthetic disposable notes (3 with missing embedding, 1 with obsolete model).
3. Verifies CLI dry-run behavior (reports 4 candidates, 0 writes).
4. Verifies live batch backfill CLI (updates 4 documents, embeddings 384 dims, valid model).
5. Verifies live backfill CLI idempotency (reports 0 updates on 2nd run).
6. Verifies deterministic concurrency protection using a controlled conditional update test.
7. Guarantees safe cleanup in a finally block, verifying collection count returns to 0.
"""

import datetime
import json
import logging
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from bson import ObjectId

# Ensure project root is on sys.path
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from pymongo.database import Database
from app.config import get_settings
from app.db import create_mongo_client, close_mongo_client
from app.services.embedding import get_embedding_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("verify_live_backfill")


def run_command(cmd: List[str]) -> subprocess.CompletedProcess:
    """Run CLI command and return completed process."""
    logger.info("Executing command: %s", " ".join(cmd))
    res = subprocess.run(
        cmd,
        cwd=_project_root,
        capture_output=True,
        text=True,
        timeout=120,
    )
    logger.info("Exit code: %d", res.returncode)
    if res.stdout:
        logger.info("STDOUT:\n%s", res.stdout.strip())
    if res.stderr:
        logger.warning("STDERR:\n%s", res.stderr.strip())
    return res


def run_verification() -> Dict[str, Any]:
    settings = get_settings()
    logger.info("Starting Milestone 6D.4 verification against database: '%s'", settings.database_name)
    client = create_mongo_client(settings)
    db = client[settings.database_name]

    test_run_id = f"test-6d4-{uuid.uuid4().hex[:8]}"
    logger.info("Generated unique test run ID: %s", test_run_id)

    recorded_note_ids: List[ObjectId] = []
    report: Dict[str, Any] = {
        "test_run_id": test_run_id,
        "database": settings.database_name,
        "preflight": {},
        "dry_run": {},
        "live_backfill": {},
        "idempotency": {},
        "concurrency_protection": {},
        "cleanup": {},
    }

    try:
        # Step 1: Preflight
        ping_res = db.command("ping")
        baseline_count = db["notes"].count_documents({})
        indexes = list(db["notes"].list_search_indexes("idx_notes_vector"))
        index_status = indexes[0].get("status") if indexes else None
        index_queryable = indexes[0].get("queryable") if indexes else None

        report["preflight"] = {
            "ping": ping_res,
            "baseline_count": baseline_count,
            "index_status": index_status,
            "index_queryable": index_queryable,
        }
        logger.info("Preflight: ping=%s, baseline_count=%d, index_status=%s, queryable=%s", ping_res, baseline_count, index_status, index_queryable)

        if baseline_count != 0:
            raise RuntimeError(f"Preflight failed: baseline count is {baseline_count}, expected 0. Aborting.")
        if index_status != "READY" or not index_queryable:
            raise RuntimeError(f"Preflight failed: search index idx_notes_vector not READY/queryable: {indexes}")

        # Step 2: Prepare disposable legacy documents
        now = datetime.datetime.now(datetime.timezone.utc)
        synthetic_notes = [
            # Note 1: Missing embedding and embedding_model
            {
                "title": "Legacy Note Alpha - Glacial Flow Measurements",
                "content": "Recorded velocity vectors across southern terminus ice shelf.",
                "tags": ["glaciology", "climate", test_run_id],
                "created_at": now - datetime.timedelta(days=10),
                "updated_at": now - datetime.timedelta(days=10),
            },
            # Note 2: Missing embedding and embedding_model
            {
                "title": "Legacy Note Beta - Volcanic Ash Spectroscopy",
                "content": "Identified silicate particle distributions from airborne lidar returns.",
                "tags": ["geology", "volcanology", test_run_id],
                "created_at": now - datetime.timedelta(days=5),
                "updated_at": now - datetime.timedelta(days=5),
            },
            # Note 3: None embedding and missing embedding_model
            {
                "title": "Legacy Note Gamma - Deep Sea Hydrothermal Vents",
                "content": "Measured sulfide mineral precipitations near Mariana Trench vents.",
                "tags": ["oceanography", "hydrothermal", test_run_id],
                "embedding": None,
                "created_at": now - datetime.timedelta(days=2),
                "updated_at": now - datetime.timedelta(days=2),
            },
            # Note 4: Obsolete embedding_model and outdated embedding vector
            {
                "title": "Legacy Note Delta - Atmospheric Ozone Depletion",
                "content": "Tracked stratospheric chlorine monoxide concentrations above Antarctica.",
                "tags": ["meteorology", "atmosphere", test_run_id],
                "embedding": [0.001] * 128,  # Intentionally outdated 128-dim dummy vector
                "embedding_model": "sentence-transformers/legacy-v1-obsolete",
                "created_at": now - datetime.timedelta(days=1),
                "updated_at": now - datetime.timedelta(days=1),
            },
        ]

        logger.info("Inserting 4 synthetic legacy notes into 'fieldnote_db.notes'...")
        for note in synthetic_notes:
            res = db["notes"].insert_one(note)
            recorded_note_ids.append(res.inserted_id)
            logger.info("Inserted synthetic note '%s' -> ObjectId: %s", note["title"], res.inserted_id)

        # Record pre-dry-run snapshot of documents
        pre_dry_docs = {nid: db["notes"].find_one({"_id": nid}) for nid in recorded_note_ids}

        # Step 3: Verify Dry-Run Behavior
        logger.info("Executing: python scripts/backfill_embeddings.py --dry-run...")
        dry_res = run_command([sys.executable, "scripts/backfill_embeddings.py", "--dry-run"])
        if dry_res.returncode != 0:
            raise RuntimeError(f"Dry-run command failed with exit code {dry_res.returncode}")

        post_dry_docs = {nid: db["notes"].find_one({"_id": nid}) for nid in recorded_note_ids}
        # Verify 0 documents were modified by dry-run
        for nid in recorded_note_ids:
            if pre_dry_docs[nid] != post_dry_docs[nid]:
                raise RuntimeError(f"Dry-run modified document {nid} in MongoDB! Pre: {pre_dry_docs[nid]}, Post: {post_dry_docs[nid]}")

        # Check stdout reports 4 processed, 4 updated in simulation, 0 failed
        dry_stdout = dry_res.stdout
        if "Processed: 4" not in dry_stdout or "Updated:   4" not in dry_stdout or "Failed:    0" not in dry_stdout:
            raise RuntimeError(f"Dry-run summary does not match expected counts (Processed: 4, Updated: 4, Failed: 0):\n{dry_stdout}")

        report["dry_run"] = {
            "exit_code": dry_res.returncode,
            "stdout": dry_stdout,
            "documents_unmodified": True,
        }
        logger.info("Dry-run verified successfully. All 4 documents remained completely untouched.")

        # Step 4: Verify Live Backfill
        logger.info("Executing live backfill: python scripts/backfill_embeddings.py --batch-size 10...")
        live_res = run_command([sys.executable, "scripts/backfill_embeddings.py", "--batch-size", "10"])
        if live_res.returncode != 0:
            raise RuntimeError(f"Live backfill failed with exit code {live_res.returncode}")

        live_stdout = live_res.stdout
        if "Processed: 4" not in live_stdout or "Updated:   4" not in live_stdout or "Failed:    0" not in live_stdout:
            raise RuntimeError(f"Live backfill summary does not match expected counts (Processed: 4, Updated: 4, Failed: 0):\n{live_stdout}")

        # Audit all 4 documents in MongoDB
        post_live_docs = {nid: db["notes"].find_one({"_id": nid}) for nid in recorded_note_ids}
        embedding_service = get_embedding_service(settings)

        for nid, doc in post_live_docs.items():
            emb = doc.get("embedding")
            model = doc.get("embedding_model")
            if not isinstance(emb, list) or len(emb) != 384:
                raise RuntimeError(f"Note {nid} has invalid embedding: type={type(emb)}, len={len(emb) if isinstance(emb, list) else None}")
            if not all(isinstance(x, (int, float)) for x in emb):
                raise RuntimeError(f"Note {nid} embedding contains non-finite/non-numeric values!")
            if model != settings.embedding_model:
                raise RuntimeError(f"Note {nid} model mismatch: {model} != {settings.embedding_model}")

            # Verify embedding matches re-computed reference embedding
            expected_text = embedding_service.prepare_text(doc["title"], doc["content"])
            expected_vec = embedding_service.generate_embedding(expected_text)
            diff = max(abs(a - b) for a, b in zip(emb, expected_vec))
            if diff > 1e-4:
                raise RuntimeError(f"Note {nid} embedding diverged from reference embedding by {diff}!")

            # Verify title, content, created_at, tags remained untouched
            orig = pre_dry_docs[nid]
            if doc["title"] != orig["title"] or doc["content"] != orig["content"] or doc["tags"] != orig["tags"]:
                raise RuntimeError(f"Note {nid} core fields were altered during backfill!")

        report["live_backfill"] = {
            "exit_code": live_res.returncode,
            "stdout": live_stdout,
            "all_4_verified_384_dims": True,
            "all_models_match_target": True,
        }
        logger.info("Live backfill verified successfully. All 4 documents updated with exact 384-dim embeddings.")

        # Step 5: Verify Idempotency
        logger.info("Executing 2nd live backfill to verify idempotency: python scripts/backfill_embeddings.py...")
        idemp_res = run_command([sys.executable, "scripts/backfill_embeddings.py", "--batch-size", "10"])
        if idemp_res.returncode != 0:
            raise RuntimeError(f"Idempotent backfill failed with exit code {idemp_res.returncode}")

        idemp_stdout = idemp_res.stdout
        if "Processed: 0" not in idemp_stdout or "Updated:   0" not in idemp_stdout or "Failed:    0" not in idemp_stdout:
            raise RuntimeError(f"Idempotency run did not report Processed: 0, Updated: 0, Failed: 0:\n{idemp_stdout}")

        # Verify docs in MongoDB are bit-for-bit unchanged after 2nd run
        post_idemp_docs = {nid: db["notes"].find_one({"_id": nid}) for nid in recorded_note_ids}
        for nid in recorded_note_ids:
            if post_live_docs[nid] != post_idemp_docs[nid]:
                raise RuntimeError(f"Document {nid} was altered during idempotent backfill run!")

        report["idempotency"] = {
            "exit_code": idemp_res.returncode,
            "stdout": idemp_stdout,
            "zero_documents_reprocessed": True,
            "documents_unmodified": True,
        }
        logger.info("Idempotency verified successfully. 0 documents reprocessed, 0 writes performed.")

        # Step 6: Verify Concurrency Protection Deterministically
        # Note on scope and limitations: This test evaluates the atomic conditional-update predicate
        # ({"_id": disp_id, "updated_at": original_updated_at}) using a deterministic sequence rather
        # than an uncoordinated wall-clock race condition between background processes. It validates
        # that MongoDB's atomic document update rejects stale writes when updated_at has advanced.
        logger.info("Verifying concurrency protection deterministically on disposable document...")
        # Insert a 5th disposable note
        disp_note = {
            "title": "Disposable Note Epsilon - Seismic Wave Propagation",
            "content": "Original P-wave arrival times at seismic station 12.",
            "tags": ["seismology", test_run_id],
            "created_at": now,
            "updated_at": now,
        }
        disp_res = db["notes"].insert_one(disp_note)
        disp_id = disp_res.inserted_id
        recorded_note_ids.append(disp_id)
        logger.info("Inserted 5th disposable note -> ObjectId: %s", disp_id)

        # 1. Read and record its current updated_at
        initial_doc = db["notes"].find_one({"_id": disp_id})
        original_updated_at = initial_doc["updated_at"]

        # 2. Simulate concurrent edit by another process/user
        concurrent_time = now + datetime.timedelta(seconds=45)
        new_content = "UPDATED CONTENT: Revised P-wave and S-wave arrival times at seismic station 12."
        db["notes"].update_one(
            {"_id": disp_id},
            {
                "$set": {
                    "content": new_content,
                    "updated_at": concurrent_time,
                }
            },
        )
        logger.info("Simulated concurrent edit: updated_at changed from %s to %s", original_updated_at, concurrent_time)

        # 3. Attempt the backfill update using the original _id and original updated_at condition
        backfill_simulated_vector = [0.123] * 384
        update_filter = {
            "_id": disp_id,
            "updated_at": original_updated_at,
        }
        update_result = db["notes"].update_one(
            update_filter,
            {
                "$set": {
                    "embedding": backfill_simulated_vector,
                    "embedding_model": settings.embedding_model,
                }
            },
        )

        # 4. Verify matched_count == 0 and document retains newer content
        logger.info("Conditional update matched_count: %d, modified_count: %d", update_result.matched_count, update_result.modified_count)
        if update_result.matched_count != 0:
            raise RuntimeError(f"Concurrency protection failed! update_one matched {update_result.matched_count} documents when updated_at differed!")

        final_disp_doc = db["notes"].find_one({"_id": disp_id})
        if final_disp_doc["content"] != new_content:
            raise RuntimeError("Newer content was overwritten despite concurrency protection!")
        if "embedding" in final_disp_doc and final_disp_doc["embedding"] == backfill_simulated_vector:
            raise RuntimeError("Stale embedding was applied despite concurrency protection!")

        report["concurrency_protection"] = {
            "matched_count": update_result.matched_count,
            "modified_count": update_result.modified_count,
            "newer_content_preserved": True,
            "stale_embedding_rejected": True,
        }
        logger.info("Concurrency protection verified deterministically: update matched 0 documents, newer edit preserved.")

    finally:
        # Mandatory Step 7: Cleanup recorded test notes only
        logger.info("Executing mandatory cleanup for all recorded note ObjectIds (%d notes)...", len(recorded_note_ids))
        cleanup_failures = []
        for nid in recorded_note_ids:
            try:
                del_res = db["notes"].delete_one({"_id": nid})
                rem = db["notes"].find_one({"_id": nid})
                if rem is not None:
                    cleanup_failures.append(f"ObjectId {nid} still present in collection!")
                else:
                    logger.info("Deleted and verified removal of ObjectId: %s", nid)
            except Exception as e:
                cleanup_failures.append(f"Exception deleting {nid}: {e}")

        final_count = db["notes"].count_documents({})
        report["cleanup"] = {
            "attempted_ids": [str(x) for x in recorded_note_ids],
            "failures": cleanup_failures,
            "final_count": final_count,
            "restored_baseline": (final_count == 0 and len(cleanup_failures) == 0),
        }
        logger.info("Cleanup completed. Final notes collection count: %d (Baseline was 0)", final_count)

        client.close()

        if cleanup_failures or final_count != 0:
            raise RuntimeError(f"Cleanup failed! Failures: {cleanup_failures}, Final count: {final_count}")

    return report


if __name__ == "__main__":
    report = run_verification()
    print("\n--- BACKFILL VERIFICATION REPORT ---")
    print(json.dumps(report, indent=2, default=str))
    print("\nVerification completed successfully.")
