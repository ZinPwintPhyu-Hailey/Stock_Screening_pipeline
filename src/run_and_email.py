from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from config import load_config
from dotenv import load_dotenv
import os
load_dotenv()
from data_sources import FinvizUniverse, YahooEnricher
from emailer import send_email_with_attachments
from market_schedule import build_snapshot_context, snapshot_timestamp_text
from reporting import make_email_html, save_outputs
from scoring import finalize


def main() -> None:
    parser = argparse.ArgumentParser(description="Run CSP screener and email top-50 report.")
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

    subject = f'{config["email"]["subject_prefix"]} | Top 50 by CSP_Score | Friday Close {context.snapshot_label}'
    html_body = make_email_html(final_df, subject, snapshot_note=snapshot_timestamp_text(context))

    send_email_with_attachments(
        smtp_host=config["email"]["smtp_host"],
        smtp_port=int(config["email"]["smtp_port"]),
        use_tls=bool(config["email"].get("use_tls", True)),
        sender=config["email"]["sender"],
        password_env_var=config["email"]["password_env_var"],
        recipients=config["email"]["to"],
        subject=subject,
        html_body=html_body,
        attachments=[csv_path, xlsx_path],
    )

    print(f"Market snapshot anchor: {snapshot_timestamp_text(context)}")
    print(f"Email sent. Attachments: {csv_path.name}, {xlsx_path.name}")


if __name__ == "__main__":
    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 30)
    main()
