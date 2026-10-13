"""Seed script for Fieldnote synthetic demo dataset.

Populates a designated demo database with clearly fictional research notes
and synthetic evidence images. Designed to be completely idempotent: safe to
rerun repeatedly without creating duplicate notes or attachments.

Usage:
    # Explicit demo database selection via environment variable:
    DATABASE_NAME=fieldnote_demo python scripts/seed_demo_data.py

    # Or explicit CLI argument:
    python scripts/seed_demo_data.py --database-name fieldnote_demo

    # Dry-run inspection without database modifications:
    python scripts/seed_demo_data.py --database-name fieldnote_demo --dry-run
"""

import argparse
import io
import logging
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

# ---------------------------------------------------------------------------
# Synthetic Research Notes (Fictional academic observations)
# ---------------------------------------------------------------------------

SYNTHETIC_NOTES: List[Dict[str, Any]] = [
    {
        "title": "Field Specimen Observation: Bioluminescent Fungi Strain Lumina-9",
        "content": (
            "## Summary\n"
            "Preliminary field examination of *Mycena lux-synthetica* (Strain Lumina-9) "
            "collected from basalt cavern fissure at Grid Ref E-14.\n\n"
            "### Methodology & Observations\n"
            "- Substrate: Decomposed birch cellulose enriched with synthetic nutrient broth.\n"
            "- Peak luminescence measured at 520 nm (emerald green emission spectrum).\n"
            "- Luciferin-luciferase reaction demonstrated steady continuous emission over 72 hours.\n"
            "- Spore dispersal rate: 450 spores/cm²/hr under 85% relative humidity.\n\n"
            "### Next Steps\n"
            "Cross-verify genomic markers against fungal reference database."
        ),
        "tags": ["specimen", "mycology", "bioluminescence", "subterranean"],
        "created_at": datetime(2026, 9, 15, 10, 30, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 9, 15, 10, 30, 0, tzinfo=timezone.utc),
    },
    {
        "title": "Soil Stratification and Geochemical Assay: Site Borehole Bravo-12",
        "content": (
            "## Geochemical Profile\n"
            "Coring completed at Borehole Bravo-12 in ancient lacustrine sediment deposits. "
            "Total depth reached: 4.8 meters.\n\n"
            "### Stratigraphic Horizons\n"
            "1. **0.0 - 0.8m**: Humic loam with active micro-arthropod bioturbation.\n"
            "2. **0.8 - 2.4m**: Dense silty clay with micro-nodules of iron oxyhydroxide.\n"
            "3. **2.4 - 4.8m**: Basal glaciolacustrine varved silt with fine carbonaceous lenses.\n\n"
            "### Laboratory Notes\n"
            "Core intactness rated at 96%. Samples partitioned for moisture content and carbon assay."
        ),
        "tags": ["geology", "stratigraphy", "soil-mechanics", "lacustrine"],
        "created_at": datetime(2026, 9, 18, 14, 15, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 9, 18, 14, 15, 0, tzinfo=timezone.utc),
    },
    {
        "title": "Cryogenic Core Preservation Protocol: Glacial Archive Sample Arc-7",
        "content": (
            "## Standard Operating Procedure Trial\n"
            "Validation of cold-chain preservation protocols for synthetic glacial ice analogs.\n\n"
            "### Procedure Summary\n"
            "- Core extraction performed using diamond-tipped hollow auger.\n"
            "- Samples purged with dry gaseous argon (grade 5.0) to eliminate atmospheric CO₂ contamination.\n"
            "- Transferred immediately to vapor-phase liquid nitrogen storage unit at -160°C.\n"
            "- High-resolution tomography confirmed zero thermal fracture propagation.\n\n"
            "### Quality Assurance\n"
            "Complies with Antarctic sample preservation standard protocol Revision 4.2."
        ),
        "tags": ["protocol", "cryogenics", "ice-core", "paleoclimate"],
        "created_at": datetime(2026, 9, 22, 9, 0, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 9, 22, 9, 0, 0, tzinfo=timezone.utc),
    },
    {
        "title": "Acoustic Telemetry Log: Marine Mammal Echo Pattern Beta",
        "content": (
            "## Hydrophone Acoustic Recording\n"
            "Hydrophone array H-3 deployed along continental slope at depth 240m.\n\n"
            "### Telemetry Data\n"
            "- Frequency bandwidth sampled: 10 Hz to 96 kHz.\n"
            "- Detection: Distinct tonal sequences and multi-harmonic click trains.\n"
            "- Mean fundamental frequency: 32.4 kHz with inter-click interval of 145 ms.\n"
            "- Signal-to-noise ratio: 24 dB above ambient sea-state background.\n\n"
            "### Observations\n"
            "Pattern correlates with synthetic vocalization benchmark curves."
        ),
        "tags": ["telemetry", "bioacoustics", "marine-biology"],
        "created_at": datetime(2026, 9, 28, 16, 45, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 9, 28, 16, 45, 0, tzinfo=timezone.utc),
    },
    {
        "title": "Autonomous Sensor Drone Flight Log: Transect Quadrant 4",
        "content": (
            "## Aerial Environmental Survey\n"
            "Automated mission 4-B executed across riparian conservation zone.\n\n"
            "### Sensor Telemetry\n"
            "- Altitude: 45m AGL with 80% longitudinal overlap.\n"
            "- Multispectral payload captured NDVI and calibrated surface thermal radiometry.\n"
            "- Vegetative stress index indicated healthy canopy moisture across 92% of the surveyed transect.\n"
            "- Flight duration: 28 minutes; battery reserve on recovery: 34%."
        ),
        "tags": ["drone-survey", "thermal-imaging", "sensor-network"],
        "created_at": datetime(2026, 10, 2, 11, 20, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 10, 2, 11, 20, 0, tzinfo=timezone.utc),
    },
    {
        "title": "Enzymatic Degradation Kinetics: Synthetic Biopolymer PX-400",
        "content": (
            "## Biodegradation Assay\n"
            "In vitro degradation kinetics of synthetic polyester-amide compound PX-400.\n\n"
            "### Reaction Parameters\n"
            "- Enzyme: Recombinant cutinase analog (2.5 mg/mL in phosphate-buffered saline, pH 7.4).\n"
            "- Temperature: 37.0°C ± 0.2°C with continuous orbital shaking at 120 RPM.\n"
            "- Substrate weight loss: 42.1% at 48 hours, reaching 88.5% at 120 hours.\n"
            "- Degradation products identified: Monomeric hydroxy acids with zero toxic residues."
        ),
        "tags": ["biochemistry", "kinetics", "polymers", "enzymes"],
        "created_at": datetime(2026, 10, 8, 13, 10, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 10, 8, 13, 10, 0, tzinfo=timezone.utc),
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
            # bell-shaped curve around x=240
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
            # Look up note in db if not in current run map
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
        help="Target database name (overrides DATABASE_NAME environment variable).",
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

    # Production safety guard: unconditionally refuse to seed in production environment
    if settings.app_env.lower() == "production":
        logger.error(
            "SAFETY ABORT: Refusing to seed synthetic demo data in production environment (APP_ENV=production)."
        )
        return 1

    target_db_name = args.database_name or settings.database_name

    # Safety guard: prevent accidental seeding into the primary development database
    if target_db_name == DEFAULT_DEV_DATABASE_NAME and not args.allow_default_db:
        logger.error(
            "SAFETY ABORT: Target database is '%s' (the default development database). "
            "To prevent polluting development data with synthetic demo records, "
            "please specify a dedicated demo database using DATABASE_NAME=fieldnote_demo "
            "or --database-name fieldnote_demo. If you intentionally want to seed the "
            "default database, pass --allow-default-db.",
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
            # Ensure indexes are established on the demo database
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
