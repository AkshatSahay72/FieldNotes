"""Seed script for Fieldnote synthetic demo dataset.

Populates a designated demo database with clearly fictional research notes,
personal memories, journal reflections, ideas, learning syntheses, and synthetic
evidence images across all 5 schema types ('journal', 'memory', 'research', 'idea', 'learning').

Designed to be completely idempotent: safe to rerun repeatedly without creating duplicate
notes or attachments.

Safety Guards:
1. Requires an explicit target database name (never falls back silently to personal/dev DB).
2. Unconditionally refuses execution in production environments (APP_ENV=production).
3. Unconditionally refuses to seed personal databases ('fieldnote_private', 'fieldnote_personal').
4. Rejects default development database ('fieldnote_db') unless --allow-default-db is passed.
5. Marks all seeded records explicitly as public demo records (is_demo=True, user_id=None).

Usage:
    # Dry-run inspection without database modifications:
    python scripts/seed_demo_data.py --database-name fieldnote_demo --dry-run

    # Execute seeding into explicit demo database:
    python scripts/seed_demo_data.py --database-name fieldnote_demo
"""

import argparse
import io
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure project root is on sys.path for direct script execution
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from bson import ObjectId
from PIL import Image, ImageDraw
import gridfs
from pymongo.database import Database
from pymongo.errors import PyMongoError

from app.config import Settings, get_settings
from app.db import create_mongo_client, close_mongo_client, init_db_indexes
from app.services.embedding import (
    EmbeddingService,
    EmbeddingServiceError,
    get_embedding_service,
)

logger = logging.getLogger("seed_demo_data")

DEFAULT_DEV_DATABASE_NAME = "fieldnote_db"
KNOWN_PRIVATE_DATABASES = {"fieldnote_private", "fieldnote_personal"}

# ---------------------------------------------------------------------------
# Synthetic Entries (Fictional people, projects, dates, and experiences)
# Covering all 5 schema types: journal, memory, research, idea, learning
# ---------------------------------------------------------------------------

