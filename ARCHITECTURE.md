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
| 1 | `fetch_spending` | USAspending `spending_over_time` | quarterly contract obligations per ticker (FY2008→now) + per agency, plus a separate **assistance** series (grants/direct payments) per ticker | yes |
| 2 | `audit_recipients` | USAspending recipient + category APIs | per-ticker matched-entity list and **contamination %** | no |
| 3 | `survivorship` | USAspending top-100 recipients per FY | universe **coverage % per fiscal year** + biggest never-matched names | no |
| 4 | `fetch_prices` | stockanalysis.com (primary), Yahoo v8 (fallback) | daily adjusted closes, universe + SPY + sector ETFs | yes |
| 5 | `fetch_fundamentals` | SEC EDGAR XBRL companyfacts | point-in-time annual revenue per ticker | no |
| 6 | `signals` | 1 + 5 | z-score rows per (ticker, quarter) with materiality, **seasonally-adjusted z**, **pre-entry run-up**, and fired flags (incl. variants) | yes |
| 7 | `backtest` | 6 + 4 | per-signal forward outcomes, aggregates, CIs, materiality/run-up buckets, rule-variant comparisons, **timing placebo** | yes |
| 8 | `portfolio` | 6 + 4 | monthly costed portfolio sim vs SPY + sector basket, **hold×weighting sweep** (train-era), **Fama-French 3-factor regression** | yes |
| 9 | `rank` | 6 + 7 + 2 | current picks (quarantine applied); fades retired → informational rows | yes |
| 10 | `growth` | 4 + 1 + 9 | projected growth per horizon with P10–P90 bands | yes |
| 11 | `ledger` | 9 + 4 | frozen pick cohorts (`data/ledger.json`) marked to market | yes |
| 12 | `awards` | USAspending `spending_by_transaction` | surge drill-downs + last-60-day award feed | no |
| 13 | `announce` | war.gov daily contract announcements (RSS + headless Chrome) | **EARLY SIGNALS**: same-day announcements matched to the universe, material ones (≥0.5% of revenue) flagged as alerts | no |
| 14 | `news` | Google News RSS (GDELT fallback) | headlines for picked tickers | no |
| 15 | `thesis` | Anthropic API (`claude-haiku-4-5`) | ~120-word thesis + risks per pick, cached by input hash | no |
| 16 | `publish` | everything | validated artifacts → `web/public/data/` | yes |

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
- **FADES are retired from the ranking**: shorting collapses never beat
  chance in-sample (33% hit; faded names went on to outperform), and no
  conditioning variant showed in-sample edge. Collapse rows are still
  published, labeled informational.

All thresholds live in `config.py` and were fixed on pre-2018 data
("in-sample"); 2018+ is reported separately as the holdout.

**Rule variants evaluated and published, not adopted** (the honest-comparison
protocol — see the BACKTEST page table): a seasonally-adjusted z (causal
same-quarter offset from the trailing 12 quarters; federal fiscal Q4 always
spikes) was better in-sample but worse in the holdout; a persistent-decline
fade works ONLY in the holdout (adopting it would be holdout-tuning); the
assistance stream fires ~never under the same gates (BARDA-style COVID money
was booked as contracts — verified; assistance is mostly managed-care direct
payments). Pre-entry **run-up** (stock vs SPY from quarter end to entry)
shows no monotone decay across buckets, so it's a context column on picks,
not a gate.

**Independence checks**: a timing placebo (same tickers, same signal count,
random entry dates, 2000 permutations — real +4.0% vs random +1.7%, p≈0.06)
and a Fama-French 3-factor regression of the portfolio's monthly returns
(alpha ≈ +10.7%/yr, t≈2.9 — the excess isn't market/size/value beta).

### Look-ahead defenses (the part that makes the backtest meaningful)

1. **Knowledge date** = quarter end + 135 days (DoD's 90-day FPDS embargo +
   submission/publication buffer). Entries happen on the first trading day
   *after* it; quarters whose knowledge date hasn't passed are `provisional`
   — rankable (labeled) but never backtest rows.
2. **Point-in-time revenue** — materiality uses the earliest filing of each
   annual period, matched by `filed` date.
3. **Walk-forward split** — thresholds chosen on 2010–2017; holdout reported
   with its own stats.
4. **Survivorship: measured, not just disclosed** — the universe was curated
   in 2026, so delisted losers are invisible. The `survivorship` stage
   measures the gap: universe patterns match a stable 66–78% of each FY's
   top-100 contract dollars all the way back to FY2009 (the remainder is
   states/universities/FFRDCs/private firms), so the universe isn't thinner
   in the early years — but individual dead tickers stay invisible. The same
   audit's unmatched list caught two real series undercounts (RTX's renamed
   parent entity, GD's NASSCO shipyard), since fixed.

### The early tier (`announce`)

The quarterly signal is honest but slow — the knowledge date embargo means
entries lag quarter end by ~4.5 months. DoD, however, publicly announces
every contract action over ~$7.5M the same day (war.gov/News/Contracts).
The `announce` stage scans the daily announcements (RSS index from Python;
article bodies via `web/scripts/fetch-page.mjs` — headless system Chrome,
because Akamai TLS-fingerprint-blocks plain HTTP clients), parses each award
paragraph (company, amount, description), matches companies against the
universe's patterns with the same `strict_match` rule the audit uses, and
flags awards ≥ 0.5% of the ticker's latest annual revenue as **alerts**.
Announced values are effectively the contract **ceiling** — an IDIQ award
shows $0 obligated in USAspending until task orders land — so this feed also
serves as the leading indicator obligations can't provide. It is labeled
context, not a backtested signal (the reachable archive is ~3 months deep).
The weekly refresh opens a GitHub issue when new alerts appear, so they
arrive by email.

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
`portfolio.json`, `growth.json`, `ledger.json`, `awards.json`,
`announce.json` (early-signal feed + alerts), `survivorship.json`,
`news.json`, `thesis.json`, `quotes.json`, `universe.json`, `audit.json`,
`spending.json` (contracts + assistance), and lazy-loaded per-symbol
`prices/<SYM>.json` (trimmed to 2007+).

## 3. The web app (`web/`)

Vite + React SPA, hash-routed, five pages:

- **TERMINAL** (`Dashboard.jsx`) — picks board (materiality + run-up columns,
  expandable thesis + headlines), EARLY SIGNALS (same-day DoD announcements,
  material ones highlighted), the retired-fades board (labeled informational),
  LIVE AWARDS (last-60-day transactions), sector pulse, news rail, status bar
  with provisional/stale/early-alert tags.
- **GROWTH** (`Leaderboard.jsx`) — projected growth per horizon with the
  6m/1y/5y/20y switcher, P10–P90 bands, per-row model breakdowns.
- **BACKTEST** (`Backtest.jsx`) — portfolio equity curves (log scale) + stat
  tiles (incl. Fama-French alpha), the train-era parameter sweep, the
  materiality-gate evidence table, the timing-placebo tiles, the rule-variant
  and run-up tables, and the clickable per-signal scatter with
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

Survivorship bias (universe picked in 2026 — now *measured* per FY by the
survivorship stage, but dead tickers remain unpriceable); the assistance
stream is tracked but fires ~never under the shared gates (and BARDA-style
money was booked as contracts anyway); the announcement tier has no backtest
(archive ~3 months deep); GOCO pass-throughs inflate some series (Sandia
under Honeywell); agencies revise past quarters; ~300 fired signals is small
N (placebo p≈0.06 — suggestive, not conclusive); the fade side is retired;
the growth model is an extrapolation, not a forecast; and a signal this
simple stops working if enough capital trades it.
