"""
Language patterns generator.

Analyses word choices, metaphors, and recurring vocabulary from
language-pattern-tagged segments.
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


def generate_language_patterns() -> Path:
    """Build language pattern analysis from coded segments."""
    ENRICHMENT_OUT.mkdir(parents=True, exist_ok=True)

    coded_dir = PROCESSED_DIR / "coded_segments"
    pattern_data: list[dict[str, Any]] = []

    if coded_dir.exists():
        for path in coded_dir.glob("*_coded.json"):
            with open(path) as f:
                data = json.load(f)
            segments = data.get("coded_segments", []) if isinstance(data, dict) else data if isinstance(data, list) else []
            for seg in segments:
                if not isinstance(seg, dict):
                    continue
                enrichment = seg.get("enrichment_tags", {})
                patterns = enrichment.get("language_pattern", []) if isinstance(enrichment, dict) else []
                if patterns:
                    pattern_data.append({
                        "participant_id": seg.get("participant_id", ""),
                        "text": seg.get("text", ""),
                        "patterns": patterns if isinstance(patterns, list) else [patterns],
                        "emotions": seg.get("context_tags", {}).get("emotion", []) if isinstance(seg.get("context_tags"), dict) else [],
                    })

    # Count patterns
    pattern_counts: Counter = Counter()
    pattern_examples: dict[str, list[str]] = defaultdict(list)
    for item in pattern_data:
        for p in item["patterns"]:
            pattern_counts[p] += 1
            if len(pattern_examples[p]) < 3:
                pattern_examples[p].append(f'{item["participant_id"]}: "{item["text"][:150]}"')

    lines = ["# Student Food Delivery Language Patterns\n"]

    # Positive clusters
    positive_words = {"treat", "deserve", "earned", "reward", "ritual", "together", "sharing", "easy", "quick"}
    negative_words = {"guilty", "shouldn't", "waste", "expensive", "lazy", "bad"}

    lines.append("## Positive Language Clusters\n")
    for word, count in pattern_counts.most_common():
        if word.lower() in positive_words:
            lines.append(f"### \"{word}\" ({count} uses)\n")
            for ex in pattern_examples.get(word, []):
                lines.append(f"- {ex}")
            lines.append("")

    lines.append("## Negative Language Clusters\n")
    for word, count in pattern_counts.most_common():
        if word.lower() in negative_words:
            lines.append(f"### \"{word}\" ({count} uses)\n")
            for ex in pattern_examples.get(word, []):
                lines.append(f"- {ex}")
            lines.append("")

    lines.append("## All Patterns by Frequency\n")
    for word, count in pattern_counts.most_common(30):
        lines.append(f"- **{word}**: {count}")
    lines.append("")

    lines.append(f"\n*Based on {len(pattern_data)} language-tagged segments.*\n")

    out_path = ENRICHMENT_OUT / "language_patterns.md"
    out_path.write_text("\n".join(lines))
    logger.info("Generated language patterns: %d segments", len(pattern_data))
    return out_path
