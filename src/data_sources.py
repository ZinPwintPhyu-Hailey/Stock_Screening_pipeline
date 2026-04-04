from __future__ import annotations

import concurrent.futures as cf
import time
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf
from finvizfinance.screener.overview import Overview

from utils import parse_earnings_days, safe_float


@dataclass
class OptionSelection:
    premium: float
    open_interest: float
    bid_ask_spread_pct: float
    suggested_strike: float
    target_dte: int
    iv_rank: float


class FinvizUniverse:
    def __init__(self, exchanges: list[str]):
        self.exchanges = exchanges

    def fetch(self) -> pd.DataFrame:
        frames: list[pd.DataFrame] = []
        for exch in self.exchanges:
            ov = Overview()
            # No fundamental filter here; we want the US-listed common stock universe exposed by Finviz.
            ov.set_filter(filters_dict={"Exchange": exch.upper()})
            df = ov.screener_view(order="Ticker")
            if df is None or df.empty:
                continue
            frames.append(df)
        if not frames:
            return pd.DataFrame()

        out = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["Ticker"])
        rename_map = {
            "Ticker": "Ticker",
            "Company": "Company",
            "Sector": "Sector",
            "Price": "Price",
            "Earnings": "Earnings",
        }
        cols = [c for c in rename_map if c in out.columns]
        out = out[cols].rename(columns=rename_map)
        out["Price"] = out["Price"].map(safe_float)
        out["Earnings_Days"] = out.get("Earnings", pd.Series([None] * len(out))).map(parse_earnings_days)
        return out[["Ticker", "Company", "Sector", "Price", "Earnings_Days"]]