SYNTHETIC_NOTES: List[Dict[str, Any]] = [
    # 1. Type: journal
    {
        "title": "Journal: Quiet Solarium Reflections & Evening Chamomile",
        "type": "journal",
        "content": (
            "## Evening in the Solarium\n"
            "Sitting by the western bay window of the high-altitude station as twilight deepens over the ridge. "
            "Spent the last hour inspecting the hydroponic chamomile trays with Maya.\n\n"
            "### Reflections on Pace\n"
            "- It is tempting to treat every observation as urgent data, but quiet reflection often surfaces "
            "the patterns we missed during busy daytime collection.\n"
            "- The gentle hum of the nutrient misting pump feels grounding after hours analyzing telemetry streams.\n"
            "- Tomorrow: calibrate the optical spectrometer before the first ridge frost settles."
        ),
        "tags": ["journal", "solarium", "night", "botany", "reflection"],
        "created_at": datetime(2026, 8, 14, 21, 45, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 8, 14, 21, 45, 0, tzinfo=timezone.utc),
    },
    # 2. Type: journal
    {
        "title": "Journal: Field Station Relocation — Packing Crates for Station Apex",
        "type": "journal",
        "content": (
            "## Moving Day Reflections\n"
            "The valley field lab is almost completely packed into weather-sealed shipping containers. "
            "Dr. Soren and I spent the afternoon securing the delicate quartz cuvettes and micro-balances.\n\n"
            "### Transitions\n"
            "- Leaving the valley feels bittersweet. We spent seven months here learning the rhythms of the wetlands.\n"
            "- Station Apex sits 1,400 meters higher on the windswept eastern saddle. Expecting colder nights, "
            "cleaner optical windows, and much more wind sheer.\n"
            "- Key goal for week one at Apex: establish the satellite uplink and deploy the atmospheric sensor array."
        ),
        "tags": ["journal", "station-apex", "travel", "packing", "fieldwork"],
        "created_at": datetime(2026, 9, 2, 17, 30, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 9, 2, 17, 30, 0, tzinfo=timezone.utc),
    },
    # 3. Type: memory
    {
        "title": "Memory: First Sunrise at Observatory Ridge (May 2024)",
        "type": "memory",
        "content": (
            "## Sensory Recollection\n"
            "The memory of cresting Whispering Pines Trail at 5:15 AM with Soren and Elena. "
            "The biting cold air carried a sharp scent of subalpine cedar, damp earth, and steam from our stainless steel coffee thermos.\n\n"
            "### The Moment\n"
            "- Watching the horizon ignite from deep indigo into layered bands of amber and coral.\n"
            "- The frost on the solar panel frames began melting into tiny glistening rivulets.\n"
            "- We paused for twenty minutes in total silence before switching on the radio mast. "
            "One of those mornings where research feels indistinguishable from wonder."
        ),
        "tags": ["memory", "astronomy", "ridge", "dawn", "reflection"],
        "created_at": datetime(2026, 8, 20, 5, 30, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 8, 20, 5, 30, 0, tzinfo=timezone.utc),
    },
    # 4. Type: memory
    {
        "title": "Acoustic Telemetry Log: Marine Mammal Echo Pattern Beta",
        "type": "memory",
        "content": (
            "## Midnight in the Hydrophone Cabin\n"
            "Listening to hydrophone array H-3 deployed along the continental slope at depth 240m from the research tender *Albatross*.\n\n"
            "### Telemetry Experience\n"
            "- In the dark cabin illuminated only by oscilloscope phosphors, distinct tonal clicks began rising above ambient swell noise.\n"
            "- Frequency bandwidth sampled: 10 Hz to 96 kHz.\n"
            "- Rhythmic fundamental pulses at 32.4 kHz with an inter-click interval of 145 ms.\n"
            "- We logged the coordinates and listened for forty minutes as the pod drifted west past the underwater canyon."
        ),
        "tags": ["memory", "telemetry", "bioacoustics", "marine-biology"],
        "created_at": datetime(2026, 9, 28, 16, 45, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 9, 28, 16, 45, 0, tzinfo=timezone.utc),
    },
    # 5. Type: research
    {
        "title": "Field Specimen Observation: Bioluminescent Fungi Strain Lumina-9",
        "type": "research",
        "content": (
            "## Summary & Methodology\n"
            "Preliminary examination of *Mycena lux-synthetica* (Strain Lumina-9) collected from basalt cavern fissure at Grid Ref E-14.\n\n"
            "### Field Observations\n"
            "- Substrate: Decomposed birch cellulose enriched with synthetic nutrient broth.\n"
            "- Peak luminescence measured at 520 nm (emerald green emission spectrum).\n"
            "- Luciferin-luciferase reaction demonstrated steady continuous emission over 72 hours.\n"
            "- Spore dispersal rate: 450 spores/cm²/hr under 85% relative humidity.\n\n"
            "### Next Steps\n"
            "Cross-verify genomic markers against fungal reference database."
        ),
        "tags": ["research", "specimen", "mycology", "bioluminescence", "subterranean"],
        "created_at": datetime(2026, 9, 15, 10, 30, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 9, 15, 10, 30, 0, tzinfo=timezone.utc),
    },
    # 6. Type: research
    {
        "title": "Soil Stratification and Geochemical Assay: Site Borehole Bravo-12",
        "type": "research",
        "content": (
            "## Geochemical Profile\n"
            "Coring completed at Borehole Bravo-12 in ancient lacustrine sediment deposits. Total depth reached: 4.8 meters.\n\n"
            "### Stratigraphic Horizons\n"
            "1. **0.0 - 0.8m**: Humic loam with active micro-arthropod bioturbation.\n"
            "2. **0.8 - 2.4m**: Dense silty clay with micro-nodules of iron oxyhydroxide.\n"
            "3. **2.4 - 4.8m**: Basal glaciolacustrine varved silt with fine carbonaceous lenses.\n\n"
            "### Laboratory Notes\n"
            "Core intactness rated at 96%. Samples partitioned for moisture content and carbon assay."
        ),
        "tags": ["research", "geology", "stratigraphy", "soil-mechanics", "lacustrine"],
        "created_at": datetime(2026, 9, 18, 14, 15, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 9, 18, 14, 15, 0, tzinfo=timezone.utc),
    },
    # 7. Type: idea
    {
        "title": "Project Concept: Autonomous Solar-Kite Micro-Weather Network",
        "type": "idea",
        "content": (
            "## Concept Proposal\n"
            "A lightweight distributed weather-monitoring network using tethered carbon-fiber solar kites along coastal ridgelines.\n\n"
            "### Architecture & Capabilities\n"
            "- Ultralight airframe carrying micro-barometers, humidity sensors, and optical dewpoint probes.\n"
            "- Flexible thin-film solar backing powers low-power BLE mesh transmission down the tether.\n"
            "- Continuous vertical profiling from 10m to 150m AGL without rotor noise or battery depletion limits.\n"
            "- Potential application: early fog-inversion warnings for agricultural valleys."
        ),
        "tags": ["idea", "drone-survey", "sensor-network", "climate", "hardware"],
        "created_at": datetime(2026, 10, 2, 11, 20, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 10, 2, 11, 20, 0, tzinfo=timezone.utc),
    },
    # 8. Type: idea
    {
        "title": "Idea: Enzymatic Recycling for Expedition Polymer Ropes",
        "type": "idea",
        "content": (
            "## Sustainable Field Gear Concept\n"
            "Field stations generate significant discarded static climbing cord and nylon netting each season.\n\n"
            "### Proposed Workflow\n"
            "- Explore portable digestion tanks using recombinant cutinase enzymes (analogous to PX-400 assays).\n"
            "- Shred frayed synthetic ropes into coarse granules in a hand-cranked camp mill.\n"
            "- Digest into non-toxic liquid organic acid precursors that can be safely neutralized or reused as solvent.\n"
            "- Eliminates plastic burn pits and reduces pack-out weight on remote expeditions."
        ),
        "tags": ["idea", "biochemistry", "sustainability", "polymers", "expedition"],
        "created_at": datetime(2026, 10, 8, 13, 10, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 10, 8, 13, 10, 0, tzinfo=timezone.utc),
    },
    # 9. Type: learning
    {
        "title": "Cryogenic Core Preservation Protocol: Glacial Archive Sample Arc-7",
        "type": "learning",
        "content": (
            "## Standard Operating Procedure Takeaways\n"
            "Validation of cold-chain preservation protocols for synthetic glacial ice analogs.\n\n"
            "### Key Takeaways\n"
            "- Core extraction performed using diamond-tipped hollow auger.\n"
            "- Samples purged with dry gaseous argon (grade 5.0) to eliminate atmospheric CO₂ contamination.\n"
            "- Transferred immediately to vapor-phase liquid nitrogen storage unit at -160°C.\n"
            "- High-resolution tomography confirmed zero thermal fracture propagation.\n\n"
            "### Quality Standard\n"
            "Complies with Antarctic sample preservation standard protocol Revision 4.2."
        ),
        "tags": ["learning", "protocol", "cryogenics", "ice-core", "paleoclimate"],
        "created_at": datetime(2026, 9, 22, 9, 0, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 9, 22, 9, 0, 0, tzinfo=timezone.utc),
    },
    # 10. Type: learning
    {
        "title": "Learning Synthesis: High-Resolution Micro-CT Artifact Reduction Techniques",
        "type": "learning",
        "content": (
            "## Radiographic Imaging Study Notes\n"
            "Synthesizing lessons learned while scanning dense rock core inclusions with micro-computed tomography.\n\n"
            "### Core Principles\n"
            "- **Beam Hardening Correction**: Pre-filtering the raw X-ray beam with a 0.5mm copper shim reduces cupping artifacts in high-density basalt.\n"
            "- **Sample Orientation**: Aligning cylindrical cores parallel to the rotation axis minimizes ring artifact distortion.\n"
            "- **Ring Filter Calibration**: Always run blank detector flat-fields between every three core scans to prevent detector pixel drift."
        ),
        "tags": ["learning", "micro-ct", "imaging", "radiology", "methods"],
        "created_at": datetime(2026, 10, 11, 15, 20, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 10, 11, 15, 20, 0, tzinfo=timezone.utc),
    },
]

