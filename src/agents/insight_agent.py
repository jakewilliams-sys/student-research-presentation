"""
Insight Agent (Agent 4) -- Strategic Analysis Engine.

Distils findings into actionable insights for Deliveroo, grounded in
business context. Generates recommendations across product, marketing,
pricing, and partnerships.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import yaml

from config.settings import CONFIG_DIR, PROCESSED_DIR
from src.agents.base_agent import AgentOutput, BaseAgent

logger = logging.getLogger(__name__)

INSIGHT_DIR = PROCESSED_DIR / "insights"


class InsightAgent(BaseAgent):
    """Generates strategic insights and recommendations."""

    agent_name = "insight"
    prompt_file = "insight_agent.md"

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
        user_parts = ["# Strategic Insight Generation\n"]

        # Business context
        biz_path = CONFIG_DIR / "business_context.yaml"
        if biz_path.exists():
            with open(biz_path) as f:
                biz = yaml.safe_load(f)
            user_parts.append("## Deliveroo Business Context\n")
            cc = biz.get("company_context", {})
            for key in ["current_student_strategy", "known_challenges", "competitive_landscape"]:
                val = cc.get(key, "")
                if val:
                    user_parts.append(f"### {key.replace('_', ' ').title()}\n{val}\n")

            priorities = biz.get("strategic_priorities", [])
            if priorities:
                user_parts.append("### Strategic Priorities")
                for p in priorities:
                    user_parts.append(f"- {p}")
                user_parts.append("")

            hypotheses = biz.get("hypotheses_to_test", [])
            if hypotheses:
                user_parts.append("### Hypotheses to Test")
                for h in hypotheses:
                    user_parts.append(f"- {h}")
                user_parts.append("")

        # Glean context (if available)
        glean = context.get("glean_context", {})
        if glean:
            user_parts.append("## Additional Strategic Context (from Glean)\n")
            for key, val in glean.items():
                if isinstance(val, dict) and val.get("chat_synthesis"):
                    user_parts.append(f"### {key}\n{val['chat_synthesis']}\n")

        # Personas
        personas = context.get("personas", {})
        if personas:
            user_parts.append("## Personas\n")
            persona_list = personas.get("personas", []) if isinstance(personas, dict) else personas
            for p in persona_list[:6]:
                if isinstance(p, dict):
                    user_parts.append(f"### {p.get('name', '')}")
                    user_parts.append(f"Size: {p.get('size', '?')} participants")
                    for c in p.get("key_characteristics", [])[:5]:
                        user_parts.append(f"- {c}")
                    user_parts.append("")

        # Triangulated data
        triang = context.get("triangulated_data", {})
        if triang and isinstance(triang, dict):
            summary = triang.get("summary", "")
            if summary:
                user_parts.append(f"## Triangulation Summary\n{summary}\n")

        # Research objectives
        obj_path = CONFIG_DIR / "research_objectives.yaml"
        if obj_path.exists():
            with open(obj_path) as f:
                objectives = yaml.safe_load(f)
            user_parts.append("## Research Objectives\n")
            for ro_key, ro_data in objectives.get("objectives", {}).items():
                user_parts.append(f"- **{ro_key}**: {ro_data.get('name', '')}: {ro_data.get('question', '')}")
            user_parts.append("")

        # Inject actual sample size for language guardrails
        all_coded = context.get("all_coded_segments", {})
        n_participants = len([k for k in all_coded if not k.startswith("_")])
        user_parts.append(f"## Sample Size\n")
        user_parts.append(f"**N = {n_participants} participants** in this analysis.")
        user_parts.append(
            "Apply the sample-size language rules from your system prompt strictly.\n"
        )

        user_parts.append(
            "\nGenerate strategic insights and recommendations. Return JSON with: "
            "insights, executive_summary, report_sections."
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
        if "insights" not in data:
            logger.warning("insight: missing 'insights' key")
            data["insights"] = []
        elif not isinstance(data["insights"], list):
            data["insights"] = []
        for ins in data["insights"]:
            if not isinstance(ins, dict):
                continue
            ins.setdefault("insight_id", "UNKNOWN")
            ins.setdefault("confidence", "low")
            ins.setdefault("evidence_summary", {})
            if isinstance(ins["evidence_summary"], dict):
                ins["evidence_summary"].setdefault("participants", 0)
                ins["evidence_summary"].setdefault("supporting_quotes", 0)
        data.setdefault("executive_summary", "")
        return data

    def _save_output(self, data: dict[str, Any] | list[Any]) -> None:
        INSIGHT_DIR.mkdir(parents=True, exist_ok=True)
        with open(INSIGHT_DIR / "insights.json", "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info("Saved insight results")


def load_insights() -> dict[str, Any] | None:
    path = INSIGHT_DIR / "insights.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)
