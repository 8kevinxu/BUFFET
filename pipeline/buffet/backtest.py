"""Stage 4: outcomes of every historical fired signal.

Entry = first trading day strictly after the knowledge date. Outcome =
forward 21/63/126-trading-day total return (adjusted close) minus SPY over
the same calendar span. Provisional signals are excluded — their spending
data wasn't fully reported yet, so treating them as history would be
look-ahead bias.

Aggregates are split in-sample (knowledge_date <= TRAIN_END, where the
thresholds were chosen) vs holdout, with bootstrap 95% CIs on mean excess
return. Small N and survivorship bias (universe curated in 2026) are
disclosed in the published artifact.
"""
import bisect
import datetime as dt
import json
import random

import numpy as np

from . import config


class PriceBook:
    def __init__(self, prices):
        self.series = {}
        for sym, rows in prices.items():
            dates = [r[0] for r in rows]
            px = [r[1] for r in rows]
            self.series[sym] = (dates, px)

    def entry_index(self, sym, after_date):
        """Index of first trading day strictly after after_date, or None."""
        if sym not in self.series:
            return None
        dates, _ = self.series[sym]
        i = bisect.bisect_right(dates, after_date)
        return i if i < len(dates) else None

    def forward_return(self, sym, entry_idx, ndays):
        dates, px = self.series[sym]
        j = entry_idx + ndays
        if j >= len(dates):
            return None, None
        return px[j] / px[entry_idx] - 1.0, dates[j]

    def return_between(self, sym, d0, d1):
        """Benchmark return over the same calendar span [d0, d1]."""
        if sym not in self.series:
            return None
        dates, px = self.series[sym]
        i = bisect.bisect_left(dates, d0)
        j = bisect.bisect_right(dates, d1) - 1
        if i >= len(dates) or j <= i:
            return None
        return px[j] / px[i] - 1.0


def _era(kdate):
    y = int(kdate[:4])
    if y <= 2013:
        return "2010-2013"
    if y <= 2017:
        return "2014-2017"
    if y <= 2021:
        return "2018-2021"
    return "2022-now"


def _outcome_rows(signal_rows, book, symbol_of, fired_key="fired"):
    rows = []
    for s in signal_rows:
        if not s.get(fired_key) or s["provisional"]:
            continue
        sym = symbol_of(s)
        entry_idx = book.entry_index(sym, s["knowledge_date"])
        if entry_idx is None:
            continue
        dates, px = book.series[sym]
        entry_date, entry_px = dates[entry_idx], px[entry_idx]
        outcome = {}
        for w in config.FORWARD_WINDOWS:
            ret, exit_date = book.forward_return(sym, entry_idx, w)
            if ret is None:
                outcome[str(w)] = None
                continue
            bench = book.return_between(config.BENCHMARK, entry_date, exit_date)
            outcome[str(w)] = {
                "ret": round(ret, 4),
                "bench": round(bench, 4) if bench is not None else None,
                "excess": round(ret - bench, 4) if bench is not None else None,
                "exit_date": exit_date,
            }
        rows.append({
            **{k: s.get(k) for k in ("id", "quarter_end", "z", "z_seas", "materiality",
                                     "runup", "knowledge_date", "obligations",
                                     "trailing_mean")},
            "fired": s[fired_key],
            "symbol": sym,
            "entry_date": entry_date,
            "entry_price": entry_px,
            "in_sample": s["knowledge_date"] <= config.TRAIN_END,
            "era": _era(s["knowledge_date"]),
            "outcome": outcome,
        })
    return rows


def _bootstrap_ci(values, n=None):
    if len(values) < 3:
        return None
    n = n or config.BOOTSTRAP_N
    arr = np.asarray(values)
    rng = np.random.default_rng(42)
    means = rng.choice(arr, size=(n, len(arr)), replace=True).mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return [round(float(lo), 4), round(float(hi), 4)]