# ---------------------------------------------------------------------------
# Synthetic Evidence Images (Generated in-memory with Pillow)
# ---------------------------------------------------------------------------

def generate_synthetic_image(title_text: str, accent_color: tuple, pattern: str = "spectrum") -> bytes:
    """Generate a clean synthetic scientific chart/diagram image in memory."""
    width, height = 480, 320
    img = Image.new("RGB", (width, height), color=(248, 250, 252))
    draw = ImageDraw.Draw(img)

    # Frame border
    draw.rectangle([0, 0, width - 1, height - 1], outline=(226, 232, 240), width=2)
    # Header box
    draw.rectangle([0, 0, width - 1, 44], fill=(241, 245, 249), outline=(226, 232, 240))
    # Synthetic label
    draw.text((16, 14), f"SYNTHETIC DEMO EVIDENCE: {title_text}", fill=(15, 23, 42))

    if pattern == "spectrum":
        # Draw axes
        draw.line([(48, 260), (440, 260)], fill=(100, 116, 139), width=2)
        draw.line([(48, 260), (48, 70)], fill=(100, 116, 139), width=2)
        # Synthetic curve points
        points = []
        for x_val in range(48, 440, 6):
            dx = (x_val - 240) / 45.0
            y_val = 260 - int(160 / (1.0 + dx * dx))
            points.append((x_val, y_val))
        if len(points) >= 2:
            draw.line(points, fill=accent_color, width=3)
        draw.text((56, 270), "400 nm", fill=(100, 116, 139))
        draw.text((220, 270), "Peak: 520 nm", fill=(15, 23, 42))
        draw.text((390, 270), "700 nm", fill=(100, 116, 139))

    elif pattern == "stratigraphy":
        # Draw stacked soil layers
        layers = [
            (70, 120, (217, 249, 157), "Horizon A: Humic Loam (0 - 0.8m)"),
            (120, 190, (254, 215, 170), "Horizon B: Silty Clay (0.8 - 2.4m)"),
            (190, 270, (203, 213, 225), "Horizon C: Varved Silt (2.4 - 4.8m)"),
        ]
        for y1, y2, color, label in layers:
            draw.rectangle([48, y1, 432, y2], fill=color, outline=(148, 163, 184))
            draw.text((64, y1 + 16), label, fill=(15, 23, 42))

    elif pattern == "spectrogram":
        # Draw synthetic frequency bins
        for i in range(12):
            bx = 56 + i * 31
            by = 260 - (20 + (i % 5) * 35)
            draw.rectangle([bx, by, bx + 22, 260], fill=accent_color, outline=(15, 23, 42))
        draw.text((56, 75), "Fundamental: 32.4 kHz", fill=(15, 23, 42))
        draw.text((56, 95), "SNR: 24 dB (Calibrated)", fill=(100, 116, 139))

    elif pattern == "kite_schema":
        # Draw flight altitude telemetry grid
        draw.line([(48, 260), (440, 260)], fill=(100, 116, 139), width=2)
        draw.line([(48, 260), (48, 70)], fill=(100, 116, 139), width=2)
        for gy in range(90, 260, 40):
            draw.line([(48, gy), (440, gy)], fill=(226, 232, 240), width=1)
        # Profile curve
        kpoints = [(48, 250), (120, 220), (200, 150), (290, 110), (380, 85), (440, 80)]
        draw.line(kpoints, fill=accent_color, width=3)
        draw.text((56, 75), "Altitude: 150m AGL (Ascent Profile)", fill=(15, 23, 42))
        draw.text((56, 95), "Telemetry: Barometric & Optical Dewpoint", fill=(100, 116, 139))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


