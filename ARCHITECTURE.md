# Architecture

`buffet` is three layers with a one-way data flow:

```
 external sources ──▶ pipeline (Python) ──▶ committed JSON ──▶ SPA (React)
 USAspending API        pipeline/buffet/      web/public/data/    web/src/
 stockanalysis/Yahoo    14 idempotent          + data/ledger.json
 SEC EDGAR XBRL         stages
 Google News / GDELT
 Anthropic API
```

The web app is a **static export with zero runtime backends** — every number
it shows was computed and validated at refresh time. That makes deploys
trivial (any static host), keeps the data reviewable in git diffs, and means
a broken scrape can't take the site down (it fails CI instead).

## 1. The pipeline (`pipeline/buffet/`)

`python -m buffet.refresh` runs the stages in order; `--stage <name>` runs
one. Every stage reads its inputs from `pipeline/data/derived/`, writes one
derived artifact back, and is safe to re-run: all HTTP goes through
`cache.py`, a keyed on-disk cache with per-host rate limiting, retries, and
stale-cache fallback (a flaky source degrades to yesterday's data rather than
failing a run that already has data).

| # | Stage | Source | Produces | Fatal? |
|---|-------|--------|----------|--------|
| 1 | `fetch_spending` | USAspending `spending_over_time` | quarterly contract obligations per ticker (FY2008→now) + per agency | yes |
| 2 | `audit_recipients` | USAspending recipient + category APIs | per-ticker matched-entity list and **contamination %** | no |
| 3 | `fetch_prices` | stockanalysis.com (primary), Yahoo v8 (fallback) | daily adjusted closes, universe + SPY + sector ETFs | yes |
| 4 | `fetch_fundamentals` | SEC EDGAR XBRL companyfacts | point-in-time annual revenue per ticker | no |
| 5 | `signals` | 1 + 4 | z-score rows per (ticker, quarter) with materiality + fired flags | yes |
| 6 | `backtest` | 5 + 3 | per-signal forward outcomes, aggregates, CIs, materiality buckets | yes |
| 7 | `portfolio` | 5 + 3 | monthly costed portfolio simulation vs SPY + sector basket | yes |
| 8 | `rank` | 5 + 6 + 2 | current picks/fades (quarantine applied) | yes |
| 9 | `growth` | 3 + 1 + 8 | projected growth per horizon with P10–P90 bands | yes |
| 10 | `ledger` | 8 + 3 | frozen pick cohorts (`data/ledger.json`) marked to market | yes |
| 11 | `awards` | USAspending `spending_by_transaction` | surge drill-downs + last-60-day award feed | no |
| 12 | `news` | Google News RSS (GDELT fallback) | headlines for picked tickers | no |
| 13 | `thesis` | Anthropic API (`claude-haiku-4-5`) | ~120-word thesis + risks per pick, cached by input hash | no |
| 14 | `publish` | everything | validated artifacts → `web/public/data/` | yes |

"Fatal? no" stages are enrichment: their failure prints a warning and the run
continues (thesis keeps its previous output and flags itself stale).

`publish` is also the **self-alerting mechanism**: it validates row counts and
schema expectations and raises on failure, so an upstream site redesign fails
the weekly GitHub Action (email) instead of silently committing empty data.

### The signal

