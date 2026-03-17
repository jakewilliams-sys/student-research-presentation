"""
Micro-Moment Analysis Generator

Produces behavioural insights from the 6 in-home interviews where participants
placed real Deliveroo orders while being observed. Populates outputs from
coded segment data when structured LLM-extracted observation data is unavailable.

Outputs:
  - Per-participant ordering timelines
  - Aggregated decision heuristics
  - Friction point map
  - Price sensitivity reality check (stated vs. observed)
  - Social dynamics analysis
  - Time-to-decision analysis
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = BASE_DIR / "config"
OUTPUT_DIR = BASE_DIR / "output" / "micro_moments"
DATA_DIR = BASE_DIR / "data"
CODED_DIR = DATA_DIR / "processed" / "coded_segments"

_STAGE_KEYWORDS: dict[str, list[str]] = {
    "pre_order": ["trigger", "hungry", "craving", "decided to order",
                  "nothing in", "can't be bothered", "too tired",
                  "barrier", "before i order", "when i want to order",
                  "normally order", "usually order"],
    "app_opening": ["open the app", "opened deliveroo", "opened uber",
                    "first thing i do", "go straight to", "favourites",
                    "go on deliveroo", "go on uber", "go on just eat",
                    "which app", "check the app", "open up",
                    "download", "downloaded the app", "got the app",
                    "use deliveroo", "use uber", "i'll go on"],
    "browsing": ["scroll", "browse", "looking at", "restaurants",
                 "menus", "search for", "filter", "what's on there",
                 "see what", "look through", "options"],
    "decision_points": ["hesitat", "compare", "switch app", "switch between",
                        "change my mind", "not sure", "deciding",
                        "torn between", "depends on", "it depends",
                        "between the two"],
    "price_reactions": ["delivery fee", "service fee", "expensive",
                       "cost", "price", "too much", "minimum order",
                       "free delivery", "total", "pounds", "quid",
                       "subscription", "membership", "plus"],
    "final_decision": ["went with", "chose", "decided on", "ordered from",
                       "placed the order", "in the end", "end up",
                       "ended up", "i'll go for", "i go for",
                       "i usually get", "i always get", "my go-to"],
    "post_order": ["after order", "waiting for", "arrived", "regret",
                   "worth it", "guilty", "satisfied", "next time",
                   "afterwards", "once it arrives", "when it comes",
                   "feel bad", "feel guilty", "shouldn't have",
                   "treat myself", "deserved it"],
}

_STAGE_RO_PATTERNS: dict[str, list[str]] = {
    "pre_order": ["trigger", "barrier", "price_sensitivity"],
    "app_opening": ["platform_choice", "channel", "awareness"],
    "browsing": ["decision_process"],
    "decision_points": ["decision_process", "barrier"],
    "price_reactions": ["barrier", "cost", "subscription", "promotions"],
    "final_decision": ["platform_choice"],
    "post_order": ["guilt", "justification", "post_graduation"],
}


def _load_in_home_config() -> dict[str, Any]:
    """Load the in-home analysis configuration."""
    path = CONFIG_DIR / "in_home_analysis.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def _load_participant_map() -> dict[str, Any]:
    """Load participant map to identify in-home participants."""
    path = DATA_DIR / "reference" / "participant_map.json"
    with open(path) as f:
        return json.load(f)


def get_in_home_participants(participant_map: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """
    Return the list of in-home participants with their data sources.

    Filters the participant map for entries with ``interview_type == "in_home"``
    and ``has_order_observation == True``.
    """
    pmap = participant_map or _load_participant_map()
    return [
        pdata
        for pid, pdata in pmap.items()
        if isinstance(pdata, dict)
        and pdata.get("interview_type") == "in_home"
        and pdata.get("has_order_observation") is True
    ]


def get_observation_stages() -> list[dict[str, Any]]:
    """Return the ordered observation stages from config."""
    config = _load_in_home_config()
    return config["micro_moment_framework"]["observation_stages"]


def _load_coded_segments(participant_id: str) -> list[dict[str, Any]]:
    """Load coded segments for a single participant."""
    path = CODED_DIR / f"{participant_id.lower()}_coded.json"
    if not path.exists():
        return []
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, dict):
        return data.get("coded_segments", [])
    return data if isinstance(data, list) else []


def _classify_segment_stage(seg: dict[str, Any]) -> str:
    """Map a coded segment to an ordering journey stage using RO codes and text."""
    codes_str = " ".join(seg.get("research_objective_codes", [])).lower()
    text = seg.get("text", "").lower()

    best_stage = "pre_order"
    best_score = 0

    for stage, ro_patterns in _STAGE_RO_PATTERNS.items():
        score = sum(1 for p in ro_patterns if p in codes_str) * 2
        if score > best_score:
            best_score = score
            best_stage = stage

    for stage, keywords in _STAGE_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > best_score:
            best_score = score
            best_stage = stage

    return best_stage


def _build_timeline_from_segments(
    participant_id: str,
    segments: list[dict[str, Any]],
    participant_name: str = "",
) -> str:
    """Build a participant timeline from coded segment data."""
    stage_segments: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        stage = _classify_segment_stage(seg)
        stage_segments[stage].append(seg)

    stage_order = [
        ("pre_order", "Pre-Order Context"),
        ("app_opening", "App Opening"),
        ("browsing", "Browsing Behaviour"),
        ("decision_points", "Decision Points"),
        ("price_reactions", "Price Reactions"),
        ("final_decision", "Final Decision"),
        ("post_order", "Post-Order Reflection"),
    ]

    header = f"# Ordering Timeline -- {participant_id}"
    if participant_name:
        header += f" ({participant_name})"

    lines = [
        header,
        "",
        "**Interview Type:** In-Home Observation",
        "**Has Order Observation:** Yes",
        "**Data Source:** Coded interview segments",
        "",
        "---",
        "",
    ]

    for stage_key, stage_label in stage_order:
        segs = stage_segments.get(stage_key, [])
        lines.append(f"## {stage_label}")
        lines.append("")

        if not segs:
            lines.append("*No segments mapped to this stage.*")
            lines.append("")
            continue

        best = sorted(segs,
                       key=lambda s: s.get("quote_quality", {}).get("representativeness", 0)
                       if isinstance(s.get("quote_quality"), dict) else 0,
                       reverse=True)

        for seg in best[:3]:
            text = seg.get("text", "").strip()
            if len(text) > 300:
                text = text[:297] + "..."
            emotions = []
            ctx = seg.get("context_tags", {})
            if isinstance(ctx, dict):
                emo = ctx.get("emotion", [])
                emotions = emo if isinstance(emo, list) else [emo] if emo else []
            emo_str = f" *({', '.join(emotions)})*" if emotions else ""
            lines.append(f"> \"{text}\" -- {participant_id}{emo_str}")
            lines.append("")

        lines.append("")

    tensions = [
        seg for seg in segments
        if isinstance(seg.get("enrichment_tags", {}).get("tension"), (str, dict))
        and seg.get("enrichment_tags", {}).get("tension")
    ]
    if tensions:
        lines.append("## Stated vs. Observed Tensions")
        lines.append("")
        for t in tensions[:4]:
            tension_data = t["enrichment_tags"]["tension"]
            if isinstance(tension_data, dict):
                label = tension_data.get("tension_type", "Tension")
            else:
                raw = str(tension_data).strip()
                if re.match(r"^[\d:\-]+$", raw):
                    label = _infer_tension_label(t)
                else:
                    label = raw
            text = t.get("text", "").strip()
            if len(text) > 200:
                text = text[:197] + "..."
            lines.append(f"- **{label}**")
            lines.append(f"  > \"{text}\" -- {participant_id}")
            lines.append("")

    return "\n".join(lines)


_TENSION_LABEL_RULES: list[tuple[str, list[str]]] = [
    ("Say-Do Gap", ["but", "claims", "says", "stated", "actually",
                    "diary shows", "contradicts"]),
    ("Cost-Value Paradox", ["price", "cost", "money", "spend", "budget",
                           "expensive", "afford", "fee", "worth"]),
    ("Health vs Convenience", ["health", "cook", "meal prep", "junk",
                              "unhealthy", "diet", "fresh", "nutritio"]),
    ("Treat vs Routine", ["treat", "reward", "routine", "habit",
                          "every week", "regular", "indulgen"]),
    ("Social Pressure vs Choice", ["friend", "flatmate", "group",
                                   "social", "alone", "peer"]),
]


def _infer_tension_label(seg: dict[str, Any]) -> str:
    """Infer a human-readable tension label from segment text when the raw
    tension field is just a timestamp reference."""
    text = seg.get("text", "").lower()
    for label, keywords in _TENSION_LABEL_RULES:
        if any(kw in text for kw in keywords):
            return label
    return "Tension"


def _build_aggregate_from_segments(
    all_segments: dict[str, list[dict[str, Any]]],
) -> str:
    """Build the aggregate micro-moment report from coded segments."""

    all_segs = []
    for segs in all_segments.values():
        all_segs.extend(segs)

    stage_segments: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for seg in all_segs:
        stage = _classify_segment_stage(seg)
        stage_segments[stage].append(seg)

    n_participants = len(all_segments)

    lines = [
        "# Micro-Moment Analysis: In-Home Ordering Observations",
        "",
        f"**Participants:** {n_participants} in-home interviews (P025--P030)",
        "**Method:** Live ordering observation during in-home visits",
        "**Locations:** Manchester, Nottingham",
        f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        "",
        "---",
        "",
        "## Methodology Note",
        "",
        "This analysis is based on coded segments from in-home interviews where",
        "participants placed real food delivery orders while being observed.",
        "Observations carry higher analytical weight than self-reported data from",
        "online interviews when the two conflict. Segments are classified into",
        "ordering journey stages using research objective codes and keyword matching.",
        "",
        "---",
        "",
    ]

    # --- Decision Heuristics ---
    lines.append("## Common Decision Heuristics")
    lines.append("")
    lines.append("*Shortcuts students use when ordering, drawn from browsing and "
                 "decision-point segments*")
    lines.append("")

    decision_segs = stage_segments.get("browsing", []) + stage_segments.get("decision_points", [])
    heuristic_patterns = [
        ("Defaulting to favourites/known restaurants",
         ["favourite", "always go to", "usual", "know already", "go-to"]),
        ("Filtering by free delivery or offers",
         ["free delivery", "offer", "deal", "discount", "buy one"]),
        ("Choosing the subscription-linked app first",
         ["subscription", "plus", "member", "free delivery"]),
        ("Prioritising speed (fastest delivery time)",
         ["delivery time", "quickest", "fastest", "minutes"]),
        ("Going with a specific craving",
         ["craving", "felt like", "wanted", "in the mood"]),
    ]

    for label, keywords in heuristic_patterns:
        matches = [
            s for s in decision_segs
            if any(kw in s.get("text", "").lower() for kw in keywords)
        ]
        pids = {s.get("participant_id", "") for s in matches}
        if matches:
            lines.append(f"**{label}** ({len(pids)}/{n_participants} participants)")
            best = max(matches,
                       key=lambda s: s.get("quote_quality", {}).get("vividness", 0)
                       if isinstance(s.get("quote_quality"), dict) else 0)
            text = best.get("text", "").strip()
            if len(text) > 250:
                text = text[:247] + "..."
            lines.append(f"> \"{text}\" -- {best.get('participant_id', '')}")
            lines.append("")
    lines.extend(["---", ""])

    # --- Friction Points ---
    lines.append("## Friction Point Map")
    lines.append("")
    lines.append("*Where students hesitate, get frustrated, or abandon*")
    lines.append("")

    friction_types = {
        "Price friction": ["fee", "expensive", "cost", "price", "minimum order",
                          "too much", "money"],
        "Choice friction": ["too many", "can't decide", "overwhelm", "scroll",
                           "indecision", "choice"],
        "Social friction": ["flatmate", "group", "split", "coordinate",
                           "someone else", "agree"],
        "Technical friction": ["app", "payment", "crash", "slow", "login",
                              "checkout"],
    }

    price_segs = stage_segments.get("price_reactions", []) + stage_segments.get("decision_points", [])
    for friction_label, keywords in friction_types.items():
        matches = [
            s for s in price_segs
            if any(kw in s.get("text", "").lower() for kw in keywords)
        ]
        pids = {s.get("participant_id", "") for s in matches}
        if matches:
            lines.append(f"**{friction_label}** ({len(pids)}/{n_participants} participants, "
                         f"{len(matches)} segments)")
            for m in matches[:2]:
                text = m.get("text", "").strip()
                if len(text) > 200:
                    text = text[:197] + "..."
                lines.append(f"> \"{text}\" -- {m.get('participant_id', '')}")
            lines.append("")
    lines.extend(["---", ""])

    # --- Price Sensitivity ---
    lines.append("## Price Sensitivity in Action")
    lines.append("")
    lines.append("*How students actually react to prices vs. what they claim*")
    lines.append("")

    price_segs_all = stage_segments.get("price_reactions", [])
    fee_segs = [s for s in price_segs_all
                if any(kw in s.get("text", "").lower()
                       for kw in ["delivery fee", "service fee", "service charge"])]
    total_segs = [s for s in price_segs_all
                  if any(kw in s.get("text", "").lower()
                         for kw in ["total", "altogether", "came to", "adds up"])]

    if fee_segs:
        pids = {s.get("participant_id") for s in fee_segs}
        lines.append(f"**Delivery/service fee sensitivity** ({len(pids)}/{n_participants} "
                     "participants mentioned fees unprompted)")
        for s in fee_segs[:2]:
            text = s.get("text", "").strip()
            if len(text) > 200:
                text = text[:197] + "..."
            lines.append(f"> \"{text}\" -- {s.get('participant_id', '')}")
        lines.append("")

    if total_segs:
        pids = {s.get("participant_id") for s in total_segs}
        lines.append(f"**Total order value awareness** ({len(pids)}/{n_participants} participants)")
        for s in total_segs[:2]:
            text = s.get("text", "").strip()
            if len(text) > 200:
                text = text[:197] + "..."
            lines.append(f"> \"{text}\" -- {s.get('participant_id', '')}")
        lines.append("")
    lines.extend(["---", ""])

    # --- Social Dynamics ---
    lines.append("## Social Dynamics")
    lines.append("")
    lines.append("*How ordering changes when someone else is present*")
    lines.append("")

    social_segs = [
        s for s in all_segs
        if isinstance(s.get("context_tags"), dict)
        and s["context_tags"].get("social_context") in ("with_others", "group", "flatmates")
    ]
    solo_segs = [
        s for s in all_segs
        if isinstance(s.get("context_tags"), dict)
        and s["context_tags"].get("social_context") == "alone"
    ]

    lines.append(f"- **Social ordering segments:** {len(social_segs)}")
    lines.append(f"- **Solo ordering segments:** {len(solo_segs)}")
    lines.append("")

    for s in social_segs[:3]:
        text = s.get("text", "").strip()
        if len(text) > 200:
            text = text[:197] + "..."
        lines.append(f"> \"{text}\" -- {s.get('participant_id', '')}")
        lines.append("")
    lines.extend(["---", ""])

    # --- Emotional Arc ---
    lines.append("## Emotional Arc Across the Ordering Journey")
    lines.append("")
    lines.append("*Dominant emotions at each stage*")
    lines.append("")

    _NOISE_EMOTIONS = {"indifference", "neutral", "routine"}

    stage_labels = [
        ("pre_order", "Pre-Order"),
        ("app_opening", "App Opening"),
        ("browsing", "Browsing"),
        ("decision_points", "Decision Points"),
        ("price_reactions", "Price Reactions"),
        ("final_decision", "Final Decision"),
        ("post_order", "Post-Order"),
    ]
    for stage_key, label in stage_labels:
        segs = stage_segments.get(stage_key, [])
        all_emotions: list[str] = []
        for s in segs:
            ctx = s.get("context_tags", {})
            if isinstance(ctx, dict):
                emo = ctx.get("emotion", [])
                if isinstance(emo, list):
                    all_emotions.extend(e.lower() for e in emo if e)
                elif emo:
                    all_emotions.append(str(emo).lower())
        meaningful = [e for e in all_emotions if e not in _NOISE_EMOTIONS]
        source = meaningful if meaningful else all_emotions
        if source:
            counter = Counter(source)
            top3 = counter.most_common(3)
            emo_str = ", ".join(f"{e} ({c})" for e, c in top3)
            caveat = " *(noise emotions only)*" if not meaningful and all_emotions else ""
            lines.append(f"- **{label}:** {emo_str}{caveat}")
        else:
            lines.append(f"- **{label}:** *(no emotion data)*")
    lines.append("")

    return "\n".join(lines)


def build_observation_prompt(participant_id: str, transcript_text: str) -> str:
    """
    Build an LLM prompt for extracting micro-moment observations from
    an in-home transcript.
    """
    stages = get_observation_stages()
    config = _load_in_home_config()

    stage_instructions = []
    for stage in stages:
        cues = "\n".join(f"    - {c}" for c in stage["observation_cues"])
        questions = "\n".join(f"    - {q}" for q in stage["analysis_questions"])
        stage_instructions.append(
            f"### {stage['label']} ({stage['id']})\n"
            f"  Description: {stage['description']}\n"
            f"  Look for:\n{cues}\n"
            f"  Analyse:\n{questions}"
        )

    weighting = config["micro_moment_framework"]["analysis_weighting"]

    return f"""You are analysing an in-home interview transcript where the participant
