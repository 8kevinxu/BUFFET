"""Stage 2: daily adjusted-close history for every symbol.

Primary source: stockanalysis.com history API (verified 2026-07-02: full
history with adjusted close, e.g. LMT back to 1968, field "a").
Fallback: Yahoo v8 chart API (verified working historically but currently
429-blocking this IP; must use explicit period1/period2 — range=max silently
returns sparse data).
"""
import datetime as dt
import json
import time

from . import cache, config, mapping

SA_URL = "https://stockanalysis.com/api/symbol/s/{sym}/history?range=Max&period=Daily"
YH_URL = ("https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
          "?period1=0&period2={now}&interval=1d")


def _from_stockanalysis(sym, max_age_days):
    data = cache.get_json(SA_URL.format(sym=sym), key=f"px_sa_{sym}", max_age_days=max_age_days)
    rows = data.get("data")
    if not rows:
        raise RuntimeError(f"stockanalysis empty for {sym}")
    # newest-first in the API; return sorted oldest-first [date, adjclose]
    out = sorted((r["t"], float(r["a"])) for r in rows if r.get("a") is not None)
    return [[d, round(px, 4)] for d, px in out]


def _from_yahoo(sym, max_age_days):
    url = YH_URL.format(sym=sym, now=int(time.time()))
    data = cache.get_json(url, key=f"px_yh_{sym}", max_age_days=max_age_days)
    res = data["chart"]["result"][0]
    ts = res["timestamp"]
    adj = res["indicators"]["adjclose"][0]["adjclose"]
    out = []
    for t, px in zip(ts, adj):
        if px is None:
            continue
        out.append([dt.date.fromtimestamp(t).isoformat(), round(float(px), 4)])
    return out


def fetch_symbol(sym, max_age_days=1.0):
    try:
        return _from_stockanalysis(sym, max_age_days)
    except Exception as e:
        print(f"  [prices] {sym}: stockanalysis failed ({e}), trying yahoo")
        return _from_yahoo(sym, max_age_days)


def run(max_age_days=1.0):
    recipients = mapping.load_recipients()
    sectors = mapping.load_sectors()
    symbols = mapping.all_price_symbols(recipients, sectors)

    prices = {}
    failed = []
    for i, sym in enumerate(symbols, 1):
        try:
            series = fetch_symbol(sym, max_age_days)
            prices[sym] = series
            print(f"  [{i}/{len(symbols)}] {sym}: {len(series)} rows "
                  f"({series[0][0]} → {series[-1][0]})")
        except Exception as e:
            failed.append(sym)
            print(f"  [{i}/{len(symbols)}] {sym}: FAILED ({e})")

    if config.BENCHMARK not in prices:
        raise RuntimeError("benchmark price series missing — cannot proceed")
    if len(failed) > len(symbols) * 0.2:
        raise RuntimeError(f"too many price failures: {failed}")

    out = {"prices": prices, "failed": failed, "fetched": dt.date.today().isoformat()}
    (config.DERIVED_DIR / "prices.json").write_text(json.dumps(out))
    print(f"  wrote prices for {len(prices)}/{len(symbols)} symbols")
    return out