class YahooEnricher:
    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.pause = float(config["data"].get("request_pause_seconds", 0.15))
        self.max_workers = int(config["data"].get("max_workers", 8))
        self.iv_rank_mode = config["data"].get("iv_rank_mode", "proxy")

    def _beta(self, ticker: yf.Ticker) -> float:
        info = {}
        try:
            info = ticker.fast_info or {}
        except Exception:
            info = {}
        # yfinance beta is usually in info / quote_type fields, not fast_info.
        for getter in [lambda: ticker.info, lambda: ticker.get_info()]:
            try:
                info = getter() or {}
                break
            except Exception:
                continue
        return safe_float(info.get("beta"))

    def _choose_put(self, ticker_obj: yf.Ticker, spot: float, target_dte: int, valuation_date: pd.Timestamp) -> OptionSelection | None:
        expiries = list(getattr(ticker_obj, "options", []) or [])
        if not expiries:
            return None

        today = valuation_date.date()
        chain_candidates = []
        for expiry in expiries:
            exp_date = pd.Timestamp(expiry).date()
            dte = (exp_date - today).days
            if dte < self.config["filters"]["min_dte"] or dte > self.config["filters"]["max_dte"]:
                continue
            chain_candidates.append((abs(dte - target_dte), dte, expiry))

        if not chain_candidates:
            return None

        chain_candidates.sort(key=lambda x: (x[0], x[1]))
        _, chosen_dte, expiry = chain_candidates[0]
        chain = ticker_obj.option_chain(expiry)
        puts = chain.puts.copy()
        if puts.empty:
            return None

        puts = puts[(puts["strike"] < spot) & (puts["bid"] > 0) & (puts["ask"] > 0)]
        if puts.empty:
            return None

        # Estimate IV rank proxy from the available put surface for the chosen expiry.
        ivs = pd.to_numeric(puts["impliedVolatility"], errors="coerce")
        iv_min = ivs.min()
        iv_max = ivs.max()

        puts["distance_pct"] = (spot - puts["strike"]) / spot
        puts["mid"] = (puts["bid"] + puts["ask"]) / 2
        puts["spread_pct"] = np.where(puts["mid"] > 0, (puts["ask"] - puts["bid"]) / puts["mid"] * 100, np.nan)

        # The target strike gets filled later, so here we return the full chosen-expiry surface summary.
        # Caller will select the strike after target OTM is known.
        selection = OptionSelection(
            premium=np.nan,
            open_interest=np.nan,
            bid_ask_spread_pct=np.nan,
            suggested_strike=np.nan,
            target_dte=int(chosen_dte),
            iv_rank=np.nan if pd.isna(iv_min) or pd.isna(iv_max) or iv_min == iv_max else np.nan,
        )
        selection.surface = puts  # type: ignore[attr-defined]
        selection.iv_range = (iv_min, iv_max)  # type: ignore[attr-defined]
        return selection

    def _enrich_one(self, row: pd.Series) -> dict[str, Any]:
        ticker = row["Ticker"]
        spot = float(row["Price"])
        ticker_obj = yf.Ticker(ticker)
        time.sleep(self.pause)

        beta = self._beta(ticker_obj)

        # Temporary IV rank seed for rule-based target DTE calculation when only free data are available.
        # Uses 50 as neutral before exact option surface is inspected.
        temp_iv_rank = 50.0
        base_dte = self._base_dte(temp_iv_rank)
        beta_dte_adjustment = self._beta_rule(beta).get("dte_add", 0.0)
        target_dte = int(max(self.config["filters"]["min_dte"], min(self.config["filters"]["max_dte"], round(base_dte + beta_dte_adjustment))))

        valuation_date = pd.Timestamp(self.config["runtime"]["valuation_date"]).tz_localize(None)
        surface_selection = self._choose_put(ticker_obj, spot, target_dte, valuation_date)
        if surface_selection is None:
            return {
                "Ticker": ticker,
                "Beta": beta,
                "IV_Rank": np.nan,
                "Open_Interest": np.nan,
                "Bid_Ask_Spread_Pct": np.nan,
                "Premium": np.nan,
                "Suggested_Strike": np.nan,
                "Target_DTE": target_dte,
            }

        puts = surface_selection.surface  # type: ignore[attr-defined]
        iv_min, iv_max = surface_selection.iv_range  # type: ignore[attr-defined]
        current_iv = pd.to_numeric(puts["impliedVolatility"], errors="coerce").median()
        if pd.isna(current_iv) or pd.isna(iv_min) or pd.isna(iv_max) or iv_max == iv_min:
            iv_rank = 50.0
        else:
            iv_rank = float((current_iv - iv_min) / (iv_max - iv_min) * 100)
            iv_rank = max(0.0, min(100.0, iv_rank))

        base_otm = self._base_otm(iv_rank)
        beta_rule = self._beta_rule(beta)
        target_otm = max(0.01, base_otm + float(beta_rule.get("otm_add", 0.0)))
        target_strike = spot * (1 - target_otm)

        puts = puts.copy()
        puts["strike_distance_score"] = (puts["strike"] - target_strike).abs()
        chosen = puts.sort_values(["strike_distance_score", "openInterest"], ascending=[True, False]).iloc[0]

        mid = float((chosen["bid"] + chosen["ask"]) / 2)
        bid_ask_spread_pct = float(chosen["spread_pct"])
        open_interest = safe_float(chosen.get("openInterest"))
        suggested_strike = safe_float(chosen.get("strike"))

        return {
            "Ticker": ticker,
            "Beta": beta,
            "IV_Rank": round(iv_rank, 2),
            "Open_Interest": open_interest,
            "Bid_Ask_Spread_Pct": round(bid_ask_spread_pct, 2),
            "Premium": round(mid, 4),
            "Suggested_Strike": round(suggested_strike, 2),
            "Base_OTM": round(base_otm, 4),
            "Beta_OTM_Adjustment": round(float(beta_rule.get("otm_add", 0.0)), 4),
            "Target_OTM": round(target_otm, 4),
            "Base_DTE": int(self._base_dte(iv_rank)),
            "Beta_DTE_Adjustment": int(beta_rule.get("dte_add", 0)),
            "Target_DTE": int(surface_selection.target_dte),
        }

    def _base_otm(self, iv_rank: float) -> float:
        return self._choose_cfg_rule(iv_rank, self.config["otm_rules"]["base_otm_by_iv_rank"], "value")

    def _base_dte(self, iv_rank: float) -> float:
        return self._choose_cfg_rule(iv_rank, self.config["dte_rules"]["base_dte_by_iv_rank"], "value")

    def _beta_rule(self, beta: float) -> dict[str, Any]:
        rules = self.config["otm_rules"]["beta_adjustments"]
        for rule in rules:
            if rule["min"] <= beta < rule["max"]:
                return rule
        return rules[-1]

    @staticmethod
    def _choose_cfg_rule(value: float, rules: list[dict], field: str):
        for rule in rules:
            if rule["min"] <= value < rule["max"]:
                return rule[field]
        return rules[-1][field]

    def enrich(self, universe_df: pd.DataFrame) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        with cf.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [executor.submit(self._enrich_one, row) for _, row in universe_df.iterrows()]
            for future in cf.as_completed(futures):
                try:
                    rows.append(future.result())
                except Exception as exc:
                    rows.append({"Ticker": f"ERROR:{exc}"})
        out = pd.DataFrame(rows)
        out = out[out["Ticker"].astype(str).str.startswith("ERROR:") == False]
        return out
