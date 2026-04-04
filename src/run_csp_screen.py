from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from config import load_config
from data_sources import FinvizUniverse, YahooEnricher
from market_schedule import build_snapshot_context, snapshot_timestamp_text
from reporting import save_outputs
from scoring import finalize


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Finviz-based CSP screener for US-listed stocks.")
    parser.add_argument("--config", default=None, help="Path to JSON settings file")
    parser.add_argument("--out-dir", default=str(Path(__file__).resolve().parents[1] / "output"))
    args = parser.parse_args()

    config = load_config(args.config)
    context = build_snapshot_context(args.out_dir)
    config.setdefault("runtime", {})["valuation_date"] = context.snapshot_label
    universe = FinvizUniverse(config["filters"]["exchanges"]).fetch()
    if universe.empty:
        raise RuntimeError("Universe fetch returned no records.")

    target_universe_size = config["filters"].get("target_universe_size")
    if target_universe_size:
        universe = universe.head(int(target_universe_size)).copy()

    enriched = YahooEnricher(config).enrich(universe)
    merged = universe.merge(enriched, on="Ticker", how="left")
    final_df = finalize(merged, config)

    csv_path, xlsx_path = save_outputs(final_df, context.snapshot_dir, snapshot_label=context.snapshot_label)
    print(f"Market snapshot anchor: {snapshot_timestamp_text(context)}")
    print(f"Saved CSV:  {csv_path}")
    print(f"Saved XLSX: {xlsx_path}")
    print(final_df.head(20).to_string(index=False))


if __name__ == "__main__":
    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 30)
    main()
