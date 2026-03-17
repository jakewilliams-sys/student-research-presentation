"""
Analysis Agent (Agent 1) -- Deep Coding Engine.

Performs systematic 4-pass coding of interview transcripts:
  Pass 1: Research objective coding
  Pass 2: Context enrichment (emotion, social, temporal, platform)
  Pass 3: Emergent theme detection (tensions, language, competitive, value)
  Pass 4: Quote quality scoring

Operates on one participant at a time, informed by the participant
summary from Agent 0 and the current codebook.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import yaml

from config.settings import CONFIG_DIR, PROCESSED_DIR
from src.agents.base_agent import AgentOutput, BaseAgent
from src.storage.codebook import Codebook
from src.utils.quote_verifier import verify_quotes

logger = logging.getLogger(__name__)

CODED_DIR = PROCESSED_DIR / "coded_segments"


class AnalysisAgent(BaseAgent):
    """4-pass deep coding engine with quote quality scoring."""

    agent_name = "analysis"
    prompt_file = "analysis_agent.md"
    use_citations = True

    def __init__(self, codebook: Codebook | None = None, **kwargs: Any):
        super().__init__(**kwargs)
        self.codebook = codebook or Codebook()
        self.max_tokens = max(self.max_tokens, 64000)
        self._last_transcript: str = ""

    def run(self, participant_id: str, context: dict[str, Any]) -> AgentOutput:
        self._last_transcript = context.get("transcript", "")
        output = super().run(participant_id, context)
        if output.success and output.data:
            self._save_coded(participant_id, output.data)
            self._update_codebook(output.data)
        return output

    def _build_messages(
        self, participant_id: str, context: dict[str, Any]
    ) -> list[dict[str, str]]:
        system = self._load_system_prompt()

        user_parts = [f"# Coding Task for Participant {participant_id}\n"]

        # Participant summary from Agent 0
        summary = context.get("participant_summary", {})
        if summary:
            user_parts.append("## Participant Summary (from Summary Agent)\n")
            if isinstance(summary, dict):
                user_parts.append(f"**Summary:** {summary.get('summary', '')}\n")
                user_parts.append(f"**Food relationship:** {summary.get('food_relationship', '')}\n")
                hypotheses = summary.get("initial_hypotheses", [])
                if hypotheses:
                    user_parts.append("**Hypotheses to explore:**")
                    for h in hypotheses:
                        user_parts.append(f"- {h}")
                questions = summary.get("questions_for_coding", [])
                if questions:
                    user_parts.append("\n**Questions for coding:**")
                    for q in questions:
                        user_parts.append(f"- {q}")
            else:
                user_parts.append(json.dumps(summary, indent=2))
            user_parts.append("")

        # Research objectives
        obj_path = CONFIG_DIR / "research_objectives.yaml"
        if obj_path.exists():
            with open(obj_path) as f:
                objectives = yaml.safe_load(f)
            user_parts.append("## Research Objectives\n")
            for ro_key, ro_data in objectives.get("objectives", {}).items():
                user_parts.append(f"### {ro_key}: {ro_data.get('name', '')}")
                user_parts.append(f"Question: {ro_data.get('question', '')}")
                for sq in ro_data.get("sub_questions", []):
                    user_parts.append(f"  - {sq}")
                user_parts.append("")

        # Current codebook
        user_parts.append(self.codebook.to_prompt_context())
        user_parts.append("")

        # Profile
        profile = context.get("profile", {})
        if profile:
            user_parts.append("## Participant Profile\n")
            for k, v in profile.items():
                if not k.startswith("_"):
                    user_parts.append(f"- **{k}**: {v}")
            user_parts.append("")

        # Transcript
        transcript = context.get("transcript", "")
        if transcript:
            user_parts.append("## Interview Transcript\n")
            user_parts.append(transcript)
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
            user_parts.append("## 7-Day Food Diary Data (DScout)\n")
            user_parts.append(
                "This participant completed a 7-day food diary. Code the diary "
                "open-text responses and video reflections alongside the interview transcript. "
                "Use `source: \"diary\"` for meal-level responses and "
                "`source: \"diary_reflection\"` for daily video reflections.\n"
            )
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
                        user_parts.append(f'  - Why ordered: "{why}"')
                reflection = day.get("daily_reflection")
                if reflection:
                    user_parts.append(f"- **Daily reflection (video transcription):**\n{reflection[:2000]}")
                user_parts.append("")

        user_parts.append(
            "\nPerform all 4 coding passes on this transcript"
            + (" and the diary data" if diary else "")
            + ". Return a JSON object with:\n"
            '- "coded_segments": array of coded segment objects\n'
            '- "emergent_themes": array of new themes to add to the codebook\n'
            '- "coding_summary": brief summary of what was found\n'
            '- "coverage_gaps": array of ROs with zero primary codes and why\n'
        )

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": "\n".join(user_parts)})
        return messages

    def _save_coded(self, participant_id: str, data: dict[str, Any] | list[Any]) -> None:
        CODED_DIR.mkdir(parents=True, exist_ok=True)
        if isinstance(data, dict):
            data = self._validate_coded_output(data, participant_id)

            # Run quote verification against transcript
            segments = data.get("coded_segments", [])
            transcript = self._last_transcript or ""
            if segments and transcript:
                DIARY_SOURCES = {"diary", "diary_reflection"}
                interview_segments = [
                    s for s in segments
                    if isinstance(s, dict)
                    and s.get("source", "interview") not in DIARY_SOURCES
                ]
                diary_segments = [
                    s for s in segments
                    if isinstance(s, dict)
                    and s.get("source", "interview") in DIARY_SOURCES
                ]
                if interview_segments:
                    verify_quotes(interview_segments, transcript)
                for s in diary_segments:
                    s["_quote_verification"] = {
                        "status": "DIARY_SOURCE",
                        "similarity": None,
                        "best_match": "(diary data — not verified against interview transcript)",
                    }
                unverified = [
                    s.get("segment_id", "?")
                    for s in interview_segments
                    if s.get("_quote_verification", {}).get("status") == "UNVERIFIED"
                ]
                if unverified:
                    logger.warning(
                        "%s: %d quote(s) could not be verified against transcript: %s",
                        participant_id, len(unverified), unverified,
                    )
                if diary_segments:
                    logger.info(
                        "%s: %d diary-sourced segment(s) skipped quote verification",
                        participant_id, len(diary_segments),
                    )

        out_path = CODED_DIR / f"{participant_id.lower()}_coded.json"
        with open(out_path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        cit_count = data.get("_citation_count", 0) if isinstance(data, dict) else 0
        logger.info(
            "Saved coded segments for %s -> %s (%d citations)",
            participant_id, out_path.name, cit_count,
        )

    def _validate_coded_output(self, data: dict[str, Any], participant_id: str) -> dict[str, Any]:
        """Validate and auto-correct analysis output before saving."""
        segments = data.get("coded_segments", [])
        actual_count = len(segments)

        # Auto-correct coding_summary to match actual segment count
        summary = data.get("coding_summary", "")
        if summary:
            corrected = re.sub(
                r"(\d+)\s+segments?\s+were\s+coded",
                f"{actual_count} segments were coded",
                summary,
            )
            if corrected != summary:
                logger.warning(
                    "%s: corrected segment count in coding_summary (was mismatched, now %d)",
                    participant_id, actual_count,
                )
            data["coding_summary"] = corrected

        # Validate each segment has required fields
        required_fields = {"segment_id", "text", "research_objective_codes"}
        for i, seg in enumerate(segments):
            if not isinstance(seg, dict):
                logger.warning("%s: segment %d is not a dict, skipping validation", participant_id, i)
                continue
            missing = required_fields - seg.keys()
            if missing:
                logger.warning(
                    "%s: segment %s missing fields: %s",
                    participant_id, seg.get("segment_id", f"index_{i}"), missing,
                )

            # Clamp quote quality scores to 1-5
            qq = seg.get("quote_quality", {})
            if isinstance(qq, dict):
                for dim in ("clarity", "vividness", "representativeness", "emotional_resonance", "uniqueness"):
                    val = qq.get(dim)
                    if isinstance(val, (int, float)):
                        qq[dim] = max(1, min(5, val))

        # Ensure emergent_themes is a list
        if "emergent_themes" not in data:
            data["emergent_themes"] = []
        elif not isinstance(data["emergent_themes"], list):
            data["emergent_themes"] = []

        # Add participant_id if missing
        data.setdefault("participant_id", participant_id)

        # Build RO coverage summary
        ro_hits: dict[str, int] = {}
        for seg in segments:
            if not isinstance(seg, dict):
                continue
            for code in seg.get("research_objective_codes", []):
                ro = code.split(".")[0] if "." in code else code.split("_")[0]
                ro_hits[ro] = ro_hits.get(ro, 0) + 1
        data["_ro_coverage"] = ro_hits

        return data

    def _update_codebook(self, data: dict[str, Any] | list[Any]) -> None:
        """Merge emergent themes from this analysis into the codebook."""
        if not isinstance(data, dict):
            return

        emergent = data.get("emergent_themes", [])
        if not emergent:
            return

        for theme in emergent:
            if isinstance(theme, dict):
                code = theme.get("code", theme.get("theme", ""))
                label = theme.get("label", theme.get("description", code))
                if code:
                    self.codebook.add_emergent_theme(
                        code=code,
                        label=label,
                        description=theme.get("description", ""),
                        discovered_by=self.agent_name,
                        participant_id=theme.get("participant_id", ""),
                    )

        # Update segment counts
        segments = data.get("coded_segments", [])
        for seg in segments:
            if not isinstance(seg, dict):
                continue
            for code in seg.get("research_objective_codes", []):
                self.codebook.increment_count(code)

        self.codebook.save()


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------

def load_coded_segments(participant_id: str) -> dict[str, Any] | None:
    """Load previously coded segments for a participant."""
    path = CODED_DIR / f"{participant_id.lower()}_coded.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)
