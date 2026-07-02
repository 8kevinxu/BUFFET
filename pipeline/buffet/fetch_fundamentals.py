"""Stage 2b: annual revenue per ticker from SEC EDGAR XBRL (keyless).

Purpose: materiality — a $300M obligations surge is transformative for a
$1B-revenue company and noise for Amazon. We need revenue *as it was knowable
at the time* (point-in-time), so each period keeps the earliest `filed` date;
signal code then uses the latest revenue filed on or before a knowledge date.

Revenue tags changed across GAAP generations (ASC 606 in ~2017), so we merge
a priority list of tags from the companyfacts blob. The raw blob is 2–10MB
per company; we cache only the slim extracted series.
"""
import datetime as dt
import json
import time

import requests

from . import config, mapping

UA = {"User-Agent": "buffet-research kevinxu1234561@gmail.com"}
TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"

REVENUE_TAGS = [
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
    "SalesRevenueGoodsNet",
    "SalesRevenueServicesNet",
]

CACHE_DAYS = 30


def _cik_map():
    path = config.RAW_DIR / "sec_ticker_cik.json"
    if path.exists() and (time.time() - path.stat().st_mtime) < CACHE_DAYS * 86400:
        return json.loads(path.read_text())
    resp = requests.get(TICKER_MAP_URL, headers=UA, timeout=60)
    resp.raise_for_status()
    out = {v["ticker"].upper(): v["cik_str"] for v in resp.json().values()}
    path.write_text(json.dumps(out))
    return out


def _annual_revenue(facts):
    """Merge annual (10-K/FY, ~1-year duration) revenue rows across tags.
    Returns [[period_end, first_filed, value], ...] sorted by period_end."""
    gaap = facts.get("facts", {}).get("us-gaap", {})
    by_end = {}
    for tag in REVENUE_TAGS:
        units = gaap.get(tag, {}).get("units", {}).get("USD", [])
        for u in units:
            if u.get("form") != "10-K" or u.get("fp") != "FY":
                continue
            start, end = u.get("start"), u.get("end")
            if not start or not end:
                continue
            days = (dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days
            if not 340 <= days <= 380:      # annual periods only
                continue
            cur = by_end.get(end)
            # point-in-time: keep the EARLIEST filing of each period;
            # earlier-priority tags win ties
            if cur is None or u["filed"] < cur[0]:
                by_end[end] = (u["filed"], float(u["val"]))
    return sorted([[end, filed, val] for end, (filed, val) in by_end.items()])


def fetch_ticker(ticker, cik):
    slim = config.RAW_DIR / f"fund_{ticker}.json"
    if slim.exists() and (time.time() - slim.stat().st_mtime) < CACHE_DAYS * 86400:
        return json.loads(slim.read_text())
    time.sleep(0.5)  # SEC asks for <=10 req/s; stay far under
    resp = requests.get(FACTS_URL.format(cik=cik), headers=UA, timeout=120)
    resp.raise_for_status()
    series = _annual_revenue(resp.json())
    slim.write_text(json.dumps(series))
    return series


def run():
    recipients = mapping.load_recipients()
    ciks = _cik_map()
    out = {}
    missing = []
    for i, ticker in enumerate(sorted(recipients), 1):
        cik = ciks.get(ticker)
        if cik is None:
            missing.append(ticker)
            continue
        try:
            series = fetch_ticker(ticker, cik)
        except requests.RequestException as e:
            print(f"  [{i}] {ticker}: EDGAR failed ({e})")
            missing.append(ticker)
            continue
        if series:
            out[ticker] = series
            print(f"  [{i}] {ticker}: {len(series)} annual periods "
                  f"({series[0][0]} → {series[-1][0]}, latest ${series[-1][2]/1e9:.1f}B)")
        else:
            missing.append(ticker)
            print(f"  [{i}] {ticker}: no annual revenue rows found")

    if len(out) < len(recipients) * 0.7:
        raise RuntimeError(f"fundamentals: only {len(out)}/{len(recipients)} tickers have revenue")
    print(f"  revenue for {len(out)} tickers; missing: {missing or 'none'} "
          f"(missing tickers keep the un-gated signal rule)")
    result = {"revenue": out, "missing": missing}
    (config.DERIVED_DIR / "fundamentals.json").write_text(json.dumps(result))
    return result
