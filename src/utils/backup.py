"""
Pre-run backup utility.

Creates a timestamped copy of pipeline outputs that will be overwritten
during a re-run, allowing rollback if needed.

Usage:
    python -m src.utils.backup           # backup all agent outputs
    python -m src.utils.backup --list    # list existing backups
"""

from __future__ import annotations

import shutil
import logging
from datetime import datetime
from pathlib import Path

from config.settings import PROCESSED_DIR, OUTPUT_DIR

logger = logging.getLogger(__name__)

BACKUP_ROOT = Path(__file__).resolve().parent.parent.parent / "data" / "backups"

DIRS_TO_BACKUP = [
    PROCESSED_DIR / "participant_summaries",
    PROCESSED_DIR / "coded_segments",
    PROCESSED_DIR / "triangulated_data",
    PROCESSED_DIR / "personas",
    PROCESSED_DIR / "insights",
    PROCESSED_DIR / "qa_results",
    PROCESSED_DIR / "advocate_results",
    PROCESSED_DIR / "pipeline_state.json",
]


def create_backup(label: str = "") -> Path:
    """
    Snapshot current agent outputs into a timestamped backup folder.

    Returns the backup directory path.
    """
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    name = f"{ts}_{label}" if label else ts
    backup_dir = BACKUP_ROOT / name
    backup_dir.mkdir(parents=True, exist_ok=True)

    copied = 0
    for src in DIRS_TO_BACKUP:
        if not src.exists():
            continue
        dest = backup_dir / src.name
        if src.is_file():
            shutil.copy2(src, dest)
            copied += 1
        elif src.is_dir():
            shutil.copytree(src, dest)
            n_files = sum(1 for _ in dest.rglob("*") if _.is_file())
            copied += n_files

    logger.info("Backup created at %s (%d files)", backup_dir, copied)
    print(f"Backup: {backup_dir} ({copied} files)")
    return backup_dir


def list_backups() -> list[Path]:
    """List existing backup directories."""
    if not BACKUP_ROOT.exists():
        print("No backups found.")
        return []
    backups = sorted(BACKUP_ROOT.iterdir())
    for b in backups:
        n = sum(1 for _ in b.rglob("*") if _.is_file()) if b.is_dir() else 0
        print(f"  {b.name} ({n} files)")
    return backups


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    if "--list" in sys.argv:
        list_backups()
    else:
        create_backup(label="pre_v5")
