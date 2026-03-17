"""
Base agent infrastructure shared by all analysis agents.

Provides Anthropic SDK integration with native Citations API,
LiteLLM fallback, prompt loading, structured JSON output parsing
with fallback, retry logic, and token usage logging.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import anthropic
import httpx
import litellm

from config.settings import (
    ANTHROPIC_API_KEY,
    LLM_MAX_TOKENS,
    LLM_MODEL,
    LLM_TEMPERATURE,
    PROMPTS_DIR,
)
from src.utils.citation_processor import (
    build_document_block,
    extract_citations,
    map_citations_to_participants,
)

logger = logging.getLogger(__name__)

litellm.drop_params = True


@dataclass
class AgentOutput:
    """Standard output wrapper for all agents."""

    agent_name: str
    participant_id: str
    data: dict[str, Any] | list[Any] = field(default_factory=dict)
    raw_text: str = ""
    tokens_used: int = 0
    model: str = ""
    duration_seconds: float = 0.0
    success: bool = True
    error: str = ""
    citations: list[dict[str, Any]] = field(default_factory=list)
    citation_count: int = 0


class BaseAgent:
    """
    Shared infrastructure for all research analysis agents.

    Subclasses implement ``_build_messages()`` and ``_parse_response()``
    to define agent-specific behaviour.  When ``use_citations`` is True,
    the agent uses the Anthropic SDK with native Citations API instead
    of LiteLLM.
    """

    agent_name: str = "base"
    prompt_file: str = ""
    use_citations: bool = False
    max_retries: int = 3
    retry_delay: float = 2.0

    def __init__(
        self,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ):
        self.model = model or LLM_MODEL
        self.temperature = temperature if temperature is not None else LLM_TEMPERATURE
        self.max_tokens = max_tokens or LLM_MAX_TOKENS
        self._system_prompt: str | None = None
        self._anthropic_client: anthropic.Anthropic | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, participant_id: str, context: dict[str, Any]) -> AgentOutput:
        """
        Execute the agent for a single participant.

        When ``use_citations`` is True and a transcript is available in
        context, uses the Anthropic Citations API for source attribution.
        Otherwise falls back to the standard LiteLLM path.
        """
        start = time.time()
        output = AgentOutput(
            agent_name=self.agent_name,
            participant_id=participant_id,
            model=self.model,
        )

        try:
            if self.use_citations and context.get("transcript"):
                documents = self._build_cited_content(participant_id, context)
                user_text = self._build_user_text(participant_id, context)
                response_text, raw_citations = self._call_llm_with_citations(
                    documents, user_text
                )
                output.raw_text = response_text
                output.citations = map_citations_to_participants(
                    raw_citations, participant_id
                )
                output.citation_count = len(output.citations)
                output.data = self._parse_response(response_text, participant_id)
                if isinstance(output.data, dict):
                    output.data["_citations"] = output.citations
                    output.data["_citation_count"] = output.citation_count
                output.success = True
            else:
                messages = self._build_messages(participant_id, context)
                response_text = self._call_llm(messages)
                output.raw_text = response_text
                output.data = self._parse_response(response_text, participant_id)
                output.success = True
        except Exception as e:
            logger.exception("Agent %s failed for %s", self.agent_name, participant_id)
            output.success = False
            output.error = str(e)

        output.duration_seconds = round(time.time() - start, 2)
        logger.info(
            "%s for %s: success=%s, duration=%.1fs, tokens=%d, citations=%d",
            self.agent_name, participant_id, output.success,
            output.duration_seconds, output.tokens_used, output.citation_count,
        )
        return output

    # ------------------------------------------------------------------
    # Citation document building
    # ------------------------------------------------------------------

    def _build_cited_content(
        self, participant_id: str, context: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Build document blocks for the Anthropic Citations API."""
        documents: list[dict[str, Any]] = []

        transcript = context.get("transcript", "")
        if transcript:
            documents.append(
                build_document_block(
                    f"Interview Transcript — {participant_id}",
                    transcript,
                )
            )

        notes = context.get("researcher_notes", "")
        if notes:
            documents.append(
                build_document_block(
                    f"Researcher Notes — {participant_id}",
                    notes,
                )
            )

        mod_summary = context.get("moderator_summary", "")
        if mod_summary:
            documents.append(
                build_document_block(
                    "Moderator Summary",
                    mod_summary,
                )
            )

        marvin_summary = context.get("marvin_summary", "")
        if marvin_summary:
            documents.append(
                build_document_block(
                    f"AI Summary — {participant_id}",
                    marvin_summary,
                )
            )

        return documents

    def _build_user_text(
        self, participant_id: str, context: dict[str, Any]
    ) -> str:
        """Build the non-document user text for citation calls."""
        messages = self._build_messages(participant_id, context)
        user_msg = next(
            (m["content"] for m in messages if m["role"] == "user"), ""
        )
        return user_msg

    # ------------------------------------------------------------------
    # Subclass hooks
    # ------------------------------------------------------------------

    def _build_messages(
        self, participant_id: str, context: dict[str, Any]
    ) -> list[dict[str, str]]:
        """
        Build the message list for the LLM call.

        Override in subclasses. Default implementation sends the system
        prompt and a user message with serialised context.
        """
        system = self._load_system_prompt()
        user_content = self._format_context(participant_id, context)
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user_content})
        return messages

    def _parse_response(
        self, response_text: str, participant_id: str
    ) -> dict[str, Any] | list[Any]:
        """
        Parse the LLM response into structured data.

        Override in subclasses for custom parsing. Default extracts JSON.
        """
        data = extract_json(response_text)
        return self._validate_structure(data, participant_id)

    def _validate_structure(
        self, data: dict[str, Any] | list[Any], participant_id: str
    ) -> dict[str, Any] | list[Any]:
        """
        Validate and repair common structural issues in LLM output.

        Override in subclasses for agent-specific validation. The base
        implementation checks for the ``raw_text`` fallback (meaning JSON
        extraction failed) and logs a warning.
        """
        if isinstance(data, dict) and "raw_text" in data and len(data) == 1:
            logger.warning(
                "%s (%s): LLM returned non-JSON output; downstream agents may fail",
                self.agent_name, participant_id,
            )
        return data

    def _format_context(
        self, participant_id: str, context: dict[str, Any]
    ) -> str:
        """
        Format the context dict into a user message string.

        Override in subclasses for custom formatting.
        """
        parts = [f"## Participant: {participant_id}\n"]
        for key, value in context.items():
            if isinstance(value, str):
                parts.append(f"### {key}\n\n{value}\n")
            else:
                parts.append(f"### {key}\n\n```json\n{json.dumps(value, indent=2, default=str)}\n```\n")
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # LLM calling — Anthropic Citations (primary path)
    # ------------------------------------------------------------------

    def _call_llm_with_citations(
        self,
        documents: list[dict[str, Any]],
        user_text: str,
    ) -> tuple[str, list[dict[str, Any]]]:
        """
        Call the Anthropic Messages API with document citations enabled.

        Uses the native Anthropic SDK (not LiteLLM) because citations
        require the ``document`` content block type.  Uses streaming to
        handle large outputs that may exceed Anthropic's 10-minute limit.
        """
        if self._anthropic_client is None:
            self._anthropic_client = anthropic.Anthropic(
                api_key=ANTHROPIC_API_KEY or None,
                timeout=httpx.Timeout(600.0, connect=30.0),
            )

        model_name = self.model.removeprefix("anthropic/")
        system_prompt = self._load_system_prompt()

        citation_instruction = (
            "\n\nIMPORTANT: Before providing your JSON output, write a brief "
            "\"Key Evidence\" section that quotes the most important passages "
            "from the provided documents. Then provide your structured JSON "
            "output inside a ```json code block."
        )

        user_content: list[dict[str, Any]] = []
        for doc in documents:
            user_content.append(doc)
        user_content.append({
            "type": "text",
            "text": user_text + citation_instruction,
        })

        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                kwargs: dict[str, Any] = {
                    "model": model_name,
                    "max_tokens": self.max_tokens,
                    "temperature": self.temperature,
                    "messages": [{"role": "user", "content": user_content}],
                }
                if system_prompt:
                    kwargs["system"] = system_prompt

                with self._anthropic_client.messages.stream(**kwargs) as stream:
                    response = stream.get_final_message()

                text, citations = extract_citations(response)
                usage = response.usage
                if usage:
                    total = (usage.input_tokens or 0) + (usage.output_tokens or 0)
                    logger.info(
                        "Anthropic citation call: %d input + %d output = %d tokens, %d citations",
                        usage.input_tokens or 0,
                        usage.output_tokens or 0,
                        total,
                        len(citations),
                    )
                return text, citations

            except Exception as e:
                last_error = e
                logger.warning(
                    "Citation LLM call attempt %d/%d failed: %s",
                    attempt, self.max_retries, e,
                )
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay * attempt)

        raise RuntimeError(
            f"Citation LLM call failed after {self.max_retries} attempts: {last_error}"
        )

    # ------------------------------------------------------------------
    # LLM calling — LiteLLM fallback
    # ------------------------------------------------------------------

    def _call_llm(self, messages: list[dict[str, str]]) -> str:
        """Call the LLM via LiteLLM with retry logic (fallback path)."""
        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                response = litellm.completion(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    api_key=ANTHROPIC_API_KEY or None,
                )
                text = response.choices[0].message.content or ""
                usage = getattr(response, "usage", None)
                if usage:
                    total = getattr(usage, "total_tokens", 0)
                    logger.info("LLM call: %d tokens", total)
                return text

            except Exception as e:
                last_error = e
                logger.warning(
                    "LLM call attempt %d/%d failed: %s",
                    attempt, self.max_retries, e,
                )
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay * attempt)

        raise RuntimeError(
            f"LLM call failed after {self.max_retries} attempts: {last_error}"
        )

    # ------------------------------------------------------------------
    # Prompt loading
    # ------------------------------------------------------------------

    def _load_system_prompt(self) -> str:
        """Load the system prompt from the prompts directory."""
        if self._system_prompt is not None:
            return self._system_prompt

        if not self.prompt_file:
            return ""

        path = PROMPTS_DIR / self.prompt_file
        if not path.exists():
            logger.warning("Prompt file not found: %s", path)
            return ""

        self._system_prompt = path.read_text().strip()
        return self._system_prompt


# ---------------------------------------------------------------------------
# JSON extraction utilities
# ---------------------------------------------------------------------------

def extract_json(text: str) -> dict[str, Any] | list[Any]:
    """
    Extract JSON from LLM output, handling markdown code fences.

    Tries in order:
    1. Direct JSON parse
    2. Extract from ```json ... ``` fences
    3. Find first { or [ and parse from there
    """
    text = text.strip()

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from code fences
    fence_pattern = re.compile(r"```(?:json)?\s*\n(.*?)\n```", re.DOTALL)
    matches = fence_pattern.findall(text)
    for match in matches:
        try:
            return json.loads(match.strip())
        except json.JSONDecodeError:
            continue

    # Try finding JSON start
    for start_char, end_char in [("{", "}"), ("[", "]")]:
        start_idx = text.find(start_char)
        if start_idx == -1:
            continue
        end_idx = text.rfind(end_char)
        if end_idx <= start_idx:
            continue
        candidate = text[start_idx : end_idx + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    logger.warning("Could not extract JSON from response, returning raw text wrapper")
    return {"raw_text": text}
