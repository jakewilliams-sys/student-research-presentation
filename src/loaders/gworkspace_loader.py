"""
Google Workspace MCP Loader

Fetches participant data, researcher notes, and discussion guides from Google
Workspace via the MCP integration. Caches all data locally for offline analysis.

Key design decisions:
  - The master notes document uses TABS (one per session), not separate docs.
    This loader parses the single document and splits by session headers.
  - Participant spreadsheet has separate sheets per segment (Undergrad, Postgrad,
    Early grad) plus a Diary Study tracking sheet.
  - Discussion guides are fetched once and cached as markdown in data/reference/.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"
PROCESSED_DIR = DATA_DIR / "processed"
REFERENCE_DIR = DATA_DIR / "reference"
NOTES_DIR = PROCESSED_DIR / "researcher_notes"


def _load_google_sources() -> dict[str, Any]:
    """Load google_sources.yaml configuration."""
    path = CONFIG_DIR / "google_sources.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def _load_participant_map() -> dict[str, Any]:
    """Load the participant map JSON."""
    path = REFERENCE_DIR / "participant_map.json"
    with open(path) as f:
        return json.load(f)


def _save_participant_map(pmap: dict[str, Any]) -> None:
    """Persist the participant map JSON."""
    path = REFERENCE_DIR / "participant_map.json"
    with open(path, "w") as f:
        json.dump(pmap, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Participant Spreadsheet Sync
# ---------------------------------------------------------------------------

PROFILE_SHEETS = ["Undergrad", "Postgrad", "Early grad"]

SEGMENT_LOOKUP = {
    "Undergrad": "undergraduate",
    "Postgrad": "postgraduate",
    "Early grad": "early_graduate",
}

COLUMN_MAP = {
    "Name": "name",
    "Session": "session",
    "Current Location": "current_location",
    "University City": "university_city",
    "University": "university",
    "Year of Study": "year_of_study",
    "Contact Hours": "contact_hours",
    "Age": "age",
    "Gender": "gender",
    "Food Delivery Apps Used": "platforms_used",
    "Order Frequency": "order_frequency",
    "Current Subscription": "current_subscription",
    "Past Subscriptions": "past_subscriptions",
    "Living Situation": "living_situation",
    "Food Habits": "food_habits",
}


def sync_participant_spreadsheet(
    mcp_read_sheet: Any,
    spreadsheet_id: str | None = None,
) -> dict[str, Any]:
    """
    Fetch participant data from Google Sheets and cache as JSON.

    Parameters
    ----------
    mcp_read_sheet : callable
        A callable that accepts (spreadsheet_id, range_name) and returns sheet
        rows. This is the Google Workspace MCP ``read_sheet_values`` function.
    spreadsheet_id : str, optional
        Override the spreadsheet ID from google_sources.yaml.

    Returns
    -------
    dict
        Parsed participant profiles keyed by participant_id.
    """
    sources = _load_google_sources()
    sid = spreadsheet_id or sources["google_workspace"]["participant_spreadsheet"]["id"]

    all_profiles: list[dict[str, Any]] = []

    for sheet_name in PROFILE_SHEETS:
        logger.info("Fetching sheet: %s", sheet_name)
        rows = mcp_read_sheet(sid, f"{sheet_name}!A1:Z100")

        if not rows or len(rows) < 2:
            logger.warning("Sheet %s is empty or has no data rows", sheet_name)
            continue

        headers = rows[0]
        segment = SEGMENT_LOOKUP[sheet_name]

        for row_idx, row in enumerate(rows[1:], start=2):
            if not row or not row[0].strip():
                continue

            profile: dict[str, Any] = {"_sheet": sheet_name, "_row": row_idx, "_segment": segment}
            for col_idx, header in enumerate(headers):
                mapped = COLUMN_MAP.get(header)
                if mapped and col_idx < len(row):
                    profile[mapped] = row[col_idx].strip() if row[col_idx] else ""
            all_profiles.append(profile)

    out_path = PROCESSED_DIR / "participant_profiles.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(all_profiles, f, indent=2, ensure_ascii=False)

    logger.info("Saved %d participant profiles to %s", len(all_profiles), out_path)
    return {"profiles": all_profiles, "count": len(all_profiles)}


def sync_diary_study_tracking(
    mcp_read_sheet: Any,
    spreadsheet_id: str | None = None,
) -> list[str]:
    """
    Fetch the Diary Study sheet to identify which participants have diary data.

    Returns a list of participant names enrolled in the diary study.
    """
    sources = _load_google_sources()
    sid = spreadsheet_id or sources["google_workspace"]["participant_spreadsheet"]["id"]

    rows = mcp_read_sheet(sid, "Diary Study!A1:Z50")
    if not rows or len(rows) < 2:
        return []

    diary_participants: list[str] = []
    for row in rows[1:]:
        if row and row[0].strip():
            name = re.sub(r"\s*\(.*?\)\s*$", "", row[0].strip())
            diary_participants.append(name)

    logger.info("Found %d diary study participants", len(diary_participants))
    return diary_participants


# ---------------------------------------------------------------------------
# Researcher Notes Sync (Tabbed Master Document)
# ---------------------------------------------------------------------------

SESSION_TAB_PATTERN = re.compile(
    r"^(?:Session\s+\d+\s*[-–—]\s*)(.+?)(?:\s*\(ID:\s*\w+\))?$",
    re.IGNORECASE,
)

SECTION_HEADER_PATTERN = re.compile(
    r"^(?:#{1,3}\s+)?("
    r"Background|Living situation|Social media|Meals|Ordering|"
    r"Grocery|Stress|Perceptions|Competition|Subscription|"
    r"Summary|Notes|Other|Wrap.up"
    r")\s*$",
    re.IGNORECASE,
)


def _parse_tabbed_notes(doc_content: str) -> dict[str, dict[str, str]]:
    """
    Parse a master notes document that uses session headers as tabs.

    The document is structured as:
        Session N - Participant Name (ID: xxx)
        Background
        ...notes...
        Living situation
        ...notes...

    Returns
    -------
    dict
        Mapping of participant name -> {section_name: section_text}.
    """
    sessions: dict[str, dict[str, str]] = {}
    current_participant: str | None = None
    current_section: str | None = None
    current_text: list[str] = []

    def _flush_section() -> None:
        if current_participant and current_section and current_text:
            if current_participant not in sessions:
                sessions[current_participant] = {}
            sessions[current_participant][current_section] = "\n".join(current_text).strip()

    for line in doc_content.splitlines():
        stripped = line.strip()

        tab_match = SESSION_TAB_PATTERN.match(stripped)
        if tab_match:
            _flush_section()
            current_participant = tab_match.group(1).strip()
            current_section = None
            current_text = []
            continue

        if not current_participant:
            header_in_line = stripped.lower()
            if any(
                kw in header_in_line
                for kw in ["session", "interview", "participant"]
            ):
                for name_candidate in re.findall(r"[-–—]\s*(.+?)(?:\s*\(|$)", stripped):
                    name = name_candidate.strip()
                    if len(name) > 2:
                        _flush_section()
                        current_participant = name
                        current_section = None
                        current_text = []
                        break
            continue

        section_match = SECTION_HEADER_PATTERN.match(stripped)
        if section_match:
            _flush_section()
            current_section = section_match.group(1).strip().lower().replace(" ", "_")
            current_text = []
            continue

        if current_section is not None:
            current_text.append(line)

    _flush_section()
    return sessions


def _match_notes_to_participant(
    session_name: str,
    participant_map: dict[str, Any],
) -> str | None:
    """
    Fuzzy-match a session/participant name from notes to a participant ID.

    Tries exact name match first, then falls back to partial matching.
    """
    session_lower = session_name.lower().strip()

    for pid, pdata in participant_map.items():
        if pid.startswith("_"):
            continue
        pname = pdata.get("name")
        if not pname:
            continue

        if pname.lower() == session_lower:
            return pid

        name_parts = pname.lower().split()
        if any(part in session_lower for part in name_parts if len(part) > 2):
            return pid

    return None


def sync_researcher_notes(
    mcp_get_doc: Any,
    master_doc_id: str | None = None,
    individual_doc_ids: list[dict[str, str]] | None = None,
) -> dict[str, str]:
    """
    Fetch researcher notes from Google Docs and cache per-participant.

    Handles two source types:
      1. A single master document with session tabs (primary)
      2. Individual supplementary note documents (secondary)

    Parameters
    ----------
    mcp_get_doc : callable
        Callable accepting a document ID and returning document text content.
    master_doc_id : str, optional
        Override the master doc ID from google_sources.yaml.
    individual_doc_ids : list[dict], optional
        Override the individual notes list from google_sources.yaml.

    Returns
    -------
    dict
        Mapping of participant_id -> cached file path.
    """
    sources = _load_google_sources()
    notes_config = sources["google_workspace"]["researcher_notes"]

    mid = master_doc_id or notes_config["master_doc"]["id"]
    indiv = individual_doc_ids or notes_config.get("individual_notes", [])

    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    pmap = _load_participant_map()
    cached_paths: dict[str, str] = {}

    logger.info("Fetching master notes document: %s", mid)
    master_content = mcp_get_doc(mid)

    if master_content:
        parsed_sessions = _parse_tabbed_notes(master_content)
        logger.info("Parsed %d sessions from master notes", len(parsed_sessions))

        for session_name, sections in parsed_sessions.items():
            pid = _match_notes_to_participant(session_name, pmap)
            if not pid:
                logger.warning(
                    "Could not match session '%s' to a participant", session_name
                )
                continue

            note_path = NOTES_DIR / f"{pid.lower()}_{_slugify(session_name)}_notes.md"
            _write_notes_markdown(note_path, session_name, sections)
            cached_paths[pid] = str(note_path.relative_to(BASE_DIR))
            logger.info("Cached notes for %s (%s) -> %s", pid, session_name, note_path.name)

    for doc_info in indiv:
        doc_id = doc_info["id"]
        participant_name = doc_info.get("participant", "unknown")
        logger.info("Fetching individual notes: %s (%s)", participant_name, doc_id)

        content = mcp_get_doc(doc_id)
        if not content:
            continue

        pid = _match_notes_to_participant(participant_name, pmap)
        if not pid:
            logger.warning(
                "Could not match individual doc '%s' to a participant", participant_name
            )
            continue

        if pid in cached_paths:
            supp_path = NOTES_DIR / f"{pid.lower()}_{_slugify(participant_name)}_supplementary.md"
            with open(supp_path, "w") as f:
                f.write(f"# Supplementary Notes - {participant_name}\n\n")
                f.write(f"Source: Google Docs ({doc_id})\n\n")
                f.write(content)
        else:
            note_path = NOTES_DIR / f"{pid.lower()}_{_slugify(participant_name)}_notes.md"
            with open(note_path, "w") as f:
                f.write(f"# Researcher Notes - {participant_name}\n\n")
                f.write(f"Source: Google Docs ({doc_id})\n\n")
                f.write(content)
            cached_paths[pid] = str(note_path.relative_to(BASE_DIR))

    _update_participant_map_notes(pmap, cached_paths)
    return cached_paths


def _write_notes_markdown(
    path: Path, session_name: str, sections: dict[str, str]
) -> None:
    """Write parsed session notes to a structured markdown file."""
    with open(path, "w") as f:
        f.write(f"# Researcher Notes - {session_name}\n\n")
        f.write(f"Synced: {datetime.now(timezone.utc).isoformat()}\n\n")
        for section_key, section_text in sections.items():
            heading = section_key.replace("_", " ").title()
            f.write(f"## {heading}\n\n")
            f.write(section_text)
            f.write("\n\n")


def _update_participant_map_notes(
    pmap: dict[str, Any], cached_paths: dict[str, str]
) -> None:
    """Update participant_map.json with cached note file paths."""
    updated = False
    for pid, cache_path in cached_paths.items():
        if pid in pmap and isinstance(pmap[pid], dict):
            sources = pmap[pid].setdefault("sources", {})
            notes = sources.setdefault("notes", {})
            notes["cached_at"] = cache_path
            updated = True

    if updated:
        pmap["_metadata"]["last_synced"] = datetime.now(timezone.utc).isoformat()
        _save_participant_map(pmap)
        logger.info("Updated participant map with note cache paths")


# ---------------------------------------------------------------------------
# Discussion Guide Sync
# ---------------------------------------------------------------------------

def sync_discussion_guides(mcp_get_doc: Any) -> dict[str, str]:
    """
    Fetch discussion guides from Google Docs and cache in data/reference/.

    Returns mapping of guide_key -> cached file path.
    """
    sources = _load_google_sources()
    guides_config = sources["google_workspace"]["discussion_guides"]
    cached: dict[str, str] = {}

    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)

    for key, guide_info in guides_config.items():
        doc_id = guide_info["id"]
        filename = f"discussion_guide_{key}.md"
        out_path = REFERENCE_DIR / filename

        logger.info("Fetching discussion guide: %s (%s)", key, doc_id)
        content = mcp_get_doc(doc_id)

        if content:
            with open(out_path, "w") as f:
                f.write(f"<!-- Synced: {datetime.now(timezone.utc).isoformat()} -->\n")
                f.write(f"<!-- Source: Google Docs {doc_id} -->\n\n")
                f.write(content)
            cached[key] = str(out_path.relative_to(BASE_DIR))
            logger.info("Cached guide: %s -> %s", key, out_path.name)
        else:
            logger.warning("Failed to fetch discussion guide: %s", key)

    return cached


# ---------------------------------------------------------------------------
# Business Context Source Sync
# ---------------------------------------------------------------------------

def sync_business_context_sources(mcp_get_doc: Any) -> dict[str, str]:
    """
    Fetch business context source documents for reference.

    These are not directly consumed by the system at runtime (the pre-populated
    business_context.yaml is used instead), but are cached for auditability.
    """
    sources = _load_google_sources()
    biz_config = sources["google_workspace"]["business_context_sources"]
    cached: dict[str, str] = {}

    ref_biz_dir = PROCESSED_DIR / "business_context_sources"
    ref_biz_dir.mkdir(parents=True, exist_ok=True)

    for key, doc_info in biz_config.items():
        doc_id = doc_info["id"]
        filename = f"{key}_{doc_id[:8]}.md"
        out_path = ref_biz_dir / filename

        logger.info("Fetching business context source: %s", key)
        content = mcp_get_doc(doc_id)

        if content:
            with open(out_path, "w") as f:
                f.write(f"<!-- Source: {doc_info.get('description', key)} -->\n")
                f.write(f"<!-- Doc ID: {doc_id} -->\n")
                f.write(f"<!-- Synced: {datetime.now(timezone.utc).isoformat()} -->\n\n")
                f.write(content)
            cached[key] = str(out_path.relative_to(BASE_DIR))
        else:
            logger.warning("Failed to fetch business context source: %s", key)

    return cached


# ---------------------------------------------------------------------------
# Full Sync Orchestrator
# ---------------------------------------------------------------------------

def sync_all(
    mcp_read_sheet: Any,
    mcp_get_doc: Any,
) -> dict[str, Any]:
    """
    Run a full sync of all Google Workspace data sources.

    Parameters
    ----------
    mcp_read_sheet : callable
        Google Workspace MCP sheet reader.
    mcp_get_doc : callable
        Google Workspace MCP document reader.

    Returns
    -------
    dict
        Summary of all synced data.
    """
    logger.info("Starting full Google Workspace sync...")

    results: dict[str, Any] = {}

    results["participants"] = sync_participant_spreadsheet(mcp_read_sheet)
    results["diary_participants"] = sync_diary_study_tracking(mcp_read_sheet)
    results["notes"] = sync_researcher_notes(mcp_get_doc)
    results["guides"] = sync_discussion_guides(mcp_get_doc)
    results["business_sources"] = sync_business_context_sources(mcp_get_doc)

    results["synced_at"] = datetime.now(timezone.utc).isoformat()
    logger.info("Full sync complete.")
    return results


# ---------------------------------------------------------------------------
# Moderator Summary Loading
# ---------------------------------------------------------------------------


def load_moderator_summary(interview_type: str) -> str | None:
    """
    Load a locally cached moderator summary document.

    Parameters
    ----------
    interview_type : str
        Either "online" or "in_home".

    Returns
    -------
    str or None
        The summary text, or None if not available.
    """
    if interview_type == "in_home":
        path = REFERENCE_DIR / "moderator_summary_inhome.txt"
    else:
        path = REFERENCE_DIR / "moderator_summary_online.txt"

    if not path.exists():
        return None

    text = path.read_text().strip()
    if text:
        logger.info("Loaded moderator summary (%s): %d chars", interview_type, len(text))
    return text or None


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _slugify(text: str) -> str:
    """Convert a string to a filesystem-safe slug."""
    slug = text.lower().strip()
    slug = re.sub(r"['\"]", "", slug)
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    return slug.strip("_")
