"""
Topline summary generator — stakeholder-ready style.

Creates a concise executive summary designed for stakeholder readouts,
using qualitative narrative framing, participant quotes, and thematic
headings rather than raw data counts. Follows the style established
in the V4 topline approved by Molly.
"""

from __future__ import annotations

import functools
import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from config.settings import OUTPUT_DIR, PROCESSED_DIR, REFERENCE_DIR

logger = logging.getLogger(__name__)

TOPLINE_DIR = OUTPUT_DIR / "topline"


def _get(d: dict, *keys: str, default: Any = "") -> Any:
    for key in keys:
        val = d.get(key)
        if val not in (None, "", [], {}):
            return val
    return default


def generate_topline_summary(version: str = "") -> Path:
    """Generate a stakeholder-ready topline summary from agent outputs."""
    if not version:
        _archive_existing(TOPLINE_DIR)
    TOPLINE_DIR.mkdir(parents=True, exist_ok=True)

    insights = _load_json(PROCESSED_DIR / "insights" / "insights.json")
    personas = _load_json(PROCESSED_DIR / "personas" / "personas.json")
    plus_strategy = _load_json(PROCESSED_DIR / "plus_strategy" / "plus_strategy.json")
    qa = _load_json(PROCESSED_DIR / "qa_results" / "qa_results.json")

    qa_confidence: dict[str, str] = {}
    if isinstance(qa, dict):
        qa_confidence = qa.get("confidence_scores", {}).get("insights", {})

    sections: list[str] = []

    sections.append("# Student Food & Delivery Habits: Topline Summary\n")
    sections.append(f"*Generated: {datetime.now().strftime('%d %B %Y')}*\n")
    sections.append("---\n")

    # Project snapshot table
    sections.append("## Project Snapshot\n")
    sections.append(
        "| | |\n"
        "|---|---|\n"
        "| **Client** | Deliveroo |\n"
        "| **Research focus** | Student food delivery attitudes, behaviours & subscription dynamics |\n"
        "| **Methods** | Online semi-structured interviews (n=29), In-home contextual interviews (n=6), "
        "7-day diary study (n=15, subset of interview sample, via DScout) |\n"
        "| **Sample** | 35 participants — Undergraduate (n=25, including 6 in-home), "
        "Postgraduate (n=4), Graduate (n=6) |\n"
        "| **Fieldwork** | January–February 2026 |\n"
    )
    sections.append("---\n")

    # Big Picture — prose paragraph, no bullet lists
    sections.append("## The Big Picture\n")
    exec_summary = ""
    if isinstance(insights, dict):
        exec_summary = insights.get("executive_summary", "")
    if exec_summary:
        sections.append(f"{exec_summary}\n")
    else:
        sections.append(
            "Student food delivery is shaped by predictable emotional and social patterns. "
            "Most students use multiple platforms, choosing between them based on occasion "
            "rather than loyalty — and Deliveroo is well-regarded for restaurant choice, "
            "quality and reliability. However, awareness and perceived differentiation of "
            "the student Plus Silver offering is lower than competitors, particularly Uber One, "
            "whose multi-benefit ecosystem makes its subscription feel broader in value. "
            "Convenience and mental effort reduction matter more than price alone: the key "
            "ordering triggers are time pressure, low energy after study or work, social "
            "occasions, and the familiar weekend treat.\n\n"
            "Integration of 7-day diary data (n=15) revealed significant say-do gaps between "
            "what students claim in interviews and how they actually eat — with meal skipping, "
            "lower-than-expected cooking rates, and near-zero delivery usage during tracked "
            "periods suggesting that delivery competes with the decision to eat at all, "
            "not just with home cooking.\n"
        )
    sections.append("---\n")

    # Headline findings — narrative style with thematic headings and quotes
    sections.append("## Headline Findings\n")
    sections.append(_build_narrative_findings(insights, personas, qa_confidence))
    sections.append("---\n")

    # Persona snapshot table — built as a single string to avoid blank-line breaks
    table_lines = [
        "## Persona Snapshot\n",
        "| Persona | Size | Core Profile |",
        "|---------|------|-------------|",
    ]
    if isinstance(personas, dict):
        for p in personas.get("personas", []):
            if not isinstance(p, dict):
                continue
            name = _get(p, "name", default="Unnamed")
            reps = _get(p, "representative_participants", "participants", default=[])
            size = _get(p, "size", default="")
            if not size and isinstance(reps, list):
                size = str(len(reps))
            tagline = _get(p, "tagline", "archetype", default="")
            table_lines.append(f"| {name} | {size} | {tagline} |")
    sections.append("\n".join(table_lines))
    sections.append("\n---\n")

    # Priority recommendations — Top 5 with growth lens tags, then full list
    sections.append("## Priority Recommendations\n")
    sections.append("### Top 5 Priorities\n")
    sections.append(_build_top5_recommendations(insights, plus_strategy))
    sections.append("\n### Full Recommendation List\n")
    sections.append(_build_priority_recommendations(insights, plus_strategy))
    sections.append("---\n")

    # What's next
    sections.append("## What's Next\n")
    sections.append(
        "- **Quantitative validation:** Survey (target n=200+) to test meal-skipping "
        "frequency (22% rate), weekend cooking drop-off (29%), and the delivery "
        "consideration-usage gap across a representative student sample\n"
        "- **Stakeholder workshop:** Convene Marketing, Product, and Partnerships leads "
        "to prioritise the Top 5 recommendations and map to H2 2026 roadmap\n"
        "- **Research archival:** Import coded segments and transcripts into Dovetail "
        "with project and participant tags for long-term discoverability\n"
        "- **Targeted deep dives:** Friday night group ordering dynamics and "
        "meal-skipping conversion opportunities as directed by the team\n"
    )

    topline_text = "\n".join(sections)
    filename = f"topline_summary_{version}.md" if version else "topline_summary.md"
    out_path = TOPLINE_DIR / filename
    out_path.write_text(topline_text)
    logger.info("Generated topline summary: %s (%d chars)", out_path.name, len(topline_text))
    return out_path


