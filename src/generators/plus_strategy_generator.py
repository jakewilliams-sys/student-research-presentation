"""
Deliveroo Plus Student Strategy Report Generator.

Reads the consolidated plus_strategy.json and produces a stakeholder-ready
markdown report covering competitive landscape, value drivers, pain points,
acquisition channels, churn risks, and prioritised recommendations.
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

PLUS_DIR = OUTPUT_DIR / "plus_strategy"
SOURCE_PATH = PROCESSED_DIR / "plus_strategy" / "plus_strategy.json"


def generate_plus_strategy() -> Path:
    """Generate a formatted Plus strategy report from processed data."""
    _archive_existing(PLUS_DIR)
    PLUS_DIR.mkdir(parents=True, exist_ok=True)

    data = _load_json(SOURCE_PATH)
    if not data:
        out = PLUS_DIR / "plus_strategy_report.md"
        out.write_text("# Deliveroo Plus Student Strategy\n\n*No data available.*\n")
        return out

    sections: list[str] = []

    sections.append(f"# {data.get('document_title', 'Deliveroo Plus Student Strategy')}\n")
    sections.append(f"*Generated: {datetime.now().strftime('%d %B %Y')}*\n")
    sections.append(f"*Data basis: {data.get('data_basis', '')}*\n")
    sections.append("---\n")

    # Executive summary
    sections.append("## Executive Summary\n")
    sections.append(data.get("executive_summary", "") + "\n")
    sections.append("---\n")

    # Competitive landscape
    _build_competitive(sections, data.get("competitive_landscape", {}))

    # Subscription ownership map
    _build_ownership(sections, data.get("subscription_ownership_map", {}))

    # Value driver hierarchy
    _build_value_drivers(sections, data.get("value_driver_hierarchy", {}))

    # Pain points
    _build_pain_points(sections, data.get("pain_point_inventory", {}))

    # Acquisition channels
    _build_acquisition(sections, data.get("acquisition_channel_analysis", {}))

    # Churn risk factors
    _build_churn(sections, data.get("churn_risk_factors", {}))

    # Stage-specific attitudes
    _build_stage_attitudes(sections, data.get("stage_specific_subscription_attitudes", {}))

    # Persona-specific attitudes
    _build_persona_attitudes(sections, data.get("persona_specific_subscription_attitudes", {}))

    # Strategic recommendations
    _build_recommendations(sections, data.get("strategic_recommendations_consolidated", {}))

    # Methodology
    _build_methodology(sections, data.get("methodological_notes", {}))

    # Design questions for Experience & Design teams
    _build_design_questions(sections)

    report_text = "\n".join(sections)
    out_path = PLUS_DIR / "plus_strategy_report.md"
    out_path.write_text(report_text)
    logger.info("Generated Plus strategy report: %s (%d chars)", out_path.name, len(report_text))
    return out_path


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------


def _build_competitive(sections: list[str], comp: dict[str, Any]) -> None:
    if not comp:
        return
    sections.append("## Competitive Landscape\n")
    for platform, details in comp.items():
        if not isinstance(details, dict):
            continue
        label = platform.replace("_", " ").title()
        reach = details.get("reach", "")
        sections.append(f"### {label} ({reach})\n")

        perception = details.get("student_perception", "")
        if perception:
            sections.append(f"{perception}\n")

        advantages = details.get("key_advantages", [])
        if advantages:
            sections.append("**Advantages:**\n")
            for a in advantages:
                sections.append(f"- {a}")
            sections.append("")

        weaknesses = details.get("key_weaknesses", [])
        if weaknesses:
            sections.append("**Weaknesses:**\n")
            for w in weaknesses:
                sections.append(f"- {w}")
            sections.append("")

        quote = details.get("key_quote", "")
        if quote:
            sections.append(f"> {quote}\n")
    sections.append("---\n")


def _build_ownership(sections: list[str], ownership: dict[str, Any]) -> None:
    if not ownership:
        return
    sections.append("## Subscription Ownership\n")

    by_stage = ownership.get("by_stage", {})
    if by_stage:
        sections.append("### By Academic Stage\n")
        sections.append("| Stage | Deliveroo Plus | Uber One | Both | Neither | Total |")
        sections.append("|-------|---------------|----------|------|---------|-------|")
        for stage, counts in by_stage.items():
            if not isinstance(counts, dict):
                continue
            sections.append(
                f"| {stage.title()} | {counts.get('deliveroo_plus', 0)} "
                f"| {counts.get('uber_one', 0)} | {counts.get('both', 0)} "
                f"| {counts.get('neither', 0)} | {counts.get('total', 0)} |"
            )
        sections.append("")

    by_persona = ownership.get("by_persona", {})
    if by_persona:
        sections.append("### By Persona\n")
        sections.append("| Persona | Deliveroo Plus | Uber One | Both | Neither | Total |")
        sections.append("|---------|---------------|----------|------|---------|-------|")
        for persona, counts in by_persona.items():
            if not isinstance(counts, dict):
                continue
            label = persona.replace("_", " ").title()
            sections.append(
                f"| {label} | {counts.get('deliveroo_plus', 0)} "
                f"| {counts.get('uber_one', 0)} | {counts.get('both', 0)} "
                f"| {counts.get('neither', 0)} | {counts.get('total', 0)} |"
            )
        sections.append("")

    multi = ownership.get("multi_subscription_holders", [])
    if multi:
        sections.append(f"**Multi-subscription holders:** {', '.join(multi)}\n")
    sections.append("---\n")


def _build_value_drivers(sections: list[str], drivers: dict[str, Any]) -> None:
    if not drivers:
        return
    sections.append("## Value Driver Hierarchy\n")
    desc = drivers.get("description", "")
    if desc:
        sections.append(f"*{desc}*\n")

    for rank_key in sorted(k for k in drivers if k.startswith("rank_")):
        item = drivers[rank_key]
        if not isinstance(item, dict):
            continue
        benefit = item.get("benefit", "")
        mentions = item.get("mentions", "?")
        participants = item.get("participants", "?")
        pct = item.get("pct_of_sample", "?")
        lang = item.get("student_language", [])
        lang_str = ", ".join(f'"{w}"' for w in lang) if lang else ""

        rank_num = rank_key.replace("rank_", "#")
        sections.append(
            f"**{rank_num} {benefit}** -- {mentions} mentions, "
            f"{participants} participants ({pct}% of sample)"
        )
        if lang_str:
            sections.append(f"  Student language: {lang_str}")
        sections.append("")
    sections.append("---\n")


def _build_pain_points(sections: list[str], pains: dict[str, Any]) -> None:
    if not pains:
        return
    sections.append("## Pain Points\n")
    for key, item in pains.items():
        if not isinstance(item, dict):
            continue
        label = key.replace("_", " ").title()
        severity = item.get("severity", "")
        mentions = item.get("mentions", "?")
        participants = item.get("participants", "?")
        pct = item.get("pct_of_sample", "?")
        desc = item.get("description", "")
        quote = item.get("key_quote", "")

        sections.append(f"### {label} [{severity}]\n")
        sections.append(f"*{mentions} mentions, {participants} participants ({pct}%)*\n")
        if desc:
            sections.append(f"{desc}\n")
        if quote:
            sections.append(f'> "{quote}"\n')
    sections.append("---\n")


def _build_acquisition(sections: list[str], channels: dict[str, Any]) -> None:
    if not channels:
        return
    sections.append("## Acquisition Channels\n")
    for key, item in channels.items():
        if not isinstance(item, dict):
            continue
        label = key.replace("_", " ").title()
        eff = item.get("effectiveness", "")
        segments = item.get("segments", "?")
        desc = item.get("description", "")
        quality = item.get("conversion_quality", "")

        sections.append(f"### {label}\n")
        if quality:
            sections.append(f"*Conversion quality: {quality} | {segments} segments | Effectiveness: {eff}*\n")
        else:
            sections.append(f"*{segments} segments | Effectiveness: {eff}*\n")
        if desc:
            sections.append(f"{desc}\n")
    sections.append("---\n")


def _build_churn(sections: list[str], churn: dict[str, Any]) -> None:
    if not churn:
        return
    sections.append("## Churn Risk Factors\n")
    for key, item in churn.items():
        if not isinstance(item, dict):
            continue
        label = key.replace("_", " ").title()
        severity = item.get("severity", "")
        desc = item.get("description", "")
        mitigation = item.get("mitigation", "")
        periods = item.get("periods", [])

        sections.append(f"### {label} [{severity}]\n")
        if desc:
            sections.append(f"{desc}\n")
        if periods:
            sections.append("Affected periods: " + ", ".join(periods) + "\n")
        if mitigation:
            sections.append(f"**Mitigation:** {mitigation}\n")
    sections.append("---\n")


def _build_stage_attitudes(sections: list[str], stages: dict[str, Any]) -> None:
    if not stages:
        return
    sections.append("## Subscription Attitudes by Academic Stage\n")
    for stage, item in stages.items():
        if not isinstance(item, dict):
            continue
        label = stage.replace("_", " ").title()
        n = item.get("n", "?")
        engagement = item.get("subscription_engagement", "")
        driver = item.get("primary_driver", "")
        attitude = item.get("attitude", "")
        behaviors = item.get("key_behaviors", [])
        opportunity = item.get("plus_opportunity", "")

        n_val = int(n) if str(n).isdigit() else 0
        caveat = " *(directional only — small sample)*" if 0 < n_val <= 6 else ""
        sections.append(f"### {label} (n={n}){caveat}\n")
        sections.append(f"**Engagement:** {engagement} | **Primary driver:** {driver}\n")
        if attitude:
            sections.append(f"{attitude}\n")
        if behaviors:
            for b in behaviors:
                sections.append(f"- {b}")
            sections.append("")
        if opportunity:
            sections.append(f"**Plus opportunity:** {opportunity}\n")
    sections.append("---\n")


def _build_persona_attitudes(sections: list[str], personas: dict[str, Any]) -> None:
    if not personas:
        return
    sections.append("## Subscription Attitudes by Persona\n")
    for persona, item in personas.items():
        if not isinstance(item, dict):
            continue
        label = persona.replace("_", " ").title()
        behavior = item.get("subscription_behavior", "")
        opportunity = item.get("plus_opportunity", "")
        quote = item.get("key_quote", "")

        sections.append(f"### {label}\n")
        if behavior:
            sections.append(f"{behavior}\n")
        if opportunity:
            sections.append(f"**Plus opportunity:** {opportunity}\n")
        if quote:
            sections.append(f'> "{quote}"\n')
    sections.append("---\n")


def _build_recommendations(sections: list[str], recs: dict[str, Any]) -> None:
    if not recs:
        return
    sections.append("## Strategic Recommendations\n")
    priority_labels = {
        "priority_1_critical": "Priority 1 -- Critical",
        "priority_2_high": "Priority 2 -- High",
        "priority_3_medium": "Priority 3 -- Medium",
    }
    for key, label in priority_labels.items():
        items = recs.get(key, [])
        if not items:
            continue
        sections.append(f"### {label}\n")
        for item in items:
            if not isinstance(item, dict):
                continue
            area = item.get("area", "")
            action = item.get("action", "")
            evidence = item.get("evidence", "")
            impact = item.get("expected_impact", "")

            sections.append(f"**{area}**\n")
            if action:
                sections.append(f"{action}\n")
            if evidence:
                sections.append(f"*Evidence:* {evidence}\n")
            if impact:
                sections.append(f"*Expected impact:* {impact}\n")
            if "service fee" in area.lower() or "service fee" in action.lower():
                sections.append(
                    "*Note: Eliminating service fees for Plus changes the PAYG "
                    "experience — non-subscribers will see a more visible fee gap. "
                    "This may drive conversion to Plus or feel punitive; the UX "
                    "impact on non-subscribers should be tested before rollout.*\n"
                )
        sections.append("")
    sections.append("---\n")


def _build_design_questions(sections: list[str]) -> None:
    """Append UX research questions raised by the Plus strategy findings."""
    sections.append("## Design Questions for Experience & Design\n")
    sections.append(
        "*The strategic recommendations above raise specific UX research "
        "questions that require investigation before implementation:*\n"
    )
    questions = [
        "Which app touchpoints need redesign for service fee elimination — "
        "checkout summary, order confirmation, subscription management, or savings dashboard?",
        "What should the Silver onboarding flow communicate to Prime-acquired "
        "subscribers who cannot articulate their current benefits?",
        "How does the PAYG (non-subscriber) experience change if Plus eliminates "
        "service fees? Does visible fee differentiation push PAYG users toward "
        "Plus, or does it feel punitive?",
        "What does the free trial journey look like end-to-end — at what point "
        "do trial users decide to cancel, and what in-app signals predict "
        "post-trial conversion?",
        "How should group ordering UX support the collaborative price comparison "
        "behaviour observed in social ordering contexts?",
    ]
    for q in questions:
        sections.append(f"- {q}")
    sections.append("")
    sections.append("---\n")


def _build_methodology(sections: list[str], notes: dict[str, Any]) -> None:
    if not notes:
        return
    sections.append("## Methodological Notes\n")
    source = notes.get("data_source", "")
    if source:
        sections.append(f"**Data source:** {source}\n")
    coverage = notes.get("subscription_coverage", "")
    if coverage:
        sections.append(f"**Coverage:** {coverage}\n")
    limitations = notes.get("limitations", [])
    if limitations:
        sections.append("**Limitations:**\n")
        for lim in limitations:
            sections.append(f"- {lim}")
        sections.append("")
    related = notes.get("related_insights", [])
    if related:
        sections.append(f"**Related insights:** {', '.join(related)}\n")
    dives = notes.get("related_deep_dives", [])
    if dives:
        sections.append(f"**Related deep dives:** {', '.join(dives)}\n")

    sections.append(
        "\n**Diary validation note:** 15 participants completed both interviews and "
        "a 7-day diary study. Diary-tracked ordering behaviour broadly corroborates "
        "stated subscription attitudes — participants who claimed infrequent ordering "
        "showed near-zero delivery in diaries, confirming that consideration exceeds "
        "usage. However, diary data was not separately analysed for subscription-specific "
        "behaviour; a dedicated cross-tabulation would strengthen these findings.\n"
    )


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
