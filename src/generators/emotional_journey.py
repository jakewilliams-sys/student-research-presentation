"""
Emotional journey generator.

Maps the emotional arc through the ordering process for each persona,
using emotion-tagged segments from the coded data.
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


def generate_emotional_journeys() -> Path:
    """Build emotional journey maps from coded segments."""
    ENRICHMENT_OUT.mkdir(parents=True, exist_ok=True)

    coded_dir = PROCESSED_DIR / "coded_segments"
    emotion_data: list[dict[str, Any]] = []

    if coded_dir.exists():
        for path in coded_dir.glob("*_coded.json"):
            with open(path) as f:
                data = json.load(f)
            segments = data.get("coded_segments", []) if isinstance(data, dict) else data if isinstance(data, list) else []
            for seg in segments:
                if not isinstance(seg, dict):
                    continue
                ctx = seg.get("context_tags", {})
                emotions = ctx.get("emotion", []) if isinstance(ctx, dict) else []
                if emotions:
                    emotion_data.append({
                        "participant_id": seg.get("participant_id", ""),
                        "text": seg.get("text", ""),
                        "emotions": emotions if isinstance(emotions, list) else [emotions],
                        "codes": seg.get("research_objective_codes", []),
                        "social_context": ctx.get("social_context", ""),
                    })

    # Aggregate emotion frequency
    emotion_counts: Counter = Counter()
    for item in emotion_data:
        for e in item["emotions"]:
            emotion_counts[e] += 1

    lines = ["# Emotional Journey Through Ordering\n"]

    lines.append("## Emotion Frequency\n")
    for emotion, count in emotion_counts.most_common(15):
        bar = "=" * min(count, 30)
        lines.append(f"- **{emotion}**: {count} mentions {bar}")
    lines.append("")

    # Group by ordering stage (using RO codes as proxy)
    stage_emotions: dict[str, list[str]] = defaultdict(list)
    for item in emotion_data:
        for code in item["codes"]:
            if "trigger" in code.lower():
                stage_emotions["trigger"].extend(item["emotions"])
            elif "social" in code.lower():
                stage_emotions["social_context"].extend(item["emotions"])
            elif "engagement" in code.lower():
                stage_emotions["engagement"].extend(item["emotions"])
            else:
                stage_emotions["general"].extend(item["emotions"])

    lines.append("## Emotions by Stage\n")
    for stage, emotions in stage_emotions.items():
        top = Counter(emotions).most_common(5)
        lines.append(f"### {stage.replace('_', ' ').title()}")
        for e, c in top:
            lines.append(f"- {e}: {c}")
        lines.append("")

    lines.append(f"\n*Based on {len(emotion_data)} emotion-tagged segments.*\n")

    out_path = ENRICHMENT_OUT / "emotional_journeys.md"
    out_path.write_text("\n".join(lines))
    logger.info("Generated emotional journeys: %d segments", len(emotion_data))
    return out_path