# ---------------------------------------------------------------------------
# Narrative finding builders
# ---------------------------------------------------------------------------

_THEMATIC_HEADINGS: dict[str, str] = {
    "INS_001": "The Meal-Skipping Reality: Delivery Competes with Not Eating",
    "INS_002": "Habit Stacking: The Gap Between What Students Say and What They Do",
    "INS_003": "Ordering Together: Community and Belonging in Shared Living",
    "INS_004": "Delivery in the Mind vs. Delivery on the Plate",
    "INS_005": "The Graduate Shift: From Treat to Utility",
    "INS_006": "Three Distinct Student Segments, Not a Single Profile",
    "INS_007": "Friday Night and Weekend Socialising: The Highest-Value Window",
    "INS_008": "Price Comparison as a Group Sport",
}


def _build_narrative_findings(
    insights: dict[str, Any] | None,
    personas: dict[str, Any] | None,
    qa_confidence: dict[str, str] | None = None,
) -> str:
    """Build narrative-style headline findings with quotes and prose."""
    if not isinstance(insights, dict):
        return "*Findings will be generated after full analysis.*\n"
    if qa_confidence is None:
        qa_confidence = {}

    quote_bank = _load_quote_bank()
    used_quotes: set[str] = set()
    pid_usage: dict[str, int] = {}
    lines: list[str] = []

    _CONF_ORDER = {"high": 0, "medium": 1, "low": 2, "tentative": 3}
    sorted_insights = sorted(
        [i for i in insights.get("insights", []) if isinstance(i, dict)],
        key=lambda i: _CONF_ORDER.get(
            (qa_confidence or {}).get(
                _get(i, "insight_id", default=""),
                _get(i, "confidence", "evidence_strength", default="high"),
            ),
            1,
        ),
    )

    for ins in sorted_insights:
        if not isinstance(ins, dict):
            continue

        insight_id = _get(ins, "insight_id", default="")
        confidence = _get(ins, "confidence", "evidence_strength", default="high")
        qa_rating = qa_confidence.get(insight_id, "")
        effective_confidence = qa_rating if qa_rating else confidence
        if effective_confidence in ("low", "tentative"):
            continue

        heading = _THEMATIC_HEADINGS.get(
            insight_id,
            _get(ins, "title", "insight", default="Untitled Finding"),
        )

        insight_text = _get(ins, "insight", "title", default="")
        so_what = _get(ins, "so_what", "strategic_implication", default="")

        lines.append(f"### {heading}\n")

        if insight_text:
            lines.append(f"{insight_text}\n")

        if so_what:
            lines.append(f"{so_what}\n")

        quotes = _get_supporting_quotes(ins, quote_bank, used_quotes, pid_usage)
        if insight_id == "INS_004" and quotes:
            lines.append(
                "*The quotes below reflect interview claims; diary tracking "
                "showed markedly lower actual delivery usage for these participants.*\n"
            )
        for q_text, q_participant in quotes[:2]:
            lines.append(f'> "{q_text}" — {q_participant}\n')

        lines.append("")

    return "\n".join(lines)


