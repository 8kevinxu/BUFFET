"""Stage 4b: portfolio-level simulation of the buy signal.

Per-signal event studies overstate what's implementable. This stage runs the
strategy as an actual portfolio: hold every fired (non-provisional) buy for
HOLD_DAYS trading days from its knowledge date, equal-weight across whatever
is active, rebalance membership monthly, pay TRADING_COST per side on churn.
Months with no active signal sit in cash.

Benchmarks: SPY, and a sector-hedged basket (the same monthly weights placed
in each position's sector ETF) — so defense-sector beta can't masquerade as
signal alpha.

Two evidence layers on top of the baseline sim:
- a hold-days x weighting SWEEP evaluated on the training era only (entries
  with knowledge_date <= TRAIN_END), with each config's holdout stats shown
  alongside — published as a comparison, the pre-registered baseline stays
  the headline;
- a Fama-French 3-factor regression of the monthly returns (Ken French data
  library, free) — is the excess return alpha, or market/size/value beta?
"""
import bisect
import datetime as dt
import io
import json
import math
import zipfile

import numpy as np

from . import cache, config, mapping

FF_URL = ("https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
          "F-F_Research_Data_Factors_CSV.zip")

SWEEP_HOLD_DAYS = [63, 126, 189, 252]
SWEEP_WEIGHTINGS = ["equal", "materiality", "z"]


def _month_key(d):
    return d[:7]


def _weight(weighting, mat, z):
    if weighting == "materiality":
        return min(max(mat if mat is not None else 0.005, 0.005), 0.05)
    if weighting == "z":
        return min(max((z or 1.5) - 1.0, 0.5), 4.0)
    return 1.0


def _simulate(signals, px, calendar, recipients, *, hold_days, weighting="equal",
              kdate_min=None, kdate_max=None):
    """Run the monthly-rebalanced sim; returns (series, stats_by_key) or None."""
    holdings = []
    for s in signals:
        if s["fired"] != "buy" or s["provisional"] or s["id"] not in px:
            continue
        kd = s["knowledge_date"]
        if (kdate_min and kd < kdate_min) or (kdate_max and kd > kdate_max):
            continue
        i = bisect.bisect_right(calendar, kd)
        if i >= len(calendar):
            continue
        j = min(i + hold_days, len(calendar) - 1)
        holdings.append((s["id"], calendar[i], calendar[j],
                         _weight(weighting, s.get("materiality"), s.get("z"))))
    if not holdings:
        return None

    def monthly_ret(sym, dates):
        r = 1.0
        prev = None
        for d in dates:
            p = px.get(sym, {}).get(d)
            if p is not None and prev is not None:
                r *= p / prev
            if p is not None:
                prev = p
        return r - 1.0

    first = min(e for _, e, _, _ in holdings)
    months = {}
    for d in calendar:
        if d >= first[:8] + "01":
            months.setdefault(_month_key(d), []).append(d)
    month_keys = sorted(months)[:-1] if len(months) > 1 else sorted(months)
    if len(months[sorted(months)[-1]]) >= 5 and sorted(months)[-1] not in month_keys:
        month_keys.append(sorted(months)[-1])

    series = []
    prev_members = set()
    eq = eq_spy = eq_sector = 1.0
    for mk in month_keys:
        dates = months[mk]
        start = dates[0]
        active = {}
        for t, e, x, w in holdings:
            if e <= start < x:
                active[t] = max(active.get(t, 0.0), w)
        members = set(active)
        n = max(len(members | prev_members), 1)
        churn = len(members ^ prev_members) / n
        cost = churn * config.TRADING_COST

        if members:
            total_w = sum(active.values())
            weights = {t: w / total_w for t, w in active.items()}
            port = sum(weights[t] * monthly_ret(t, dates) for t in members) - cost
            sector = sum(weights[t] * monthly_ret(config.TICKER_SECTOR_ETF.get(
                recipients.get(t, {}).get("sector", ""), config.BENCHMARK), dates)
                for t in members)
        else:
            port, sector = 0.0, 0.0
        spy = monthly_ret(config.BENCHMARK, dates)

        eq *= 1 + port
        eq_spy *= 1 + spy
        eq_sector *= 1 + sector
        series.append({"month": mk, "n": len(members), "ret": round(port, 5),
                       "spy": round(spy, 5), "sector": round(sector, 5),
                       "eq": round(eq, 4), "eq_spy": round(eq_spy, 4),
                       "eq_sector": round(eq_sector, 4)})
        prev_members = members
    return series


def _stats(series, key):
    rets = [m[key] for m in series]
    n = len(rets)
    if n < 12:
        return None
    mean = sum(rets) / n
    var = sum((r - mean) ** 2 for r in rets) / (n - 1)
    ann_ret = (math.prod(1 + r for r in rets)) ** (12 / n) - 1
    ann_vol = math.sqrt(var * 12)
    sharpe = (mean * 12) / ann_vol if ann_vol > 0 else 0
    peak, mdd = 1.0, 0.0
    eqc = 1.0
    for r in rets:
        eqc *= 1 + r
        peak = max(peak, eqc)
        mdd = min(mdd, eqc / peak - 1)
    return {"ann_return": round(ann_ret, 4), "ann_vol": round(ann_vol, 4),
            "sharpe": round(sharpe, 2), "max_drawdown": round(mdd, 4)}


