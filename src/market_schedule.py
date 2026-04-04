from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

SG_TZ = ZoneInfo("Asia/Singapore")
ET_TZ = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class SnapshotContext:
    run_ts_sg: datetime
    anchor_friday_et: datetime
    snapshot_label: str
    snapshot_dir: Path


def now_sg() -> datetime:
    return datetime.now(SG_TZ)


def latest_completed_friday_et(run_ts_sg: datetime | None = None) -> datetime:
    run_ts_sg = run_ts_sg or now_sg()
    run_ts_et = run_ts_sg.astimezone(ET_TZ)

    weekday = run_ts_et.weekday()  # Mon=0 ... Sun=6
    days_since_friday = (weekday - 4) % 7
    friday = (run_ts_et - timedelta(days=days_since_friday)).replace(hour=16, minute=0, second=0, microsecond=0)

    # Before Friday 4:00 PM ET, the latest completed Friday is the prior week.
    if weekday == 4 and run_ts_et < friday:
        friday = friday - timedelta(days=7)

    return friday


def build_snapshot_context(out_dir: str | Path, run_ts_sg: datetime | None = None) -> SnapshotContext:
    run_ts_sg = run_ts_sg or now_sg()
    anchor_friday = latest_completed_friday_et(run_ts_sg)
    snapshot_label = anchor_friday.strftime("%Y-%m-%d")
    snapshot_dir = Path(out_dir) / f"snapshot_{snapshot_label}"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    return SnapshotContext(
        run_ts_sg=run_ts_sg,
        anchor_friday_et=anchor_friday,
        snapshot_label=snapshot_label,
        snapshot_dir=snapshot_dir,
    )


def latest_snapshot_dir(out_dir: str | Path) -> Path:
    base = Path(out_dir)
    candidates = sorted([p for p in base.glob("snapshot_*") if p.is_dir()])
    if not candidates:
        raise FileNotFoundError(f"No snapshot directories found in {base}")
    return candidates[-1]


def latest_snapshot_files(out_dir: str | Path) -> tuple[Path, Path]:
    snap_dir = latest_snapshot_dir(out_dir)
    csv_files = sorted(snap_dir.glob("*.csv"))
    xlsx_files = sorted(snap_dir.glob("*.xlsx"))
    if not csv_files or not xlsx_files:
        raise FileNotFoundError(f"Snapshot exists but CSV/XLSX files are missing in {snap_dir}")
    return csv_files[-1], xlsx_files[-1]


def snapshot_timestamp_text(context: SnapshotContext) -> str:
    return pd.Timestamp(context.anchor_friday_et).strftime("%Y-%m-%d Friday close (US/Eastern)")