_INSIGHT_KEYWORDS: dict[str, list[str]] = {
    "INS_001": ["skip", "breakfast", "don't eat", "didn't eat", "not eat", "miss breakfast",
                "forgot to eat", "too busy to eat", "no time to eat"],
    "INS_002": ["cook", "batch", "meal prep", "home cook", "make food", "fridge",
                "groceries", "weekend", "lazy", "can't be bothered"],
    "INS_003": ["friend", "group", "together", "social", "flatmate", "housemate",
                "everyone", "night in", "split", "share"],
    "INS_004": ["takeaway", "delivery", "order", "uber", "deliveroo", "just eat",
                "treat", "once a week", "rarely"],
    "INS_005": ["order a bit more", "more takeaways", "enough money for convenience",
                "proper adult", "started off as a treat", "habit", "not as cheap",
                "value", "more often", "changed", "post-uni"],
    "INS_006": ["exam", "stress", "reward", "treat", "earned it",
                "deserve", "comfort", "after revision", "post-exam",
                "budget", "price", "cost", "phd", "intentional", "healthier",
                "practical", "save money", "conscious"],
    "INS_007": ["friday night", "friday evening", "end of the week",
                "takeaway on a friday", "long week", "friday"],
    "INS_008": ["compare", "cheaper", "price", "deal", "offer", "which app",
                "subscription", "plus", "uber one"],
}


_MAX_PID_USES = 2


@functools.lru_cache(maxsize=1)
def _load_postgrad_pids() -> frozenset[str]:
    """Load postgraduate participant IDs from participant_map.json (cached)."""
    pmap = _load_json(REFERENCE_DIR / "participant_map.json")
    if not isinstance(pmap, dict):
        return frozenset()
    pids: set[str] = set()
    for key, val in pmap.items():
        if isinstance(val, dict) and val.get("segment") == "postgraduate":
            pids.add(val.get("participant_id", key))
    return frozenset(pids)