placed a real food delivery order while being observed by a researcher.

PARTICIPANT: {participant_id}

IMPORTANT PRINCIPLE: {weighting['principle']}
Rationale: {weighting['rationale']}

Your task is to extract a structured micro-moment analysis of the Live Order
section of this interview. For each stage below, extract what you observed
in the transcript.

OBSERVATION STAGES:

{"".join(stage_instructions)}

OUTPUT FORMAT:
Return a JSON object with the following structure:
{{
  "participant_id": "{participant_id}",
  "interview_type": "in_home",
  "order_observation": {{
    "pre_order": {{
      "context": "...",
      "trigger": "...",
      "time_to_app_open": "..."
    }},
    "app_opening": {{
      "first_action": "...",
      "initial_browse": ["..."],
      "app_chosen": "...",
      "reason": "..."
    }},
    "browsing_behavior": {{
      "total_time": "...",
      "restaurants_viewed": 0,
      "menus_opened": 0,
      "items_added_then_removed": 0,
      "search_vs_scroll": "..."
    }},
    "decision_points": [
      {{
        "moment": "...",
        "reaction": "...",
        "outcome": "..."
      }}
    ],
    "price_sensitivity": {{
      "total_order_value": "...",
      "mentioned_price": true/false,
      "price_influenced_choice": true/false,
      "delivery_fee_reaction": "...",
      "notes": "..."
    }},
    "final_decision": {{
      "restaurant": "...",
      "deciding_factor": "...",
      "time_from_open_to_order": "..."
    }},
    "post_order": {{
      "immediate_feeling": "...",
      "quote": "..."
    }}
  }},
  "insights": ["..."],
  "stated_vs_observed_gaps": [
    {{
      "topic": "...",
      "stated": "...",
      "observed": "...",
      "implication": "..."
    }}
  ]
}}