For each ticker, quarterly federal contract obligations are aggregated by
recipient-name patterns (`data/mapping/recipients.csv`; see "Recipient
matching" below). Then per (ticker, quarter):

- `z` = (this quarter − trailing 8-quarter mean) / trailing 8-quarter std
- `materiality` = (this quarter − trailing mean) / latest annual revenue
  *knowable at the time* (10-K `filed` date ≤ knowledge date)
- **LONG fires** at `z ≥ +1.5` AND trailing-4q obligations ≥ $200M AND
  `materiality ≥ 0.5%` of revenue (the gate is evidence-based: sub-0.5%
  surges backtest at 44% hit / −0.5% excess; 0.5–2% at 66% / +5.9%)
- **FADE fires** symmetrically (and does not work — the UI says so)

All thresholds live in `config.py` and were fixed on pre-2018 data
("in-sample"); 2018+ is reported separately as the holdout.

### Look-ahead defenses (the part that makes the backtest meaningful)

1. **Knowledge date** = quarter end + 135 days (DoD's 90-day FPDS embargo +
   submission/publication buffer). Entries happen on the first trading day
   *after* it; quarters whose knowledge date hasn't passed are `provisional`
   — rankable (labeled) but never backtest rows.
2. **Point-in-time revenue** — materiality uses the earliest filing of each
   annual period, matched by `filed` date.
3. **Walk-forward split** — thresholds chosen on 2010–2017; holdout reported
   with its own stats.
4. **Survivorship disclosure** — the universe was curated in 2026; delisted
   losers are invisible. Not fixable with free data; disclosed in the UI.

### Recipient matching (the crux, and its audit)

USAspending recipients are legal entities, not tickers. Matching is by
`recipient_search_text` name patterns, which is **fuzzy**: it matches
parent-linked subsidiaries (searching "LOCKHEED MARTIN" correctly returns
Sikorsky) but single-word patterns also match strangers (bare "CISCO"
returned Dell Federal Systems). Design response, in layers:

1. **Multi-word patterns only** for ambiguous names (`recipients.csv`).
2. **`audit_recipients`** re-measures every ticker's contamination on the
   live API each refresh: it pulls the top recipients the patterns actually
   aggregate, classifies each name with a word-boundary/prefix rule plus
   curated verdicts (`recipient_overrides.csv` — "Sikorsky IS Lockheed",
   "CADDELL is NOT Dell"), and publishes leak% + top leaks per ticker.
3. **Quarantine**: `rank.py` refuses to pick tickers >25% contaminated
   (currently Jacobs — Amentum's novated contracts are still parent-linked
   to Jacobs server-side and cannot be excluded by patterns).

UEI parent-hash aggregation was evaluated and **rejected**: the `-P` rollup
undercounts history roughly 2× because older transactions lack parent
linkage (verified 2026-07-02, LMT FY2024Q1: $5.3B via hash vs $12.0B real).

### Growth projections

An explicitly-labeled toy model, decomposed so the UI can show its work:
`ann = w·hist_CAGR + (1−w)·SPY_CAGR(full lookback) + spending tilt + signal bump`,
where `w` shrinks with horizon and with missing history, the tilt (damped 3y
obligations CAGR) decays at long horizons, the bump (backtested mean excess)
applies only at 6m/1y when a LONG actually fired, and per-horizon ceilings
cap compounding (capped rows are tagged). Each row carries a **P10–P90 band**
from the ticker's own rolling-window outcome distribution (universe pool for
young tickers), centered on the projection.

### The paper ledger

`data/ledger.json` (committed, append-only) freezes each new ranking
quarter's fired buys with real entry prices at publication time. Refreshes
re-mark cohorts to market vs SPY but never edit them — the strategy
accumulates a live out-of-sample record in git history that cannot be
curve-fit after the fact.

## 2. The data contract (`web/public/data/`)

All artifacts are committed so the site deploys with no build-time fetching
(the hoopmap model). Key files: `meta.json` (run info, data-through dates,
signal config), `picks.json`, `signals.json`, `backtest.json`,
`portfolio.json`, `growth.json`, `ledger.json`, `awards.json`, `news.json`,
`thesis.json`, `quotes.json`, `universe.json`, `audit.json`, `spending.json`,
and lazy-loaded per-symbol `prices/<SYM>.json` (trimmed to 2007+).

## 3. The web app (`web/`)

Vite + React SPA, hash-routed, five pages:

- **TERMINAL** (`Dashboard.jsx`) — picks/fades boards (materiality column,
  expandable thesis + headlines), LIVE AWARDS (last-60-day transactions),
  sector pulse, news rail, status bar with provisional/stale tags.
- **GROWTH** (`Leaderboard.jsx`) — projected growth per horizon with the
  6m/1y/5y/20y switcher, P10–P90 bands, per-row model breakdowns.
- **BACKTEST** (`Backtest.jsx`) — portfolio equity curves (log scale) + stat
  tiles, materiality-gate evidence table, clickable per-signal scatter with
  in-sample/holdout shading and outcome cards.
- **LEDGER** (`Ledger.jsx`) — frozen cohorts marked to market.
- **THEORY** (`Theory.jsx`) — methodology and the honest-caveats list.
- **Company** (`Company.jsx`, via ticker links) — 19y price chart over
  quarterly obligations (lightweight-charts, signal markers at knowledge
  dates), WHAT DROVE IT award drill-down, signal history, mapping + audit
  transparency, thesis, news.

Charts follow the dataviz method: recharts for statistical charts,
lightweight-charts for the financial pane; series colors come from the
validated dark-surface palette in `theme.css` (the neon UI accents fail the
chart lightness band and are chrome-only).

## 4. Refresh & deploy

- **Local:** `make refresh` (everything cached; a warm run is seconds).
- **CI:** `.github/workflows/refresh.yml` runs weekly (Mondays), commits
  changed artifacts + the ledger, and fails loudly on validation errors.
  `ANTHROPIC_API_KEY` repo secret enables theses.
- **Hosting:** point any static host at `web/` (`npm run build` → `dist`).
  Hash routing means no rewrite rules.

## Known limitations (also disclosed in the UI)

Survivorship bias (universe picked in 2026); contracts only (grants — BARDA,
CHIPS — not counted); GOCO pass-throughs inflate some series (Sandia under
Honeywell); agencies revise past quarters; ~300 fired signals is small N;
the fade side doesn't beat chance; the growth model is an extrapolation, not
a forecast; and a signal this simple stops working if enough capital trades it.
