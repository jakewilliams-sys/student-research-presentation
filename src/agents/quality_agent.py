"""
Quality Agent (Agent 5) -- Research Quality Auditor.

Validates analysis rigour by auditing evidence sufficiency,
detecting contradictions, identifying gaps, and scoring confidence
across all prior agent outputs.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from config.settings import PROCESSED_DIR
from src.agents.base_agent import AgentOutput, BaseAgent

logger = logging.getLogger(__name__)

QA_DIR = PROCESSED_DIR / "qa_results"


class QualityAgent(BaseAgent):
    """Audits the full analysis pipeline for quality and rigour."""

    agent_name = "quality"
    prompt_file = "quality_agent.md"

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
        user_parts = ["# Quality Assurance Audit\n"]

        # Insights
        insights = context.get("insights", {})
        if insights:
            user_parts.append("## Generated Insights\n")
            insight_list = insights.get("insights", []) if isinstance(insights, dict) else insights
            for ins in insight_list:
                if isinstance(ins, dict):
                    user_parts.append(f"### {ins.get('insight_id', '')}: {ins.get('insight', '')}")
                    ev = ins.get("evidence_summary", {})
                    user_parts.append(f"Evidence: {ev.get('supporting_quotes', '?')} quotes from {ev.get('participants', '?')} participants")
                    user_parts.append(f"Confidence: {ins.get('confidence', '?')}")
                    user_parts.append(f"Contradictions: {ins.get('contradicting_evidence', 0)}")
                    user_parts.append("")

        # Personas
        personas = context.get("personas", {})
        if personas:
            user_parts.append("## Personas\n")
            persona_list = personas.get("personas", []) if isinstance(personas, dict) else personas
            for p in persona_list:
                if isinstance(p, dict):
                    user_parts.append(f"- **{p.get('name', '')}**: {p.get('size', '?')} participants")
            user_parts.append("")

        # Coded segment counts per participant
        all_coded = context.get("all_coded_segments", {})
        if all_coded:
            user_parts.append("## Evidence Volume\n")
            total_segs = 0
            for pid, data in all_coded.items():
                segments = data.get("coded_segments", []) if isinstance(data, dict) else data if isinstance(data, list) else []
                total_segs += len(segments)
                user_parts.append(f"- {pid}: {len(segments)} coded segments")
            user_parts.append(f"\n**Total coded segments: {total_segs}**\n")

        # Triangulated data
        triang = context.get("triangulated_data", {})
        if triang and isinstance(triang, dict):
            comparisons = triang.get("segment_comparisons", [])
            user_parts.append(f"## Triangulation: {len(comparisons)} comparisons\n")

        # Research objectives for gap check
        user_parts.append(
            "\nAudit all outputs for evidence sufficiency, contradictions, gaps, "
            "and confidence. Return JSON with: overall_assessment, objective_coverage, "
            "critical_issues, moderate_issues, confidence_scores, recommended_deep_dives."
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
        data.setdefault("overall_assessment", {})
        for key in ("critical_issues", "moderate_issues", "recommended_deep_dives"):
            if key not in data or not isinstance(data.get(key), list):
                data[key] = []
        return data

    def _save_output(self, data: dict[str, Any] | list[Any]) -> None:
        QA_DIR.mkdir(parents=True, exist_ok=True)
        with open(QA_DIR / "qa_results.json", "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info("Saved QA results")


def load_qa_results() -> dict[str, Any] | None:
    path = QA_DIR / "qa_results.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)