def _aggregate(rows, window="126"):
    """Hit rate / mean excess stats for a set of outcome rows at one window."""
    out = {}
    for side in ("buy", "fade"):
        vals = [r["outcome"][window]["excess"] for r in rows
                if r["fired"] == side and r["outcome"].get(window)
                and r["outcome"][window]["excess"] is not None]
        if not vals:
            out[side] = {"n": 0}
            continue
        # a fade "hits" when the stock underperforms
        hits = sum(1 for v in vals if (v > 0) == (side == "buy"))
        ci = _bootstrap_ci(vals)
        out[side] = {
            "n": len(vals),
            "hit_rate": round(hits / len(vals), 3),
            "mean_excess": round(float(np.mean(vals)), 4),
            "median_excess": round(float(np.median(vals)), 4),
            "ci95": ci,
            "ci_includes_zero": (ci is None) or (ci[0] <= 0 <= ci[1]),
        }
    return out


def _placebo(buy_rows, book, window=126, n_perm=2000):
    """Permutation test of TIMING: keep the tickers and signal count fixed,
    replace each real entry date with a random trading day from that ticker's
    own backtestable history, and ask how often random timing matches the real
    mean excess. Controls for ticker mix and era-long sector drift — what's
    left is whether the signal's dates beat chance."""
    real_vals = []
    slots = []   # (symbol, lo_idx, hi_idx) valid random-entry index range
    floor = "2010-01-01"
    for r in buy_rows:
        o = r["outcome"].get(str(window))
        if not o or o["excess"] is None:
            continue
        real_vals.append(o["excess"])
        sym = r["symbol"]
        dates, _ = book.series[sym]
        lo = bisect.bisect_left(dates, floor)
        hi = len(dates) - window - 1
        if hi > lo:
            slots.append((sym, lo, hi))
    if len(real_vals) < 20 or not slots:
        return None
    real_mean = float(np.mean(real_vals))
    rng = random.Random(42)
    perm_means = []
    for _ in range(n_perm):
        vals = []
        for sym, lo, hi in slots:
            i = rng.randint(lo, hi)
            dates, px = book.series[sym]
            ret = px[i + window] / px[i] - 1.0
            bench = book.return_between(config.BENCHMARK, dates[i], dates[i + window])
            if bench is not None:
                vals.append(ret - bench)
        if vals:
            perm_means.append(float(np.mean(vals)))
    perm_means = np.asarray(perm_means)
    p = float((perm_means >= real_mean).mean())
    return {
        "n_signals": len(real_vals),
        "n_perm": len(perm_means),
        "real_mean_excess": round(real_mean, 4),
        "perm_mean_excess": round(float(perm_means.mean()), 4),
        "perm_p95": round(float(np.percentile(perm_means, 95)), 4),
        "p_value": round(p, 4),
    }


