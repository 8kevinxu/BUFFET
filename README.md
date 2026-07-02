# buffet

**Federal spending → stock signals.** A personal research agent that scrapes US
government contract obligations (USAspending.gov, FY2008→present), cross-references
spending surges with stock returns of ~60 publicly traded federal contractors,
backtests the resulting signal (per-event and as a costed portfolio), applies it
to the newest quarter to rank "best stock to buy now," and renders everything in
a hacker-terminal dashboard. Surges are **materiality-weighted** (relative to
each company's SEC-reported revenue), the recipient matching is **audited for
contamination** every refresh (over-contaminated tickers are quarantined from
picks), projections carry **P10–P90 uncertainty bands**, and a **paper ledger**
freezes each quarter's picks with real entry prices so the strategy accumulates
a live out-of-sample record that can't be backtest-gamed.

> ⚠ **Research/education tool. Not financial advice.** The backtest has
> survivorship bias, small N, and revision risk — the UI discloses all of it.

## Quick start

```bash
make setup     # python venv + pip install + npm install
make refresh   # run the full data pipeline (~5 min first run; cached after)
make dev       # vite dev server → http://localhost:5173
make build     # static production build → web/dist
```

Set `ANTHROPIC_API_KEY` before `make refresh` to have Claude
(`claude-haiku-4-5` by default; override with `BUFFET_THESIS_MODEL`) write a
~120-word thesis + risk bullets for each pick. Without a key the stage skips
gracefully and the UI shows a `THESIS STALE` tag.

## How it works

1. **`fetch_spending`** — one `spending_over_time` POST per ticker to the
   USAspending API v2 (no key), with the ticker's hand-curated recipient name
   patterns OR'd together (`data/mapping/recipients.csv` — Lockheed appears
   under multiple UEIs, "ELECTRIC BOAT" is General Dynamics, etc.). Quarterly
   contract obligations, FY2008→present. Sector series per agency
   (`sectors.csv` maps DoD→ITA, HHS→XLV, …).
2. **`fetch_prices`** — daily adjusted closes. Primary source:
   stockanalysis.com history API (full history, includes adjusted close).
   Fallback: Yahoo v8 chart API (`period1/period2` explicit — `range=max`
   silently returns sparse data). **Stooq is dead** (proof-of-work challenge
   as of 2026-07).
3. **`signals`** — per (ticker, quarter): z-score vs the trailing 8-quarter
   mean/std. LONG fires at z ≥ +1.5, FADE at z ≤ −1.5, both gated on
   trailing-4q obligations ≥ $200M. **Knowledge date** = quarter end + 135
   days (90-day DoD FPDS embargo + publication buffer) — the look-ahead
   defense. Quarters whose knowledge date hasn't passed are `provisional`.
4. **`backtest`** — entry at the first trading day after the knowledge date;
   outcome = 21/63/126-trading-day return minus SPY. Thresholds fixed on
   2010–2017 (in-sample); 2018+ is the holdout. Bootstrap 95% CIs.
5. **`rank`** — the signal applied to the newest usable quarter → top-10 longs
   and top-5 fades. News and the Claude thesis are presentation only — never
   inputs to the score.
6. **`growth`** — the GROWTH leaderboard: projected 6m/1y/5y/20y total return
   per ticker. An explicit toy extrapolation, decomposed in the UI: trailing
   CAGR (weighted by how much of the lookback the ticker actually traded,
   outliers clamped) shrunk toward SPY's full-lookback CAGR, plus a damped
   3-year spending-trend tilt that decays with horizon, plus (6m/1y only) the
   backtested signal bump when a LONG fired. Per-horizon ceilings stop 20-year
   compounding fantasies; capped rows are tagged `CAP`.
7. **`news`** — Google News RSS (primary, keyless) + GDELT (secondary,
   1 req/6 s with a circuit breaker; it penalty-boxes IPs).
8. **`thesis`** — Claude writes the pick narratives (cached by input hash).
9. **`publish`** — schema/row-count-validated JSON into `web/public/data/`
   (committed, so the static site deploys with zero build-time fetching).

Later stages: `audit_recipients` (measures per-ticker series contamination on
the live API and publishes it; >25% ⇒ quarantined from picks), `fetch_fundamentals`
(SEC EDGAR revenue for materiality), `portfolio` (monthly-rebalanced costed
simulation vs SPY and sector ETFs), `ledger` (freezes picks into `data/ledger.json`,
committed), `awards` (transaction drill-downs: what drove each surge + a live
feed of the last 60 days).

Run one stage: `cd pipeline && ../.venv/bin/python -m buffet.refresh --stage rank`

## Repo layout

```
pipeline/buffet/       the 8 pipeline stages + config.py (all thresholds live here)
data/mapping/          hand-curated recipient-pattern → ticker map (the crux)
web/                   Vite + React SPA (recharts + lightweight-charts)
web/public/data/       generated JSON artifacts — committed, never hand-edited
pipeline/data/raw/     HTTP response cache — gitignored
```

Adding a company = adding rows to `data/mapping/recipients.csv` (uppercase
substring patterns matched against USAspending recipient names; set
`history_starts` for post-merger/IPO tickers so pre-history never fires).

## Deploy

`web/` is a static SPA (hash routing — no rewrites needed). Point Vercel/Netlify
at `web/` with build `npm run build`, output `dist`. The GitHub Action
(`.github/workflows/refresh.yml`) re-runs the pipeline weekly and commits
changed artifacts; add `ANTHROPIC_API_KEY` as a repo secret for theses.

## Honest limitations

- **Survivorship bias**: the universe was curated in 2026 from companies still
  public. Contractors that collapsed and delisted are invisible.
- **Small N**: ~500 fired signals over 15 years; the holdout is smaller.
- **Revisions**: agencies restate past quarters; the newest 2 quarters are
  materially incomplete (hence `PROVISIONAL`).
- The fade side does **not** backtest well (hit rate < 50%, CI includes zero)
  and the UI says so.
