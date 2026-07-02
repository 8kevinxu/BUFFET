# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

A research tool that cross-references US federal contract spending
(USAspending.gov) with stock returns of ~60 public federal contractors,
backtests a materiality-weighted spending-surge signal, and renders picks in a
hacker-terminal web dashboard. **It is not financial advice and every surface
says so — keep it that way.** See `ARCHITECTURE.md` for the full design;
`README.md` for the product overview.

## Commands

```bash
make setup      # python venv (.venv) + pip install -e "pipeline[thesis]" + npm install
make refresh    # full pipeline → web/public/data/*.json (~5 min cold, seconds warm)
make dev        # vite dev server (web/) → http://localhost:5173
make build      # production build → web/dist

# Run a single pipeline stage (they are idempotent and individually runnable):
cd pipeline && ../.venv/bin/python -m buffet.refresh --stage <name>
# stages, in order: fetch_spending, audit_recipients, fetch_prices,
#   fetch_fundamentals, signals, backtest, portfolio, rank, growth, ledger,
#   awards, news, thesis, publish
```

There is **no test suite or linter**. Verifying a change means: run the
affected stages, sanity-check the printed stats, `npm run build`, and look at
the pages in a browser (headless Chrome via `playwright-core` with
`channel: 'chrome'` works — no browser download needed).

`ANTHROPIC_API_KEY` enables the `thesis` stage (Claude-written pick
narratives, default model `claude-haiku-4-5`, override with
`BUFFET_THESIS_MODEL`). Without it the stage skips gracefully — never make
the pipeline require it.

## Invariants — do not break these

- **`web/public/data/` and `pipeline/data/` are generated. Never hand-edit.**
  The two hand-authored inputs are `data/mapping/recipients.csv` and
  `data/mapping/recipient_overrides.csv` (plus `sectors.csv`).
- **`data/ledger.json` is append-only history.** Frozen cohorts record real
  entry prices at publication time — the whole point is that they can never
  be retroactively edited or regenerated. Code may append cohorts and re-mark
  to market; nothing may rewrite an existing cohort.
- **Look-ahead hygiene.** Backtest returns are only ever measured after a
  signal's `knowledge_date` (quarter end + 135 days — DoD's 90-day FPDS
  embargo plus publication buffer). Revenue for materiality uses the 10-K
  `filed` date, not the period end. Provisional quarters never become
  backtest rows. Any new feature that feeds the backtest must respect this.
- **The ranking is the quant signal.** News, award descriptions, and Claude
  theses are presentation only — they must never become inputs to the score.
- **Signal thresholds are pre-registered in `pipeline/buffet/config.py`.**
  Don't tune them against the post-2017 holdout. If you evaluate new
  parameterizations, report the comparison honestly (like the materiality
  bucket table) rather than silently switching.
- **Honesty in the UI.** Show N, show confidence intervals, say when a CI
  includes zero, label provisional data, keep the not-financial-advice banner.

## Sharp edges learned the hard way (verified live, dates noted)

- **USAspending `recipient_search_text` is fuzzy.** Single-word patterns match
  strangers (bare `CISCO` returned Dell Federal Systems and San Francisco
  entities; `MERCK` returned Merck KGaA). Use multi-word phrases. It also
  matches parent-linked subsidiaries (searching `LOCKHEED MARTIN` returns
  Sikorsky) — that is usually *correct*. The `audit_recipients` stage measures
  per-ticker contamination each refresh; tickers >25% leaked are quarantined
  from picks by `rank.py`. When adding a ticker, check the audit output and
  add `recipient_overrides.csv` verdicts for its subsidiaries.
- **Do not switch to UEI parent-hash aggregation.** Tested 2026-07-02: the
  `-P` recipient-hash rollup undercounts history ~2× (older transactions lack
  parent linkage). Pattern search + audit is the better trade.
- **Prices:** stockanalysis.com history API is primary (full adjusted history,
  field `a`). Yahoo v8 chart is fallback (requires explicit
  `period1/period2`; `range=max` silently returns sparse data; it 429-blocked
  this IP once). Stooq is dead (proof-of-work wall since ~2026-07).
- **SEC EDGAR** needs a `User-Agent` with contact info; stay well under
  10 req/s. Revenue tags changed with ASC 606 (~2017) — `fetch_fundamentals`
  merges a priority list of tags; keep that list if you touch it.
- **GDELT** penalty-boxes IPs (≥6s between requests, circuit breaker in
  `fetch_news`). Google News RSS is the primary headline source.
- **Fiscal quarters:** USAspending returns fiscal year/quarter; FY Q1 ends
  Dec 31 of the prior calendar year. Conversion lives in
  `fetch_spending.fiscal_quarter_end` — reuse it.

## Web app conventions

- Vite + React SPA, **hash routing** (works on any static host, no rewrites).
- Data loads via `useData(name)` from `web/src/useData.js` (module-scope
  cached fetch of `/data/<name>.json`); per-ticker prices are lazy-loaded
  from `/data/prices/<SYM>.json`.
- Theme lives in `web/src/theme.css`. UI chrome uses the bright neons
  (`--green #33ff99` etc.); **chart marks must use the validated darker
  series palette** (`--chart-green #0fab68`, `--chart-cyan #1489a8`,
  `--chart-amber #b57708`, `--chart-red #ef4257`) — the neons fail the
  dark-surface lightness band. Read the `dataviz` skill before adding charts.
- lightweight-charts needs `minBarSpacing` lowered to fit ~19y of daily bars.
- For fades, *negative* excess return is the win — color accordingly.

## When adding a new generated artifact

1. Write it in `publish.py` (atomic write) and add a validation gate there —
   gates raising is the self-alerting mechanism (a broken source fails CI
   loudly instead of committing empty data).
2. If it must be committed by the weekly refresh, add its path to the
   `git add` line in `.github/workflows/refresh.yml` — otherwise the cron
   will regenerate it and never commit it.
