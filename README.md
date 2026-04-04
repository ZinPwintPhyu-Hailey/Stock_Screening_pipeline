# Finviz US-Listed CSP Screener + Top-50 Email Automation

This project builds a **cash-secured put (CSP) screening pipeline** using:
- **Finviz** as the **US-listed ticker universe** source (NYSE, NASDAQ, AMEX)
- **Yahoo Finance / yfinance** for price, beta, option-chain, open interest, spreads, and put premium data
- **SMTP email** for automated delivery of the **top 50 stocks ranked by CSP_Score**

## Output columns
The final output file contains these columns:

- `Ticker`
- `Company`
- `Sector`
- `Price`
- `Beta`
- `IV_Rank`
- `Earnings_Days`
- `Open_Interest`
- `Bid_Ask_Spread_Pct`
- `Premium`
- `Base_OTM`
- `Beta_OTM_Adjustment`
- `Target_OTM`
- `Suggested_Strike`
- `Base_DTE`
- `Beta_DTE_Adjustment`
- `Target_DTE`
- `Premium_to_Strike_Pct`
- `Annualized_ROI_Pct`
- `IV_Gate`
- `Earnings_Gate`
- `OI_Gate`
- `Spread_Gate`
- `All_Gates_Pass`
- `CSP_Score`
- `Decision`

## Important implementation note on IV Rank
A true 52-week **IV Rank** requires a historical time series of implied volatility. That is **not directly available from the free Finviz + Yahoo stack** in a robust way.

So this project uses a **free-data proxy**:
- It pulls the selected expiration's put surface from Yahoo.
- It computes a **cross-sectional IV percentile proxy** from the available put-chain IV values for that expiry.
- The output column is still named `IV_Rank` so your downstream workflow stays consistent, but it is a **proxy**, not a vendor-grade 52-week IV Rank.

If you later add a paid options data provider, you can keep the same output schema and swap in a true IV Rank calculation.

## Screening logic

### 1) Universe
The universe is all Finviz-covered US-listed stocks across:
- NYSE
- NASDAQ
- AMEX

### 2) Enrichment
For each ticker, the pipeline fetches:
- spot price
- beta
- nearest eligible put-chain near target DTE
- option open interest
- bid/ask spread %
- mid premium
- suggested strike

### 3) Rule engine
The project calculates:
- `Base_OTM` from IV bucket
- `Beta_OTM_Adjustment` from beta bucket
- `Target_OTM`
- `Base_DTE` from IV bucket
- `Beta_DTE_Adjustment` from beta bucket
- `Target_DTE`

### 4) Gates
The default gates are:
- IV gate: `IV_Rank >= 25`
- Earnings gate: no earnings within `21` days
- OI gate: `Open_Interest >= 500`
- Spread gate: `Bid_Ask_Spread_Pct <= 12%`

### 5) Score and decision
`CSP_Score` is a weighted score using:
- premium-to-strike
- annualized ROI
- IV rank proxy
- open interest
- spread efficiency
- earnings buffer

Decisions:
- `Strong Consider`
- `Consider`
- `Watchlist`
- `Reject`

## Project structure

```text
csp_finviz_email_project/
├─ config/
│  └─ settings.example.json
├─ output/
├─ src/
│  ├─ config.py
│  ├─ data_sources.py
│  ├─ emailer.py
│  ├─ reporting.py
│  ├─ run_and_email.py
│  ├─ run_csp_screen.py
│  ├─ scoring.py
│  └─ utils.py
├─ requirements.txt
├─ run_friday_capture_linux.sh
├─ run_friday_capture_windows.bat
├─ run_monday_email_linux.sh
├─ run_monday_email_windows.bat
├─ run_weekly_linux.sh
├─ run_weekly_windows.bat
└─ README.md
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Configure
1. Copy `config/settings.example.json` to your own file, for example `config/settings.json`
2. Edit:
   - email sender
   - email recipients
   - SMTP host/port
   - filter thresholds
   - scoring weights
3. Set your email password in an environment variable:

```bash
export CSP_EMAIL_PASSWORD='YOUR_SMTP_APP_PASSWORD'
```

For Gmail, use an **App Password**, not your normal account password.

## Friday-close workflow

This package now supports the exact cadence you requested:
- **Data fetch + screening:** after **Friday US market close**
- **Email dispatch:** **Monday morning Singapore time**

Operationally, the project works in two stages:
1. **Friday-close snapshot capture**: run on **Saturday morning Singapore time** after the US Friday close has propagated into Finviz/Yahoo delayed feeds. The output is saved under `output/snapshot_YYYY-MM-DD/`, where the date is the relevant **US Friday close**.
2. **Monday email**: send the **latest saved Friday snapshot** on Monday morning Singapore time, without refreshing market data.

That ensures the email always reflects **Friday close data**, not Monday pre-market conditions.

## Run the screener only

```bash
python src/run_csp_screen.py --config config/settings.json --out-dir output
```

This writes both:
- CSV output
- Excel output

into the `output/` folder.

## Capture the Friday-close snapshot

```bash
python src/run_csp_screen.py --config config/settings.json --out-dir output
```

This saves a dated snapshot folder such as:
- `output/snapshot_2026-03-27/csp_screen_2026-03-27.csv`
- `output/snapshot_2026-03-27/csp_screen_2026-03-27.xlsx`

## Email the latest saved Friday snapshot on Monday morning

```bash
python src/send_latest_snapshot_email.py --config config/settings.json --out-dir output
```

This reads the latest saved snapshot and emails the **top 50 by CSP_Score** in descending order, plus the full CSV/XLSX attachments.

## Run and email the top 50 immediately

```bash
python src/run_and_email.py --config config/settings.json --out-dir output
```

The email contains:
- HTML table of the top 50 by `CSP_Score`
- full CSV attachment
- full Excel attachment

## Automation

### Recommended Linux cron schedule

Capture the Friday-close dataset on **Saturday 7:30 AM Singapore time**:

```cron
30 7 * * 6 cd /path/to/csp_finviz_email_project && /usr/bin/bash run_friday_capture_linux.sh >> capture.log 2>&1
```

Send the saved Friday snapshot on **Monday 8:00 AM Singapore time**:

```cron
0 8 * * 1 cd /path/to/csp_finviz_email_project && /usr/bin/bash run_monday_email_linux.sh >> email.log 2>&1
```

### Recommended Windows Task Scheduler schedule
Create two weekly tasks:
- `run_friday_capture_windows.bat` on **Saturday 7:30 AM Singapore time**
- `run_monday_email_windows.bat` on **Monday 8:00 AM Singapore time**

### Optional one-step script
`run_weekly_linux.sh` and `run_weekly_windows.bat` still exist for same-run capture-and-email testing, but for production use your requested workflow is the two-step schedule above.

## Recommended enhancements

### For better production accuracy
Add one or more of these later:
- true historical IV source for real 52-week IV Rank
- corporate-action and ETF filtering
- price/liquidity filters such as minimum average volume
- exclusion list for binary event names or biotech
- retry logic and local caching
- richer HTML email formatting and sector summaries

### For your CSP workflow specifically
You may want to add:
- minimum premium-to-strike threshold
- minimum annualized ROI threshold
- beta-based capital haircut
- earnings blackout override list
- assignment-risk penalty for ultra-high beta names

## Caveats
- Finviz data is delayed and site structure can change.
- Yahoo option-chain coverage and earnings parsing can occasionally fail.
- Free-data IV rank is a proxy.
- This is a research and workflow tool, not execution advice.
