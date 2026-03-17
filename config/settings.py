"""
Central configuration for the student research analysis system.

All paths, LLM settings, and runtime parameters are defined here.
Import this module rather than hardcoding paths or model names.
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
REFERENCE_DIR = DATA_DIR / "reference"
OUTPUT_DIR = BASE_DIR / "output"
PROMPTS_DIR = CONFIG_DIR / "prompts"

# ---------------------------------------------------------------------------
# LLM Configuration
# ---------------------------------------------------------------------------

LLM_MODEL = os.getenv("LLM_MODEL", "anthropic/claude-sonnet-4-20250514")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.1"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "4096"))

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# ---------------------------------------------------------------------------
# ChromaDB
# ---------------------------------------------------------------------------

CHROMA_PERSIST_DIR = str(PROCESSED_DIR / "chromadb")
CHROMA_COLLECTION_NAME = "student_research"

# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

AGENT_NAMES = [
    "summary",
    "analysis",
    "triangulation",
    "persona",
    "insight",
    "quality",
    "advocate",
]

HUMAN_CHECKPOINTS = {
    "analysis": "Review codebook and coded segments before triangulation",
    "persona": "Review persona groupings before insight generation",
    "advocate": "Review QA and Devil's Advocate reports before output generation",
}

# When True, the Analysis Agent runs twice per participant at different
# temperatures and produces a disagreement report.  Doubles API cost.
DUAL_PASS_CODING = bool(os.getenv("DUAL_PASS_CODING", ""))

# Minimum number of participants required for a finding to qualify as
# a full insight.  Findings below this threshold are downgraded to
# "tentative" and flagged.
MIN_INSIGHT_PARTICIPANTS = int(os.getenv("MIN_INSIGHT_PARTICIPANTS", "3"))

# ---------------------------------------------------------------------------
# Google Sheets Data Sources
# ---------------------------------------------------------------------------

GOOGLE_SHEET_ONLINE_PARTICIPANTS = "1ZNtV5wbv3XlnZ-td5wbeSYLxRGrTVbx9PdLbDi411WM"
GOOGLE_SHEET_INHOME_PARTICIPANTS = "140gtXs126Jzk4N44TGOcvOU_siEAsW9UG1Oi-gOQ74U"

# ---------------------------------------------------------------------------
# Moderator Summary Documents (from research agencies)
# ---------------------------------------------------------------------------

MODERATOR_SUMMARY_INHOME = REFERENCE_DIR / "moderator_summary_inhome.txt"
MODERATOR_SUMMARY_ONLINE = REFERENCE_DIR / "moderator_summary_online.txt"

MODERATOR_DOC_INHOME_ID = "1F7D59QG-u91b7OlByA88eYvbFtKPgz3r"
MODERATOR_DOC_ONLINE_ID = "1QmxTExL3loUMP_hFkgNOyawc11HvNaDfg_VOu2_4peI"

# ---------------------------------------------------------------------------
# Chunking (for vector store ingestion)
# ---------------------------------------------------------------------------

CHUNK_SIZE = 1500
CHUNK_OVERLAP = 200
