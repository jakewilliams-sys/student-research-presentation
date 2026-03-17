"""
Pipeline state manager for tracking analysis progress.

Persists which participants have completed which agent phases,
enabling resume-from-failure and incremental analysis.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import AGENT_NAMES, PROCESSED_DIR

logger = logging.getLogger(__name__)

STATE_PATH = PROCESSED_DIR / "pipeline_state.json"


class StateManager:
    """Tracks pipeline progress per participant."""

    def __init__(self, path: Path | None = None):
        self._path = path or STATE_PATH
        self._state: dict[str, Any] = self._load_or_init()

    def _load_or_init(self) -> dict[str, Any]:
        if self._path.exists():
            with open(self._path) as f:
                return json.load(f)
        return {
            "_metadata": {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "last_updated": None,
                "agent_names": AGENT_NAMES,
            },
            "participants": {},
        }

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_status(self, participant_id: str) -> dict[str, Any]:
        """Get the current pipeline status for a participant."""
        return self._state["participants"].get(participant_id, {})

    def is_complete(self, participant_id: str, agent_name: str) -> bool:
        """Check if a specific agent has completed for a participant."""
        status = self.get_status(participant_id)
        return status.get(agent_name, {}).get("status") == "completed"

    def get_pending_participants(self, agent_name: str) -> list[str]:
        """List participants that have not completed a given agent."""
        pending = []
        for pid, status in self._state["participants"].items():
            if status.get(agent_name, {}).get("status") != "completed":
                pending.append(pid)
        return pending

    def get_completed_participants(self, agent_name: str) -> list[str]:
        """List participants that have completed a given agent."""
        return [
            pid for pid, status in self._state["participants"].items()
            if status.get(agent_name, {}).get("status") == "completed"
        ]

    def get_next_agent(self, participant_id: str) -> str | None:
        """Determine the next agent to run for a participant."""
        status = self.get_status(participant_id)
        for agent in AGENT_NAMES:
            if status.get(agent, {}).get("status") != "completed":
                return agent
        return None

    def get_pipeline_summary(self) -> dict[str, Any]:
        """Summary of pipeline progress across all participants."""
        summary: dict[str, Any] = {
            "total_participants": len(self._state["participants"]),
            "agents": {},
        }

        cross = self._state.get("cross_participant", {})

        for agent in AGENT_NAMES:
            if agent in cross and cross[agent].get("status") == "completed":
                summary["agents"][agent] = {
                    "completed": summary["total_participants"],
                    "pending": 0,
                    "scope": "cross_participant",
                }
            else:
                completed = len(self.get_completed_participants(agent))
                summary["agents"][agent] = {
                    "completed": completed,
                    "pending": summary["total_participants"] - completed,
                }
        return summary

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def register_participant(self, participant_id: str) -> None:
        """Add a participant to the state tracker if not already present."""
        if participant_id not in self._state["participants"]:
            self._state["participants"][participant_id] = {}
            self._save()

    def mark_started(self, participant_id: str, agent_name: str) -> None:
        """Mark an agent as started for a participant."""
        self._ensure_participant(participant_id)
        self._state["participants"][participant_id][agent_name] = {
            "status": "in_progress",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
        }
        self._save()

    def mark_completed(
        self, participant_id: str, agent_name: str, output_path: str = ""
    ) -> None:
        """Mark an agent as completed for a participant."""
        self._ensure_participant(participant_id)
        entry = self._state["participants"][participant_id].get(agent_name, {})
        entry["status"] = "completed"
        entry["completed_at"] = datetime.now(timezone.utc).isoformat()
        if output_path:
            entry["output_path"] = output_path
        self._state["participants"][participant_id][agent_name] = entry
        self._save()

    def mark_failed(
        self, participant_id: str, agent_name: str, error: str = ""
    ) -> None:
        """Mark an agent as failed for a participant."""
        self._ensure_participant(participant_id)
        entry = self._state["participants"][participant_id].get(agent_name, {})
        entry["status"] = "failed"
        entry["failed_at"] = datetime.now(timezone.utc).isoformat()
        entry["error"] = error
        self._state["participants"][participant_id][agent_name] = entry
        self._save()

    def mark_checkpoint(self, agent_name: str, approved: bool, notes: str = "") -> None:
        """Record a human checkpoint decision."""
        self._state.setdefault("checkpoints", {})[agent_name] = {
            "approved": approved,
            "notes": notes,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
        }
        self._save()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _ensure_participant(self, participant_id: str) -> None:
        if participant_id not in self._state["participants"]:
            self._state["participants"][participant_id] = {}

    def _save(self) -> None:
        self._state["_metadata"]["last_updated"] = datetime.now(timezone.utc).isoformat()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w") as f:
            json.dump(self._state, f, indent=2, ensure_ascii=False)

    def reset(self) -> None:
        """Reset all pipeline state."""
        self._state = {
            "_metadata": {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "last_updated": None,
                "agent_names": AGENT_NAMES,
            },
            "participants": {},
        }
        self._save()
        logger.info("Pipeline state reset")