def _get_supporting_quotes(
    ins: dict[str, Any],
    quote_bank: list[dict[str, Any]],
    used_quotes: set[str] | None = None,
    pid_usage: dict[str, int] | None = None,
) -> list[tuple[str, str]]:
    """Extract supporting quotes, skipping duplicates and over-used participants."""
    if used_quotes is None:
        used_quotes = set()
    if pid_usage is None:
        pid_usage = {}

    quotes: list[tuple[str, str]] = []

    evidence = ins.get("evidence", ins.get("evidence_chain", []))
    if isinstance(evidence, list):
        for e in evidence:
            if isinstance(e, dict):
                q = e.get("quote", "")
                p = e.get("participant", "")
                q_key = q[:80].lower()
                if (q and p and 20 < len(q) < 350
                        and q_key not in used_quotes
                        and pid_usage.get(p, 0) < _MAX_PID_USES):
                    quotes.append((q, p))
                    used_quotes.add(q_key)
                    pid_usage[p] = pid_usage.get(p, 0) + 1

    if not quotes:
        insight_id = ins.get("insight_id", "")
        ro = ins.get("research_objective", "")
        keywords = _INSIGHT_KEYWORDS.get(insight_id, [])

        candidates: list[tuple[float, str, str]] = []
        for seg in quote_bank:
            text = seg["text"]
            pid = seg["pid"]
            codes = seg["codes"]

            q_key = text[:80].lower()
            if q_key in used_quotes:
                continue
            if pid_usage.get(pid, 0) >= _MAX_PID_USES:
                continue

            ro_match = any(
                c.lower().startswith(ro.lower()) for c in codes
            ) if ro else False

            text_lower = text.lower()
            kw_hits = sum(1 for kw in keywords if kw in text_lower)

            if kw_hits == 0:
                continue

            score = (1.0 if ro_match else 0.0) + kw_hits
            if 60 < len(text) < 250:
                score += 1.0
            if insight_id == "INS_006" and pid in _load_postgrad_pids():
                score += 2.0
            candidates.append((score, text, pid))

        candidates.sort(key=lambda x: -x[0])

        seen_pids: set[str] = set()
        for _, text, pid in candidates:
            if pid in seen_pids:
                continue
            seen_pids.add(pid)
            quotes.append((text, pid))
            used_quotes.add(text[:80].lower())
            pid_usage[pid] = pid_usage.get(pid, 0) + 1
            if len(quotes) >= 2:
                break

    return quotes


def _load_quote_bank() -> list[dict[str, Any]]:
    """Load all usable quotes from coded segments."""
    bank: list[dict[str, Any]] = []
    coded_dir = PROCESSED_DIR / "coded_segments"
    if not coded_dir.exists():
        return bank

    for path in sorted(coded_dir.glob("*_coded.json")):
        data = _load_json(path)
        if not isinstance(data, dict):
            continue
        pid = data.get("participant_id", path.stem.replace("_coded", "").upper())
        for seg in data.get("coded_segments", []):
            text = seg.get("text", "")
            if not text or len(text) < 30 or len(text) > 350:
                continue
            codes = seg.get("research_objective_codes", [])
            bank.append({"text": text, "pid": pid, "codes": codes})

    return bank


_GROWTH_LENSES: dict[str, list[str]] = {
    "INS_001": ["Lifecycle", "New Verticals"],
    "INS_002": ["Affordability", "Plus"],
    "INS_003": ["Quality", "Plus"],
    "INS_004": ["Lifecycle", "Affordability"],
    "INS_006": ["Lifecycle"],
    "INS_007": ["Quality", "Plus"],
    "INS_008": ["Affordability", "Plus"],
}


