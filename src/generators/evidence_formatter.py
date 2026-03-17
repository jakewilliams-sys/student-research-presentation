"""
Evidence formatter for traceable quote citations.

Ensures every quote in the report links back to a coded segment
with participant ID, source, timestamp, and quality score.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from config.settings import PROCESSED_DIR

logger = logging.getLogger(__name__)


def format_quote(segment: dict[str, Any]) -> str:
    """Format a coded segment as a citable quote."""
    text = segment.get("text", "")
    pid = segment.get("participant_id", "")
    ts = segment.get("timestamp", "")
    source = segment.get("source", "interview")
    quality = segment.get("quote_quality", {})
    overall = quality.get("overall", 0) if isinstance(quality, dict) else 0
    rec = quality.get("recommendation", "") if isinstance(quality, dict) else ""

    citation = f'> "{text}"\n> -- {pid}'
    if ts:
        citation += f" [{ts}]"
    citation += f" ({source})"
    if overall >= 4:
        citation += f" [Quality: {overall:.1f} - {rec}]"

    return citation


def build_evidence_chain(
    insight: dict[str, Any],
    all_coded: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Build a full evidence chain for an insight.

    Links insight -> supporting segment IDs -> full segment data.
    """
    chain: list[dict[str, Any]] = []

    evidence = insight.get("evidence_chain", insight.get("evidence", []))
    for e in evidence:
        if not isinstance(e, dict):
            continue
        pid = e.get("participant", "")
        quote = e.get("quote", "")

        # Find matching coded segment
        participant_data = all_coded.get(pid, {})
        segments = (
            participant_data.get("coded_segments", [])
            if isinstance(participant_data, dict) else []
        )
        for seg in segments:
            if isinstance(seg, dict) and seg.get("text", "").strip() == quote.strip():
                chain.append({
                    "participant": pid,
                    "segment_id": seg.get("segment_id", ""),
                    "quote": quote,
                    "timestamp": seg.get("timestamp", ""),
                    "codes": seg.get("research_objective_codes", []),
                    "quality_score": seg.get("quote_quality", {}).get("overall", 0),
                    "context": seg.get("context_tags", {}),
                })
                break
        else:
            chain.append({
                "participant": pid,
                "quote": quote,
                "segment_id": "",
                "note": "Segment not found in coded data",
            })

    return chain


def get_top_quotes(
    theme_code: str,
    all_coded: dict[str, dict[str, Any]],
    n: int = 5,
) -> list[dict[str, Any]]:
    """Get the top-scoring quotes for a given theme code."""
    matching: list[dict[str, Any]] = []

    for pid, data in all_coded.items():
        segments = data.get("coded_segments", []) if isinstance(data, dict) else []
        for seg in segments:
            if not isinstance(seg, dict):
                continue
            codes = seg.get("research_objective_codes", [])
            if any(theme_code in c for c in codes):
                matching.append({
                    "participant_id": pid,
                    **seg,
                })

    matching.sort(
        key=lambda s: s.get("quote_quality", {}).get("overall", 0),
        reverse=True,
    )
    return matching[:n]
