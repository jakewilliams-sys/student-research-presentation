"""
Codebook manager for qualitative research theme hierarchy.

The codebook tracks all codes (themes and sub-themes) used during analysis.
It is seeded from the research objectives and grows as the Analysis Agent
discovers emergent themes.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from config.settings import CONFIG_DIR, REFERENCE_DIR

logger = logging.getLogger(__name__)

CODEBOOK_PATH = REFERENCE_DIR / "codebook.json"


class Codebook:
    """Manages the qualitative coding theme hierarchy."""

    def __init__(self, path: Path | None = None):
        self._path = path or CODEBOOK_PATH
        self._data: dict[str, Any] = self._load_or_init()

    def _load_or_init(self) -> dict[str, Any]:
        """Load existing codebook or initialise from research objectives."""
        if self._path.exists():
            with open(self._path) as f:
                data = json.load(f)
            logger.info("Loaded codebook with %d themes", len(data.get("themes", {})))
            return data

        logger.info("Initialising new codebook from research objectives")
        return self._seed_from_objectives()

    def _seed_from_objectives(self) -> dict[str, Any]:
        """Create initial codebook structure from research_objectives.yaml."""
        obj_path = CONFIG_DIR / "research_objectives.yaml"
        if not obj_path.exists():
            return self._empty_codebook()

        with open(obj_path) as f:
            objectives = yaml.safe_load(f)

        themes: dict[str, Any] = {}
        for ro_key, ro_data in objectives.get("objectives", {}).items():
            prefix = ro_data.get("coding_prefix", ro_key)
            themes[prefix] = {
                "label": ro_data.get("name", ro_key),
                "description": ro_data.get("question", ""),
                "source": "research_objective",
                "sub_themes": {},
                "segment_count": 0,
            }
            for sq in ro_data.get("sub_questions", []):
                sub_key = _slugify(sq)[:40]
                themes[prefix]["sub_themes"][f"{prefix}.{sub_key}"] = {
                    "label": sq,
                    "source": "research_objective",
                    "segment_count": 0,
                }

        # Add context tag categories
        for tag_group, tags in _CONTEXT_TAGS.items():
            themes[f"context_{tag_group}"] = {
                "label": tag_group.replace("_", " ").title(),
                "description": f"Context tagging: {tag_group}",
                "source": "system",
                "sub_themes": {
                    f"context_{tag_group}.{t}": {"label": t, "source": "system", "segment_count": 0}
                    for t in tags
                },
                "segment_count": 0,
            }

        data = {
            "_metadata": {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "version": 1,
                "total_themes": len(themes),
            },
            "themes": themes,
            "emergent_themes": {},
        }

        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info("Seeded codebook with %d themes", len(themes))
        return data

    def _empty_codebook(self) -> dict[str, Any]:
        return {
            "_metadata": {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "version": 1,
                "total_themes": 0,
            },
            "themes": {},
            "emergent_themes": {},
        }

    # ------------------------------------------------------------------
    # Access
    # ------------------------------------------------------------------

    @property
    def themes(self) -> dict[str, Any]:
        return self._data.get("themes", {})

    @property
    def emergent_themes(self) -> dict[str, Any]:
        return self._data.get("emergent_themes", {})

    @property
    def all_codes(self) -> list[str]:
        """Flat list of all theme and sub-theme codes."""
        codes: list[str] = []
        for key, theme in self.themes.items():
            codes.append(key)
            for sub_key in theme.get("sub_themes", {}):
                codes.append(sub_key)
        for key in self.emergent_themes:
            codes.append(key)
        return codes

    def get_theme(self, code: str) -> dict[str, Any] | None:
        """Look up a theme or sub-theme by code."""
        if code in self.themes:
            return self.themes[code]
        for theme in self.themes.values():
            if code in theme.get("sub_themes", {}):
                return theme["sub_themes"][code]
        return self.emergent_themes.get(code)

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def add_emergent_theme(
        self,
        code: str,
        label: str,
        description: str = "",
        discovered_by: str = "",
        participant_id: str = "",
    ) -> None:
        """Add a new theme discovered during analysis."""
        if code in self.emergent_themes or code in self.themes:
            return

        self._data["emergent_themes"][code] = {
            "label": label,
            "description": description,
            "source": "emergent",
            "discovered_by": discovered_by,
            "first_seen_in": participant_id,
            "segment_count": 0,
            "added_at": datetime.now(timezone.utc).isoformat(),
        }
        self._data["_metadata"]["last_updated"] = datetime.now(timezone.utc).isoformat()
        self.save()
        logger.info("Added emergent theme: %s (%s)", code, label)

    def increment_count(self, code: str, n: int = 1) -> None:
        """Increment the segment count for a code."""
        theme = self.get_theme(code)
        if theme:
            theme["segment_count"] = theme.get("segment_count", 0) + n

    def merge_emergent_themes(self, codes: list[str], into_parent: str) -> None:
        """Promote emergent themes into the main hierarchy under a parent."""
        parent = self.themes.get(into_parent)
        if not parent:
            logger.warning("Parent theme %s not found", into_parent)
            return

        for code in codes:
            emergent = self.emergent_themes.pop(code, None)
            if emergent:
                parent.setdefault("sub_themes", {})[code] = emergent
                emergent["source"] = "promoted_emergent"

        self._data["_metadata"]["last_updated"] = datetime.now(timezone.utc).isoformat()
        self.save()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self) -> None:
        """Write codebook to disk."""
        self._data["_metadata"]["last_updated"] = datetime.now(timezone.utc).isoformat()
        self._data["_metadata"]["total_themes"] = (
            len(self.themes) + len(self.emergent_themes)
        )
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    def to_prompt_context(self) -> str:
        """Serialise the codebook as a compact string for LLM prompts."""
        lines = ["## Current Codebook\n"]
        for code, theme in self.themes.items():
            lines.append(f"- **{code}**: {theme.get('label', '')} ({theme.get('segment_count', 0)} segments)")
            for sub_code, sub in theme.get("sub_themes", {}).items():
                lines.append(f"  - {sub_code}: {sub.get('label', '')} ({sub.get('segment_count', 0)})")
        if self.emergent_themes:
            lines.append("\n### Emergent Themes\n")
            for code, theme in self.emergent_themes.items():
                lines.append(f"- **{code}**: {theme.get('label', '')} ({theme.get('segment_count', 0)})")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CONTEXT_TAGS = {
    "emotion": [
        "joy", "stress", "comfort", "guilt", "excitement", "frustration",
        "relief", "anticipation", "indifference", "connection", "loneliness",
    ],
    "social_context": [
        "alone", "flatmates", "partner", "family", "friends", "colleagues",
    ],
    "temporal": [
        "weekday", "weekend", "morning", "afternoon", "evening", "late_night",
        "exam_period", "term_time", "holiday", "freshers",
    ],
    "platform": [
        "deliveroo", "ubereats", "justeat", "other",
    ],
}


def _slugify(text: str) -> str:
    import re
    slug = text.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    return slug.strip("_")
