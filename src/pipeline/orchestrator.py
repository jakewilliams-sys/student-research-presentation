"""
Pipeline orchestrator for the multi-agent research analysis system.

Coordinates agent execution in the correct sequence, manages state
persistence, and supports both full-pipeline and single-agent modes.
Human-in-the-loop checkpoints pause execution for researcher review.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from config.settings import (
    AGENT_NAMES,
    CONFIG_DIR,
    HUMAN_CHECKPOINTS,
    PROCESSED_DIR,
    REFERENCE_DIR,
)
from src.agents.advocate_agent import AdvocateAgent
from src.agents.analysis_agent import AnalysisAgent, load_coded_segments
from src.agents.base_agent import AgentOutput
from src.agents.deep_dive_agent import DeepDiveAgent
from src.agents.insight_agent import InsightAgent, load_insights
from src.agents.persona_agent import PersonaAgent, load_personas
from src.agents.quality_agent import QualityAgent, load_qa_results
from src.agents.summary_agent import SummaryAgent, load_summary
from src.loaders.gworkspace_loader import load_moderator_summary
from src.agents.triangulation_agent import TriangulationAgent, load_triangulated
from src.storage.codebook import Codebook
from src.storage.state_manager import StateManager

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    """
    Runs the full analysis pipeline or individual agents.

    Supports:
    - Full pipeline: ingest -> summary -> analysis -> ... -> advocate
    - Single agent: run one agent for specified participants
    - Resume: pick up from where the pipeline last stopped
    - Human checkpoints: pause after coding, personas, and QA
    """

    def __init__(self):
        self.state = StateManager()
        self.codebook = Codebook()
        self._participant_map: dict[str, Any] | None = None

    @property
    def participant_map(self) -> dict[str, Any]:
        if self._participant_map is None:
            path = REFERENCE_DIR / "participant_map.json"
            with open(path) as f:
                self._participant_map = json.load(f)
        return self._participant_map

    # ------------------------------------------------------------------
    # Full pipeline
    # ------------------------------------------------------------------

    def run_full(
        self,
        participant_ids: list[str] | None = None,
        skip_checkpoints: bool = False,
    ) -> dict[str, Any]:
        """
        Run the complete pipeline for the specified participants.

        Returns a summary of what was completed.
        """
        pids = participant_ids or self._get_all_participant_ids()
        results: dict[str, Any] = {"participants": pids, "agents": {}}

        # Register participants
        for pid in pids:
            self.state.register_participant(pid)

        # Phase 1: Per-participant agents (summary, analysis)
        for agent_name in ["summary", "analysis"]:
            agent_results = self.run_agent(agent_name, pids)
            results["agents"][agent_name] = agent_results

            if agent_name in HUMAN_CHECKPOINTS and not skip_checkpoints:
                logger.info(
                    "HUMAN CHECKPOINT after '%s': %s",
                    agent_name, HUMAN_CHECKPOINTS[agent_name],
                )
                results["checkpoint_reached"] = agent_name
                return results

        # Phase 2: Cross-participant agents
        for agent_name in ["triangulation", "persona"]:
            agent_results = self._run_cross_participant_agent(agent_name, pids)
            results["agents"][agent_name] = agent_results

            if agent_name in HUMAN_CHECKPOINTS and not skip_checkpoints:
                logger.info(
                    "HUMAN CHECKPOINT after '%s': %s",
                    agent_name, HUMAN_CHECKPOINTS[agent_name],
                )
                results["checkpoint_reached"] = agent_name
                return results

        # Phase 3: Insight + QA + Advocate
        for agent_name in ["insight", "quality", "advocate"]:
            agent_results = self._run_cross_participant_agent(agent_name, pids)
            results["agents"][agent_name] = agent_results

            if agent_name in HUMAN_CHECKPOINTS and not skip_checkpoints:
                logger.info(
                    "HUMAN CHECKPOINT after '%s': %s",
                    agent_name, HUMAN_CHECKPOINTS[agent_name],
                )
                results["checkpoint_reached"] = agent_name
                return results

        results["status"] = "completed"
        return results

    # ------------------------------------------------------------------
    # Single agent
    # ------------------------------------------------------------------

    def run_agent(
        self, agent_name: str, participant_ids: list[str] | None = None
    ) -> dict[str, Any]:
        """Run a single agent for specified participants."""
        pids = participant_ids or self._get_all_participant_ids()

        if agent_name in ("summary", "analysis"):
            return self._run_per_participant_agent(agent_name, pids)
        else:
            return self._run_cross_participant_agent(agent_name, pids)

    def _run_per_participant_agent(
        self, agent_name: str, pids: list[str]
    ) -> dict[str, Any]:
        """Run an agent that processes one participant at a time."""
        agent = self._create_agent(agent_name)
        results: dict[str, Any] = {"agent": agent_name, "participants": {}}

        for pid in pids:
            if self.state.is_complete(pid, agent_name):
                logger.info("Skipping %s for %s (already complete)", agent_name, pid)
                results["participants"][pid] = "skipped"
                continue

            self.state.mark_started(pid, agent_name)
            context = self._build_context(agent_name, pid)

            try:
                output = agent.run(pid, context)
                if output.success:
                    out_path = str(
                        PROCESSED_DIR / f"{'participant_summaries' if agent_name == 'summary' else 'coded_segments'}"
                        / f"{pid.lower()}_{'summary' if agent_name == 'summary' else 'coded'}.json"
                    )
                    self.state.mark_completed(pid, agent_name, out_path)
                    results["participants"][pid] = "completed"
                else:
                    self.state.mark_failed(pid, agent_name, output.error)
                    results["participants"][pid] = f"failed: {output.error}"
            except Exception as e:
                self.state.mark_failed(pid, agent_name, str(e))
                results["participants"][pid] = f"error: {e}"
                logger.exception("Agent %s failed for %s", agent_name, pid)

        return results

    def _run_cross_participant_agent(
        self, agent_name: str, pids: list[str]
    ) -> dict[str, Any]:
        """Run an agent that processes all participants at once."""
        agent = self._create_agent(agent_name)
        context = self._build_cross_context(agent_name, pids)

        try:
            output = agent.run("all", context)
            if output.success:
                for pid in pids:
                    self.state.mark_completed(pid, agent_name)
                return {"agent": agent_name, "status": "completed"}
            else:
                for pid in pids:
                    self.state.mark_failed(pid, agent_name, output.error)
                return {"agent": agent_name, "status": f"failed: {output.error}"}
        except Exception as e:
            logger.exception("Cross-participant agent %s failed", agent_name)
            return {"agent": agent_name, "status": f"error: {e}"}

    # ------------------------------------------------------------------
    # Agent factory
    # ------------------------------------------------------------------

    def _create_agent(self, agent_name: str) -> Any:
        agents = {
            "summary": lambda: SummaryAgent(),
            "analysis": lambda: AnalysisAgent(codebook=self.codebook),
            "triangulation": lambda: TriangulationAgent(),
            "persona": lambda: PersonaAgent(),
            "insight": lambda: InsightAgent(),
            "quality": lambda: QualityAgent(),
            "advocate": lambda: AdvocateAgent(),
            "deep_dive": lambda: DeepDiveAgent(),
        }
        factory = agents.get(agent_name)
        if not factory:
            raise ValueError(f"Unknown agent: {agent_name}")
        return factory()

    # ------------------------------------------------------------------
    # Context building
    # ------------------------------------------------------------------

    def _build_context(self, agent_name: str, pid: str) -> dict[str, Any]:
        """Build input context for a per-participant agent."""
        context: dict[str, Any] = {}
        pdata = self.participant_map.get(pid, {})

        # Profile
        context["profile"] = pdata.get("profile", {})
        context["interview_type"] = pdata.get("interview_type", "online")

        # Transcript
        transcript = self._load_transcript(pid, pdata)
        if transcript:
            context["transcript"] = transcript

        # Marvin summary
        marvin_summary = self._load_marvin_summary(pid, pdata)
        if marvin_summary:
            context["marvin_summary"] = marvin_summary

        # Researcher notes
        notes = self._load_researcher_notes(pid)
        if notes:
            context["researcher_notes"] = notes

        # Moderator summary
        interview_type = pdata.get("interview_type", "online")
        mod_summary = load_moderator_summary(interview_type)
        if mod_summary:
            context["moderator_summary"] = mod_summary

        # Prior outputs for analysis agent
        if agent_name == "analysis":
            summary = load_summary(pid)
            if summary:
                context["participant_summary"] = summary

        # Diary study data (if participant was in the DScout study)
        diary = self._load_diary_data(pid)
        if diary:
            context["diary_data"] = diary

        return context

    def _build_cross_context(self, agent_name: str, pids: list[str]) -> dict[str, Any]:
        """Build input context for a cross-participant agent."""
        context: dict[str, Any] = {}

        # Participant profiles
        profiles: dict[str, Any] = {}
        for pid in pids:
            pdata = self.participant_map.get(pid, {})
            profiles[pid] = {
                "name": pdata.get("name", ""),
                "segment": pdata.get("segment", ""),
                **pdata.get("profile", {}),
            }
        context["participant_profiles"] = profiles

        # All coded segments
        all_coded: dict[str, Any] = {}
        for pid in pids:
            coded = load_coded_segments(pid)
            if coded:
                all_coded[pid] = coded
        context["all_coded_segments"] = all_coded

        # Participant summaries
        all_summaries: dict[str, Any] = {}
        for pid in pids:
            s = load_summary(pid)
            if s:
                all_summaries[pid] = s
        context["participant_summaries"] = all_summaries

        # Diary study data for all participants who have it
        all_diary: dict[str, Any] = {}
        for pid in pids:
            diary = self._load_diary_data(pid)
            if diary:
                all_diary[pid] = diary
        if all_diary:
            context["diary_data"] = all_diary

        # DScout aggregate analysis (pre-computed patterns)
        dscout_analysis = self._load_dscout_analysis()
        if dscout_analysis:
            context["dscout_analysis"] = dscout_analysis

        # Prior cross-participant outputs
        if agent_name in ("persona", "insight", "quality", "advocate"):
            triang = load_triangulated()
            if triang:
                context["triangulated_data"] = triang

        if agent_name == "persona":
            verified_quotes = self._collect_verified_quotes(pids)
            if verified_quotes:
                context["verified_quotes"] = verified_quotes

        if agent_name in ("insight", "quality", "advocate"):
            personas = load_personas()
            if personas:
                context["personas"] = personas

        if agent_name in ("quality", "advocate"):
            insights = load_insights()
            if insights:
                context["insights"] = insights

        if agent_name == "advocate":
            qa = load_qa_results()
            if qa:
                context["qa_results"] = qa

        return context

    # ------------------------------------------------------------------
    # Data loading helpers
    # ------------------------------------------------------------------

    def _collect_verified_quotes(self, pids: list[str]) -> dict[str, list[dict[str, str]]]:
        """Gather top verified quotes per participant from coded segments."""
        result: dict[str, list[dict[str, str]]] = {}
        for pid in pids:
            coded = load_coded_segments(pid)
            if not coded:
                continue
            segments = coded.get("coded_segments", []) if isinstance(coded, dict) else coded if isinstance(coded, list) else []
            verified: list[dict[str, str]] = []
            for seg in segments:
                if not isinstance(seg, dict):
                    continue
                verification = seg.get("_quote_verification", {})
                status = verification.get("status", "")
                if status in ("VERIFIED", "PARAPHRASED"):
                    text = seg.get("text", "")
                    if text and len(text) > 15:
                        verified.append({
                            "quote": text,
                            "context": seg.get("research_objective_codes", [""])[0] if seg.get("research_objective_codes") else "",
                            "status": status,
                        })
            verified.sort(key=lambda q: len(q["quote"]), reverse=True)
            result[pid] = verified[:5]
        return result

    def _load_transcript(self, pid: str, pdata: dict[str, Any]) -> str | None:
        """Load transcript text for a participant.

        Searches multiple locations for the file_id, then falls back
        to a name-based search of the transcripts directory.
        """
        cache_dir = PROCESSED_DIR / "transcripts"

        # Collect candidate file_ids from all known locations
        file_ids: list[str] = []
        interview = pdata.get("sources", {}).get("interview", {})
        if isinstance(interview, dict):
            fid = interview.get("file_id")
            if fid:
                file_ids.append(str(fid))
        top_fid = pdata.get("file_id")
        if top_fid:
            file_ids.append(str(top_fid))
        transcript_src = pdata.get("sources", {}).get("transcript", {})
        if isinstance(transcript_src, dict):
            marvin_fid = transcript_src.get("marvin_file_id")
            if marvin_fid:
                file_ids.append(str(marvin_fid))

        for fid in file_ids:
            for path in cache_dir.glob(f"{fid}_*"):
                with open(path) as f:
                    data = json.load(f)
                text = data.get("transcript_text", "")
                if text:
                    return text

        # Fallback: search by participant name
        name = pdata.get("name")
        if name:
            first_name = name.split()[0].lower()
            for path in sorted(cache_dir.glob("*.json")):
                if first_name in path.name.lower():
                    with open(path) as f:
                        data = json.load(f)
                    text = data.get("transcript_text", "")
                    if text:
                        return text

        return None

    def _load_marvin_summary(self, pid: str, pdata: dict[str, Any]) -> str | None:
        """Load Marvin AI summary for a participant."""
        interview = pdata.get("sources", {}).get("interview", {})
        if isinstance(interview, dict) and interview.get("source") == "marvin":
            file_id = interview.get("file_id")
            if file_id:
                cache_dir = PROCESSED_DIR / "marvin_summaries"
                for path in cache_dir.glob(f"{file_id}_*"):
                    with open(path) as f:
                        data = json.load(f)
                    return data.get("summary", "")
        return None

    def _load_diary_data(self, pid: str) -> dict[str, Any] | None:
        """Load structured DScout diary data for a participant."""
        diary_path = PROCESSED_DIR / "diary_entries" / f"{pid.lower()}_diary.json"
        if not diary_path.exists():
            return None
        with open(diary_path) as f:
            return json.load(f)

    def _load_dscout_analysis(self) -> str | None:
        """Load the pre-computed DScout aggregate analysis document."""
        path = REFERENCE_DIR / "dscout_raw_analysis.txt"
        if not path.exists():
            return None
        text = path.read_text().strip()
        return text or None

    def _load_researcher_notes(self, pid: str) -> str | None:
        """Load cached researcher notes for a participant."""
        notes_dir = PROCESSED_DIR / "researcher_notes"
        if not notes_dir.exists():
            return None
        for path in notes_dir.glob(f"{pid.lower()}_*"):
            return path.read_text()
        return None

    def _get_all_participant_ids(self) -> list[str]:
        """Get all participant IDs from the participant map."""
        return [
            k for k in self.participant_map
            if not k.startswith("_")
        ]

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self) -> dict[str, Any]:
        """Get current pipeline progress summary."""
        return self.state.get_pipeline_summary()

    def approve_checkpoint(self, agent_name: str, notes: str = "") -> None:
        """Approve a human checkpoint to allow pipeline to continue."""
        self.state.mark_checkpoint(agent_name, approved=True, notes=notes)
        logger.info("Checkpoint '%s' approved", agent_name)

    def resume(self, participant_ids: list[str] | None = None) -> dict[str, Any]:
        """Resume the pipeline from where it left off."""
        return self.run_full(participant_ids, skip_checkpoints=False)
