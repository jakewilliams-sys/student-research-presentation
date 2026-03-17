"""
DScout Diary Study Loader

Reads the DScout diary study data from a cached raw JSON export (originally
sourced from Google Sheets 'All Participants' tab), maps Scout Names to
participant IDs, structures each participant's 7-day diary into JSON,
and saves per-participant files for pipeline consumption.

The raw export is stored as a list of row arrays in
    data/raw/dscout_all_participants_raw.json
The first element is the header row; subsequent elements are data rows.

Usage:
    python -m src.loaders.dscout_loader          # process cached raw data
    python -m src.loaders.dscout_loader --check   # validate output files
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_PATH = DATA_DIR / "raw" / "dscout_all_participants_raw.json"
OUTPUT_DIR = DATA_DIR / "processed" / "diary_entries"

SCOUT_NAME_TO_PID: dict[str, str] = {
    "Aayush M": "P009",
    "Adam P": "P006",
    "Chika S": "P005",
    "Dearbhla J": "P010",
    "Edna P": "P024",
    "Evan D": "P015",
    "Indiana K": "P003",
    "Jill L": "P017",
    "Joshua W": "P007",
    "Katie L": "P022",
    "Louise H": "P018",
    "Mrugesh M": "P011",
    "Rory C": "P002",
    "Sian W": "P004",
    "Suryansh J": "P012",
}

MEAL_SLOTS = ["Breakfast", "Lunch", "Dinner"]

COLUMN_PREFIXES = {
    "source": "Food source",
    "category": "Meal category",
    "delivery_app": "Delivery app",
    "why_ordered": "Why ordered (open text)",
    "reasons": "Reason for choice",
    "ate_with": "Who ate with",
    "photo": "Photo",
}


def _build_column_index(headers: list[str]) -> dict[str, int]:
    """Map header strings to column indices."""
    return {h: i for i, h in enumerate(headers)}


def _parse_multi_value(raw: str) -> list[str]:
    """Split comma-separated multi-select values, stripping whitespace."""
    if not raw or not raw.strip():
        return []
    return [v.strip() for v in raw.split(",") if v.strip()]


def _cell(row: list[str], idx: int) -> str:
    """Safely get a cell value, returning empty string if out of bounds."""
    if idx < 0 or idx >= len(row):
        return ""
    return row[idx].strip() if row[idx] else ""


def _parse_meal(row: list[str], meal: str, col_idx: dict[str, int]) -> dict[str, Any]:
    """Extract structured data for a single meal slot from a row."""
    prefix = f"{meal} - "

    source_key = prefix + COLUMN_PREFIXES["source"]
    category_key = prefix + COLUMN_PREFIXES["category"]
    app_key = prefix + COLUMN_PREFIXES["delivery_app"]
    why_key = prefix + COLUMN_PREFIXES["why_ordered"]
    reasons_key = prefix + COLUMN_PREFIXES["reasons"]
    ate_with_key = prefix + COLUMN_PREFIXES["ate_with"]
    photo_key = prefix + COLUMN_PREFIXES["photo"]

    source = _cell(row, col_idx.get(source_key, -1))
    category = _cell(row, col_idx.get(category_key, -1)) or None
    delivery_app = _cell(row, col_idx.get(app_key, -1)) or None
    why_ordered = _cell(row, col_idx.get(why_key, -1)) or None
    reasons = _parse_multi_value(_cell(row, col_idx.get(reasons_key, -1)))
    ate_with = _parse_multi_value(_cell(row, col_idx.get(ate_with_key, -1)))
    photo_raw = _cell(row, col_idx.get(photo_key, -1))
    has_photo = bool(photo_raw and photo_raw != "")

    skipped = source.lower().startswith("skipped") if source else False

    return {
        "source": source if source else "Unknown / not specified",
        "category": category,
        "delivery_app": delivery_app,
        "why_ordered": why_ordered,
        "reasons": reasons,
        "ate_with": ate_with,
        "has_photo": has_photo,
        "skipped": skipped,
    }


def _compute_summary_stats(days: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute aggregate statistics across all diary days."""
    total_meals = 0
    total_skipped = 0
    delivery_orders = 0
    apps_used: set[str] = set()
    sources: list[str] = []
    all_reasons: list[str] = []

    for day in days:
        for meal_key in ["breakfast", "lunch", "dinner"]:
            meal = day.get(meal_key, {})
            if not meal:
                continue
            total_meals += 1
            if meal.get("skipped"):
                total_skipped += 1
                continue

            src = meal.get("source", "")
            sources.append(src)

            if meal.get("delivery_app"):
                delivery_orders += 1
                apps_used.add(meal["delivery_app"])

            all_reasons.extend(meal.get("reasons", []))

    from collections import Counter
    reason_counts = Counter(all_reasons)
    top_reasons = [r for r, _ in reason_counts.most_common(5)]

    source_counts = Counter(sources)
    most_common_source = source_counts.most_common(1)[0][0] if source_counts else None

    return {
        "total_meals_logged": total_meals,
        "total_skipped": total_skipped,
        "delivery_orders": delivery_orders,
        "delivery_apps_used": sorted(apps_used),
        "top_reasons": top_reasons,
        "most_common_source": most_common_source,
    }


