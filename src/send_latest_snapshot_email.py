from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from config import load_config
from dotenv import load_dotenv
import os
load_dotenv()
from emailer import send_email_with_attachments
from market_schedule import latest_snapshot_files, latest_snapshot_dir, now_sg
from reporting import make_email_html


def main() -> None:
    parser = argparse.ArgumentParser(description="Email the latest saved Friday-close CSP snapshot.")
    parser.add_argument("--config", default=None, help="Path to JSON settings file")
    parser.add_argument("--out-dir", default=str(Path(__file__).resolve().parents[1] / "output"))
    args = parser.parse_args()

    config = load_config(args.config)
    csv_path, xlsx_path = latest_snapshot_files(args.out_dir)
    df = pd.read_csv(csv_path)
    snapshot_label = latest_snapshot_dir(args.out_dir).name.replace("snapshot_", "")

    subject = f'{config["email"]["subject_prefix"]} | Top 50 by CSP_Score | Friday Close {snapshot_label} | Sent {now_sg():%Y-%m-%d %H:%M SGT}'
    html_body = make_email_html(
        df,
        subject,
        snapshot_note=f"Friday close snapshot date: {snapshot_label} (US market close); email dispatched Monday morning Singapore time.",
    )

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

    print(f"Email sent from snapshot {snapshot_label}: {csv_path.name}, {xlsx_path.name}")


if __name__ == "__main__":
    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 30)
    main()
