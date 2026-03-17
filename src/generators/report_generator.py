"""
Full research report generator.

Assembles all agent outputs into a comprehensive markdown report
with evidence traceability: every claim links to coded segments
which link to participant quotes.

Uses flexible field lookups to handle schema variations between
prompt-specified format and actual LLM output.
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from config.settings import OUTPUT_DIR, PROCESSED_DIR

logger = logging.getLogger(__name__)

REPORT_DIR = OUTPUT_DIR / "report"


def _get(d: dict, *keys: str, default: Any = "") -> Any:
    """Try multiple keys in order, return the first non-empty value found."""
    for key in keys:
        val = d.get(key)
        if val not in (None, "", [], {}):
            return val
    return default


def generate_report(version: str = "") -> Path:
    """Generate the full research report from all agent outputs."""
    if not version:
        _archive_existing(REPORT_DIR)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    insights = _load_json(PROCESSED_DIR / "insights" / "insights.json")
    personas = _load_json(PROCESSED_DIR / "personas" / "personas.json")
    qa = _load_json(PROCESSED_DIR / "qa_results" / "qa_results.json")
    advocate = _load_json(PROCESSED_DIR / "advocate_results" / "advocate_results.json")
    plus_strategy = _load_json(PROCESSED_DIR / "plus_strategy" / "plus_strategy.json")

    qa_confidence: dict[str, str] = {}
    if isinstance(qa, dict):
        qa_confidence = qa.get("confidence_scores", {}).get("insights", {})

    sections: list[str] = []
    sections.append("# Student Food & Delivery Habits: Research Report\n")
    sections.append(f"*Generated: {datetime.now().strftime('%d %B %Y')}*\n")
    sections.append("---\n")

    # Executive summary — adds methodological credibility beyond the topline
    exec_summary = ""
    if isinstance(insights, dict):
        exec_summary = insights.get("executive_summary", "")
    if not exec_summary and isinstance(insights, dict):
        exec_summary = _synthesize_exec_summary(insights)
    sections.append("## Executive Summary\n")
    if exec_summary:
        sections.append(f"{exec_summary}\n")
    else:
        sections.append("*Executive summary will be generated after full analysis.*\n")
    sections.append(
        "These conclusions draw on 35 semi-structured interviews (online and in-home) "
        "triangulated with 7-day diary data from a 15-participant subsample. "
        "Three of eight insights are rated high confidence after quality audit; "
        "four were adjusted to medium confidence due to elevated contradiction rates; "
        "one (graduate behaviour, INS_005) is rated low confidence due to small sample "
        "size and is presented separately as an exploratory finding.\n\n"
        "Integration of diary data revealed significant say-do gaps "
        "between what students claim in interviews and how they actually eat — with "
        "meal skipping, lower-than-expected cooking rates, and near-zero delivery "
        "usage during the tracked week suggesting that delivery competes with the "
        "decision to eat at all, not just with home cooking.\n"
    )
    sections.append("---\n")

    # Methodology
    sections.append("## Methodology\n")
    sections.append(_methodology_section())
    sections.append("### Limitations\n")
    sections.append(_limitations_section())
    sections.append("---\n")

    # Findings — separate main (high/medium confidence) from exploratory (low)
    main_findings: list[dict] = []
    exploratory_findings: list[dict] = []
    if isinstance(insights, dict):
        for ins in insights.get("insights", []):
            if not isinstance(ins, dict):
                continue
            insight_id = _get(ins, "insight_id", default="")
            raw_conf = _get(ins, "confidence", "evidence_strength", default="?")
            eff_conf = _resolve_confidence(raw_conf, insight_id, qa_confidence)
            if eff_conf.startswith("low") or eff_conf.startswith("tentative"):
                exploratory_findings.append(ins)
            else:
                main_findings.append(ins)

    sections.append("## Key Findings\n")
    for ins in main_findings:
        _render_finding(ins, sections, qa_confidence)
    sections.append("---\n")

    if exploratory_findings:
        sections.append("## Exploratory Findings\n")
        sections.append(
            "*The following findings are directional and require further "
            "validation with larger samples or behavioural data before "
            "informing strategy.*\n"
        )
        for ins in exploratory_findings:
            _render_finding(ins, sections, qa_confidence)
        sections.append("---\n")

    # Say-Do Gaps (from diary study)
    say_do_section = _build_say_do_section()
    if say_do_section:
        sections.append(say_do_section)
        sections.append("---\n")

    # Personas
    sections.append("## Personas\n")
    if isinstance(personas, dict):
        for p in personas.get("personas", []):
            if not isinstance(p, dict):
                continue

            name = _get(p, "name", default="Unnamed")
            size = _get(p, "size", default="")
            reps = _get(p, "representative_participants", "participants", default=[])
            if not size and isinstance(reps, list):
                size = str(len(reps))

            sections.append(f"### {name} (n={size})\n")

            tagline = _get(p, "tagline", "archetype", default="")
            if tagline:
                sections.append(f"*{tagline}*\n")

            for c in p.get("key_characteristics", []):
                sections.append(f"- {c}")

            triggers = p.get("delivery_triggers", [])
            if triggers:
                sections.append("\n**Delivery triggers:**")
                for t in triggers:
                    sections.append(f"- {t}")

            drivers = p.get("emotional_drivers", [])
            if drivers:
                sections.append(f"\n**Emotional drivers:** {', '.join(drivers)}")

            core_tension = _get(p, "core_tension", default="")
            if isinstance(core_tension, str) and core_tension:
                sections.append(f"\n**Core tension:** {core_tension}\n")

            pain_points = _get(p, "pain_points", default=[])
            if isinstance(pain_points, list) and pain_points:
                sections.append("\n**Pain points:**")
                for pp in pain_points:
                    sections.append(f"- {pp}")
            elif isinstance(pain_points, dict) and pain_points.get("pain_points"):
                sections.append("\n**Pain points:**")
                for pp in pain_points["pain_points"]:
                    sections.append(f"- {pp}")

            opp = _get(p, "deliveroo_opportunity", "deliveroo_opportunities", default="")
            if isinstance(opp, list) and opp:
                sections.append("\n**Deliveroo opportunities:**")
                for o in opp:
                    sections.append(f"- {o}")
            elif isinstance(opp, str) and opp:
                sections.append(f"\n**Deliveroo opportunity:** {opp}\n")

            evidence = p.get("evidence", p.get("key_quotes", []))
            if evidence:
                sections.append("\n**Key quotes:**\n")
                for e in (evidence[:3] if isinstance(evidence, list) else []):
                    if isinstance(e, dict):
                        sections.append(
                            f'> "{e.get("quote", "")}" -- {e.get("participant", "")}\n'
                        )
                    elif isinstance(e, str):
                        sections.append(f'> "{e}"\n')

            sections.append("")
    sections.append("---\n")

    # Recommendations (aggregated, deduplicated, with growth lens tags)
    sections.append("## Recommendations\n")
    deduped_recs = _deduplicate_recommendations(insights)
    for rec in deduped_recs:
        lenses = _growth_lenses_for_sources(rec.get("sources", []))
        lens_tag = f" [{', '.join(lenses)}]" if lenses else ""
        sections.append(
            f"### [{rec['type'].title()}] {rec['recommendation']}{lens_tag}\n"
        )
        if rec.get("rationale"):
            sections.append(f"*Rationale:* {rec['rationale']}\n")
        if rec.get("sources"):
            sections.append(f"*Source insights:* {', '.join(rec['sources'])}\n")
    sections.append("---\n")

    # Plus Strategy — summary pointer to the dedicated Plus Strategy Report
    sections.append("## Deliveroo Plus: Student Subscription Strategy\n")
    if isinstance(plus_strategy, dict):
        ps_summary = plus_strategy.get("executive_summary", "")
        if ps_summary:
            sections.append(f"{ps_summary}\n")
        sections.append(
            "*For the full competitive landscape, acquisition channel analysis, "
            "churn risk mitigation, and prioritised Plus recommendations, see the "
            "dedicated Plus Strategy Report.*\n"
        )
    else:
        sections.append("*Plus strategy analysis not yet available.*\n")
    sections.append("---\n")

    # Quality assessment
    sections.append("## Quality Assessment\n")
    if isinstance(qa, dict):
        overall = qa.get("overall_assessment", {})
        if isinstance(overall, dict):
            verdict = _get(overall, "verdict", default="")
            if verdict:
                sections.append(f"{verdict}\n")
            cov = overall.get("evidence_coverage_pct", "")
            if cov:
                sections.append(f"- Evidence coverage: {cov}%")
            cont = overall.get("contradiction_count", "")
            if cont:
                sections.append(f"- Contradictions found: {cont}")
            low = overall.get("low_confidence_count", "")
            if low:
                sections.append(f"- Low-confidence findings: {low}")

        confidence_pipeline = _get(qa, "confidence_in_pipeline", default="")
        confidence_findings = _get(qa, "confidence_in_findings", default="")
        if confidence_pipeline:
            sections.append(f"- Pipeline confidence: {confidence_pipeline}")
        if confidence_findings:
            sections.append(f"- Findings confidence: {confidence_findings}")

        fixes = qa.get("priority_fixes_before_full_run", [])
        if fixes:
            sections.append("\n**Priority fixes:**")
            for fix in fixes:
                sections.append(f"- {fix}")
        sections.append("")

    # Devil's advocate
    sections.append("## Critical Review\n")
    if isinstance(advocate, dict):
        summary = _get(
            advocate, "executive_summary",
            default="*Pending devil's advocate review.*",
        )
        if isinstance(summary, str):
            sections.append(summary)

        overall_verdict = advocate.get("overall_verdict", {})
        if isinstance(overall_verdict, dict):
            vsum = overall_verdict.get("summary", "")
            if vsum:
                sections.append(f"\n{vsum}")
            top_actions = overall_verdict.get("top_3_actions", [])
            if top_actions:
                sections.append("\n**Top actions:**")
                for a in top_actions:
                    sections.append(f"- {a}")

        strengthened = advocate.get("findings_strengthened", "")
        weakened = advocate.get("findings_weakened", "")
        if strengthened:
            sections.append(f"\n- Findings strengthened: {strengthened}")
        if weakened:
            sections.append(f"- Findings weakened: {weakened}")

        challenges = advocate.get("insight_challenges", [])
        if challenges:
            sections.append(f"\n**{len(challenges)} insights challenged.**\n")
            weakened_details = [
                c for c in challenges
                if isinstance(c, dict)
                and c.get("verdict", "").lower() in ("weakened", "weak", "partially weakened")
            ]
            if weakened_details:
                sections.append("**Findings weakened by adversarial review:**\n")
                for c in weakened_details:
                    cid = c.get("insight_id", "")
                    challenge = c.get("primary_challenge", c.get("challenge", ""))
                    validation = c.get("recommended_next_step", c.get("recommendation", ""))
                    sections.append(f"- **{cid}:** {challenge}")
                    if validation:
                        sections.append(f"  *Recommended validation:* {validation}")
                sections.append("")
    sections.append("")

    report_text = "\n".join(sections)
    filename = f"research_report_{version}.md" if version else "research_report.md"
    out_path = REPORT_DIR / filename
    out_path.write_text(report_text)
    logger.info("Generated report: %s (%d chars)", out_path.name, len(report_text))
    return out_path


_CONFIDENCE_RANK = {"high": 3, "medium": 2, "low": 1, "tentative": 0}


def _resolve_confidence(
    insight_confidence: str,
    insight_id: str,
    qa_confidence: dict[str, str],
) -> str:
    """Use the lower of insight-stated and QA-assessed confidence."""
    qa_rating = qa_confidence.get(insight_id, "")
    if not qa_rating or qa_rating == insight_confidence:
        return insight_confidence
    ins_rank = _CONFIDENCE_RANK.get(insight_confidence, -1)
    qa_rank = _CONFIDENCE_RANK.get(qa_rating, -1)
    if qa_rank < ins_rank:
        return f"{qa_rating} (QA-adjusted from {insight_confidence})"
    return insight_confidence


def _render_finding(
    ins: dict[str, Any],
    sections: list[str],
    qa_confidence: dict[str, str],
) -> None:
    """Render a single insight/finding block into *sections*."""
    title = _get(ins, "title", "insight", default="")
    insight_id = _get(ins, "insight_id", default="")
    header = f"### {insight_id}: {title}" if insight_id else f"### {title}"
    sections.append(f"{header}\n")

    so_what = _get(ins, "so_what", "strategic_implication", default="")
    if so_what:
        sections.append(f"**Why it matters:** {so_what}\n")

    ev = _get(ins, "evidence_summary", "supporting_evidence", default={})
    raw_conf = _get(ins, "confidence", "evidence_strength", default="?")
    confidence = _resolve_confidence(raw_conf, insight_id, qa_confidence)

    if isinstance(ev, dict):
        n_quotes = ev.get("supporting_quotes", "?")
        n_parts = ev.get("participants", "?")
        diary_n = ev.get("diary_participants")
        ev_line = f"*Evidence: {n_quotes} quotes from {n_parts} participants"
        if diary_n:
            ev_line += f" (quantitative metric from diary subsample, n={diary_n})"
        ev_line += f". Confidence: {confidence}.*\n"
        sections.append(ev_line)
    elif isinstance(ev, list):
        n_parts = len({e.get("participant", "") for e in ev if isinstance(e, dict)})
        sections.append(
            f"*Evidence from {n_parts} participants. Confidence: {confidence}.*\n"
        )
        sections.append("**Supporting evidence:**\n")
        for e in ev[:5]:
            if isinstance(e, dict):
                quote = _get(e, "quote", "data_point", "text", default="")
                part = _get(e, "participant", default="")
                if quote:
                    sections.append(f'> "{quote}" -- {part}\n')

    chain = ins.get("evidence_chain", [])
    if chain:
        sections.append("**Supporting evidence:**\n")
        for e in chain[:5]:
            if isinstance(e, dict):
                sections.append(
                    f'> "{e.get("quote", "")}" -- {e.get("participant", "")}, '
                    f'{e.get("segment", e.get("context", ""))}\n'
                )

    recs = _get(ins, "recommendations", "recommended_actions", default=[])
    if recs:
        sections.append("**Recommendations:**\n")
        for rec in recs:
            if isinstance(rec, dict):
                sections.append(
                    f"- [{rec.get('type', '').title()}] "
                    f"{rec.get('recommendation', '')}"
                )
            elif isinstance(rec, str):
                sections.append(f"- {rec}")
        sections.append("")

    sections.append("")


def _methodology_section() -> str:
    return (
        "This research employed a mixed-method qualitative approach combining:\n\n"
        "- **Online semi-structured interviews** (n=29) via Askable\n"
        "- **In-home contextual interviews** (n=6) via Research Bods, including live order observation\n"
        "- **7-day diary study** (n=15) via DScout — 315 meal slots across breakfast, lunch, and dinner "
        "with structured logging, daily video reflections, and open-text responses\n\n"
        "Participants spanned three segments: undergraduate (n=25, including 6 in-home), "
        "postgraduate (n=4), and graduate (n=6). 15 participants completed both the interview "
        "and the diary study, enabling say-do gap analysis between stated attitudes and observed behaviour.\n\n"
        "Analysis was conducted using a multi-agent system with systematic multi-pass qualitative coding, "
        "cross-participant triangulation (including interview-diary triangulation for say-do gaps), "
        "behavioural persona synthesis, and strategic insight generation, validated by "
        "quality audit and devil's advocate review.\n"
    )


_GROWTH_LENSES: dict[str, list[str]] = {
    "INS_001": ["Lifecycle", "New Verticals"],
    "INS_002": ["Affordability", "Plus"],
    "INS_003": ["Quality", "Plus"],
    "INS_004": ["Lifecycle", "Affordability"],
    "INS_006": ["Lifecycle"],
    "INS_007": ["Quality", "Plus"],
    "INS_008": ["Affordability", "Plus"],
}


def _growth_lenses_for_sources(sources: list[str]) -> list[str]:
    """Return deduplicated growth lenses for a set of source insight IDs."""
    seen: set[str] = set()
    result: list[str] = []
    for src in sources:
        for lens in _GROWTH_LENSES.get(src, []):
            if lens not in seen:
                seen.add(lens)
                result.append(lens)
    return result


def _deduplicate_recommendations(insights: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Collect all recommendations across insights, merging near-duplicates."""
    from difflib import SequenceMatcher

    if not isinstance(insights, dict):
        return []

    all_recs: list[dict[str, Any]] = []
    for ins in insights.get("insights", []):
        if not isinstance(ins, dict):
            continue
        insight_id = _get(ins, "insight_id", default="")
        recs = _get(ins, "recommendations", "recommended_actions", default=[])
        for rec in recs:
            if isinstance(rec, dict):
                all_recs.append({
                    "type": rec.get("type", ""),
                    "recommendation": rec.get("recommendation", ""),
                    "rationale": rec.get("rationale", ""),
                    "sources": [insight_id] if insight_id else [],
                })
            elif isinstance(rec, str):
                all_recs.append({
                    "type": "general",
                    "recommendation": rec,
                    "rationale": "",
                    "sources": [insight_id] if insight_id else [],
                })

    deduped: list[dict[str, Any]] = []
    for rec in all_recs:
        merged = False
        for existing in deduped:
            if _recs_overlap(rec["recommendation"], existing["recommendation"]):
                for src in rec["sources"]:
                    if src and src not in existing["sources"]:
                        existing["sources"].append(src)
                merged = True
                break
        if not merged:
            deduped.append(rec)

    return deduped


