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
FORWARD_WINDOWS = [21, 63, 126]  # trading days (~1m / 3m / 6m)
TRAIN_END = "2017-12-31"   # knowledge dates <= this are "in-sample"; later = holdout
BOOTSTRAP_N = 10_000

# --- Current ranking ---
# Rank on the most recent quarter whose end is at least this many days past —
# a quarter that ended days ago has almost no reported data yet.
RANK_MIN_AGE_DAYS = 45
PICKS_N = 10
FADES_N = 5
NEWS_PER_TICKER = 8

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
