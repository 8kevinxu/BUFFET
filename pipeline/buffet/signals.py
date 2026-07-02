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
import bisect
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


def _revenue_asof(revenue_rows, knowledge_date):
    """Latest annual revenue whose 10-K was FILED on or before the knowledge
    date — point-in-time, so the backtest can't peek at unreported revenue."""
    best = None
    for _end, filed, val in revenue_rows or []:
        if filed <= knowledge_date and (best is None or filed > best[0]):
            best = (filed, val)
    return best[1] if best else None


def _deseasonalize(values, ends):
    """Causally seasonally-adjusted copy of a quarterly series.

    Federal fiscal Q4 (the Sep 30 quarter) always spikes — use-it-or-lose-it
    year-end obligation — so a raw trailing-8q z over-reads routine September
    surges. For each point, estimate the seasonal offset of its quarter type
    (by calendar month of the quarter end) from the trailing 12 quarters
    (3 observations of each type), using ONLY data before the point — no
    look-ahead. Points with under 12 quarters of history are left unadjusted.
    """
    adj = []
    for i, v in enumerate(values):
        if i < 12:
            adj.append(v)
            continue
        window = values[i - 12:i]
        month = ends[i].month
        same = [values[j] for j in range(i - 12, i) if ends[j].month == month]
        if not same:
            adj.append(v)
            continue
        seasonal = statistics.fmean(same) - statistics.fmean(window)
        adj.append(v - seasonal)
    return adj


def _series_rows(series, name, history_starts, today, revenue_rows=None):
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
    values_adj = _deseasonalize(values, ends)
    rows = []
    w = config.ZSCORE_WINDOW
    prev_z = None
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
        kdate = qend + dt.timedelta(days=config.KNOWLEDGE_LAG_DAYS)

        # seasonal variant: same z rule on the causally deseasonalized series
        window_adj = values_adj[i - w:i]
        mu_adj = statistics.fmean(window_adj)
        sd_adj = statistics.stdev(window_adj)
        z_seas = (values_adj[i] - mu_adj) / sd_adj if sd_adj > 0 else None

        revenue = _revenue_asof(revenue_rows, kdate.isoformat())
        materiality = round((v - mu) / revenue, 5) if revenue else None
        materiality_seas = (round((values_adj[i] - mu_adj) / revenue, 5)
                            if revenue else None)

        def _fire(zval, mat):
            f = None
            if zval is not None and trailing4 >= config.DOLLAR_FLOOR:
                if zval >= config.Z_BUY:
                    f = "buy"
                elif zval <= config.Z_FADE:
                    f = "fade"
            # materiality gate applies when revenue is knowable;
            # ungated variants are kept so the backtest can compare
            if f and mat is not None:
                if f == "buy" and mat < config.MATERIALITY_MIN:
                    f = None
                elif f == "fade" and mat > -config.MATERIALITY_MIN:
                    f = None
            return f

        fired_ungated = None
        if z is not None and trailing4 >= config.DOLLAR_FLOOR:
            if z >= config.Z_BUY:
                fired_ungated = "buy"
            elif z <= config.Z_FADE:
                fired_ungated = "fade"
        fired = _fire(z, materiality)
        fired_seasonal = _fire(z_seas, materiality_seas)
        # fade hypothesis variant: only fade declines that PERSIST — the
        # trailing quarter must also have been below its own trailing mean
        fired_fade2 = ("fade" if fired == "fade" and prev_z is not None
                       and prev_z < 0 else None)
        prev_z = z

        rows.append({
            "id": name,
            "quarter_end": qend.isoformat(),
            "obligations": v,
            "trailing_mean": round(mu, 2),
            "trailing4": round(trailing4, 2),
            "z": round(z, 3) if z is not None else None,
            "z_seas": round(z_seas, 3) if z_seas is not None else None,
            "materiality": materiality,
            "revenue": revenue,
            "fired": fired,
            "fired_ungated": fired_ungated,
            "fired_seasonal": fired_seasonal,
            "fired_fade2": fired_fade2,
            "knowledge_date": kdate.isoformat(),
            "provisional": kdate > today,
        })
    return rows


