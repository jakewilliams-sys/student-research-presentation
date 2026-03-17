"""
Quote verification utility.

Fuzzy-matches quoted text segments against the original interview
transcript to verify that LLM-generated quotes are grounded in the
source material.

Verification statuses:
- VERIFIED   : similarity >= 70%  (genuine quote or minor transcription variation)
- PARAPHRASED: similarity 50-69%  (captures the meaning but rephrased)
- UNVERIFIED : similarity < 50%   (not reliably matched to transcript)
"""

from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher
from typing import Any

logger = logging.getLogger(__name__)

VERIFIED_THRESHOLD = 0.70
PARAPHRASED_THRESHOLD = 0.50

_SPEAKER_LABEL = re.compile(r"\bspk_\d+\s*:\s*", re.IGNORECASE)
_INTERVIEWER_LABEL = re.compile(
    r"^(interviewer|moderator|researcher|speaker\s*\d+)\s*:\s*",
    re.IGNORECASE | re.MULTILINE,
)


def verify_quotes(
    coded_segments: list[dict[str, Any]],
    transcript: str,
) -> list[dict[str, Any]]:
    """
    Verify each coded segment's quote against the original transcript.

    Adds a ``_quote_verification`` dict to each segment with keys:
    - ``status``: "VERIFIED", "PARAPHRASED", or "UNVERIFIED"
    - ``similarity``: float similarity score 0-1
    - ``best_match``: the closest matching substring from the transcript
    """
    transcript_clean = _clean_text(transcript)
    transcript_words = transcript_clean.split()

    verified_count = 0
    paraphrased_count = 0
    unverified_count = 0

    for seg in coded_segments:
        if not isinstance(seg, dict):
            continue

        quote = seg.get("text", "")
        if not quote or len(quote.strip()) < 10:
            seg["_quote_verification"] = {
                "status": "VERIFIED",
                "similarity": 1.0,
                "best_match": "(too short to verify)",
            }
            verified_count += 1
            continue

        similarity, best_match = _find_best_match(quote, transcript_clean, transcript_words)

        if similarity >= VERIFIED_THRESHOLD:
            status = "VERIFIED"
            verified_count += 1
        elif similarity >= PARAPHRASED_THRESHOLD:
            status = "PARAPHRASED"
            paraphrased_count += 1
        else:
            status = "UNVERIFIED"
            unverified_count += 1

        seg["_quote_verification"] = {
            "status": status,
            "similarity": round(similarity, 2),
            "best_match": best_match[:300] if best_match else "",
        }

    total = verified_count + paraphrased_count + unverified_count
    logger.info(
        "Quote verification: %d segments — %d VERIFIED, %d PARAPHRASED, %d UNVERIFIED",
        total, verified_count, paraphrased_count, unverified_count,
    )

    if unverified_count > 0:
        logger.warning(
            "%d quote(s) could not be matched to the transcript (similarity < %d%%)",
            unverified_count,
            int(PARAPHRASED_THRESHOLD * 100),
        )

    return coded_segments


def _find_best_match(
    quote: str,
    transcript_clean: str,
    transcript_words: list[str],
) -> tuple[float, str]:
    """
    Find the best match for a quote in the transcript using a
    word-level sliding window for efficiency.
    """
    quote_clean = _clean_text(quote)
    if not quote_clean or not transcript_clean:
        return 0.0, ""

    # Strategy 1: exact substring match
    if quote_clean in transcript_clean:
        return 1.0, quote_clean

    # Strategy 2: word-level sliding window (much faster than char-level)
    quote_words = quote_clean.split()
    qlen = len(quote_words)

    if qlen == 0:
        return 0.0, ""

    tlen = len(transcript_words)
    window_words = min(tlen, max(qlen * 2, 30))
    step = max(qlen // 3, 3)

    best_score = 0.0
    best_match = ""

    for start in range(0, max(1, tlen - qlen // 2), step):
        end = min(start + window_words, tlen)
        window_text = " ".join(transcript_words[start:end])

        score = SequenceMatcher(None, quote_clean, window_text, autojunk=False).ratio()

        if score > best_score:
            best_score = score
            best_match = " ".join(
                transcript_words[start : min(start + qlen + 5, tlen)]
            )
            if score >= 0.95:
                break

    return best_score, best_match


def _clean_text(text: str) -> str:
    """
    Normalise text for comparison: remove speaker labels,
    lowercase, strip punctuation, collapse whitespace.
    """
    text = _SPEAKER_LABEL.sub(" ", text)
    text = _INTERVIEWER_LABEL.sub(" ", text)
    text = text.lower()
    text = re.sub(r"[^\w\s']", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