def run():
    signals = json.loads((config.DERIVED_DIR / "signals.json").read_text())
    prices = json.loads((config.DERIVED_DIR / "prices.json").read_text())["prices"]
    book = PriceBook(prices)

    ticker_outcomes = _outcome_rows(signals["tickers"], book, lambda s: s["id"])
    ungated_outcomes = _outcome_rows(signals["tickers"], book, lambda s: s["id"],
                                     fired_key="fired_ungated")
    seasonal_outcomes = _outcome_rows(signals["tickers"], book, lambda s: s["id"],
                                      fired_key="fired_seasonal")
    fade2_outcomes = _outcome_rows(signals["tickers"], book, lambda s: s["id"],
                                   fired_key="fired_fade2")
    assistance_outcomes = _outcome_rows(signals.get("assistance", []), book,
                                        lambda s: s["id"])
    sector_outcomes = _outcome_rows(signals["sectors"], book, lambda s: s["etf"])

    # evidence for the materiality gate: excess return by surge-size bucket
    # (share of annual revenue), among ungated buys with known revenue
    def _bucket(m):
        if m is None:
            return None
        if m < 0.005:
            return "<0.5%"
        if m < 0.02:
            return "0.5-2%"
        if m < 0.10:
            return "2-10%"
        return ">10%"

    # pre-entry run-up buckets: is a surge the market already chased still
    # worth buying? (post-announcement-drift check)
    def _runup_bucket(r):
        v = r.get("runup")
        if v is None:
            return None
        if v < -0.10:
            return "<-10%"
        if v < 0:
            return "-10-0%"
        if v < 0.10:
            return "0-10%"
        return ">10%"

    RUNUP_BUCKETS = ("<-10%", "-10-0%", "0-10%", ">10%")

    aggregates = {}
    for w in config.FORWARD_WINDOWS:
        w = str(w)
        aggregates[w] = {
            "all": _aggregate(ticker_outcomes, w),
            "ungated": _aggregate(ungated_outcomes, w),
            "in_sample": _aggregate([r for r in ticker_outcomes if r["in_sample"]], w),
            "holdout": _aggregate([r for r in ticker_outcomes if not r["in_sample"]], w),
            "eras": {era: _aggregate([r for r in ticker_outcomes if r["era"] == era], w)
                     for era in ("2010-2013", "2014-2017", "2018-2021", "2022-now")},
            "sectors": _aggregate(sector_outcomes, w),
            "materiality": {b: _aggregate([r for r in ungated_outcomes
                                           if _bucket(r.get("materiality")) == b], w)
                            for b in ("<0.5%", "0.5-2%", "2-10%", ">10%")},
            "seasonal": _aggregate(seasonal_outcomes, w),
            "seasonal_in_sample": _aggregate([r for r in seasonal_outcomes if r["in_sample"]], w),
            "seasonal_holdout": _aggregate([r for r in seasonal_outcomes if not r["in_sample"]], w),
            "fade2": _aggregate(fade2_outcomes, w),
            "fade2_in_sample": _aggregate([r for r in fade2_outcomes if r["in_sample"]], w),
            "fade2_holdout": _aggregate([r for r in fade2_outcomes if not r["in_sample"]], w),
            "assistance": _aggregate(assistance_outcomes, w),
            "runup": {b: _aggregate([r for r in ticker_outcomes if _runup_bucket(r) == b], w)
                      for b in RUNUP_BUCKETS},
        }

    placebo = _placebo([r for r in ticker_outcomes if r["fired"] == "buy"], book)

    # per-ticker track record at the 126d window
    track = {}
    for r in ticker_outcomes:
        o = r["outcome"].get("126")
        if not o or o["excess"] is None:
            continue
        t = track.setdefault(r["id"], {"n": 0, "hits": 0, "sum_excess": 0.0})
        t["n"] += 1
        t["sum_excess"] += o["excess"]
        if (o["excess"] > 0) == (r["fired"] == "buy"):
            t["hits"] += 1
    track = {k: {"n": v["n"], "hit_rate": round(v["hits"] / v["n"], 3),
                 "mean_excess": round(v["sum_excess"] / v["n"], 4)}
             for k, v in track.items()}

    print(f"  {len(ticker_outcomes)} ticker outcomes, {len(sector_outcomes)} sector outcomes, "
          f"{len(assistance_outcomes)} assistance outcomes")
    a = aggregates["126"]["all"].get("buy", {})
    if a.get("n"):
        print(f"  buys @126d: n={a['n']} hit={a['hit_rate']:.0%} "
              f"mean excess={a['mean_excess']:+.1%} ci95={a['ci95']}")
    s = aggregates["126"]["seasonal"].get("buy", {})
    if s.get("n"):
        print(f"  seasonal-z buys @126d: n={s['n']} hit={s['hit_rate']:.0%} "
              f"mean excess={s['mean_excess']:+.1%}")
    if placebo:
        print(f"  placebo: real {placebo['real_mean_excess']:+.1%} vs perm "
              f"{placebo['perm_mean_excess']:+.1%}, p={placebo['p_value']:.3f}")

    out = {"tickers": ticker_outcomes, "sectors": sector_outcomes,
           "assistance": assistance_outcomes,
           "aggregates": aggregates, "track": track, "placebo": placebo,
           "train_end": config.TRAIN_END,
           "caveats": {
               "survivorship": "Universe curated in 2026 from today's public contractors; "
                               "companies that shrank or delisted after spending collapses are invisible.",
               "revisions": "Agencies revise past quarters; recent data is incomplete (90-day DoD embargo).",
               "small_n": "Few hundred signals over ~15 years; treat all stats as noisy.",
           }}
    (config.DERIVED_DIR / "backtest.json").write_text(json.dumps(out))
    return out
