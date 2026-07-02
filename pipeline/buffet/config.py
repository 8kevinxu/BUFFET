"""Central knobs for the buffet pipeline. All thresholds that define the
signal live here so sensitivity tests touch one file."""
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MAPPING_DIR = REPO_ROOT / "data" / "mapping"
RAW_DIR = REPO_ROOT / "pipeline" / "data" / "raw"        # gitignored HTTP cache
DERIVED_DIR = REPO_ROOT / "pipeline" / "data" / "derived"  # gitignored intermediates
WEB_DATA_DIR = REPO_ROOT / "web" / "public" / "data"     # committed, served to the SPA

# --- Data window ---
SPENDING_START = "2007-10-01"   # FY2008 Q1 — earliest USAspending award coverage
BENCHMARK = "SPY"

# --- Signal definition (pre-registered; do not tune against the holdout) ---
ZSCORE_WINDOW = 8          # trailing quarters used for mean/std
Z_BUY = 1.5                # fire "buy" at z >= this
Z_FADE = -1.5              # fire "fade" at z <= this
DOLLAR_FLOOR = 200e6       # trailing-4q obligations must exceed this (kills small-denominator noise)
KNOWLEDGE_LAG_DAYS = 135   # quarter end -> date the data is publicly knowable
                           # (90-day DoD FPDS embargo + agency submission/publication buffer)
MATERIALITY_MIN = 0.005    # surge must be >= 0.5% of the latest knowable annual
                           # revenue to fire (a $300M surge is noise for Amazon,
                           # transformative for Kratos). Tickers with no EDGAR
                           # revenue keep the un-gated rule.
FORWARD_WINDOWS = [21, 63, 126]  # trading days (~1m / 3m / 6m)
TRAIN_END = "2017-12-31"   # knowledge dates <= this are "in-sample"; later = holdout
BOOTSTRAP_N = 10_000

# --- Portfolio simulation ---
HOLD_DAYS = 126             # hold each buy signal ~6 months from its knowledge date
TRADING_COST = 0.001        # 10 bps per side
TICKER_SECTOR_ETF = {       # sector-hedge benchmark per mapping `sector`
    "defense": "ITA", "space": "ITA", "health": "XLV", "energy": "XLE",
    "it_services": "XLK", "engineering": "XLI", "logistics": "XLI",
    "services": "XLI",
}
EXTRA_BENCHMARKS = ["XLK", "XLI"]

# --- Current ranking ---
# Rank on the most recent quarter whose end is at least this many days past —
# a quarter that ended days ago has almost no reported data yet.
RANK_MIN_AGE_DAYS = 45
PICKS_N = 10
FADES_N = 5
NEWS_PER_TICKER = 8

# --- Growth projections (the leaderboard) ---
# ann_growth = w_hist * ticker_cagr(lookback) + (1-w_hist) * spy_cagr(lookback)
#              + spending tilt + signal bump (short horizons only).
# w_hist shrinks and the CAGR clamp tightens as the horizon grows — long-run
# single-stock returns mean-revert toward the market, and compounding an
# outlier CAGR for 20 years produces nonsense.
GROWTH_HORIZONS = {
    "6m":  {"years": 0.5, "lookback": 1,  "w_hist": 0.50, "clamp": (-0.25, 0.45), "bump": True,  "tilt_scale": 1.0},
    "1y":  {"years": 1.0, "lookback": 3,  "w_hist": 0.40, "clamp": (-0.25, 0.45), "bump": True,  "tilt_scale": 1.0},
    "5y":  {"years": 5.0, "lookback": 10, "w_hist": 0.35, "clamp": (-0.15, 0.25), "bump": False, "tilt_scale": 0.6},
    "20y": {"years": 20.0, "lookback": 20, "w_hist": 0.25, "clamp": (-0.08, 0.15), "bump": False, "tilt_scale": 0.3},
}
HIST_CAGR_CLAMP = (-0.50, 0.60)  # tame outlier trailing CAGRs before blending
                                 # (the final clamp is just a safety rail)
SPEND_TILT_COEF = 0.15      # fraction of 3y spending CAGR added as a tailwind tilt
SPEND_TILT_CLAMP = 0.03     # tilt capped at ±3%/yr
SPEND_TILT_MIN_BASE = 10e6  # need $10M+ trailing-4q base 3y ago to compute a trend

# --- Politeness ---
HTTP_TIMEOUT = 60
MIN_INTERVAL = {            # seconds between requests, per host
    "api.usaspending.gov": 1.0,
    "stockanalysis.com": 1.0,
    "query1.finance.yahoo.com": 1.5,
    "query2.finance.yahoo.com": 1.5,
    "news.google.com": 1.0,
    "api.gdeltproject.org": 6.0,
}
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# --- Thesis (Claude) ---
THESIS_MODEL = os.environ.get("BUFFET_THESIS_MODEL", "claude-haiku-4-5")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

for _d in (RAW_DIR, DERIVED_DIR, WEB_DATA_DIR):
    _d.mkdir(parents=True, exist_ok=True)