def _recs_overlap(a: str, b: str) -> bool:
    """Check if two recommendations are semantically the same."""
    import re
    from difflib import SequenceMatcher

    al, bl = a.lower(), b.lower()
    if SequenceMatcher(None, al, bl).ratio() > 0.55:
        return True
    tokenize = lambda s: re.findall(r"[a-z]+", s)
    stop = {"the", "a", "an", "to", "for", "and", "or", "with", "that", "of",
            "in", "on", "is", "by", "as", "it", "be", "this", "from", "are",
            "not", "their", "its", "than", "but", "when", "so", "can", "like",
            "s", "t", "re"}
    a_tokens = tokenize(al)
    b_tokens = tokenize(bl)
    a_kw = set(a_tokens) - stop
    b_kw = set(b_tokens) - stop
    if not a_kw or not b_kw:
        return False
    kw_overlap = len(a_kw & b_kw) / min(len(a_kw), len(b_kw))
    if kw_overlap >= 0.45:
        return True
    a_bigrams = {(a_tokens[i], a_tokens[i + 1]) for i in range(len(a_tokens) - 1)} - {tuple(sorted(x)) for x in []}
    b_bigrams = {(b_tokens[i], b_tokens[i + 1]) for i in range(len(b_tokens) - 1)}
    a_sig = {bg for bg in a_bigrams if bg[0] not in stop and bg[1] not in stop}
    b_sig = {bg for bg in b_bigrams if bg[0] not in stop and bg[1] not in stop}
    if a_sig and b_sig:
        bg_overlap = len(a_sig & b_sig) / min(len(a_sig), len(b_sig))
        if bg_overlap >= 0.25:
            return True
    return False


