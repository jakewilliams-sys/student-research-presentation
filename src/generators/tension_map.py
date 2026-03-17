"""
Tension map generator.

Extracts and visualises paradoxes and contradictions that students
live with, drawn from tension-tagged coded segments.
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from config.settings import OUTPUT_DIR, PROCESSED_DIR

logger = logging.getLogger(__name__)

ENRICHMENT_OUT = OUTPUT_DIR / "enrichments"

_TENSION_CATEGORIES: list[tuple[str, list[str]]] = [
    (
        "Say-Do Gap",
        ["say-do", "says.*but", "claims.*but", "interview.*diary",
         "stated.*observed", "overestimate", "underestimate",
         "intention-action", "claims to.*but"],
    ),
    (
        "Cost-Value Paradox",
        ["price", "cost", "money", "saving", "spend", "budget",
         "afford", "expensive", "cheap", "worth", "value",
         "fee", "subscription"],
    ),
    (
        "Health vs Convenience",
        ["health", "healthy", "cook", "cooking", "meal prep",
         "nutritio", "junk", "unhealthy", "guilt.*eat",
         "diet", "fresh"],
    ),
    (
        "Social Pressure vs Individual Choice",
        ["social", "friend", "group", "peer", "flatmate",
         "alone.*order", "solo.*order", "others", "influenced",
         "pressure", "judge"],
    ),
    (
        "Treat vs Routine",
        ["treat", "reward", "special", "routine", "habit",
         "regular", "frequency", "every week", "daily",
         "normaliz", "indulgen"],
    ),
    (
        "Dependency vs Control",
        ["depend", "relian", "addict", "control", "limit",
         "can't stop", "too much", "should.*less", "try.*cut"],
    ),
    (
        "Platform Loyalty vs Price Shopping",
        ["platform", "switch", "uber", "deliveroo", "just eat",
         "loyal", "compari", "prefer.*but", "multi.*app",
         "shop around"],
    ),
]


def _classify_tension(text: str) -> str:
    """Classify a tension description into a category using keyword matching."""
    lower = text.lower()
    for category, patterns in _TENSION_CATEGORIES:
        for pattern in patterns:
            if re.search(pattern, lower):
                return category
    return "Other Contradictions"


def generate_tension_map() -> Path:
    """Build a tension/paradox map from coded segments."""
    ENRICHMENT_OUT.mkdir(parents=True, exist_ok=True)

    coded_dir = PROCESSED_DIR / "coded_segments"
    tensions: list[dict[str, Any]] = []

    if coded_dir.exists():
        for path in coded_dir.glob("*_coded.json"):
            with open(path) as f:
                data = json.load(f)
            segments = (
                data.get("coded_segments", [])
                if isinstance(data, dict)
                else data if isinstance(data, list) else []
            )
            for seg in segments:
                if not isinstance(seg, dict):
                    continue
                enrichment = seg.get("enrichment_tags", {})
                tension = enrichment.get("tension") if isinstance(enrichment, dict) else None
                if tension:
                    tensions.append({
                        "participant_id": seg.get("participant_id", ""),
                        "segment_id": seg.get("segment_id", ""),
                        "text": seg.get("text", ""),
                        "tension": tension,
                    })

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for t in tensions:
        tension_data = t["tension"]
        if isinstance(tension_data, dict):
            ttype = tension_data.get("tension_type", "Other Contradictions")
        elif isinstance(tension_data, str):
            ttype = _classify_tension(tension_data)
        else:
            ttype = "Other Contradictions"
        t["category"] = ttype
        grouped[ttype].append(t)

    total_participants = len({
        p.stem.replace("_coded", "").upper()
        for p in coded_dir.glob("*_coded.json")
    }) if coded_dir.exists() else 0
    tension_pids = {t["participant_id"] for t in tensions}
    n_with_tensions = len(tension_pids)

    lines = ["# Student Food Delivery Tensions\n"]
    if n_with_tensions < total_participants and total_participants > 0:
        lines.append(
            f"*{len(tensions)} tensions identified across "
            f"{n_with_tensions} of {total_participants} participants "
            f"({total_participants - n_with_tensions} showed no coded tensions)*\n"
        )
    else:
        lines.append(f"*{len(tensions)} tensions identified across "
                     f"{n_with_tensions} participants*\n")
    lines.append("## Core Paradoxes Students Live With\n")

    for i, (ttype, items) in enumerate(
        sorted(grouped.items(), key=lambda x: -len(x[1])), 1
    ):
        participant_ids = {item["participant_id"] for item in items}
        lines.append(
            f"### {i}. {ttype} "
            f"({len(items)} tensions, {len(participant_ids)} participants)\n"
        )
        for item in items[:5]:
            tension_desc = item["tension"]
            if isinstance(tension_desc, str):
                lines.append(f"- *{tension_desc}*")
            lines.append(
                f'  > "{item["text"]}" -- {item["participant_id"]}\n'
            )
        if len(items) > 5:
            lines.append(f"  *...and {len(items) - 5} more*\n")
        lines.append("")

    if not tensions:
        lines.append(
            "*No tension-tagged segments found yet. Run the Analysis Agent first.*\n"
        )

    out_path = ENRICHMENT_OUT / "tension_map.md"
    out_path.write_text("\n".join(lines))
    logger.info("Generated tension map: %d tensions in %d categories",
                len(tensions), len(grouped))

    json_path = OUTPUT_DIR / "data_exports" / "all_tensions.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(json_path, "w") as f:
        json.dump(
            {"tensions": tensions, "grouped": {k: v for k, v in grouped.items()}},
            f, indent=2, ensure_ascii=False,
        )

    return out_path
