"""
Anthropic Citations API utilities.

Provides helpers for building document content blocks and extracting
citations from Anthropic Messages API responses.  These functions
bridge the gap between the Anthropic SDK's citation response format
and the pipeline's internal data structures.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def build_document_block(title: str, content: str) -> dict[str, Any]:
    """
    Build a document content block for the Anthropic Citations API.

    The Citations API requires source documents to be passed as
    ``type: "document"`` content blocks within the user message.
    """
    return {
        "type": "document",
        "source": {
            "type": "text",
            "media_type": "text/plain",
            "data": content,
        },
        "title": title,
        "citations": {"enabled": True},
    }


def extract_citations(response: Any) -> tuple[str, list[dict[str, Any]]]:
    """
    Extract plain text and citation objects from an Anthropic response.

    Returns
    -------
    text : str
        The concatenated text content of the response.
    citations : list[dict]
        Each citation dict has keys: ``cited_text``, ``document_title``,
        ``start_char_index``, ``end_char_index``, ``document_index``.
    """
    text_parts: list[str] = []
    citations: list[dict[str, Any]] = []

    for block in getattr(response, "content", []):
        block_type = getattr(block, "type", "")

        if block_type == "text":
            text_parts.append(getattr(block, "text", ""))

            for citation in getattr(block, "citations", []) or []:
                cit_type = getattr(citation, "type", "")
                if cit_type == "char_location":
                    citations.append({
                        "cited_text": getattr(citation, "cited_text", ""),
                        "document_title": getattr(citation, "document_title", ""),
                        "document_index": getattr(citation, "document_index", 0),
                        "start_char_index": getattr(citation, "start_char_index", 0),
                        "end_char_index": getattr(citation, "end_char_index", 0),
                    })

    return "".join(text_parts), citations


def map_citations_to_participants(
    raw_citations: list[dict[str, Any]],
    participant_id: str,
) -> list[dict[str, Any]]:
    """
    Add participant context to raw citation objects.

    Enriches each citation with the participant_id so downstream
    agents can trace evidence back to the source participant.
    """
    mapped: list[dict[str, Any]] = []
    for cit in raw_citations:
        mapped.append({
            **cit,
            "participant_id": participant_id,
        })
    return mapped
