"""Stage 1: quarterly federal contract obligations per ticker + per sector.

One USAspending spending_over_time POST per ticker (its name patterns OR
together — verified: multi-pattern sums equal the sum of single-pattern
queries) and one per sector agency.

Fiscal quarters are converted to calendar quarter-end dates:
FY Q1 ends Dec 31 (of FY-1), Q2 Mar 31, Q3 Jun 30, Q4 Sep 30.
"""
import datetime as dt
import json

from . import cache, config, mapping

API = "https://api.usaspending.gov/api/v2/search/spending_over_time/"
CONTRACT_CODES = ["A", "B", "C", "D"]


def fiscal_quarter_end(fy, q):
    fy, q = int(fy), int(q)
    month_day = {1: (12, 31), 2: (3, 31), 3: (6, 30), 4: (9, 30)}[q]
    year = fy - 1 if q == 1 else fy
    return dt.date(year, month_day[0], month_day[1])


def _spending_series(filters, key, max_age_days):
    body = {"group": "quarter", "filters": filters}
    data = cache.post_json(API, body, key=key, max_age_days=max_age_days)
    series = {}
    for r in data.get("results", []):
        tp = r["time_period"]
        end = fiscal_quarter_end(tp["fiscal_year"], tp["quarter"])
        series[end.isoformat()] = round(float(r["aggregated_amount"] or 0.0), 2)
    return series


def run(max_age_days=6.0):
    recipients = mapping.load_recipients()
    sectors = mapping.load_sectors()
    today = dt.date.today().isoformat()
    window = [{"start_date": config.SPENDING_START, "end_date": today}]

    by_ticker = {}
    for i, (ticker, info) in enumerate(sorted(recipients.items()), 1):
        filters = {
            "time_period": window,
            "recipient_search_text": info["patterns"],
            "award_type_codes": CONTRACT_CODES,
        }
        print(f"  [{i}/{len(recipients)}] spending {ticker} ({len(info['patterns'])} patterns)")
        by_ticker[ticker] = _spending_series(filters, key=f"spend_{ticker}", max_age_days=max_age_days)

    by_sector = {}
    for s in sectors:
        filters = {
            "time_period": window,
            "agencies": [{"type": "awarding", "tier": "toptier", "name": s["agency"]}],
            "award_type_codes": CONTRACT_CODES,
        }
        print(f"  sector {s['sector_id']} ({s['agency']})")
        by_sector[s["sector_id"]] = _spending_series(filters, key=f"spend_sector_{s['sector_id']}",
                                                     max_age_days=max_age_days)

    nonempty = sum(1 for v in by_ticker.values() if v)
    if nonempty < len(by_ticker) * 0.6:
        raise RuntimeError(f"only {nonempty}/{len(by_ticker)} tickers returned spending — source broken?")

    out = {"tickers": by_ticker, "sectors": by_sector, "fetched": today}
    (config.DERIVED_DIR / "spending.json").write_text(json.dumps(out))
    print(f"  wrote spending for {len(by_ticker)} tickers, {len(by_sector)} sectors")
    return out