def process_rows(headers: list[str], rows: list[list[str]]) -> dict[str, dict[str, Any]]:
    """
    Process raw Google Sheets rows into structured per-participant diary data.

    Returns a dict keyed by participant ID.
    """
    col_idx = _build_column_index(headers)

    grouped: dict[str, list[list[str]]] = defaultdict(list)
    for row in rows:
        name = _cell(row, col_idx.get("Scout Name", -1))
        if name:
            grouped[name].append(row)

    results: dict[str, dict[str, Any]] = {}

    for scout_name, scout_rows in grouped.items():
        pid = SCOUT_NAME_TO_PID.get(scout_name)
        if not pid:
            logger.warning("Unknown scout name '%s', skipping", scout_name)
            continue

        scout_id = _cell(scout_rows[0], col_idx.get("Scout ID", -1))
        grad_status = _cell(scout_rows[0], col_idx.get("Graduate Status", -1))

        days: list[dict[str, Any]] = []
        for row in sorted(scout_rows, key=lambda r: int(_cell(r, col_idx.get("Day", -1)) or 0)):
            day_num = int(_cell(row, col_idx.get("Day", -1)) or 0)
            date_submitted = _cell(row, col_idx.get("Date Submitted", -1))
            reflection = _cell(row, col_idx.get("Daily reflection (video transcription)", -1)) or None

            day_data: dict[str, Any] = {
                "day": day_num,
                "date": date_submitted.split(" ")[0] if date_submitted else None,
                "date_submitted": date_submitted,
            }

            for meal in MEAL_SLOTS:
                day_data[meal.lower()] = _parse_meal(row, meal, col_idx)

            day_data["daily_reflection"] = reflection
            days.append(day_data)

        participant_data = {
            "participant_id": pid,
            "scout_name": scout_name,
            "scout_id": scout_id,
            "segment": grad_status,
            "days": days,
            "summary_stats": _compute_summary_stats(days),
        }

        results[pid] = participant_data

    return results


def load_and_save(raw_path: Path | None = None) -> dict[str, str]:
    """
    Load raw cached data, process it, and save per-participant JSON files.

    Returns a dict mapping PID -> output file path.
    """
    path = raw_path or RAW_PATH
    if not path.exists():
        raise FileNotFoundError(f"Raw DScout data not found at {path}")

    with open(path) as f:
        raw_data = json.load(f)

    headers = raw_data[0]
    rows = raw_data[1:]

    results = process_rows(headers, rows)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    saved: dict[str, str] = {}

    for pid, data in results.items():
        out_path = OUTPUT_DIR / f"{pid.lower()}_diary.json"
        with open(out_path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        saved[pid] = str(out_path)
        logger.info("Saved diary data for %s (%s) -> %s", pid, data["scout_name"], out_path.name)

    logger.info("Processed %d diary participants", len(saved))
    return saved


def validate_output() -> None:
    """Check that all 15 participants have diary files with expected structure."""
    if not OUTPUT_DIR.exists():
        print("No diary_entries directory found. Run load_and_save() first.")
        return

    files = list(OUTPUT_DIR.glob("*.json"))
    print(f"Found {len(files)} diary files")

    for path in sorted(files):
        with open(path) as f:
            data = json.load(f)
        pid = data.get("participant_id", "?")
        name = data.get("scout_name", "?")
        n_days = len(data.get("days", []))
        stats = data.get("summary_stats", {})
        print(
            f"  {pid} ({name}): {n_days} days, "
            f"{stats.get('total_meals_logged', 0)} meals, "
            f"{stats.get('total_skipped', 0)} skipped, "
            f"{stats.get('delivery_orders', 0)} delivery orders"
        )


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    if "--check" in sys.argv:
        validate_output()
    else:
        load_and_save()
