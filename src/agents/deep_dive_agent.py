"""
Deep Dive Agent -- Guided Second-Pass Analysis.

Enables focused re-analysis of specific themes, participants, or
questions after reviewing QA and Devil's Advocate reports. The
researcher specifies what to explore deeper.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from config.settings import PROCESSED_DIR
from src.agents.base_agent import AgentOutput, BaseAgent

logger = logging.getLogger(__name__)

DEEP_DIVE_DIR = PROCESSED_DIR / "deep_dive"


class DeepDiveAgent(BaseAgent):
    """Guided second-pass analysis on specified areas."""

    agent_name = "deep_dive"
    prompt_file = "analysis_agent.md"  # Reuses analysis prompt with additional focus

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.max_tokens = max(self.max_tokens, 8192)

    def run(self, participant_id: str = "", context: dict[str, Any] | None = None) -> AgentOutput:
        context = context or {}
        dive_id = context.get("dive_id", "DD_001")
        output = super().run(dive_id, context)
        if output.success and output.data:
            self._save_output(dive_id, output.data)
        return output

    def _build_messages(
        self, participant_id: str, context: dict[str, Any]
    ) -> list[dict[str, str]]:
        system = self._load_system_prompt()
        user_parts = ["# Deep Dive Re-Analysis\n"]

        # Deep dive specification
        focus = context.get("focus_area", "")
        questions = context.get("specific_questions", [])
        participants = context.get("participants_to_revisit", [])
        themes = context.get("themes_to_explore", [])
        hypothesis = context.get("alternative_hypothesis", {})

        user_parts.append(f"## Focus Area: {focus}\n")

        if questions:
            user_parts.append("## Specific Questions\n")
            for q in questions:
                user_parts.append(f"- {q}")
            user_parts.append("")

        if themes:
            user_parts.append("## Themes to Explore\n")
            for t in themes:
                user_parts.append(f"- {t}")
            user_parts.append("")

        if hypothesis:
            user_parts.append("## Hypothesis Testing\n")
            user_parts.append(f"**Current assumption:** {hypothesis.get('current', '')}")
            user_parts.append(f"**Alternative to test:** {hypothesis.get('alternative', '')}")
            user_parts.append("")

        # Relevant transcripts
        transcripts = context.get("transcripts", {})
        if transcripts:
            user_parts.append(f"## Transcripts for Re-Analysis ({len(transcripts)} participants)\n")
            for pid, text in transcripts.items():
                user_parts.append(f"### {pid}\n")
                user_parts.append(text[:5000] if isinstance(text, str) else json.dumps(text, default=str)[:5000])
                user_parts.append("")

        # Prior coded data for these participants
        prior_coded = context.get("prior_coded_segments", {})
        if prior_coded:
            user_parts.append("## Prior Coding for These Participants\n")
            for pid, data in prior_coded.items():
                segments = data.get("coded_segments", []) if isinstance(data, dict) else []
                user_parts.append(f"### {pid}: {len(segments)} existing segments")
                user_parts.append("")

        user_parts.append(
            "\nRe-analyse these transcripts with the deep dive focus. Return JSON with: "
            "deep_dive_id, focus, findings (hypothesis_tested, verdict, evidence, "
            "new_insight, recommendation_update)."
        )

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": "\n".join(user_parts)})
        return messages

    def _save_output(self, dive_id: str, data: dict[str, Any] | list[Any]) -> None:
        DEEP_DIVE_DIR.mkdir(parents=True, exist_ok=True)
        with open(DEEP_DIVE_DIR / f"{dive_id.lower()}_results.json", "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info("Saved deep dive results for %s", dive_id)
