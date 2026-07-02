"""Stage 5b: projected growth per ticker per horizon (the leaderboard).

This is an explicit toy extrapolation, decomposed so the UI can show its work:

  annualized = w_hist * ticker_cagr(lookback) + (1 - w_hist) * spy_cagr(lookback)
             + spending_tilt                (gov tailwind: 3y obligations CAGR, damped)
             + signal_bump                  (6m/1y only, only if a buy fired this
                                             quarter — the backtested mean excess,
                                             the one component with actual evidence)

The historical weight shrinks and the clamp tightens with the horizon:
single-stock returns mean-revert, and compounding an outlier CAGR for 20
years produces fantasy. Every number ships with its components + caveat.
"""
import bisect
import datetime as dt
import json

from . import config


def _cagr(rows, lookback_years, today):
    """Annualized return over the trailing lookback (or what history exists).
    Returns (cagr, actual_years) or (None, 0) with <1y of data."""
    if not rows or len(rows) < 2:
        return None, 0
    dates = [r[0] for r in rows]
    target = (today - dt.timedelta(days=round(lookback_years * 365.25))).isoformat()
    i = bisect.bisect_left(dates, target)
    if i >= len(rows) - 1:
        return None, 0
    d0, p0 = rows[i]
    d1, p1 = rows[-1]
    years = (dt.date.fromisoformat(d1) - dt.date.fromisoformat(d0)).days / 365.25
    # a "1y" lookback lands on ~0.99y actual (first trading day >= target);
    # only reject genuinely short windows where annualizing would overstate
    if years < 0.75 or p0 <= 0:
        return None, 0
    return (p1 / p0) ** (1 / years) - 1, years


WINDOW_STEP = 21  # trading days between rolling-window starts


def _window_anns(rows, years):
    """Annualized returns of all rolling windows of `years` length in this
    ticker's own history — the raw material for the uncertainty band."""
    n_days = round(years * 252)
    if len(rows) < n_days + WINDOW_STEP:
        return []
    out = []
    for i in range(0, len(rows) - n_days, WINDOW_STEP):
        p0, p1 = rows[i][1], rows[i + n_days][1]
        if p0 > 0:
            out.append((p1 / p0) ** (1 / years) - 1)
    return out


