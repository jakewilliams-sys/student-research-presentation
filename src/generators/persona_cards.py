"""
Persona card generator.

Creates formatted markdown persona profiles from agent output,
including key characteristics, evidence quotes, and segment distribution.
Uses flexible field lookups to handle schema variations.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from config.settings import OUTPUT_DIR, PROCESSED_DIR, REFERENCE_DIR

logger = logging.getLogger(__name__)

PERSONA_OUT = OUTPUT_DIR / "personas"


def _get(d: dict, *keys: str, default: Any = "") -> Any:
    """Try multiple keys in order, return the first non-empty value found."""
    for key in keys:
        val = d.get(key)
        if val not in (None, "", [], {}):
            return val
    return default


def _compute_segment_distribution(
    participant_ids: list[str], pmap: dict[str, Any]
) -> dict[str, int]:
    """Compute segment distribution by looking up each participant in the map."""
    dist: dict[str, int] = {}
    for pid in participant_ids:
        pdata = pmap.get(pid, {})
        if not isinstance(pdata, dict):
            continue
        seg = pdata.get("segment", "unknown")
        dist[seg] = dist.get(seg, 0) + 1
    return dict(sorted(dist.items(), key=lambda x: -x[1]))


def generate_persona_cards() -> list[Path]:
    """Generate individual persona card files."""
    PERSONA_OUT.mkdir(parents=True, exist_ok=True)

    data = _load_json(PROCESSED_DIR / "personas" / "personas.json")
    if not data:
        logger.warning("No persona data found")
        return []

    pmap = _load_json(REFERENCE_DIR / "participant_map.json") or {}

    personas = data.get("personas", []) if isinstance(data, dict) else data
    paths: list[Path] = []

    for p in personas:
        if not isinstance(p, dict):
            continue
        pid = p.get("persona_id", "unknown")
        name = p.get("name", pid)
        path = PERSONA_OUT / f"{pid}.md"

        lines = [f"# {name}\n"]

        tagline = _get(p, "tagline", "archetype", default="")
        if tagline:
            lines.append(f"*{tagline}*\n")

        reps = _get(p, "representative_participants", "participants", default=[])
        size = _get(p, "size", default="")
        if not size and isinstance(reps, list) and reps:
            size = str(len(reps))
        if size:
            lines.append(f"**Size:** {size} participants\n")

        # Demographics
        demo = p.get("demographics", {})
        if isinstance(demo, dict) and demo:
            lines.append("## Demographics\n")
            for k, v in demo.items():
                lines.append(f"- **{k.replace('_', ' ').title()}:** {v}")
            lines.append("")

        # Segment distribution (computed from participant_map, not LLM output)
        if isinstance(reps, list) and reps and pmap:
            dist = _compute_segment_distribution(reps, pmap)
        else:
            dist = p.get("segment_distribution", {})
        if dist:
            lines.append("**Segment distribution:**")
            for seg, count in dist.items():
                lines.append(f"- {seg}: {count}")
            lines.append("")

        # Behavioural profile
        behav = p.get("behavioural_profile", {})
        if isinstance(behav, dict) and behav:
            lines.append("## Behavioural Profile\n")
            for k, v in behav.items():
                if isinstance(v, list):
                    v = ", ".join(str(x) for x in v)
                lines.append(f"- **{k.replace('_', ' ').title()}:** {v}")
            lines.append("")

        # Key characteristics
        chars = p.get("key_characteristics", [])
        if chars:
            lines.append("## Key Characteristics\n")
            for c in chars:
                lines.append(f"- {c}")
            lines.append("")

        # Psychological profile
        psych = p.get("psychological_profile", {})
        if isinstance(psych, dict) and psych:
            lines.append("## Psychological Profile\n")
            for k, v in psych.items():
                lines.append(f"- **{k.replace('_', ' ').title()}:** {v}")
            lines.append("")

        # Delivery triggers
        triggers = p.get("delivery_triggers", [])
        if triggers:
            lines.append("## Delivery Triggers\n")
            for t in triggers:
                lines.append(f"- {t}")
            lines.append("")

        # Emotional drivers
        drivers = p.get("emotional_drivers", [])
        if drivers:
            lines.append(f"**Emotional drivers:** {', '.join(drivers)}\n")

        # Needs and pain points
        needs = p.get("needs_and_pain_points", {})
        if isinstance(needs, dict):
            unmet = needs.get("unmet_needs", [])
            if unmet:
                lines.append("## Unmet Needs\n")
                for n in unmet:
                    lines.append(f"- {n}")
                lines.append("")
            pains = needs.get("pain_points", [])
            if pains:
                lines.append("## Pain Points\n")
                for pp in pains:
                    lines.append(f"- {pp}")
                lines.append("")
        else:
            pains = p.get("pain_points", [])
            if pains:
                lines.append("## Pain Points\n")
                for pp in pains:
                    lines.append(f"- {pp}")
                lines.append("")

        # Deliveroo opportunity
        opp = _get(p, "deliveroo_opportunity", "deliveroo_opportunities", default="")
        if isinstance(opp, str) and opp:
            lines.append(f"## Deliveroo Opportunity\n\n{opp}\n")
        elif isinstance(opp, list) and opp:
            lines.append("## Deliveroo Opportunities\n")
            for o in opp:
                lines.append(f"- {o}")
            lines.append("")

        # Key quotes / evidence
        evidence = _get(p, "evidence", "key_quotes", default=[])
        if evidence:
            lines.append("## Key Quotes\n")
            for e in (evidence[:5] if isinstance(evidence, list) else []):
                if isinstance(e, dict):
                    lines.append(
                        f'> "{e.get("quote", "")}" '
                        f'-- {e.get("participant", "")}, {e.get("context", "")}'
                    )
                    lines.append("")
                elif isinstance(e, str):
                    lines.append(f'> "{e}"\n')
            lines.append("")

        # Confidence
        conf = _get(p, "confidence", default="")
        if conf:
            lines.append(f"*Confidence: {conf}*\n")

        # Representative participants
        if isinstance(reps, list) and reps:
            lines.append(f"**Participants:** {', '.join(reps)}\n")

        path.write_text("\n".join(lines))
        paths.append(path)
        logger.info("Generated persona card: %s", path.name)

    return paths


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)
