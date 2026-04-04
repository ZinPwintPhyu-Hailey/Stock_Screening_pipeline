from __future__ import annotations

import numpy as np
import pandas as pd

from utils import clamp, inverse_minmax_score, minmax_score


OUTPUT_COLUMNS = [
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
    "Base_OTM",
    "Beta_OTM_Adjustment",
    "Target_OTM",
    "Suggested_Strike",
    "Base_DTE",
    "Beta_DTE_Adjustment",
    "Target_DTE",
    "Premium_to_Strike_Pct",
    "Annualized_ROI_Pct",
    "IV_Gate",
    "Earnings_Gate",
    "OI_Gate",
    "Spread_Gate",
    "All_Gates_Pass",
    "CSP_Score",
    "Decision",
]


def finalize(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    df = df.copy()
    df["Premium_to_Strike_Pct"] = np.where(
        (df["Suggested_Strike"] > 0) & df["Premium"].notna(),
        df["Premium"] / df["Suggested_Strike"] * 100,
        np.nan,
    )
    df["Annualized_ROI_Pct"] = np.where(
        (df["Target_DTE"] > 0) & df["Premium_to_Strike_Pct"].notna(),
        df["Premium_to_Strike_Pct"] * (365 / df["Target_DTE"]),
        np.nan,
    )

    filters = config["filters"]
    df["IV_Gate"] = df["IV_Rank"] >= filters["min_iv_rank"]
    df["Earnings_Gate"] = df["Earnings_Days"].isna() | (df["Earnings_Days"] >= filters["max_earnings_days"])
    df["OI_Gate"] = df["Open_Interest"] >= filters["min_open_interest"]
    df["Spread_Gate"] = df["Bid_Ask_Spread_Pct"] <= filters["max_bid_ask_spread_pct"]
    df["All_Gates_Pass"] = df[["IV_Gate", "Earnings_Gate", "OI_Gate", "Spread_Gate"]].all(axis=1)

    weights = config["scoring"]["weights"]
    premium_score = minmax_score(df["Premium_to_Strike_Pct"]).fillna(0)
    roi_score = minmax_score(df["Annualized_ROI_Pct"]).fillna(0)
    iv_score = minmax_score(df["IV_Rank"]).fillna(0)
    oi_score = minmax_score(np.log1p(df["Open_Interest"].fillna(0))).fillna(0)
    spread_score = inverse_minmax_score(df["Bid_Ask_Spread_Pct"]).fillna(0)

    earnings_buffer = df["Earnings_Days"].fillna(999).clip(0, 120)
    earnings_score = minmax_score(earnings_buffer).fillna(50)

    raw_score = (
        premium_score * weights["premium_to_strike"]
        + roi_score * weights["annualized_roi"]
        + iv_score * weights["iv_rank"]
        + oi_score * weights["open_interest"]
        + spread_score * weights["spread_efficiency"]
        + earnings_score * weights["earnings_buffer"]
    )

    gate_penalty = np.where(df["All_Gates_Pass"], 1.0, 0.70)
    df["CSP_Score"] = (raw_score * gate_penalty).round(2)

    strong = config["decision_thresholds"]["strong_consider"]
    consider = config["decision_thresholds"]["consider"]

    decisions = []
    for _, row in df.iterrows():
        if not row["All_Gates_Pass"]:
            decisions.append("Reject")
        elif row["CSP_Score"] >= strong:
            decisions.append("Strong Consider")
        elif row["CSP_Score"] >= consider:
            decisions.append("Consider")
        else:
            decisions.append("Watchlist")
    df["Decision"] = decisions

    for col in OUTPUT_COLUMNS:
        if col not in df.columns:
            df[col] = np.nan

    return df[OUTPUT_COLUMNS].sort_values(["CSP_Score", "Annualized_ROI_Pct"], ascending=[False, False]).reset_index(drop=True)