TRANSCRIPT:
{transcript_text}
"""


def generate_participant_timeline(
    observation: dict[str, Any],
    coded_segments: list[dict[str, Any]] | None = None,
) -> str:
    """
    Generate a markdown timeline for a single participant's ordering observation.
    Falls back to coded segment data when structured observation data is absent.
    """
    pid = observation.get("participant_id", "Unknown")
    order_obs = observation.get("order_observation", {})

    has_observation_data = bool(order_obs) and any(
        isinstance(v, (dict, list)) and v for v in order_obs.values()
    )

    if not has_observation_data and coded_segments:
        return _build_timeline_from_segments(
            pid, coded_segments, observation.get("name", ""),
        )

    lines = [
        f"# Ordering Timeline - {pid}",
        "",
        "**Interview Type:** In-Home Observation",
        "**Has Order Observation:** Yes",
        "",
        "## Timeline",
        "",
    ]

    stage_data = [
        ("Pre-Order", order_obs.get("pre_order", {})),
        ("App Opening", order_obs.get("app_opening", {})),
        ("Browsing", order_obs.get("browsing_behavior", {})),
        ("Decision Points", order_obs.get("decision_points", [])),
        ("Price Reactions", order_obs.get("price_sensitivity", {})),
        ("Final Decision", order_obs.get("final_decision", {})),
        ("Post-Order", order_obs.get("post_order", {})),
    ]

    for stage_name, data in stage_data:
        lines.append(f"### {stage_name}")
        lines.append("")
        if isinstance(data, dict):
            for k, v in data.items():
                label = k.replace("_", " ").title()
                lines.append(f"- **{label}:** {v}")
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    moment = item.get("moment", "")
                    reaction = item.get("reaction", "")
                    outcome = item.get("outcome", "")
                    lines.append(f"- **{moment}** -> {reaction} -> _{outcome}_")
                else:
                    lines.append(f"- {item}")
        lines.append("")

    insights = observation.get("insights", [])
    if insights:
        lines.append("## Key Insights")
        lines.append("")
        for insight in insights:
            lines.append(f"- {insight}")
        lines.append("")

    gaps = observation.get("stated_vs_observed_gaps", [])
    if gaps:
        lines.append("## Stated vs. Observed Gaps")
        lines.append("")
        for gap in gaps:
            lines.append(f"### {gap.get('topic', 'Unknown')}")
            lines.append(f"- **Stated:** {gap.get('stated', '')}")
            lines.append(f"- **Observed:** {gap.get('observed', '')}")
            lines.append(f"- **Implication:** {gap.get('implication', '')}")
            lines.append("")

    return "\n".join(lines)


def generate_aggregate_report(
    observations: list[dict[str, Any]],
    all_coded_segments: dict[str, list[dict[str, Any]]] | None = None,
) -> str:
    """
    Generate the aggregated micro-moment report.
    Uses coded segment data when structured observation data is unavailable.
    """
    has_observation_data = any(
        bool(obs.get("order_observation"))
        and any(isinstance(v, (dict, list)) and v
                for v in obs.get("order_observation", {}).values())
        for obs in observations
    )

    if not has_observation_data and all_coded_segments:
        return _build_aggregate_from_segments(all_coded_segments)

    config = _load_in_home_config()
    agg_outputs = config["micro_moment_framework"]["aggregate_outputs"]

    report_lines = [
        "# Micro-Moment Analysis: In-Home Ordering Observations",
        "",
        f"**Participants:** {len(observations)} in-home interviews",
        "**Method:** Live ordering observation during in-home visits",
        "**Locations:** Manchester, Nottingham",
        f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        "",
        "---",
        "",
    ]

    for output_spec in agg_outputs:
        report_lines.append(f"## {output_spec['label']}")
        report_lines.append("")
        report_lines.append(f"*{output_spec['description']}*")
        report_lines.append("")

    return "\n".join(report_lines)


def save_outputs(
    observations: list[dict[str, Any]],
    all_coded_segments: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, str]:
    """
    Generate and save all micro-moment analysis outputs.

    Returns mapping of output name -> file path.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timeline_dir = OUTPUT_DIR / "participant_timelines"
    timeline_dir.mkdir(parents=True, exist_ok=True)

    saved: dict[str, str] = {}

    for obs in observations:
        pid = obs.get("participant_id", "unknown")
        pid_coded = (all_coded_segments or {}).get(pid.upper(), [])
        timeline_md = generate_participant_timeline(obs, pid_coded or None)
        timeline_path = timeline_dir / f"{pid.lower()}_timeline.md"
        with open(timeline_path, "w") as f:
            f.write(timeline_md)
        saved[f"timeline_{pid}"] = str(timeline_path)

    report_md = generate_aggregate_report(observations, all_coded_segments)
    report_path = OUTPUT_DIR / "micro_moment_report.md"
    with open(report_path, "w") as f:
        f.write(report_md)
    saved["aggregate_report"] = str(report_path)

    data_path = OUTPUT_DIR.parent / "data_exports" / "all_micro_moments.json"
    data_path.parent.mkdir(parents=True, exist_ok=True)
    with open(data_path, "w") as f:
        json.dump(observations, f, indent=2, ensure_ascii=False)
    saved["data_export"] = str(data_path)

    logger.info("Saved micro-moment outputs: %s", list(saved.keys()))
    return saved
