"""
Marvin MCP Loader

Fetches interview transcripts and AI-generated summaries from Marvin
(heymarvin.com) via the MCP integration. Marvin stores video recordings
with auto-generated transcripts for the Student Research project.

Marvin MCP provides:
  - list_projects / list_project_files: Discover available interviews
  - get_file_summary: AI-generated summary per interview
  - get_file_content: Full transcript with speaker labels and timestamps
  - search: Keyword search across transcripts with context
  - ask: AI-powered question answering across all interviews

Key design decision:
  Marvin's get_file_content may return transcript=null for some files.
  In that case we fall back to the search API to reconstruct transcript
  segments, and rely on the AI summary for holistic understanding.
  Both the summary and available transcript segments are cached locally.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
PROCESSED_DIR = DATA_DIR / "processed"
TRANSCRIPT_CACHE_DIR = PROCESSED_DIR / "transcripts"
SUMMARY_CACHE_DIR = PROCESSED_DIR / "marvin_summaries"

PROJECT_ID = 51271


class MarvinLoader:
    """
    Loads interview data from Marvin MCP for the student research project.

    Wraps the Marvin MCP tools to provide a clean interface for the
    analysis pipeline. Handles caching, participant matching, and
    fallback strategies when full transcripts are unavailable.
    """

    def __init__(
        self,
        list_project_files: Any | None = None,
        get_file_summary: Any | None = None,
        get_file_content: Any | None = None,
        search: Any | None = None,
        ask: Any | None = None,
        project_id: int = PROJECT_ID,
    ):
        self._list_files = list_project_files
        self._get_summary = get_file_summary
        self._get_content = get_file_content
        self._search = search
        self._ask = ask
        self._project_id = project_id

        TRANSCRIPT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        SUMMARY_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    @property
    def is_available(self) -> bool:
        return self._list_files is not None

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def list_interviews(self) -> list[dict[str, Any]]:
        """List all interview files in the Student Research project."""
        if not self._list_files:
            return self._load_cached_file_list()

        result = self._list_files(project_id=str(self._project_id), count=100)
        files = result.get("files", []) if isinstance(result, dict) else []

        cache_path = PROCESSED_DIR / "marvin_file_list.json"
        with open(cache_path, "w") as f:
            json.dump(files, f, indent=2, ensure_ascii=False)

        logger.info("Found %d interviews in Marvin project %d", len(files), self._project_id)
        return files

    def _load_cached_file_list(self) -> list[dict[str, Any]]:
        """Load previously cached file list when MCP is unavailable."""
        cache_path = PROCESSED_DIR / "marvin_file_list.json"
        if cache_path.exists():
            with open(cache_path) as f:
                return json.load(f)
        return []

    # ------------------------------------------------------------------
    # Transcript retrieval
    # ------------------------------------------------------------------

    def get_transcript(self, file_id: int, file_name: str = "") -> dict[str, Any]:
        """
        Retrieve the full transcript for an interview.

        Tries get_file_content first. If transcript is null, falls back
        to searching for all segments from this file.

        Returns a dict with:
          - transcript_text: Plain text transcript (may be reconstructed)
          - segments: List of timestamped, speaker-labelled segments
          - source: "full_transcript" or "search_reconstruction"
          - cached_at: Local file path
        """
        cache_path = TRANSCRIPT_CACHE_DIR / f"{file_id}_{_slugify(file_name)}.json"

        if cache_path.exists():
            with open(cache_path) as f:
                cached = json.load(f)
            logger.info("Loaded cached transcript for %s (%d)", file_name, file_id)
            return cached

        result: dict[str, Any] = {
            "file_id": file_id,
            "file_name": file_name,
            "transcript_text": None,
            "segments": [],
            "source": None,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

        if self._get_content:
            content = self._get_content(
                project_id=str(self._project_id),
                file_id=str(file_id),
            )
            transcript = None
            if isinstance(content, dict):
                transcript = content.get("transcript")

            if transcript:
                result["transcript_text"] = transcript
                result["source"] = "full_transcript"
                logger.info("Got full transcript for %s", file_name)

        if not result["transcript_text"] and self._search:
            result = self._reconstruct_via_search(file_id, file_name, result)

        with open(cache_path, "w") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        result["cached_at"] = str(cache_path.relative_to(BASE_DIR))

        return result

    def _reconstruct_via_search(
        self, file_id: int, file_name: str, result: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Reconstruct a transcript by searching for common research terms
        across the interview. This is a fallback when get_file_content
        returns transcript=null.
        """
        search_terms = [
            "Deliveroo", "Uber Eats", "Just Eat", "delivery", "order",
            "cook", "food", "subscription", "Plus", "student",
            "grocery", "takeaway", "price", "app", "housemate",
            "flatmate", "university", "budget", "treat", "social",
        ]

        all_segments: list[dict[str, Any]] = []
        seen_timestamps: set[str] = set()

        for term in search_terms:
            try:
                search_result = self._search(
                    query=term,
                    projects=[self._project_id],
                    search_type="transcripts",
                    count=100,
                )
                results_list = search_result.get("results", []) if isinstance(search_result, dict) else []

                for r in results_list:
                    if r.get("wav_id") != file_id:
                        continue
                    for match in r.get("matches", []):
                        ts = match.get("timestamp", {})
                        ts_key = f"{ts.get('start', '')}_{ts.get('end', '')}"
                        if ts_key in seen_timestamps:
                            continue
                        seen_timestamps.add(ts_key)

                        text = match.get("text", "")
                        text = re.sub(r"</?em>", "", text)

                        all_segments.append({
                            "text": text,
                            "speaker": match.get("speaker", "Unknown"),
                            "start": ts.get("start", ""),
                            "end": ts.get("end", ""),
                        })
            except Exception:
                logger.exception("Search failed for term '%s'", term)

        all_segments.sort(key=lambda s: s.get("start", ""))
        result["segments"] = all_segments
        result["source"] = "search_reconstruction"

        if all_segments:
            lines = []
            for seg in all_segments:
                speaker = seg.get("speaker", "")
                ts = seg.get("start", "")
                text = seg.get("text", "")
                lines.append(f"[{ts}] {speaker}: {text}")
            result["transcript_text"] = "\n\n".join(lines)

        logger.info(
            "Reconstructed %d segments for %s via search",
            len(all_segments), file_name,
        )
        return result

    # ------------------------------------------------------------------
    # Summary retrieval
    # ------------------------------------------------------------------

    def get_summary(self, file_id: int, file_name: str = "") -> dict[str, Any]:
        """
        Retrieve the AI-generated summary for an interview.

        Marvin summaries include participant profile, key findings,
        opportunities, and a TL;DR - useful as input for the
        Participant Summary Agent.
        """
        cache_path = SUMMARY_CACHE_DIR / f"{file_id}_{_slugify(file_name)}_summary.json"

        if cache_path.exists():
            with open(cache_path) as f:
                return json.load(f)

        if not self._get_summary:
            return {"file_id": file_id, "summary": None}

        result = self._get_summary(
            project_id=str(self._project_id),
            file_id=str(file_id),
        )

        summary_data = {
            "file_id": file_id,
            "file_name": file_name,
            "summary": result.get("summary", {}).get("text") if isinstance(result, dict) else None,
            "has_summary": result.get("has_summary", False) if isinstance(result, dict) else False,
            "duration_seconds": result.get("duration_seconds") if isinstance(result, dict) else None,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

        with open(cache_path, "w") as f:
            json.dump(summary_data, f, indent=2, ensure_ascii=False)

        return summary_data

    # ------------------------------------------------------------------
    # Cross-interview querying
    # ------------------------------------------------------------------

    def search_across_interviews(
        self, query: str, count: int = 20
    ) -> list[dict[str, Any]]:
        """
        Search across all student research transcripts for a keyword or phrase.

        Returns timestamped, speaker-labelled matches with file context.
        Useful for the Analysis Agent's coding passes.
        """
        if not self._search:
            return []

        result = self._search(
            query=query,
            projects=[self._project_id],
            search_type="transcripts",
            count=count,
        )

        matches = []
        for r in (result.get("results", []) if isinstance(result, dict) else []):
            for match in r.get("matches", []):
                text = re.sub(r"</?em>", "", match.get("text", ""))
                matches.append({
                    "file_id": r.get("wav_id"),
                    "file_name": r.get("wav_name"),
                    "text": text,
                    "speaker": match.get("speaker"),
                    "start": match.get("timestamp", {}).get("start"),
                    "end": match.get("timestamp", {}).get("end"),
                })

        return matches

    def ask_question(self, question: str) -> str | None:
        """
        Ask an AI-powered question across all student research interviews.

        Marvin synthesises an answer from the full corpus. Useful for
        the Insight Agent and Deep Dive Agent.
        """
        if not self._ask:
            return None

        result = self._ask(
            question=question,
            project_ids=[self._project_id],
        )

        if isinstance(result, dict):
            if result.get("status") == "in_progress":
                return f"[pending: request_id={result.get('request_id')}]"
            return result.get("answer")
        return None

    # ------------------------------------------------------------------
    # Batch operations
    # ------------------------------------------------------------------

    def sync_all_interviews(self) -> dict[str, Any]:
        """
        Fetch summaries and transcripts for all interviews in the project.

        Returns a summary of what was synced.
        """
        files = self.list_interviews()
        synced: dict[str, Any] = {
            "total_files": len(files),
            "summaries_fetched": 0,
            "transcripts_fetched": 0,
            "files": [],
        }

        for f in files:
            fid = f.get("id")
            fname = f.get("name", "")
            if not fid:
                continue

            summary = self.get_summary(fid, fname)
            transcript = self.get_transcript(fid, fname)

            file_status = {
                "file_id": fid,
                "file_name": fname,
                "has_summary": bool(summary.get("summary")),
                "transcript_source": transcript.get("source"),
                "segment_count": len(transcript.get("segments", [])),
            }
            synced["files"].append(file_status)

            if summary.get("summary"):
                synced["summaries_fetched"] += 1
            if transcript.get("transcript_text"):
                synced["transcripts_fetched"] += 1

        synced["synced_at"] = datetime.now(timezone.utc).isoformat()

        sync_report_path = PROCESSED_DIR / "marvin_sync_report.json"
        with open(sync_report_path, "w") as f:
            json.dump(synced, f, indent=2, ensure_ascii=False)

        logger.info(
            "Marvin sync complete: %d summaries, %d transcripts from %d files",
            synced["summaries_fetched"],
            synced["transcripts_fetched"],
            synced["total_files"],
        )
        return synced

    def get_transcript_for_participant(
        self, participant_id: str, participant_map: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """
        Get transcript for a participant using their participant map entry.

        Looks up the Marvin file_id from the participant map and fetches
        the transcript.
        """
        if participant_map is None:
            pmap_path = DATA_DIR / "reference" / "participant_map.json"
            with open(pmap_path) as f:
                participant_map = json.load(f)

        pdata = participant_map.get(participant_id)
        if not pdata:
            return None

        interview_source = pdata.get("sources", {}).get("interview", {})
        if not isinstance(interview_source, dict):
            return None

        if interview_source.get("source") != "marvin":
            return None

        file_id = interview_source.get("file_id")
        if not file_id:
            logger.warning("No Marvin file_id for %s (pending upload)", participant_id)
            return None

        file_name = interview_source.get("file_name", "")
        return self.get_transcript(file_id, file_name)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_marvin_loader(
    list_project_files: Any | None = None,
    get_file_summary: Any | None = None,
    get_file_content: Any | None = None,
    search: Any | None = None,
    ask: Any | None = None,
) -> MarvinLoader:
    """
    Create a MarvinLoader with the given MCP tool functions.

    If no functions are provided, returns a loader that operates from
    cache only (offline mode).
    """
    loader = MarvinLoader(
        list_project_files=list_project_files,
        get_file_summary=get_file_summary,
        get_file_content=get_file_content,
        search=search,
        ask=ask,
    )
    if not loader.is_available:
        logger.warning(
            "Marvin MCP not configured. Operating in cache-only mode. "
            "Run sync_all_interviews() with MCP functions to populate cache."
        )
    return loader


def _slugify(text: str) -> str:
    slug = text.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    return slug.strip("_")[:60]