SYNTHETIC_ATTACHMENTS: List[Dict[str, Any]] = [
    {
        "parent_title": "Field Specimen Observation: Bioluminescent Fungi Strain Lumina-9",
        "filename": "lumina9_emission_spectrum.png",
        "caption": "Emission Spectrogram (520 nm peak)",
        "description": "Continuous spectroradiometric emission scan of Strain Lumina-9.",
        "accent_color": (5, 150, 105),  # emerald
        "pattern": "spectrum",
    },
    {
        "parent_title": "Soil Stratification and Geochemical Assay: Site Borehole Bravo-12",
        "filename": "borehole_b12_stratigraphy.png",
        "caption": "Borehole Bravo-12 Stratigraphic Core Cross-section",
        "description": "Cross-sectional visualization of lacustrine sediment horizons.",
        "accent_color": (217, 119, 6),  # amber
        "pattern": "stratigraphy",
    },
    {
        "parent_title": "Acoustic Telemetry Log: Marine Mammal Echo Pattern Beta",
        "filename": "acoustic_telemetry_beta.png",
        "caption": "Hydrophone Harmonic Click Profile",
        "description": "Calibrated acoustic telemetry spectrogram at 240m depth.",
        "accent_color": (2, 132, 199),  # sky blue
        "pattern": "spectrogram",
    },
    {
        "parent_title": "Project Concept: Autonomous Solar-Kite Micro-Weather Network",
        "filename": "solar_kite_telemetry_schema.png",
        "caption": "Solar-Kite Ascent Altitude Profile",
        "description": "Vertical barometric and optical dewpoint profiling telemetry.",
        "accent_color": (13, 148, 136),  # teal
        "pattern": "kite_schema",
    },
]

