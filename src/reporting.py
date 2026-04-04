from __future__ import annotations

import html
from pathlib import Path

import pandas as pd


def save_outputs(df: pd.DataFrame, out_dir: str | Path, snapshot_label: str | None = None) -> tuple[Path, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = snapshot_label or pd.Timestamp.utcnow().strftime("%Y%m%d_%H%M%S")
    csv_path = out_dir / f"csp_screen_{stamp}.csv"
    xlsx_path = out_dir / f"csp_screen_{stamp}.xlsx"
    df.to_csv(csv_path, index=False)
    df.to_excel(xlsx_path, index=False)
    return csv_path, xlsx_path


def make_email_html(df: pd.DataFrame, title: str, snapshot_note: str | None = None) -> str:
    top50 = df.head(50).copy()
    show_cols = [
        "Ticker",
        "Company",
        "Sector",
        "Price",
        "Beta",
        "IV_Rank",
        "Earnings_Days",
        "Open_Interest",
        "Bid_Ask_Spread_Pct",
        "Premium",
        "Suggested_Strike",
        "Target_DTE",
        "Premium_to_Strike_Pct",
        "Annualized_ROI_Pct",
        "CSP_Score",
        "Decision",
    ]
    table_html = top50[show_cols].to_html(index=False, border=0, justify="left")
    return f"""
    <html>
      <body>
        <h2>{html.escape(title)}</h2>
        <p>Attached are the full CSP screen outputs. The table below shows the top 50 names ranked by <b>CSP_Score</b>.</p>
        {f"<p><b>Market data snapshot:</b> {html.escape(snapshot_note)}</p>" if snapshot_note else ""}
        {table_html}
      </body>
    </html>
    """