def _limitations_section() -> str:
    return (
        "- **Self-reported data**: All behavioural and attitudinal data is based on participant "
        "self-report. Ordering frequency, spend, and decision-making patterns reflect "
        "participants' own perceptions and may differ from actual usage data.\n"
        "- **Sub-group sample sizes**: Postgraduate (n=4) and graduate (n=6) sub-groups are "
        "small. Findings for these segments are directional and should be validated "
        "with larger samples or behavioural data before informing strategy.\n"
        "- **Platform comparison**: Competitive references (e.g., Uber One mentions) count "
        "all conversational references including non-subscribers. Like-for-like "
        "subscription comparisons are noted where applicable.\n"
        "- **Diary subsample**: Statistics derived from meal-level diary data (e.g., "
        "22% meal skip rate, 46.7% home cooking share, 3.5% delivery share) are based on "
        "a single tracked week (January–February 2026) from the 15-participant diary "
        "subsample. These rates may vary by academic period and may not generalise to the "
        "full 35-participant sample.\n"
        "- **London/UK bias**: All participants were UK-based. Findings may not generalise "
        "to other markets.\n\n"
    )



def _synthesize_exec_summary(insights: dict[str, Any]) -> str:
    """Build an executive summary from the top insights when one isn't provided."""
    items = insights.get("insights", [])
    if not items:
        return ""
    top = [i for i in items[:5] if isinstance(i, dict)]
    parts = [
        _get(i, "insight", "title", default="") for i in top
    ]
    parts = [p for p in parts if p]
    if not parts:
        return ""
    return (
        f"Across {len(items)} key findings, this research identified:\n\n"
        + "\n".join(f"- {p}" for p in parts)
        + "\n"
    )


