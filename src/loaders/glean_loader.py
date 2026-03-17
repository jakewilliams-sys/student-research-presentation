"""
Glean MCP Loader

Provides runtime access to Deliveroo's internal knowledge base via the Glean
MCP for strategic context enrichment. Used by the Insight Agent and Devil's
Advocate Agent to cross-reference findings against internal strategy documents.

The Glean MCP exposes three primary interfaces:
  - glean_default-search: Keyword search across internal documents
  - glean_default-chat: AI-powered synthesis across multiple sources
  - glean_default-code_search: Code repository search (not used here)

This loader wraps those interfaces with research-specific query templates
and caching to avoid redundant lookups during analysis runs.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CACHE_DIR = BASE_DIR / "data" / "processed" / "glean_cache"


class GleanContextProvider:
    """
    Provides strategic context from Glean for agent consumption.

    Wraps the Glean MCP search and chat functions with caching and
    research-specific query templates. Agents call high-level methods
    like ``get_competitive_context()`` rather than raw Glean queries.
    """

    def __init__(
        self,
        glean_search: Any | None = None,
        glean_chat: Any | None = None,
        cache_enabled: bool = True,
    ):
        """
        Parameters
        ----------
        glean_search : callable, optional
            Glean MCP search function. Accepts a query string.
        glean_chat : callable, optional
            Glean MCP chat function. Accepts a message string.
        cache_enabled : bool
            Whether to cache Glean responses locally.
        """
        self._search = glean_search
        self._chat = glean_chat
        self._cache_enabled = cache_enabled
        self._session_cache: dict[str, Any] = {}

        if cache_enabled:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)

    @property
    def is_available(self) -> bool:
        """Check if Glean MCP functions are configured."""
        return self._search is not None or self._chat is not None

    # ------------------------------------------------------------------
    # High-level context methods (called by agents)
    # ------------------------------------------------------------------

    def get_competitive_context(self) -> dict[str, Any]:
        """
        Retrieve current competitive intelligence for the student segment.

        Used by: Insight Agent (recommendation grounding),
                 Devil's Advocate Agent (competitive challenge).
        """
        return self._query_and_cache(
            cache_key="competitive_context",
            search_queries=[
                "student food delivery competitive landscape UberOne JustEat",
                "Deliveroo student proposition competitive positioning",
            ],
            chat_question=(
                "What is the current competitive landscape for student food "
                "delivery in the UK? How does Deliveroo's student proposition "
                "compare to UberOne Student and JustEat?"
            ),
        )

    def get_student_strategy(self) -> dict[str, Any]:
        """
        Retrieve current Deliveroo student strategy and metrics.

        Used by: Insight Agent (strategic alignment),
                 Report Generator (context framing).
        """
        return self._query_and_cache(
            cache_key="student_strategy",
            search_queries=[
                "Deliveroo student strategy Plus Silver sign-up",
                "Students Y3 Launch metrics targets",
            ],
            chat_question=(
                "What is Deliveroo's current student strategy? What are the "
                "key targets, metrics, and known challenges for the student "
                "Plus Silver proposition?"
            ),
        )

    def get_plus_programme_context(self) -> dict[str, Any]:
        """
        Retrieve Plus programme metrics and strategic direction.

        Used by: Insight Agent (subscription recommendations),
                 Devil's Advocate Agent (commercial reality check).
        """
        return self._query_and_cache(
            cache_key="plus_programme",
            search_queries=[
                "Deliveroo Plus loyalty programme metrics churn conversion",
                "Plus Silver Gold DoorDash subscription strategy",
            ],
            chat_question=(
                "What are the current Deliveroo Plus programme metrics "
                "(churn, conversion, NPS) and how does the programme fit "
                "within the broader DoorDash loyalty strategy?"
            ),
        )

    def get_previous_research(self) -> dict[str, Any]:
        """
        Retrieve findings from previous student research studies.

        Used by: Triangulation Agent (cross-study validation),
                 Devil's Advocate Agent (confirmation bias check).
        """
        return self._query_and_cache(
            cache_key="previous_research",
            search_queries=[
                "student research findings Deadlines Nights Out WAD",
                "student food delivery habits research qualitative",
            ],
            chat_question=(
                "What were the key findings from previous Deliveroo student "
                "research, particularly the 'From Deadlines to Nights Out' "
                "study? What questions remain unanswered?"
            ),
        )

    def query_custom(self, topic: str, question: str) -> dict[str, Any]:
        """
        Run a custom Glean query for ad-hoc context needs.

        Used by: Deep Dive Agent (exploring specific areas).
        """
        cache_key = f"custom_{_slugify(topic)}"
        return self._query_and_cache(
            cache_key=cache_key,
            search_queries=[topic],
            chat_question=question,
        )

    # ------------------------------------------------------------------
    # Internal query and cache logic
    # ------------------------------------------------------------------

    def _query_and_cache(
        self,
        cache_key: str,
        search_queries: list[str],
        chat_question: str,
    ) -> dict[str, Any]:
        """Execute Glean queries with local caching."""

        if cache_key in self._session_cache:
            return self._session_cache[cache_key]

        if self._cache_enabled:
            cached = self._load_disk_cache(cache_key)
            if cached:
                self._session_cache[cache_key] = cached
                return cached

        result: dict[str, Any] = {
            "cache_key": cache_key,
            "queried_at": datetime.now(timezone.utc).isoformat(),
            "search_results": [],
            "chat_synthesis": None,
        }

        if self._search:
            for query in search_queries:
                try:
                    search_result = self._search(query=query)
                    result["search_results"].append({
                        "query": query,
                        "results": search_result,
                    })
                except Exception:
                    logger.exception("Glean search failed for query: %s", query)

        if self._chat:
            try:
                chat_result = self._chat(message=chat_question)
                result["chat_synthesis"] = chat_result
            except Exception:
                logger.exception("Glean chat failed for question: %s", chat_question)

        if self._cache_enabled:
            self._save_disk_cache(cache_key, result)

        self._session_cache[cache_key] = result
        return result

    def _load_disk_cache(self, cache_key: str) -> dict[str, Any] | None:
        """Load cached Glean response from disk."""
        cache_path = CACHE_DIR / f"{cache_key}.json"
        if not cache_path.exists():
            return None
        try:
            with open(cache_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            logger.warning("Failed to load Glean cache: %s", cache_path)
            return None

    def _save_disk_cache(self, cache_key: str, data: dict[str, Any]) -> None:
        """Persist Glean response to disk cache."""
        cache_path = CACHE_DIR / f"{cache_key}.json"
        try:
            with open(cache_path, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        except OSError:
            logger.exception("Failed to save Glean cache: %s", cache_path)

    def clear_cache(self) -> None:
        """Clear all cached Glean responses (forces fresh queries)."""
        self._session_cache.clear()
        if CACHE_DIR.exists():
            for f in CACHE_DIR.glob("*.json"):
                f.unlink()
            logger.info("Cleared Glean cache")


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------

def create_glean_provider(
    glean_search: Any | None = None,
    glean_chat: Any | None = None,
) -> GleanContextProvider:
    """
    Create a GleanContextProvider with the given MCP functions.

    If no MCP functions are provided, returns a provider that will return
    empty results (graceful degradation when Glean is unavailable).
    """
    provider = GleanContextProvider(
        glean_search=glean_search,
        glean_chat=glean_chat,
    )
    if not provider.is_available:
        logger.warning(
            "Glean MCP not configured. Strategic context queries will return "
            "empty results. The system will use config/business_context.yaml "
            "as the primary context source."
        )
    return provider


def _slugify(text: str) -> str:
    """Convert text to a cache-safe key."""
    import re
    slug = text.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    return slug.strip("_")[:80]
