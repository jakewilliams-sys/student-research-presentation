"""
Persona Agent (Agent 3) -- Synthesis Engine.

Clusters participants into behavioural archetypes and creates
journey maps for each persona. Operates on the full triangulated
dataset.
"""

from __future__ import annotations

import json
import logging
from difflib import SequenceMatcher
from typing import Any

from config.settings import PROCESSED_DIR
from src.agents.base_agent import AgentOutput, BaseAgent

logger = logging.getLogger(__name__)

PERSONA_DIR = PROCESSED_DIR / "personas"


class PersonaAgent(BaseAgent):
    """Synthesises behavioural personas and journey maps."""

    agent_name = "persona"
    prompt_file = "persona_agent.md"

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.max_tokens = max(self.max_tokens, 8192)

    def run(self, participant_id: str = "", context: dict[str, Any] | None = None) -> AgentOutput:
        context = context or {}
        self._verified_quotes = context.get("verified_quotes", {})
        output = super().run("all", context)
        if output.success and output.data:
            self._flag_unverified_quotes(output.data)
            self._save_output(output.data)
        return output

    def _flag_unverified_quotes(self, data: dict[str, Any]) -> None:
        """Flag persona evidence quotes that don't match verified sources."""
        if not self._verified_quotes:
            return
        all_verified = []
        for quotes in self._verified_quotes.values():
            all_verified.extend(q.get("quote", "") for q in quotes)
        for persona in data.get("personas", []):
            if not isinstance(persona, dict):
                continue
            for ev in persona.get("evidence", []):
                if not isinstance(ev, dict):
                    continue
                quote = ev.get("quote", "")
                if not quote:
                    continue
                best = max(
                    (SequenceMatcher(None, quote.lower(), v.lower()).ratio() for v in all_verified),
                    default=0.0,
                )
                if best < 0.5:
                    ev["_unverified_persona_quote"] = True
                    logger.warning("Unverified persona quote (sim=%.2f): %s...", best, quote[:60])

    def _build_messages(
        self, participant_id: str, context: dict[str, Any]
    ) -> list[dict[str, str]]:
        system = self._load_system_prompt()
        user_parts = ["# Persona Synthesis Task\n"]

        # Triangulated data
        triang = context.get("triangulated_data", {})
        if triang:
            user_parts.append("## Triangulated Findings\n")
            if isinstance(triang, dict):
                summary = triang.get("summary", "")
                if summary:
                    user_parts.append(f"{summary}\n")
                patterns = triang.get("patterns", [])
                if patterns:
                    user_parts.append("### Key Patterns\n")
                    for p in patterns[:20]:
                        if isinstance(p, dict):
                            user_parts.append(f"- **{p.get('pattern_type', '')}**: {p.get('pattern', '')}")
                    user_parts.append("")
            else:
                user_parts.append(f"```json\n{json.dumps(triang, indent=2, default=str)[:3000]}\n```\n")

        # All participant profiles
        profiles = context.get("participant_profiles", {})
        if profiles:
            user_parts.append("## All Participant Profiles\n")
            for pid, prof in profiles.items():
                if isinstance(prof, dict) and not pid.startswith("_"):
                    seg = prof.get("segment", "")
                    name = prof.get("name", "")
                    freq = prof.get("order_frequency", prof.get("delivery_frequency", ""))
                    sub = prof.get("current_subscription", "")
                    user_parts.append(f"- **{pid}** {name}: {seg}, orders {freq}, subscription: {sub}")
            user_parts.append("")

        # All coded segments summary (key themes per participant)
        all_coded = context.get("all_coded_segments", {})
        if all_coded:
            user_parts.append("## Coding Summary per Participant\n")
            for pid, data in all_coded.items():
                segments = data.get("coded_segments", []) if isinstance(data, dict) else data if isinstance(data, list) else []
                codes = set()
                for seg in segments:
                    if isinstance(seg, dict):
                        for c in seg.get("research_objective_codes", []):
                            codes.add(c.split(".")[0] if "." in c else c)
                user_parts.append(f"- **{pid}**: {len(segments)} segments, themes: {', '.join(sorted(codes))}")
            user_parts.append("")

        # Participant summaries
        summaries = context.get("participant_summaries", {})
        if summaries:
            user_parts.append("## Participant Summaries\n")
            for pid, s in summaries.items():
                if isinstance(s, dict):
                    user_parts.append(f"### {pid}")
                    user_parts.append(s.get("summary", "")[:500])
                    user_parts.append("")

        # Diary study behavioural summary (for participants with diary data)
        diary_data = context.get("diary_data", {})
        if diary_data:
            user_parts.append(f"## Diary Study Behaviour ({len(diary_data)} participants)\n")
            user_parts.append(
                "These participants completed a 7-day food diary. "
                "Use their observed behaviour to inform persona clustering.\n"
            )
            for pid, diary in diary_data.items():
                if not isinstance(diary, dict):
                    continue
                stats = diary.get("summary_stats", {})
                user_parts.append(
                    f"- **{pid}**: {stats.get('delivery_orders', 0)} delivery orders, "
                    f"most common source: {stats.get('most_common_source', 'N/A')}, "
                    f"top reasons: {', '.join(stats.get('top_reasons', [])[:3])}"
                )
            user_parts.append("")

        # Verified quotes for evidence grounding
        verified_quotes = context.get("verified_quotes", {})
        if verified_quotes:
            user_parts.append("## Verified Participant Quotes\n")
            user_parts.append("Use ONLY these quotes in persona evidence. Do NOT fabricate quotes.\n")
            for pid, quotes in verified_quotes.items():
                if quotes:
                    user_parts.append(f"### {pid}")
                    for q in quotes:
                        user_parts.append(f'- "{q.get("quote", "")}" (context: {q.get("context", "")})')
                    user_parts.append("")

        user_parts.append(
            "\nCluster participants into 4-6 behavioural personas. For each, provide "
            "journey maps with emotional states. Return JSON with: personas, journey_maps, "
            "participant_assignments."
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
        if "personas" not in data:
            logger.warning("persona: missing 'personas' key, wrapping data")
            if isinstance(data, list):
                data = {"personas": data}
            else:
                data["personas"] = []
        elif not isinstance(data["personas"], list):
            data["personas"] = []

        # Flatten participant_assignments so each PID maps to exactly one persona
        assignments = data.get("participant_assignments", {})
        for pid, assigned in list(assignments.items()):
            if isinstance(assigned, list):
                assignments[pid] = assigned[0]
                logger.warning(
                    "persona: P%s assigned to multiple personas %s — keeping first (%s)",
                    pid, assigned, assigned[0],
                )
        data["participant_assignments"] = assignments

        pid_by_persona: dict[str, list[str]] = {}
        for pid, persona_id in assignments.items():
            pid_by_persona.setdefault(persona_id, []).append(pid)

        for persona in data["personas"]:
            if not isinstance(persona, dict):
                continue
            persona.setdefault("persona_id", "UNKNOWN")
            persona.setdefault("name", "Unnamed Persona")

            pid_key = persona["persona_id"]
            assigned_pids = sorted(pid_by_persona.get(pid_key, []))

            if not persona.get("representative_participants") and assigned_pids:
                persona["representative_participants"] = assigned_pids
                logger.info(
                    "persona %s: populated representative_participants from assignments (%d)",
                    pid_key, len(assigned_pids),
                )

            if assigned_pids:
                actual_size = len(assigned_pids)
                claimed_size = persona.get("size", 0)
                if claimed_size != actual_size:
                    logger.warning(
                        "persona %s: correcting size from %s to %d (based on assignments)",
                        pid_key, claimed_size, actual_size,
                    )
                    persona["size"] = actual_size

        return data

    def _save_output(self, data: dict[str, Any] | list[Any]) -> None:
        PERSONA_DIR.mkdir(parents=True, exist_ok=True)
        with open(PERSONA_DIR / "personas.json", "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info("Saved persona results")


def load_personas() -> dict[str, Any] | None:
    path = PERSONA_DIR / "personas.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)