# ---------------------------------------------------------------------------
# Seeding Logic (Idempotent and database-isolated)
# ---------------------------------------------------------------------------

def seed_demo_data(
    db: Database,
    fs: Optional[gridfs.GridFS] = None,
    embedding_service: Optional[EmbeddingService] = None,
    dry_run: bool = False,
) -> Dict[str, int]:
    """Populate database with synthetic notes and attachments idempotently.

    - Checks for existing notes by title; skips if present.
    - Checks for existing attachments by (note_id, filename); skips if present.
    - Explicitly sets is_demo=True and user_id=None on all demo records.
    - Computes vector embeddings if embedding_service is available.
    - Returns counts of created and skipped records.
    """
    counts = {
        "notes_created": 0,
        "notes_skipped": 0,
        "attachments_created": 0,
        "attachments_skipped": 0,
    }

    if fs is None and not dry_run:
        fs = gridfs.GridFS(db)

    title_to_id: Dict[str, ObjectId] = {}

    # 1. Process synthetic notes
    for note_template in SYNTHETIC_NOTES:
        title = note_template["title"]
        existing = db["notes"].find_one({"title": title})

        if existing is not None:
            title_to_id[title] = existing["_id"]
            counts["notes_skipped"] += 1
            logger.info("Note already exists (skipped): %s", title)
            continue

        counts["notes_created"] += 1
        logger.info("Creating synthetic note: %s", title)

        if dry_run:
            title_to_id[title] = ObjectId()
            continue

        doc = dict(note_template)
        if "type" not in doc:
            doc["type"] = "memory"
        # Always set is_demo=True and user_id=None for public demo records
        doc["is_demo"] = True
        doc["user_id"] = None

        # Compute vector embedding if service is provided
        if embedding_service is not None:
            try:
                emb_text = embedding_service.prepare_text(title, doc["content"])
                emb = embedding_service.generate_embedding(emb_text)
                doc["embedding"] = emb
                doc["embedding_model"] = embedding_service.model_name
            except Exception as err:
                logger.warning("Could not compute embedding for '%s': %s", title, err)

        res = db["notes"].insert_one(doc)
        title_to_id[title] = res.inserted_id

    # 2. Process synthetic attachments
    for att_template in SYNTHETIC_ATTACHMENTS:
        parent_title = att_template["parent_title"]
        note_id = title_to_id.get(parent_title)

        if note_id is None:
            parent_note = db["notes"].find_one({"title": parent_title})
            if parent_note is not None:
                note_id = parent_note["_id"]

        if note_id is None:
            logger.warning("Parent note not found for attachment: %s", att_template["filename"])
            continue

        filename = att_template["filename"]
        existing_att = db["attachments"].find_one({"note_id": note_id, "filename": filename})

        if existing_att is not None:
            counts["attachments_skipped"] += 1
            logger.info("Attachment already exists (skipped): %s for note %s", filename, note_id)
            continue

        counts["attachments_created"] += 1
        logger.info("Creating synthetic attachment: %s for note %s", filename, note_id)

        if dry_run:
            continue

        image_bytes = generate_synthetic_image(
            title_text=att_template["caption"],
            accent_color=att_template["accent_color"],
            pattern=att_template["pattern"],
        )

        file_id = fs.put(
            image_bytes,
            filename=filename,
            content_type="image/png",
        )

        att_doc = {
            "note_id": note_id,
            "file_id": file_id,
            "filename": filename,
            "content_type": "image/png",
            "file_size": len(image_bytes),
            "caption": att_template.get("caption"),
            "description": att_template.get("description"),
            "is_demo": True,
            "user_id": None,
            "created_at": datetime.now(timezone.utc),
        }
        try:
            db["attachments"].insert_one(att_doc)
        except Exception as insert_err:
            logger.error(
                "Failed to insert attachment metadata for '%s' (note %s); deleting newly created GridFS file %s: %s",
                filename,
                note_id,
                file_id,
                type(insert_err).__name__,
            )
            try:
                fs.delete(file_id)
            except Exception as cleanup_err:
                logger.warning(
                    "Compensating GridFS cleanup failed for %s: %s",
                    file_id,
                    type(cleanup_err).__name__,
                )
            raise insert_err

    return counts


