"""
Participant Summary Agent (Agent 0).

Reads the full interview transcript, participant profile, and researcher
notes to build a holistic understanding of each participant before
detailed coding begins. This ensures we don't lose the "whole person"
by diving straight into segment-level analysis.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from config.settings import PROCESSED_DIR
from src.agents.base_agent import AgentOutput, BaseAgent

logger = logging.getLogger(__name__)

SUMMARIES_DIR = PROCESSED_DIR / "participant_summaries"


class SummaryAgent(BaseAgent):
    """Builds holistic participant summaries before coding."""

    agent_name = "summary"
    prompt_file = "participant_summary.md"
    use_citations = True

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        # Summaries need more output space for rich narrative
        self.max_tokens = max(self.max_tokens, 4096)

    def run(self, participant_id: str, context: dict[str, Any]) -> AgentOutput:
        output = super().run(participant_id, context)
        if output.success and output.data:
            self._save_summary(participant_id, output.data)
        return output

    def _build_messages(
        self, participant_id: str, context: dict[str, Any]
    ) -> list[dict[str, str]]:
        system = self._load_system_prompt()

        user_parts = [f"# Participant {participant_id}\n"]

        # Profile
        profile = context.get("profile", {})
        if profile:
            user_parts.append("## Participant Profile\n")
            for k, v in profile.items():
                if k.startswith("_"):
                    continue
                user_parts.append(f"- **{k}**: {v}")
            user_parts.append("")

        # Interview metadata
        interview_type = context.get("interview_type", "online")
        user_parts.append(f"## Interview Type: {interview_type}\n")
        if interview_type == "in_home":
            user_parts.append(
                "NOTE: This was an in-home interview that included a live "
                "order observation. Pay special attention to observed vs stated behaviour.\n"
            )

        # Transcript
        transcript = context.get("transcript", "")
        if transcript:
            user_parts.append("## Full Interview Transcript\n")
            user_parts.append(transcript)
            user_parts.append("")

        # Marvin AI summary (supplementary context)
        marvin_summary = context.get("marvin_summary", "")
        if marvin_summary:
            user_parts.append("## AI-Generated Interview Summary (from Marvin)\n")
            user_parts.append(marvin_summary)
            user_parts.append("")

        # Researcher notes
        notes = context.get("researcher_notes", "")
        if notes:
            user_parts.append("## Researcher Notes\n")
            user_parts.append(notes)
            user_parts.append("")

        # Diary study data (7-day DScout food diary)
        diary = context.get("diary_data")
        if diary and isinstance(diary, dict):
            user_parts.append("## 7-Day Food Diary (DScout Study)\n")
            user_parts.append(
                f"This participant completed a 7-day diary study. "
                f"Scout name: {diary.get('scout_name', 'N/A')}, "
                f"Segment: {diary.get('segment', 'N/A')}.\n"
            )
            stats = diary.get("summary_stats", {})
            if stats:
                user_parts.append("### Diary Summary Statistics")
                user_parts.append(f"- Meals logged: {stats.get('total_meals_logged', 0)}")
                user_parts.append(f"- Meals skipped: {stats.get('total_skipped', 0)}")
                user_parts.append(f"- Delivery orders: {stats.get('delivery_orders', 0)}")
                user_parts.append(f"- Delivery apps used: {', '.join(stats.get('delivery_apps_used', []))}")
                user_parts.append(f"- Most common source: {stats.get('most_common_source', 'N/A')}")
                user_parts.append(f"- Top reasons: {', '.join(stats.get('top_reasons', []))}")
                user_parts.append("")

            for day in diary.get("days", []):
                user_parts.append(f"### Day {day.get('day', '?')} ({day.get('date', 'N/A')})")
                for meal_key in ("breakfast", "lunch", "dinner"):
                    meal = day.get(meal_key, {})
                    if not meal:
                        continue
                    src = meal.get("source", "N/A")
                    app = meal.get("delivery_app")
                    why = meal.get("why_ordered")
                    reasons = ", ".join(meal.get("reasons", []))
                    social = ", ".join(meal.get("ate_with", []))
                    line = f"- **{meal_key.title()}**: {src}"
                    if app:
                        line += f" (via {app})"
                    if reasons:
                        line += f" | Reasons: {reasons}"
                    if social:
                        line += f" | With: {social}"
                    user_parts.append(line)
                    if why:
                        user_parts.append(f'  - Why: "{why}"')
                reflection = day.get("daily_reflection")
                if reflection:
                    user_parts.append(f"- **Daily reflection**: {reflection[:1500]}")
                user_parts.append("")

        user_parts.append(
            "\nAnalyse this participant holistically and return your summary "
            "as a JSON object following the format specified in your system prompt."
        )

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": "\n".join(user_parts)})
        return messages

    def _save_summary(self, participant_id: str, data: dict[str, Any] | list[Any]) -> None:
        SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)
        out_path = SUMMARIES_DIR / f"{participant_id.lower()}_summary.json"
        if isinstance(data, dict):
            data["participant_id"] = participant_id
        with open(out_path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info("Saved summary for %s -> %s", participant_id, out_path.name)


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------

def load_summary(participant_id: str) -> dict[str, Any] | None:
    """Load a previously generated participant summary."""
    path = SUMMARIES_DIR / f"{participant_id.lower()}_summary.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)
