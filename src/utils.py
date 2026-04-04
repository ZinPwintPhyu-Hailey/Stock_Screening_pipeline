from __future__ import annotations

from datetime import datetime, timezone
from math import isnan
from typing import Iterable, Optional

import numpy as np
import pandas as pd


US_EXCHANGES = {
    "nyse": "Exchange == NYSE",
    "nasd": "Exchange == NASD",
    "amex": "Exchange == AMEX",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def safe_float(value, default: float = np.nan) -> float:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if text in {"", "-", "None", "nan", "NaN"}:
        return default
    if text.endswith("%"):
        text = text[:-1]
    multiplier = 1.0
    if text.endswith("B"):
        multiplier = 1_000_000_000
        text = text[:-1]
    elif text.endswith("M"):
        multiplier = 1_000_000
        text = text[:-1]
    elif text.endswith("K"):
        multiplier = 1_000
        text = text[:-1]
    try:
        return float(text) * multiplier
    except ValueError:
        return default


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def minmax_score(series: pd.Series) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce")
    if s.notna().sum() <= 1:
        return pd.Series(np.where(s.notna(), 50.0, np.nan), index=series.index)
    min_v = s.min()
    max_v = s.max()
    if pd.isna(min_v) or pd.isna(max_v) or max_v == min_v:
        return pd.Series(np.where(s.notna(), 50.0, np.nan), index=series.index)
    return ((s - min_v) / (max_v - min_v) * 100).round(2)


def inverse_minmax_score(series: pd.Series) -> pd.Series:
    return 100 - minmax_score(series)


def choose_rule(value: float, rules: list[dict], field: str = "value") -> float:
    for rule in rules:
        if rule["min"] <= value < rule["max"]:
            return float(rule[field])
    return float(rules[-1][field])


def parse_earnings_days(value) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not pd.isna(value):
        return int(value)

    text = str(value).strip()
    if text in {"", "-", "nan", "None"}:
        return None

    candidates = [
        "%b %d %Y",
        "%b %d",
        "%Y-%m-%d",
        "%m/%d/%Y",
    ]
    now = utc_now().date()
    parsed_dates = []
    for fmt in candidates:
        try:
            dt = datetime.strptime(text, fmt).date()
            if fmt == "%b %d":
                dt = dt.replace(year=now.year)
                if dt < now:
                    dt = dt.replace(year=now.year + 1)
            parsed_dates.append(dt)
        except ValueError:
            continue

    if parsed_dates:
        dt = parsed_dates[0]
        return (dt - now).days

    # Handles strings such as "Apr 25 AMC" or "May 02 BMO"
    parts = text.split()
    if len(parts) >= 2:
        core = " ".join(parts[:2])
        for fmt in ["%b %d", "%B %d"]:
            try:
                dt = datetime.strptime(core, fmt).date().replace(year=now.year)
                if dt < now:
                    dt = dt.replace(year=now.year + 1)
                return (dt - now).days
            except ValueError:
                pass
    return None


def nearest_strike_below(price: float, strikes: Iterable[float]) -> float | None:
    strikes = sorted([float(x) for x in strikes if pd.notna(x)])
    below = [s for s in strikes if s <= price]
    return below[-1] if below else None


def pct(value: float) -> float:
    if value is None or (isinstance(value, float) and isnan(value)):
        return np.nan
    return value * 100.0
