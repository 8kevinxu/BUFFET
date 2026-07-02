"""Stage 3: the event-study signal.

For every (ticker, quarter): z-score of contract obligations vs the trailing
ZSCORE_WINDOW quarters (excluding the current one). A "buy" fires at
z >= Z_BUY, a "fade" at z <= Z_FADE, both gated on trailing-4-quarter
obligations >= DOLLAR_FLOOR so tiny denominators can't fire.

Look-ahead defense: each quarter's knowledge_date = quarter end +
KNOWLEDGE_LAG_DAYS (90-day DoD FPDS embargo + publication buffer). Returns
are only ever measured from after the knowledge date, and quarters whose
knowledge date hasn't arrived yet are flagged provisional (data still
incomplete due to reporting lag) — usable for the current ranking, labeled,
but never as backtest rows.
"""
import datetime as dt
import json
import statistics

from . import config, mapping


def _quarter_ends(first, last):
    """All calendar quarter-end dates from first to last inclusive."""
    ends = []
    y, m = first.year, first.month
    d = first
    while d <= last:
        ends.append(d)
        if d.month == 12:
            d = dt.date(d.year + 1, 3, 31)
        elif d.month == 3:
            d = dt.date(d.year, 6, 30)
        elif d.month == 6:
            d = dt.date(d.year, 9, 30)
        else:
            d = dt.date(d.year, 12, 31)
    return ends


def _series_rows(series, name, history_starts, today):
    """Compute signal rows for one quarterly obligations series."""
    if not series:
        return []
    dates = sorted(dt.date.fromisoformat(k) for k in series)
    # Fill missing quarters with 0 (no awards that quarter is a real zero),
    # but start at the first quarter with any obligations so pre-existence
    # zeros don't fabricate a "surge" the day a company first appears.
    first_nonzero = next((d for d in dates if series[d.isoformat()] > 0), None)
    if first_nonzero is None:
        return []
    last = max(d for d in dates if d <= today)
    ends = _quarter_ends(first_nonzero, last)
    values = [series.get(d.isoformat(), 0.0) for d in ends]

    hs = dt.date.fromisoformat(history_starts) if history_starts else None
    rows = []
    w = config.ZSCORE_WINDOW
    for i, (qend, v) in enumerate(zip(ends, values)):
        if i < w:
            continue
        if hs and qend < hs:
            continue
        window = values[i - w:i]
        mu = statistics.fmean(window)
        sd = statistics.stdev(window)
        trailing4 = sum(values[max(0, i - 3):i + 1])
        z = (v - mu) / sd if sd > 0 else None
        fired = None
        if z is not None and trailing4 >= config.DOLLAR_FLOOR:
            if z >= config.Z_BUY:
                fired = "buy"
            elif z <= config.Z_FADE:
                fired = "fade"
        kdate = qend + dt.timedelta(days=config.KNOWLEDGE_LAG_DAYS)
        rows.append({
            "id": name,
            "quarter_end": qend.isoformat(),
            "obligations": v,
            "trailing_mean": round(mu, 2),
            "trailing4": round(trailing4, 2),
            "z": round(z, 3) if z is not None else None,
            "fired": fired,
            "knowledge_date": kdate.isoformat(),
            "provisional": kdate > today,
        })
    return rows


def run():
    spending = json.loads((config.DERIVED_DIR / "spending.json").read_text())
    recipients = mapping.load_recipients()
    sectors = {s["sector_id"]: s for s in mapping.load_sectors()}
    today = dt.date.today()

    ticker_rows = []
    for ticker, series in spending["tickers"].items():
        info = recipients.get(ticker, {})
        ticker_rows.extend(_series_rows(series, ticker, info.get("history_starts"), today))

    sector_rows = []
    for sid, series in spending["sectors"].items():
        rows = _series_rows(series, sid, None, today)
        for r in rows:
            r["etf"] = sectors[sid]["etf"]
        sector_rows.extend(rows)

    fired = [r for r in ticker_rows if r["fired"]]
    print(f"  {len(ticker_rows)} ticker-quarters, {len(fired)} fired "
          f"({sum(1 for r in fired if r['fired'] == 'buy')} buy / "
          f"{sum(1 for r in fired if r['fired'] == 'fade')} fade); "
          f"{len(sector_rows)} sector-quarters")

    out = {"tickers": ticker_rows, "sectors": sector_rows}
    (config.DERIVED_DIR / "signals.json").write_text(json.dumps(out))
    return out
