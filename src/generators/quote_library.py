"""
Quote library builder.

Collates all coded quotes, ranked by quality score, organised by
theme. Produces a JSON export and markdown summary for report use.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from config.settings import OUTPUT_DIR, PROCESSED_DIR

logger = logging.getLogger(__name__)

QUOTES_OUT = OUTPUT_DIR / "quotes"


def generate_quote_library() -> Path:
    """Build the ranked quote library from all coded segments."""
    QUOTES_OUT.mkdir(parents=True, exist_ok=True)

    coded_dir = PROCESSED_DIR / "coded_segments"
    if not coded_dir.exists():
        logger.warning("No coded segments directory found")
        return QUOTES_OUT / "ranked_quotes.json"

    all_quotes: list[dict[str, Any]] = []
    themes: dict[str, list[dict[str, Any]]] = {}

    for path in coded_dir.glob("*_coded.json"):
        with open(path) as f:
            data = json.load(f)

        segments = data.get("coded_segments", []) if isinstance(data, dict) else data if isinstance(data, list) else []

        for seg in segments:
            if not isinstance(seg, dict):
                continue
            quality = seg.get("quote_quality", {})
            overall = quality.get("overall", 0) if isinstance(quality, dict) else 0

            quote_entry = {
                "segment_id": seg.get("segment_id", ""),
                "participant_id": seg.get("participant_id", ""),
                "text": seg.get("text", ""),
                "timestamp": seg.get("timestamp", ""),
                "quality_score": overall,
                "recommendation": quality.get("recommendation", "") if isinstance(quality, dict) else "",
                "codes": seg.get("research_objective_codes", []),
            }
            all_quotes.append(quote_entry)

            for code in seg.get("research_objective_codes", []):
                root = code.split(".")[0] if "." in code else code
                themes.setdefault(root, []).append(quote_entry)

    all_quotes.sort(key=lambda q: q.get("quality_score", 0), reverse=True)

    # Save JSON
    library = {
        "total_quotes": len(all_quotes),
        "high_quality_count": sum(1 for q in all_quotes if q.get("quality_score", 0) >= 4),
        "quotes_by_rank": all_quotes,
        "quotes_by_theme": {
            theme: sorted(quotes, key=lambda q: q.get("quality_score", 0), reverse=True)
            for theme, quotes in themes.items()
        },
    }

    json_path = QUOTES_OUT / "ranked_quotes.json"
    with open(json_path, "w") as f:
        json.dump(library, f, indent=2, ensure_ascii=False)

    logger.info(
        "Generated quote library: %d quotes (%d high quality)",
        len(all_quotes),
        library["high_quality_count"],
    )
    return json_path
