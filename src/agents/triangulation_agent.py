"""
Triangulation Agent (Agent 2) -- Cross-Reference Engine.

Analyses all coded segments across participants to identify patterns,
compare segments, and detect say-do gaps. Operates on the full dataset
rather than individual participants.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import yaml

from config.settings import CONFIG_DIR, PROCESSED_DIR
from src.agents.base_agent import AgentOutput, BaseAgent

logger = logging.getLogger(__name__)

TRIANG_DIR = PROCESSED_DIR / "triangulated_data"


class TriangulationAgent(BaseAgent):
    """Cross-references and compares data across all participants."""

    agent_name = "triangulation"
    prompt_file = "triangulation_agent.md"

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.max_tokens = max(self.max_tokens, 8192)

    def run(self, participant_id: str = "", context: dict[str, Any] | None = None) -> AgentOutput:
        """
        Triangulation runs across all participants (participant_id is ignored).
        Context should include 'all_coded_segments', 'participant_profiles', and 'participant_map'.
        """
        context = context or {}
        output = super().run("all", context)
        if output.success and output.data:
            self._save_output(output.data)
        return output

    def _build_messages(
        self, participant_id: str, context: dict[str, Any]
    ) -> list[dict[str, str]]:
        system = self._load_system_prompt()
        user_parts = ["# Cross-Participant Triangulation Analysis\n"]

        # Segment definitions
        seg_path = CONFIG_DIR / "segment_definitions.yaml"
        if seg_path.exists():
            with open(seg_path) as f:
                seg_defs = yaml.safe_load(f)
            user_parts.append("## Segment Definitions\n")
            user_parts.append(f"```yaml\n{yaml.dump(seg_defs.get('comparison_matrix', []), default_flow_style=False)}\n```\n")

        # All coded segments (summarised to fit context)
        all_coded = context.get("all_coded_segments", {})
        user_parts.append(f"## Coded Data from {len(all_coded)} Participants\n")
        for pid, data in all_coded.items():
            segments = data.get("coded_segments", []) if isinstance(data, dict) else data if isinstance(data, list) else []
            user_parts.append(f"### {pid} ({len(segments)} segments)")
            # Include top quotes by quality for context
            top_segs = sorted(
                [s for s in segments if isinstance(s, dict)],
                key=lambda s: s.get("quote_quality", {}).get("overall", 0),
                reverse=True,
            )[:10]
            for seg in top_segs:
                codes = ", ".join(seg.get("research_objective_codes", []))
                user_parts.append(f'- [{codes}] "{seg.get("text", "")[:200]}"')
            user_parts.append("")

        # Participant profiles
        profiles = context.get("participant_profiles", {})
        if profiles:
            user_parts.append("## Participant Profiles Summary\n")
            for pid, prof in profiles.items():
                if isinstance(prof, dict) and not pid.startswith("_"):
                    seg = prof.get("segment", prof.get("_segment", ""))
                    name = prof.get("name", "")
                    user_parts.append(f"- **{pid}** ({name}): {seg}")
            user_parts.append("")

        # Diary study data (summarised per participant)
        diary_data = context.get("diary_data", {})
        if diary_data:
            user_parts.append(f"## Diary Study Data ({len(diary_data)} participants)\n")
            user_parts.append(
                "These participants completed a 7-day DScout food diary alongside "
                "their interview. Use this for say-do gap analysis.\n"
            )
            for pid, diary in diary_data.items():
                if not isinstance(diary, dict):
                    continue
                stats = diary.get("summary_stats", {})
                user_parts.append(
                    f"- **{pid}** ({diary.get('scout_name', '')}): "
                    f"{stats.get('total_meals_logged', 0)} meals, "
                    f"{stats.get('total_skipped', 0)} skipped, "
                    f"{stats.get('delivery_orders', 0)} delivery orders "
                    f"({', '.join(stats.get('delivery_apps_used', []))}), "
                    f"top reasons: {', '.join(stats.get('top_reasons', [])[:3])}"
                )
            user_parts.append("")

        # DScout aggregate analysis
        dscout_analysis = context.get("dscout_analysis", "")
        if dscout_analysis:
            user_parts.append("## DScout Aggregate Analysis (Pre-computed)\n")
            user_parts.append(
                "This is a structured analysis of all 315 meal slots across "
                "15 diary participants. Use it as evidence for cross-cutting patterns.\n"
            )
            # Include a truncated version to stay within context limits
            user_parts.append(dscout_analysis[:12000])
            if len(dscout_analysis) > 12000:
                user_parts.append("\n[... analysis truncated for context limits ...]\n")
            user_parts.append("")

        user_parts.append(
            "\nPerform segment comparison, pattern detection, and say-do gap analysis. "
            "Return your findings as a JSON object with: segment_comparisons, patterns, "
            "say_do_gaps, and summary."
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
        for key in ("segment_comparisons", "patterns", "say_do_gaps"):
            if key not in data:
                logger.warning("triangulation: missing expected key '%s', adding empty list", key)
                data[key] = []
            elif not isinstance(data[key], list):
                data[key] = []
        if "summary" not in data:
            data["summary"] = ""
        return data

    def _save_output(self, data: dict[str, Any] | list[Any]) -> None:
        TRIANG_DIR.mkdir(parents=True, exist_ok=True)
        with open(TRIANG_DIR / "triangulated_results.json", "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info("Saved triangulated results")


def load_triangulated() -> dict[str, Any] | None:
    path = TRIANG_DIR / "triangulated_results.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)
