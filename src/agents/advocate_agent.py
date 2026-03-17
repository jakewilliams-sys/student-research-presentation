"""
Devil's Advocate Agent (Agent 6) -- Critical Reviewer.

Stress-tests the analysis by challenging each key finding, checking
for biases, proposing alternative interpretations, and identifying
blind spots. Makes the research stronger through rigorous scrutiny.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import yaml

from config.settings import CONFIG_DIR, PROCESSED_DIR
from src.agents.base_agent import AgentOutput, BaseAgent

logger = logging.getLogger(__name__)

ADVOCATE_DIR = PROCESSED_DIR / "advocate_results"


class AdvocateAgent(BaseAgent):
    """Challenges and stress-tests all analysis findings."""

    agent_name = "advocate"
    prompt_file = "devils_advocate.md"

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.max_tokens = max(self.max_tokens, 8192)

    def run(self, participant_id: str = "", context: dict[str, Any] | None = None) -> AgentOutput:
        context = context or {}
        output = super().run("all", context)
        if output.success and output.data:
            self._save_output(output.data)
        return output

    def _build_messages(
        self, participant_id: str, context: dict[str, Any]
    ) -> list[dict[str, str]]:
        system = self._load_system_prompt()
        user_parts = ["# Devil's Advocate Challenge\n"]

        # Business context for commercial reality check
        biz_path = CONFIG_DIR / "business_context.yaml"
        if biz_path.exists():
            with open(biz_path) as f:
                biz = yaml.safe_load(f)
            user_parts.append("## Business Context\n")
            cc = biz.get("company_context", {})
            for key in ["known_challenges", "competitive_landscape"]:
                val = cc.get(key, "")
                if val:
                    user_parts.append(f"### {key.replace('_', ' ').title()}\n{val}\n")

        # Insights to challenge
        insights = context.get("insights", {})
        if insights:
            user_parts.append("## Insights to Challenge\n")
            insight_list = insights.get("insights", []) if isinstance(insights, dict) else insights
            for ins in insight_list:
                if isinstance(ins, dict):
                    user_parts.append(f"### {ins.get('insight_id', '')}")
                    user_parts.append(f"**Finding:** {ins.get('insight', '')}")
                    user_parts.append(f"**So what:** {ins.get('so_what', '')}")
                    user_parts.append(f"**Confidence:** {ins.get('confidence', '')}")
                    ev = ins.get("evidence_summary", {})
                    user_parts.append(f"**Evidence:** {ev.get('supporting_quotes', '?')} quotes, {ev.get('participants', '?')} participants")
                    user_parts.append(f"**Contradictions:** {ins.get('contradicting_evidence', 0)}")
                    recs = ins.get("recommendations", [])
                    for r in recs:
                        if isinstance(r, dict):
                            user_parts.append(f"- Rec ({r.get('type', '')}): {r.get('recommendation', '')}")
                    user_parts.append("")

        # Personas to challenge
        personas = context.get("personas", {})
        if personas:
            user_parts.append("## Personas to Challenge\n")
            persona_list = personas.get("personas", []) if isinstance(personas, dict) else personas
            for p in persona_list:
                if isinstance(p, dict):
                    user_parts.append(f"### {p.get('name', '')} (n={p.get('size', '?')})")
                    dist = p.get("segment_distribution", {})
                    user_parts.append(f"Distribution: {json.dumps(dist)}")
                    for c in p.get("key_characteristics", [])[:3]:
                        user_parts.append(f"- {c}")
                    user_parts.append("")

        # QA results for context
        qa = context.get("qa_results", {})
        if qa and isinstance(qa, dict):
            user_parts.append("## QA Findings\n")
            overall = qa.get("overall_assessment", {})
            user_parts.append(f"Evidence coverage: {overall.get('evidence_coverage_pct', '?')}%")
            user_parts.append(f"Contradictions: {overall.get('contradiction_count', '?')}")
            critical = qa.get("critical_issues", [])
            if critical:
                user_parts.append(f"\n{len(critical)} critical issues flagged by QA.")
            user_parts.append("")

        # Sample size context (computed from participant profiles)
        profiles = context.get("participant_profiles", {})
        segment_counts: dict[str, int] = {}
        for pid, prof in profiles.items():
            if isinstance(prof, dict) and not pid.startswith("_"):
                seg = prof.get("segment", prof.get("_segment", "unknown"))
                segment_counts[seg] = segment_counts.get(seg, 0) + 1
        total = sum(segment_counts.values()) or 1
        user_parts.append("## Sample Composition\n")
        if segment_counts:
            for seg, count in sorted(segment_counts.items(), key=lambda x: -x[1]):
                pct = round(100 * count / total)
                user_parts.append(f"- {seg.replace('_', ' ').title()}: {count} ({pct}%)")
        else:
            user_parts.append("- Sample composition not available from context")
        user_parts.append("")

        user_parts.append(
            "\nChallenge every finding rigorously. Return JSON with: executive_summary, "
            "findings_strengthened, findings_weakened, insight_challenges, bias_assessment, "
            "alternative_interpretations, blind_spots, strengthening_recommendations."
        )

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": "\n".join(user_parts)})
        return messages

    def _validate_structure(
        self, data: dict[str, Any] | list[Any], participant_id: str
    ) -> dict[str, Any] | list[Any]:
        data = super()._validate_structure(data, participant_id)
        if not isinstance(data, dict):
            return data
        data.setdefault("executive_summary", "")
        data.setdefault("findings_strengthened", 0)
        data.setdefault("findings_weakened", 0)
        for key in ("insight_challenges", "alternative_interpretations", "blind_spots"):
            if key not in data or not isinstance(data.get(key), list):
                data[key] = []
        return data

    def _save_output(self, data: dict[str, Any] | list[Any]) -> None:
        ADVOCATE_DIR.mkdir(parents=True, exist_ok=True)
        with open(ADVOCATE_DIR / "advocate_results.json", "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info("Saved advocate results")


def load_advocate_results() -> dict[str, Any] | None:
    path = ADVOCATE_DIR / "advocate_results.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)
