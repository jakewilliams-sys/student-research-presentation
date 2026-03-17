"""
Journey map visualisation generator.

Builds Mermaid journey diagrams from coded segment data (emotions and
temporal context) and persona assignments. Falls back to per-participant
journeys when persona data is unavailable.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any

from config.settings import OUTPUT_DIR, PROCESSED_DIR

logger = logging.getLogger(__name__)

JOURNEY_OUT = OUTPUT_DIR / "journeys"

ORDERING_STAGES = [
    ("pre_order", "Pre-Order", "Deciding whether to order"),
    ("decision", "Decision Point", "Choosing platform and food"),
    ("ordering", "Ordering", "Placing the order"),
    ("waiting", "Waiting", "Waiting for delivery"),
    ("consumption", "Consumption", "Eating the food"),
    ("post_order", "Post-Order", "After the meal"),
]

_EMOTION_SCORES = {
    "joy": 5, "excitement": 5, "anticipation": 4, "connection": 5,
    "relief": 4, "satisfaction": 5, "comfort": 4,
    "indifference": 3, "routine": 3,
    "frustration": 2, "guilt": 2, "stress": 2, "anxiety": 2,
    "regret": 1, "anger": 1,
}

# Emotions that act as catch-all defaults in LLM coding. Excluded from
# dominant-emotion calculation unless they are the only emotions present.
_NOISE_EMOTIONS = {"indifference", "neutral", "routine"}


def generate_journey_maps() -> list[Path]:
    """Generate Mermaid journey diagram files from coded segments."""
    JOURNEY_OUT.mkdir(parents=True, exist_ok=True)

    personas = _load_json(PROCESSED_DIR / "personas" / "personas.json")
    coded_dir = PROCESSED_DIR / "coded_segments"
    summary_dir = PROCESSED_DIR / "participant_summaries"

    all_coded = _load_all_coded(coded_dir)
    all_summaries = _load_all_summaries(summary_dir)

    if not all_coded:
        logger.warning("No coded segment data found for journey maps")
        return []

    paths: list[Path] = []

    if personas and isinstance(personas, dict) and personas.get("personas"):
        paths.extend(
            _generate_persona_journeys(personas, all_coded, all_summaries)
        )
    else:
        paths.extend(
            _generate_participant_journeys(all_coded, all_summaries)
        )

    return paths


def _generate_persona_journeys(
    personas: dict[str, Any],
    all_coded: dict[str, dict],
    all_summaries: dict[str, dict],
) -> list[Path]:
    """One journey per persona, aggregating across representative participants."""
    paths: list[Path] = []

    for persona in personas.get("personas", []):
        if not isinstance(persona, dict):
            continue

        pid = persona.get("persona_id", "unknown")
        name = persona.get("name", pid)

        rep_ids = persona.get("representative_participants", [])
        if not rep_ids:
            rep_ids = persona.get("participants", [])

        stages = _build_stages_from_data(rep_ids, all_coded, all_summaries, name)

        lines = _render_journey_md(name, stages)
        path = JOURNEY_OUT / f"journey_{pid}.md"
        path.write_text("\n".join(lines))
        paths.append(path)
        logger.info("Generated persona journey: %s", path.name)

    return paths


def _generate_participant_journeys(
    all_coded: dict[str, dict],
    all_summaries: dict[str, dict],
) -> list[Path]:
    """One journey per participant when personas aren't available."""
    paths: list[Path] = []

    for pid in sorted(all_coded.keys()):
        summary = all_summaries.get(pid, {})
        name = f"{pid}"
        if isinstance(summary, dict):
            name = f"{pid} ({summary.get('participant_id', pid)})"

        stages = _build_stages_from_data([pid], all_coded, all_summaries, name)

        lines = _render_journey_md(name, stages)
        path = JOURNEY_OUT / f"journey_{pid}.md"
        path.write_text("\n".join(lines))
        paths.append(path)
        logger.info("Generated participant journey: %s", path.name)

    return paths