def main() -> int:
    """CLI entrypoint for synthetic demo database seeding."""
    parser = argparse.ArgumentParser(
        description="Seed Fieldnote demo database with synthetic research notes and evidence images."
    )
    parser.add_argument(
        "--database-name",
        type=str,
        default=None,
        help="Explicit target database name (e.g. 'fieldnote_demo').",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the seeding process without modifying any database records.",
    )
    parser.add_argument(
        "--allow-default-db",
        action="store_true",
        help="Explicitly permit seeding against the default development database ('fieldnote_db').",
    )
    parser.add_argument(
        "--skip-embeddings",
        action="store_true",
        help="Skip generating vector embeddings during seeding.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    settings = get_settings()

    # 1. Require explicit target database - cannot default silently
    target_db_name = args.database_name
    if not target_db_name:
        env_db = os.environ.get("DATABASE_NAME")
        if env_db and env_db.strip():
            target_db_name = env_db.strip()

    if not target_db_name:
        logger.error(
            "SAFETY ABORT: An explicit target database must be specified via "
            "--database-name <db> or DATABASE_NAME environment variable. "
            "Silent database fallback is disabled to prevent accidental data pollution."
        )
        return 1

    # 2. Production safety guard: unconditionally refuse to seed in production environment
    if settings.app_env.lower() == "production":
        logger.error(
            "SAFETY ABORT: Refusing to seed synthetic demo data in production environment (APP_ENV=production)."
        )
        return 1

    # 3. Personal user database protection: never allow seeding into private user databases
    if (
        target_db_name in KNOWN_PRIVATE_DATABASES
        or target_db_name.startswith("fieldnote_private")
        or target_db_name.startswith("fieldnote_personal")
    ):
        logger.error(
            "SAFETY ABORT: Target database '%s' is a private personal database. "
            "Demo records can NEVER be seeded into a personal user's database.",
            target_db_name,
        )
        return 1

    # 4. Prevent accidental seeding into the primary development database without explicit override
    if target_db_name == DEFAULT_DEV_DATABASE_NAME and not args.allow_default_db:
        logger.error(
            "SAFETY ABORT: Target database is '%s' (the default development database). "
            "To prevent polluting development data with synthetic demo records, "
            "please specify a dedicated demo database using --database-name fieldnote_demo. "
            "If you intentionally want to seed the default development database, pass --allow-default-db.",
            target_db_name,
        )
        return 1

    logger.info(
        "Starting synthetic demo data seed (database='%s', dry_run=%s)",
        target_db_name,
        args.dry_run,
    )

    client = None
    try:
        client = create_mongo_client(settings)
        db = client[target_db_name]

        if not args.dry_run:
            init_db_indexes(db)

        embedding_service = None
        if not args.skip_embeddings:
            try:
                embedding_service = get_embedding_service(settings)
                logger.info("Embedding service initialized using model '%s'.", settings.embedding_model)
            except Exception as emb_err:
                logger.warning("Embedding service not available (%s); continuing without embeddings.", emb_err)

        counts = seed_demo_data(
            db=db,
            embedding_service=embedding_service,
            dry_run=args.dry_run,
        )
    except Exception as err:
        logger.error("Seeding operation failed: %s", type(err).__name__)
        return 1
    finally:
        if client is not None:
            close_mongo_client(client)

    print("\n--- Synthetic Demo Seed Summary ---")
    print(f"Target Database:      {target_db_name}")
    print(f"Dry Run:              {args.dry_run}")
    print(f"Notes Created:        {counts['notes_created']}")
    print(f"Notes Skipped:        {counts['notes_skipped']}")
    print(f"Attachments Created:  {counts['attachments_created']}")
    print(f"Attachments Skipped:  {counts['attachments_skipped']}")
    print("-----------------------------------\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