def _ff_factors():
    """Monthly Fama-French 3 factors (decimal) keyed by 'YYYY-MM'."""
    raw = cache.get_bytes(FF_URL, key="ff_factors_monthly", max_age_days=7)
    z = zipfile.ZipFile(io.BytesIO(raw))
    text = z.read(z.namelist()[0]).decode("utf-8", "ignore")
    out = {}
    for line in text.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) == 5 and len(parts[0]) == 6 and parts[0].isdigit():
            ym = f"{parts[0][:4]}-{parts[0][4:]}"
            try:
                out[ym] = [float(parts[1]) / 100, float(parts[2]) / 100,
                           float(parts[3]) / 100, float(parts[4]) / 100]
            except ValueError:
                continue
    return out


def _factor_regression(series):
    """OLS of monthly strategy excess returns on FF3. Alpha t-stat > ~2 means
    the return isn't explained by market/size/value exposure."""
    try:
        ff = _ff_factors()
    except Exception as e:
        print(f"  [portfolio] FF factors unavailable ({e}) — skipping regression")
        return None
    rows = [(m["ret"], ff[m["month"]]) for m in series if m["month"] in ff]
    if len(rows) < 36:
        return None
    y = np.array([r - f[3] for r, f in rows])              # ret - RF
    X = np.column_stack([np.ones(len(rows)),
                         np.array([f[0] for _, f in rows]),  # Mkt-RF
                         np.array([f[1] for _, f in rows]),  # SMB
                         np.array([f[2] for _, f in rows])]) # HML
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    dof = len(rows) - X.shape[1]
    s2 = float(resid @ resid) / dof
    cov = s2 * np.linalg.inv(X.T @ X)
    se = np.sqrt(np.diag(cov))
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1 - float(resid @ resid) / ss_tot if ss_tot > 0 else 0.0
    return {
        "n_months": len(rows),
        "alpha_monthly": round(float(beta[0]), 5),
        "alpha_annual": round(float(beta[0]) * 12, 4),
        "alpha_t": round(float(beta[0] / se[0]), 2),
        "beta_mkt": round(float(beta[1]), 2),
        "beta_smb": round(float(beta[2]), 2),
        "beta_hml": round(float(beta[3]), 2),
        "r2": round(r2, 3),
        "note": "OLS of monthly strategy returns (net of RF) on Fama-French "
                "Mkt-RF/SMB/HML. Cash months included — this is the strategy as run.",
    }


def run():
    signals = json.loads((config.DERIVED_DIR / "signals.json").read_text())["tickers"]
    prices = json.loads((config.DERIVED_DIR / "prices.json").read_text())["prices"]
    recipients = mapping.load_recipients()

    px = {sym: {d: p for d, p in rows} for sym, rows in prices.items()}
    calendar = [d for d, _ in prices[config.BENCHMARK]]

    series = _simulate(signals, px, calendar, recipients,
                       hold_days=config.HOLD_DAYS, weighting="equal")
    if not series:
        raise RuntimeError("portfolio: no holdings")

    # sweep: chosen on the train era only; each config's holdout is shown
    # alongside so the comparison is honest (the baseline stays the headline)
    sweep = []
    for hd in SWEEP_HOLD_DAYS:
        for wt in SWEEP_WEIGHTINGS:
            tr = _simulate(signals, px, calendar, recipients, hold_days=hd,
                           weighting=wt, kdate_max=config.TRAIN_END)
            ho = _simulate(signals, px, calendar, recipients, hold_days=hd,
                           weighting=wt, kdate_min=config.TRAIN_END)
            row = {"hold_days": hd, "weighting": wt,
                   "train": _stats(tr, "ret") if tr else None,
                   "train_spy": _stats(tr, "spy") if tr else None,
                   "holdout": _stats(ho, "ret") if ho else None,
                   "holdout_spy": _stats(ho, "spy") if ho else None,
                   "baseline": hd == config.HOLD_DAYS and wt == "equal"}
            sweep.append(row)

    factors = _factor_regression(series)

    invested = [m for m in series if m["n"] > 0]
    out = {
        "series": series,
        "stats": {"strategy": _stats(series, "ret"), "spy": _stats(series, "spy"),
                  "sector": _stats(series, "sector")},
        "months": len(series),
        "months_invested": len(invested),
        "avg_positions": round(sum(m["n"] for m in invested) / max(len(invested), 1), 1),
        "hold_days": config.HOLD_DAYS,
        "cost_per_side": config.TRADING_COST,
        "sweep": sweep,
        "factors": factors,
        "note": ("Equal-weight all active buy signals, monthly membership rebalance, "
                 "held ~6 months from each knowledge date; months with no signal sit in cash. "
                 "Sector basket = same weights in each position's sector ETF."),
    }
    s = out["stats"]
    print(f"  {len(series)} months ({len(invested)} invested, avg {out['avg_positions']} positions)")
    print(f"  strategy: {s['strategy']['ann_return']:+.1%}/yr sharpe {s['strategy']['sharpe']} "
          f"mdd {s['strategy']['max_drawdown']:.0%} | SPY {s['spy']['ann_return']:+.1%} "
          f"sharpe {s['spy']['sharpe']} | sector {s['sector']['ann_return']:+.1%}")
    if factors:
        print(f"  FF3: alpha {factors['alpha_annual']:+.1%}/yr (t={factors['alpha_t']}) "
              f"beta_mkt {factors['beta_mkt']} r2 {factors['r2']}")
    best = max((r for r in sweep if r["train"]), key=lambda r: r["train"]["sharpe"])
    print(f"  sweep best (train sharpe): hold={best['hold_days']} {best['weighting']} "
          f"train {best['train']['ann_return']:+.1%} | holdout "
          f"{best['holdout']['ann_return']:+.1%}" if best.get("holdout") else "")
    (config.DERIVED_DIR / "portfolio.json").write_text(json.dumps(out))
    return out
