"""
Competitive perception map generator.

Extracts and organises how students perceive different food delivery
platforms, drawn from competitive-tagged segments.
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


def generate_competitive_map() -> Path:
    """Build competitive perception map from coded segments."""
    ENRICHMENT_OUT.mkdir(parents=True, exist_ok=True)

    coded_dir = PROCESSED_DIR / "coded_segments"
    competitive_data: list[dict[str, Any]] = []

    if coded_dir.exists():
        for path in coded_dir.glob("*_coded.json"):
            with open(path) as f:
                data = json.load(f)
            segments = data.get("coded_segments", []) if isinstance(data, dict) else data if isinstance(data, list) else []
            for seg in segments:
                if not isinstance(seg, dict):
                    continue
                enrichment = seg.get("enrichment_tags", {})
                competitive = enrichment.get("competitive") if isinstance(enrichment, dict) else None
                platform = seg.get("context_tags", {}).get("platform", []) if isinstance(seg.get("context_tags"), dict) else []
                if competitive or platform:
                    competitive_data.append({
                        "participant_id": seg.get("participant_id", ""),
                        "text": seg.get("text", ""),
                        "competitive": competitive,
                        "platforms": platform if isinstance(platform, list) else [platform],
                    })

    # Group by platform
    platform_mentions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in competitive_data:
        for p in item["platforms"]:
            platform_mentions[p].append(item)

    lines = ["# Competitive Perception Map\n"]
    lines.append("## How Students See Food Delivery Options\n")

    for platform in ["deliveroo", "ubereats", "justeat", "other"]:
        mentions = platform_mentions.get(platform, [])
        lines.append(f"### {platform.replace('_', ' ').title()} ({len(mentions)} mentions)\n")
        for m in mentions[:3]:
            lines.append(f'> "{m["text"][:200]}" -- {m["participant_id"]}\n')
        lines.append("")

    platform_counts = Counter()
    for item in competitive_data:
        for p in item["platforms"]:
            platform_counts[p] += 1

    lines.append("## Mention Frequency\n")
    for platform, count in platform_counts.most_common():
        lines.append(f"- **{platform}**: {count} mentions")
    lines.append("")

    total_mentions = sum(platform_counts.values())
    if total_mentions > len(competitive_data):
        lines.append(
            f"\n*Based on {len(competitive_data)} competitive-tagged segments. "
            f"Platform mention totals sum to {total_mentions} because "
            f"{total_mentions - len(competitive_data)} segments reference "
            f"multiple platforms (e.g., comparing Deliveroo vs. Uber Eats).*\n"
        )
    else:
        lines.append(f"\n*Based on {len(competitive_data)} competitive-tagged segments.*\n")

    out_path = ENRICHMENT_OUT / "competitive_map.md"
    out_path.write_text("\n".join(lines))

    json_path = OUTPUT_DIR / "data_exports" / "all_competitive_mentions.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(json_path, "w") as f:
        json.dump(competitive_data, f, indent=2, ensure_ascii=False)

    logger.info("Generated competitive map: %d mentions", len(competitive_data))
    return out_path