def _attach_runup(rows, prices):
    """Pre-entry run-up: the stock's excess return vs SPY from quarter end to
    the knowledge date (or today, for provisional rows). Measures how much of
    the surge the market has already priced before we could act on the data.
    Presentation/evidence only — never an input to `fired`."""
    spy = prices.get(config.BENCHMARK)
    if not spy:
        return
    books = {}

    def _px(sym, date_iso):
        if sym not in books:
            rows_ = prices.get(sym)
            books[sym] = ([r[0] for r in rows_], [r[1] for r in rows_]) if rows_ else None
        b = books[sym]
        if not b:
            return None
        i = bisect.bisect_right(b[0], date_iso) - 1
        return b[1][i] if i >= 0 else None

    today = dt.date.today().isoformat()
    for r in rows:
        asof = min(r["knowledge_date"], today)
        p0, p1 = _px(r["id"], r["quarter_end"]), _px(r["id"], asof)
        s0, s1 = _px(config.BENCHMARK, r["quarter_end"]), _px(config.BENCHMARK, asof)
        if None in (p0, p1, s0, s1) or p0 <= 0 or s0 <= 0:
            r["runup"] = None
            continue
        r["runup"] = round((p1 / p0 - 1.0) - (s1 / s0 - 1.0), 4)


def run():
    spending = json.loads((config.DERIVED_DIR / "spending.json").read_text())
    recipients = mapping.load_recipients()
    sectors = {s["sector_id"]: s for s in mapping.load_sectors()}
    today = dt.date.today()
    try:
        revenue = json.loads((config.DERIVED_DIR / "fundamentals.json").read_text())["revenue"]
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        revenue = {}
        print("  [signals] no fundamentals.json — materiality gate disabled")

    try:
        prices = json.loads((config.DERIVED_DIR / "prices.json").read_text())["prices"]
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        prices = {}
        print("  [signals] no prices.json — run-up fields disabled")

    ticker_rows = []
    for ticker, series in spending["tickers"].items():
        info = recipients.get(ticker, {})
        ticker_rows.extend(_series_rows(series, ticker, info.get("history_starts"),
                                        today, revenue.get(ticker)))
    _attach_runup(ticker_rows, prices)

    # grants / direct payments / other assistance — a separate stream with the
    # same rule (BARDA-style money is mostly booked as contracts, but managed
    # care and CHIPS-era money shows up here)
    assistance_rows = []
    for ticker, series in spending.get("assistance", {}).items():
        info = recipients.get(ticker, {})
        assistance_rows.extend(_series_rows(series, ticker, info.get("history_starts"),
                                            today, revenue.get(ticker)))
    _attach_runup(assistance_rows, prices)

    sector_rows = []
    for sid, series in spending["sectors"].items():
        rows = _series_rows(series, sid, None, today)
        for r in rows:
            r["etf"] = sectors[sid]["etf"]
        sector_rows.extend(rows)

    fired = [r for r in ticker_rows if r["fired"]]
    fired_seas = [r for r in ticker_rows if r["fired_seasonal"]]
    print(f"  {len(ticker_rows)} ticker-quarters, {len(fired)} fired "
          f"({sum(1 for r in fired if r['fired'] == 'buy')} buy / "
          f"{sum(1 for r in fired if r['fired'] == 'fade')} fade); "
          f"seasonal variant {len(fired_seas)} fired; "
          f"{len(assistance_rows)} assistance-quarters "
          f"({sum(1 for r in assistance_rows if r['fired'])} fired); "
          f"{len(sector_rows)} sector-quarters")

    out = {"tickers": ticker_rows, "assistance": assistance_rows, "sectors": sector_rows}
    (config.DERIVED_DIR / "signals.json").write_text(json.dumps(out))
    return out
