"""Stage 4b: portfolio-level simulation of the buy signal.

Per-signal event studies overstate what's implementable. This stage runs the
strategy as an actual portfolio: hold every fired (non-provisional) buy for
HOLD_DAYS trading days from its knowledge date, equal-weight across whatever
is active, rebalance membership monthly, pay TRADING_COST per side on churn.
Months with no active signal sit in cash.

Benchmarks: SPY, and a sector-hedged basket (the same monthly weights placed
in each position's sector ETF) — so defense-sector beta can't masquerade as
signal alpha.
"""
import bisect
import datetime as dt
import json
import math

from . import config, mapping


def _month_key(d):
    return d[:7]


def run():
    signals = json.loads((config.DERIVED_DIR / "signals.json").read_text())
    prices = json.loads((config.DERIVED_DIR / "prices.json").read_text())["prices"]
    recipients = mapping.load_recipients()

    px = {sym: {d: p for d, p in rows} for sym, rows in prices.items()}
    calendar = [d for d, _ in prices[config.BENCHMARK]]
    cal_idx = {d: i for i, d in enumerate(calendar)}

    # build holdings: ticker -> list of (entry_date, exit_date)
    holdings = []
    for s in signals["tickers"]:
        if s["fired"] != "buy" or s["provisional"] or s["id"] not in px:
            continue
        i = bisect.bisect_right(calendar, s["knowledge_date"])
        if i >= len(calendar):
            continue
        j = min(i + config.HOLD_DAYS, len(calendar) - 1)
        holdings.append((s["id"], calendar[i], calendar[j]))
    if not holdings:
        raise RuntimeError("portfolio: no holdings")

    def monthly_ret(sym, dates):
        """Compounded return of sym over consecutive calendar dates (0 where unpriced)."""
        r = 1.0
        prev = None
        for d in dates:
            p = px.get(sym, {}).get(d)
            if p is not None and prev is not None:
                r *= p / prev
            if p is not None:
                prev = p
        return r - 1.0

    # group trading days by month, starting from the first entry
    first = min(e for _, e, _ in holdings)
    months = {}
    for d in calendar:
        if d >= first[:8] + "01":
            months.setdefault(_month_key(d), []).append(d)
    month_keys = sorted(months)[:-1] if len(months) > 1 else sorted(months)
    # drop the current partial month only if it has < 5 trading days
    if len(months[sorted(months)[-1]]) >= 5 and sorted(months)[-1] not in month_keys:
        month_keys.append(sorted(months)[-1])

    series = []
    prev_members = set()
    eq = eq_spy = eq_sector = 1.0
    for mk in month_keys:
        dates = months[mk]
        start = dates[0]
        members = {t for t, e, x in holdings if e <= start < x}
        # membership churn cost (both sides)
        n = max(len(members | prev_members), 1)
        churn = len(members ^ prev_members) / n
        cost = churn * config.TRADING_COST

        if members:
            rets = [monthly_ret(t, dates) for t in sorted(members)]
            port = sum(rets) / len(rets) - cost
            sect = [monthly_ret(config.TICKER_SECTOR_ETF.get(
                recipients.get(t, {}).get("sector", ""), config.BENCHMARK), dates)
                for t in sorted(members)]
            sector = sum(sect) / len(sect)
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

    def stats(key):
        rets = [m[key] for m in series]
        n = len(rets)
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

    invested = [m for m in series if m["n"] > 0]
    out = {
        "series": series,
        "stats": {"strategy": stats("ret"), "spy": stats("spy"), "sector": stats("sector")},
        "months": len(series),
        "months_invested": len(invested),
        "avg_positions": round(sum(m["n"] for m in invested) / max(len(invested), 1), 1),
        "hold_days": config.HOLD_DAYS,
        "cost_per_side": config.TRADING_COST,
        "note": ("Equal-weight all active buy signals, monthly membership rebalance, "
                 "held ~6 months from each knowledge date; months with no signal sit in cash. "
                 "Sector basket = same weights in each position's sector ETF."),
    }
    s = out["stats"]
    print(f"  {len(series)} months ({len(invested)} invested, avg {out['avg_positions']} positions)")
    print(f"  strategy: {s['strategy']['ann_return']:+.1%}/yr sharpe {s['strategy']['sharpe']} "
          f"mdd {s['strategy']['max_drawdown']:.0%} | SPY {s['spy']['ann_return']:+.1%} "
          f"sharpe {s['spy']['sharpe']} | sector {s['sector']['ann_return']:+.1%}")
    (config.DERIVED_DIR / "portfolio.json").write_text(json.dumps(out))
    return out