def _deviations(anns):
    """Centered spread of window outcomes (P10/P90 offsets from the median)."""
    if len(anns) < 24:
        return None
    s = sorted(anns)
    med = s[len(s) // 2]
    p10 = s[max(0, round(0.10 * (len(s) - 1)))]
    p90 = s[min(len(s) - 1, round(0.90 * (len(s) - 1)))]
    return p10 - med, p90 - med


def _spending_tilt(series, rank_q):
    """Damped 3y CAGR of trailing-4q obligations ending at the ranking quarter."""
    if not series:
        return 0.0, None
    quarters = sorted(q for q in series if q <= rank_q)
    if len(quarters) < 16:
        return 0.0, None
    recent = sum(series[q] for q in quarters[-4:])
    prior = sum(series[q] for q in quarters[-16:-12])
    if prior < config.SPEND_TILT_MIN_BASE or recent <= 0:
        return 0.0, None
    cagr = (recent / prior) ** (1 / 3) - 1
    tilt = max(-config.SPEND_TILT_CLAMP,
               min(config.SPEND_TILT_CLAMP, config.SPEND_TILT_COEF * cagr))
    return round(tilt, 4), round(cagr, 4)


def run():
    prices = json.loads((config.DERIVED_DIR / "prices.json").read_text())["prices"]
    spending = json.loads((config.DERIVED_DIR / "spending.json").read_text())
    picks = json.loads((config.DERIVED_DIR / "picks.json").read_text())
    backtest = json.loads((config.DERIVED_DIR / "backtest.json").read_text())
    today = dt.date.today()

    buy_fired = {p["ticker"] for p in picks["picks"] if p["fired"] == "buy"}
    bump_stats = backtest["aggregates"]["126"]["all"].get("buy", {})
    bump = bump_stats.get("mean_excess", 0.0) if bump_stats.get("n") else 0.0

    spy_rows = prices[config.BENCHMARK]
    out = {"horizons": {}, "rank_quarter": picks["quarter_end"],
           "signal_bump_126d": bump,
           "caveat": ("Toy extrapolation: trailing CAGR shrunk toward SPY, a damped "
                      "government-spending-trend tilt, and (6m/1y only) the backtested "
                      "signal bump. Long horizons are mostly the market baseline. "
                      "Not a forecast; not financial advice.")}

    for hz, cfg in config.GROWTH_HORIZONS.items():
        # pooled uncertainty for tickers whose history can't produce enough
        # rolling windows of this length (e.g. PLTR at the 20y horizon)
        pooled = []
        for ticker in spending["tickers"]:
            if ticker in prices and ticker != config.BENCHMARK:
                pooled.extend(_window_anns(prices[ticker], cfg["years"]))
        pooled_dev = _deviations(pooled)

        rows = []
        for ticker in spending["tickers"]:
            if ticker not in prices or ticker == config.BENCHMARK:
                continue
            t_cagr, t_years = _cagr(prices[ticker], cfg["lookback"], today)
            if t_cagr is None:
                continue
            # baseline is SPY over the FULL horizon lookback — a short-history
            # ticker must not inherit a bull-market-only baseline
            s_cagr, _ = _cagr(spy_rows, cfg["lookback"], today)
            if s_cagr is None:
                continue
            tilt, spend_cagr = _spending_tilt(spending["tickers"][ticker], picks["quarter_end"])
            tilt = round(tilt * cfg["tilt_scale"], 4)  # a 3y spending trend decays over long horizons
            sig = bump if (cfg["bump"] and ticker in buy_fired) else 0.0

            h_lo, h_hi = config.HIST_CAGR_CLAMP
            hist = max(h_lo, min(h_hi, t_cagr))
            short_history = t_years < cfg["lookback"] * 0.6
            # trust the ticker's record in proportion to how much of the
            # lookback it actually covers
            w = cfg["w_hist"] * min(1.0, t_years / cfg["lookback"])
            raw_ann = w * hist + (1 - w) * s_cagr + tilt + sig
            lo, hi = cfg["clamp"]
            ann = max(lo, min(hi, raw_ann))
            total = (1 + ann) ** cfg["years"] - 1

            # uncertainty band: the ticker's own rolling-window outcome spread
            # (pooled universe spread when its history is too short), centered
            # on the model projection
            own_dev = _deviations(_window_anns(prices[ticker], cfg["years"]))
            dev = own_dev or pooled_dev
            band = None
            if dev:
                p10_ann = max(-0.95, ann + dev[0])
                p90_ann = ann + dev[1]
                band = {
                    "p10": round((1 + p10_ann) ** cfg["years"] - 1, 4),
                    "p90": round((1 + p90_ann) ** cfg["years"] - 1, 4),
                    "pooled": own_dev is None,
                }
            rows.append({
                "band": band,
                "ticker": ticker,
                "annualized": round(ann, 4),
                "total": round(total, 4),
                "capped": raw_ann != ann,
                "_raw": raw_ann,
                "components": {
                    "hist_cagr": round(t_cagr, 4),
                    "hist_years": round(t_years, 1),
                    "spy_cagr": round(s_cagr, 4),
                    "w_hist": w,
                    "spend_tilt": tilt,
                    "spend_cagr_3y": spend_cagr,
                    "signal_bump": round(sig, 4),
                },
                "short_history": short_history,
            })
        rows.sort(key=lambda r: (-r["total"], -r["_raw"]))
        for r in rows:
            del r["_raw"]
        out["horizons"][hz] = rows
        if rows:
            top = rows[0]
            print(f"  [{hz}] {len(rows)} tickers · top {top['ticker']} "
                  f"{top['total']:+.1%} total ({top['annualized']:+.1%}/yr)")

    if any(len(v) < 40 for v in out["horizons"].values()):
        raise RuntimeError("growth: fewer than 40 tickers projected — inputs broken?")

    (config.DERIVED_DIR / "growth.json").write_text(json.dumps(out))
    return out
