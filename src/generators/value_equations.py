"""
Value equation generator.

Analyses what "worth it" means to each persona by extracting
value-component-tagged segments and mapping them to personas.
"""

from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from config.settings import OUTPUT_DIR, PROCESSED_DIR

logger = logging.getLogger(__name__)

ENRICHMENT_OUT = OUTPUT_DIR / "enrichments"


def generate_value_equations() -> Path:
    """Build value equations per persona from coded segments."""
    ENRICHMENT_OUT.mkdir(parents=True, exist_ok=True)

    # Load persona assignments
    persona_data = _load_json(PROCESSED_DIR / "personas" / "personas.json")
    assignments: dict[str, str] = {}
    if isinstance(persona_data, dict):
        raw = persona_data.get("participant_assignments", {})
        for pid, persona in raw.items():
            if isinstance(persona, list):
                assignments[pid] = persona[0] if persona else ""
            else:
                assignments[pid] = persona

    # Load value component tags
    coded_dir = PROCESSED_DIR / "coded_segments"
    value_data: list[dict[str, Any]] = []

    if coded_dir.exists():
        for path in coded_dir.glob("*_coded.json"):
            with open(path) as f:
                data = json.load(f)
            segments = data.get("coded_segments", []) if isinstance(data, dict) else data if isinstance(data, list) else []
            for seg in segments:
                if not isinstance(seg, dict):
                    continue
                enrichment = seg.get("enrichment_tags", {})
                value = enrichment.get("value_component", []) if isinstance(enrichment, dict) else []
                if value:
                    pid = seg.get("participant_id", "")
                    value_data.append({
                        "participant_id": pid,
                        "persona": assignments.get(pid, "unassigned"),
                        "text": seg.get("text", ""),
                        "value_components": value if isinstance(value, list) else [value],
                    })

    # Group by persona
    persona_values: dict[str, Counter] = defaultdict(Counter)
    for item in value_data:
        persona = item["persona"]
        for v in item["value_components"]:
            persona_values[persona][v] += 1

    lines = ["# Value Equations by Persona\n"]

    for persona, counts in sorted(persona_values.items()):
        lines.append(f"## {persona.replace('_', ' ').title()}\n")
        total = sum(counts.values())
        lines.append("**Value = " + " + ".join(
            f"{comp.title()} ({c}/{total})" for comp, c in counts.most_common(5)
        ) + "**\n")
        for comp, c in counts.most_common():
            pct = c / total * 100 if total else 0
            lines.append(f"- {comp}: {c} mentions ({pct:.0f}%)")
        lines.append("")

    if not value_data:
        lines.append("*No value-component-tagged segments found yet.*\n")

    out_path = ENRICHMENT_OUT / "value_equations.md"
    out_path.write_text("\n".join(lines))
    logger.info("Generated value equations: %d segments", len(value_data))
    return out_path


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)