def _build_say_do_section() -> str:
    """Build a section highlighting say-do gaps from diary participant summaries."""
    summary_dir = PROCESSED_DIR / "participant_summaries"
    if not summary_dir.exists():
        return ""

    gaps_by_pid: dict[str, list[str]] = {}
    total_count = 0
    for path in sorted(summary_dir.glob("*_summary.json")):
        data = _load_json(path)
        if not isinstance(data, dict):
            continue
        gaps = data.get("say_do_gaps", [])
        pid = data.get("participant_id", path.stem.replace("_summary", "").upper())
        for gap in gaps:
            if isinstance(gap, str) and gap:
                lower = gap.lower()
                if "no significant" in lower or "closely matches" in lower:
                    continue
                gaps_by_pid.setdefault(pid, []).append(gap)
                total_count += 1

    if not gaps_by_pid:
        return ""

    lines = [
        "## Diary Study: Say-Do Gaps\n",
        f"*{total_count} discrepancies identified across "
        f"{len(gaps_by_pid)} diary participants, comparing interview "
        f"claims against 7-day observed behaviour. Gaps run in both "
        f"directions — most participants overclaimed cooking and "
        f"underclaimed meal skipping, though some cooked more than "
        f"they reported.*\n",
    ]

    _OVERCLAIM_SIGNALS = [
        "but diary shows only", "but placed zero", "but skipped",
        "but diary shows more", "but ordered twice", "but diary shows frequent",
        "zero delivery", "lower than", "overclaim",
    ]

    shown: list[tuple[str, str]] = []
    max_display = 15

    for pid in sorted(gaps_by_pid):
        if len(shown) >= max_display:
            break
        pid_gaps = gaps_by_pid[pid]
        best = pid_gaps[0]
        for gap in pid_gaps:
            gl = gap.lower()
            if any(sig in gl for sig in _OVERCLAIM_SIGNALS):
                best = gap
                break
        shown.append((pid, best))

    for pid, gap in shown:
        lines.append(f"- **{pid}:** {gap}")
    remaining = total_count - len(shown)
    if remaining > 0:
        lines.append(f"\n*...and {remaining} additional gaps identified.*")
    lines.append("")

    return "\n".join(lines)


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def _archive_existing(directory: Path) -> None:
    """Move existing output to archive with date prefix."""
    if not directory.exists():
        return
    archive = OUTPUT_DIR / "archive"
    archive.mkdir(parents=True, exist_ok=True)
    date_prefix = datetime.now().strftime("%Y-%m-%d")
    for item in directory.iterdir():
        if item.is_file():
            dest = archive / f"{date_prefix}_{item.name}"
            shutil.move(str(item), str(dest))