def _build_stages_from_data(
    participant_ids: list[str],
    all_coded: dict[str, dict],
    all_summaries: dict[str, dict],
    label: str,
) -> list[dict[str, Any]]:
    """
    Build journey stages by mapping coded segment emotions/temporal data
    to the ordering stage sequence.
    """
    stage_emotions: dict[str, list[str]] = defaultdict(list)

    for pid in participant_ids:
        coded = all_coded.get(pid, {})
        segments = coded.get("coded_segments", []) if isinstance(coded, dict) else []

        for seg in segments:
            if not isinstance(seg, dict):
                continue
            ctx_tags = seg.get("context_tags") or {}
            emotions = ctx_tags.get("emotion") or []
            if isinstance(emotions, str):
                emotions = [emotions]

            mapped_stage = _map_segment_to_stage(seg)
            for emo in emotions:
                if emo:
                    stage_emotions[mapped_stage].append(emo.lower().strip())

    stages: list[dict[str, Any]] = []
    for stage_key, stage_name, stage_desc in ORDERING_STAGES:
        all_emotions = stage_emotions.get(stage_key, [])
        meaningful = [e for e in all_emotions if e not in _NOISE_EMOTIONS]
        limited_data = False
        if meaningful:
            dominant = max(set(meaningful), key=meaningful.count)
        elif all_emotions:
            dominant = max(set(all_emotions), key=all_emotions.count)
            limited_data = True
        else:
            dominant = "neutral"
            limited_data = True
        score = _emotion_to_score(dominant)

        stages.append({
            "stage": stage_key,
            "name": stage_name,
            "description": stage_desc,
            "dominant_emotion": dominant,
            "all_emotions": list(set(meaningful)) if meaningful else list(set(all_emotions)),
            "score": score,
            "limited_data": limited_data,
        })

    return stages


def _map_segment_to_stage(segment: dict[str, Any]) -> str:
    """Heuristically map a coded segment to an ordering stage."""
    codes = segment.get("research_objective_codes", [])
    text = segment.get("text", "").lower()
    enrichment = segment.get("enrichment_tags", {})

    codes_str = " ".join(codes).lower()

    if any(kw in codes_str for kw in ("trigger", "decision", "platform_choice")):
        return "decision"
    if any(kw in codes_str for kw in ("barrier", "price_sensitivity", "subscription")):
        return "pre_order"
    if any(kw in codes_str for kw in ("social_ordering", "group")):
        return "ordering"
    if any(kw in codes_str for kw in ("brand", "awareness", "channel")):
        return "pre_order"
    if any(kw in codes_str for kw in ("guilt", "justification")):
        return "post_order"

    if any(kw in text for kw in ("before i order", "thinking about", "deciding", "compare")):
        return "decision"
    if any(kw in text for kw in ("waiting", "delivery time", "arrived")):
        return "waiting"
    if any(kw in text for kw in ("eating", "taste", "food was")):
        return "consumption"
    if any(kw in text for kw in ("after", "regret", "next time", "won't order")):
        return "post_order"
    if any(kw in text for kw in ("order", "app", "checkout", "basket")):
        return "ordering"

    tension = enrichment.get("tension")
    if isinstance(tension, dict) and tension.get("tension_type"):
        return "pre_order"

    return "pre_order"


def _render_journey_md(
    name: str, stages: list[dict[str, Any]]
) -> list[str]:
    """Render a journey as a Markdown file with a Mermaid diagram."""
    lines = [f"# {name} -- Ordering Journey\n"]
    lines.append("```mermaid")
    lines.append("journey")
    lines.append(f"    title {name} - Ordering Journey")

    for stage in stages:
        stage_name = stage["name"]
        emo_label = stage["dominant_emotion"]
        if stage.get("limited_data"):
            emo_label += ", limited data"
        desc = f"{stage['description']} ({emo_label})"
        score = stage["score"]
        lines.append(f"    section {stage_name}")
        lines.append(f"      {desc}: {score}: Participant")

    lines.append("```\n")

    lines.append("## Stage Detail\n")
    for stage in stages:
        emotions = stage.get("all_emotions", [])
        emotion_str = ", ".join(emotions) if emotions else "no data"
        caveat = " **(limited data)**" if stage.get("limited_data") else ""
        lines.append(f"- **{stage['name']}**: dominant={stage['dominant_emotion']}, "
                      f"score={stage['score']}/5, emotions=[{emotion_str}]{caveat}")
    lines.append("")

    return lines


def _emotion_to_score(emotion: str) -> int:
    """Map emotion label to Mermaid journey score (1-5)."""
    return _EMOTION_SCORES.get(emotion.lower().strip(), 3)


def _load_all_coded(coded_dir: Path) -> dict[str, dict[str, Any]]:
    """Load all coded segment files keyed by participant ID."""
    result: dict[str, dict[str, Any]] = {}
    if not coded_dir.exists():
        return result
    for path in sorted(coded_dir.glob("*_coded.json")):
        pid = path.stem.replace("_coded", "").upper()
        with open(path) as f:
            result[pid] = json.load(f)
    return result


def _load_all_summaries(summary_dir: Path) -> dict[str, dict[str, Any]]:
    """Load all participant summary files keyed by participant ID."""
    result: dict[str, dict[str, Any]] = {}
    if not summary_dir.exists():
        return result
    for path in sorted(summary_dir.glob("*_summary.json")):
        pid = path.stem.replace("_summary", "").upper()
        with open(path) as f:
            result[pid] = json.load(f)
    return result


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)
