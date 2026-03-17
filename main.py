#!/usr/bin/env python3
"""
CLI entry point for the student research analysis system.

Usage:
    python main.py ingest
    python main.py analyze [--agent NAME] [--participants P001,P002]
    python main.py generate [--output NAME]
    python main.py sync-google [--sheets|--docs|--guides]
    python main.py sync-marvin
    python main.py deep-dive --focus "topic" [--participants P001,P002]
    python main.py status
    python main.py validate
    python main.py export --format json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config.settings import BASE_DIR, PROCESSED_DIR, REFERENCE_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")


def cmd_ingest(args: argparse.Namespace) -> None:
    """Load all data sources into the vector store."""
    from src.loaders.marvin_loader import MarvinLoader
    from src.storage.vector_store import VectorStore

    logger.info("Starting data ingestion...")
    vs = VectorStore()

    # Load participant map
    pmap_path = REFERENCE_DIR / "participant_map.json"
    with open(pmap_path) as f:
        pmap = json.load(f)

    # Load cached transcripts into vector store
    transcript_dir = PROCESSED_DIR / "transcripts"
    loaded = 0
    if transcript_dir.exists():
        for path in transcript_dir.glob("*.json"):
            with open(path) as f:
                data = json.load(f)
            text = data.get("transcript_text", "")
            if not text:
                continue
            file_id = data.get("file_id", "")
            file_name = data.get("file_name", "")

            pid = _file_id_to_participant(file_id, pmap)
            pdata = pmap.get(pid, {}) if pid else {}

            vs.add_document(
                doc_id=f"transcript_{pid or file_id}",
                text=text,
                metadata={
                    "participant_id": pid or "",
                    "source": "interview",
                    "file_id": str(file_id),
                    "file_name": file_name,
                    "segment": pdata.get("segment", ""),
                    "interview_type": pdata.get("interview_type", ""),
                },
            )
            loaded += 1

    # Load researcher notes
    notes_dir = PROCESSED_DIR / "researcher_notes"
    if notes_dir.exists():
        for path in notes_dir.glob("*.md"):
            pid = path.stem.split("_")[0].upper()
            vs.add_document(
                doc_id=f"notes_{pid}",
                text=path.read_text(),
                metadata={"participant_id": pid, "source": "researcher_notes"},
            )
            loaded += 1

    logger.info("Ingestion complete: %d documents loaded, %d total in store", loaded, vs.count)


def cmd_analyze(args: argparse.Namespace) -> None:
    """Run analysis agents."""
    from src.pipeline.orchestrator import PipelineOrchestrator

    orch = PipelineOrchestrator()
    pids = args.participants.split(",") if args.participants else None

    if args.agent:
        results = orch.run_agent(args.agent, pids)
    else:
        results = orch.run_full(pids, skip_checkpoints=args.skip_checkpoints)

    logger.info("Analysis results: %s", json.dumps(results, indent=2, default=str))


def cmd_generate(args: argparse.Namespace) -> None:
    """Generate deliverables."""
    from src.generators.competitive_map import generate_competitive_map
    from src.generators.emotional_journey import generate_emotional_journeys
    from src.generators.journey_viz import generate_journey_maps
    from src.generators.language_patterns import generate_language_patterns
    from src.generators.micro_moments import (
        get_in_home_participants,
        save_outputs as save_micro_moments,
        _load_coded_segments,
    )
    from src.generators.persona_cards import generate_persona_cards
    from src.generators.plus_strategy_generator import generate_plus_strategy
    from src.generators.quote_library import generate_quote_library
    from src.generators.report_generator import generate_report
    from src.generators.tension_map import generate_tension_map
    from src.generators.topline_summary import generate_topline_summary
    from src.generators.value_equations import generate_value_equations

    def _generate_micro_moments():
        participants = get_in_home_participants()
        coded: dict[str, list] = {}
        for p in participants:
            pid = p.get("participant_id", "")
            if pid:
                segs = _load_coded_segments(pid)
                if segs:
                    coded[pid.upper()] = segs
        return save_micro_moments(participants, coded or None)

    version = getattr(args, "version", "")

    generators = {
        "report": lambda: generate_report(version=version),
        "personas": generate_persona_cards,
        "journeys": generate_journey_maps,
        "quotes": generate_quote_library,
        "tensions": generate_tension_map,
        "emotional": generate_emotional_journeys,
        "competitive": generate_competitive_map,
        "language": generate_language_patterns,
        "value": generate_value_equations,
        "plus_strategy": generate_plus_strategy,
        "topline": lambda: generate_topline_summary(version=version),
        "micro_moments": _generate_micro_moments,
    }

    enrichment_keys = {"tensions", "emotional", "competitive", "language", "value"}

    if args.output == "enrichments":
        targets = enrichment_keys
    elif args.output:
        targets = {args.output}
    else:
        targets = set(generators.keys())

    for name in targets:
        gen = generators.get(name)
        if gen:
            logger.info("Generating: %s", name)
            try:
                result = gen()
                logger.info("Generated: %s -> %s", name, result)
            except Exception:
                logger.exception("Failed to generate: %s", name)
        else:
            logger.warning("Unknown generator: %s", name)


def cmd_sync_google(args: argparse.Namespace) -> None:
    """Sync data from Google Workspace."""
    logger.info(
        "Google Workspace sync requires MCP functions. "
        "Use notebook 01_ingest_data.ipynb or pass MCP functions programmatically."
    )


def cmd_sync_marvin(args: argparse.Namespace) -> None:
    """Sync transcripts from Marvin."""
    logger.info(
        "Marvin sync requires MCP functions. "
        "Use notebook 01_ingest_data.ipynb or pass MCP functions programmatically."
    )


def cmd_deep_dive(args: argparse.Namespace) -> None:
    """Run a guided deep dive analysis."""
    from src.agents.deep_dive_agent import DeepDiveAgent
    from src.pipeline.orchestrator import PipelineOrchestrator

    orch = PipelineOrchestrator()
    agent = DeepDiveAgent()

    pids = args.participants.split(",") if args.participants else []
    context = {
        "focus_area": args.focus or "",
        "specific_questions": [args.questions] if args.questions else [],
        "participants_to_revisit": pids,
        "dive_id": "DD_001",
    }

    # Load transcripts for specified participants
    if pids:
        transcripts = {}
        for pid in pids:
            t = orch._load_transcript(pid, orch.participant_map.get(pid, {}))
            if t:
                transcripts[pid] = t
        context["transcripts"] = transcripts

    output = agent.run("deep_dive", context)
    logger.info("Deep dive result: success=%s", output.success)
    if output.data:
        logger.info(json.dumps(output.data, indent=2, default=str)[:2000])


def cmd_status(args: argparse.Namespace) -> None:
    """Check pipeline progress."""
    from src.storage.state_manager import StateManager

    state = StateManager()
    summary = state.get_pipeline_summary()
    print(json.dumps(summary, indent=2))


def cmd_validate(args: argparse.Namespace) -> None:
    """Verify data integrity."""
    issues: list[str] = []

    pmap_path = REFERENCE_DIR / "participant_map.json"
    if not pmap_path.exists():
        issues.append("participant_map.json not found")
    else:
        with open(pmap_path) as f:
            pmap = json.load(f)
        pids = [k for k in pmap if not k.startswith("_")]
        logger.info("Participant map: %d participants", len(pids))

        marvin_count = sum(
            1 for pid in pids
            if isinstance(pmap[pid].get("sources", {}).get("interview"), dict)
            and pmap[pid]["sources"]["interview"].get("source") == "marvin"
            and pmap[pid]["sources"]["interview"].get("file_id")
        )
        logger.info("Participants with Marvin transcripts: %d", marvin_count)

    transcript_dir = PROCESSED_DIR / "transcripts"
    if transcript_dir.exists():
        cached = list(transcript_dir.glob("*.json"))
        logger.info("Cached transcripts: %d", len(cached))
    else:
        issues.append("No cached transcripts found")

    if issues:
        logger.warning("Validation issues: %s", issues)
    else:
        logger.info("Validation passed")


def cmd_export(args: argparse.Namespace) -> None:
    """Export all analysis data."""
    from config.settings import OUTPUT_DIR

    export_dir = OUTPUT_DIR / "data_exports"
    export_dir.mkdir(parents=True, exist_ok=True)

    dirs_to_export = [
        ("participant_summaries", PROCESSED_DIR / "participant_summaries"),
        ("coded_segments", PROCESSED_DIR / "coded_segments"),
        ("personas", PROCESSED_DIR / "personas"),
        ("insights", PROCESSED_DIR / "insights"),
    ]

    for name, src_dir in dirs_to_export:
        if src_dir.exists():
            all_data = {}
            for f in src_dir.glob("*.json"):
                with open(f) as fh:
                    all_data[f.stem] = json.load(fh)
            out_path = export_dir / f"all_{name}.json"
            with open(out_path, "w") as fh:
                json.dump(all_data, fh, indent=2, ensure_ascii=False)
            logger.info("Exported %s: %d files", name, len(all_data))

    logger.info("Export complete -> %s", export_dir)


def _file_id_to_participant(file_id: int | str, pmap: dict) -> str | None:
    """Resolve a Marvin file_id to a participant ID."""
    file_id = int(file_id) if file_id else 0
    for pid, pdata in pmap.items():
        if pid.startswith("_"):
            continue
        interview = pdata.get("sources", {}).get("interview", {})
        if isinstance(interview, dict) and interview.get("file_id") == file_id:
            return pid
    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Student Research Analysis System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ingest
    subparsers.add_parser("ingest", help="Load all data sources into vector store")

    # analyze
    p_analyze = subparsers.add_parser("analyze", help="Run analysis agents")
    p_analyze.add_argument("--agent", choices=[
        "summary", "analysis", "triangulation", "persona",
        "insight", "quality", "advocate",
    ])
    p_analyze.add_argument("--participants", help="Comma-separated participant IDs")
    p_analyze.add_argument("--skip-checkpoints", action="store_true")

    # generate
    p_gen = subparsers.add_parser("generate", help="Generate deliverables")
    p_gen.add_argument("--output", choices=[
        "report", "topline", "personas", "journeys", "quotes",
        "tensions", "emotional", "competitive", "language", "value",
        "plus_strategy", "micro_moments", "enrichments",
    ])
    p_gen.add_argument("--version", default="", help="Version suffix (e.g. 'v2')")

    # sync
    subparsers.add_parser("sync-google", help="Sync from Google Workspace")
    subparsers.add_parser("sync-marvin", help="Sync from Marvin")

    # deep-dive
    p_dd = subparsers.add_parser("deep-dive", help="Guided deep dive analysis")
    p_dd.add_argument("--focus", help="Focus area for deep dive")
    p_dd.add_argument("--participants", help="Comma-separated participant IDs")
    p_dd.add_argument("--questions", help="Specific question to answer")

    # status / validate / export
    subparsers.add_parser("status", help="Check pipeline progress")
    subparsers.add_parser("validate", help="Verify data integrity")
    p_export = subparsers.add_parser("export", help="Export all data")
    p_export.add_argument("--format", default="json", choices=["json"])

    args = parser.parse_args()

    commands = {
        "ingest": cmd_ingest,
        "analyze": cmd_analyze,
        "generate": cmd_generate,
        "sync-google": cmd_sync_google,
        "sync-marvin": cmd_sync_marvin,
        "deep-dive": cmd_deep_dive,
        "status": cmd_status,
        "validate": cmd_validate,
        "export": cmd_export,
    }

    handler = commands.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