def _build_top5_recommendations(
    insights: dict[str, Any] | None,
    plus_strategy: dict[str, Any] | None,
) -> str:
    """Dynamically select the top 5 recommendations from insights, tagged with growth lenses.

    Ranks all recommendations across all qualifying insights by parent
    insight confidence and position within the insight's recommendation
    list, then picks the top 5 with at most 1 from any single insight
    to maximise coverage across different research themes.
    """
    if not isinstance(insights, dict):
        return "*Top priorities will be generated after full analysis.*\n"

    qa = _load_json(PROCESSED_DIR / "qa_results" / "qa_results.json")
    qa_confidence: dict[str, str] = {}
    if isinstance(qa, dict):
        qa_confidence = qa.get("confidence_scores", {}).get("insights", {})

    _CONF_SCORE = {"high": 3, "medium": 2, "low": 1, "tentative": 0}

    candidates: list[tuple[float, str, str, str]] = []
    for ins in insights.get("insights", []):
        if not isinstance(ins, dict):
            continue
        insight_id = _get(ins, "insight_id", default="")
        eff_conf = qa_confidence.get(
            insight_id, _get(ins, "confidence", "evidence_strength", default="high")
        )
        if eff_conf in ("low", "tentative"):
            continue
        conf_score = _CONF_SCORE.get(eff_conf, 2)
        recs = _get(ins, "recommendations", "recommended_actions", default=[])
        for pos, rec in enumerate(recs):
            if isinstance(rec, dict):
                text = rec.get("recommendation", "")
                rec_type = rec.get("type", "").title()
            elif isinstance(rec, str):
                text = rec
                rec_type = ""
            else:
                continue
            if not text:
                continue
            score = conf_score * 3 - pos
            candidates.append((score, insight_id, rec_type, text))

    candidates.sort(key=lambda x: -x[0])

    lines: list[str] = []
    seen_text: set[str] = set()
    insight_uses: dict[str, int] = {}
    count = 0
    for _, insight_id, rec_type, text in candidates:
        if count >= 5:
            break
        key = text[:60].lower()
        if key in seen_text:
            continue
        if insight_uses.get(insight_id, 0) >= 1:
            continue
        seen_text.add(key)
        insight_uses[insight_id] = insight_uses.get(insight_id, 0) + 1
        label = f"[{rec_type}] " if rec_type else ""
        lenses = _GROWTH_LENSES.get(insight_id, [])
        lens_tag = f" [{', '.join(lenses)}]" if lenses else ""
        lines.append(f"**{count + 1}. {label}{text}**{lens_tag}\n")
        count += 1

    return "\n".join(lines)


def _build_priority_recommendations(
    insights: dict[str, Any] | None,
    plus_strategy: dict[str, Any] | None,
) -> str:
    """Build numbered priority recommendations with prose rationale."""
    if not isinstance(insights, dict):
        return "*Recommendations will be generated after full analysis.*\n"

    seen: set[str] = set()
    lines: list[str] = []
    rec_count = 0

    for ins in insights.get("insights", []):
        if not isinstance(ins, dict):
            continue
        recs = _get(ins, "recommendations", "recommended_actions", default=[])
        for rec in recs:
            if rec_count >= 8:
                break
            if isinstance(rec, dict):
                text = rec.get("recommendation", "")
                rec_type = rec.get("type", "").title()
                rationale = rec.get("rationale", "")
            elif isinstance(rec, str):
                text = rec
                rec_type = ""
                rationale = ""
            else:
                continue

            key = text[:60].lower()
            if key in seen or not text:
                continue
            seen.add(key)

            label = f"[{rec_type}] " if rec_type else ""
            lines.append(f"**{rec_count + 1}. {label}{text}**")
            if rationale:
                lines.append(f"{rationale}")
            lines.append("")
            rec_count += 1
        if rec_count >= 8:
            break

    if isinstance(plus_strategy, dict):
        consolidated = plus_strategy.get("strategic_recommendations_consolidated", {})
        critical = consolidated.get("priority_1_critical", [])
        for item in critical[:2]:
            if rec_count >= 10:
                break
            if isinstance(item, dict):
                area = item.get("area", "")
                action = item.get("action", "")
                evidence = item.get("evidence", "")
                key = action[:60].lower()
                if key in seen or not action:
                    continue
                seen.add(key)
                lines.append(f"**{rec_count + 1}. [Product/Marketing] {area}: {action}**")
                if evidence:
                    lines.append(f"{evidence}")
                lines.append("")
                rec_count += 1

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def _archive_existing(directory: Path) -> None:
    if not directory.exists():
        return
    archive = OUTPUT_DIR / "archive"
    archive.mkdir(parents=True, exist_ok=True)
    date_prefix = datetime.now().strftime("%Y-%m-%d")
    for item in directory.iterdir():
        if item.is_file():
            dest = archive / f"{date_prefix}_{item.name}"
            shutil.move(str(item), str(dest))
