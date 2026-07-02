"""Stage 5c: the actual awards behind the numbers.

Two products from one endpoint (spending_by_transaction):
- drivers: for each ticker's latest fired quarter, the top transactions that
  caused the surge/collapse — "WHAT DROVE IT" on the company page, and raw
  material for the Claude thesis.
- recent: for currently picked/faded tickers, the largest transactions of the
  last 60 days — the LIVE AWARDS feed. (Investigated: the DoD contracts RSS
  ContentType feeds now serve feature stories, not contract announcements, so
  USAspending transactions are the freshest structured source. Civilian awards
  appear within ~weeks; DoD after its 90-day embargo — still months fresher
  than waiting for quarterly aggregation.)

Failures never break the run — this stage is enrichment.
"""
import datetime as dt
import json

from . import cache, config, mapping

TX_API = "https://api.usaspending.gov/api/v2/search/spending_by_transaction/"
FIELDS = ["Transaction Amount", "Transaction Description", "Action Date",
          "Awarding Agency", "Award ID"]


def _tx(patterns, start, end, key, limit=6):
    body = {"filters": {"time_period": [{"start_date": start, "end_date": end}],
                        "recipient_search_text": patterns,
                        "award_type_codes": ["A", "B", "C", "D"]},
            "fields": FIELDS, "sort": "Transaction Amount", "order": "desc",
            "limit": limit}
    data = cache.post_json(TX_API, body, key=key, max_age_days=6)
    out = []
    for r in data.get("results", []):
        out.append({
            "amount": r.get("Transaction Amount"),
            "desc": (r.get("Transaction Description") or "").strip()[:220],
            "date": r.get("Action Date"),
            "agency": r.get("Awarding Agency"),
            "award_id": r.get("Award ID"),
        })
    return out


def _quarter_start(qend):
    d = dt.date.fromisoformat(qend)
    return (d - dt.timedelta(days=89)).replace(day=1).isoformat()


def run():
    signals = json.loads((config.DERIVED_DIR / "signals.json").read_text())
    picks = json.loads((config.DERIVED_DIR / "picks.json").read_text())
    recipients = mapping.load_recipients()

    # drivers: latest fired quarter per ticker
    latest_fired = {}
    for r in signals["tickers"]:
        if r["fired"]:
            cur = latest_fired.get(r["id"])
            if cur is None or r["quarter_end"] > cur["quarter_end"]:
                latest_fired[r["id"]] = r

    drivers = {}
    for i, (ticker, row) in enumerate(sorted(latest_fired.items()), 1):
        pats = recipients.get(ticker, {}).get("patterns")
        if not pats:
            continue
        try:
            rows = _tx(pats, _quarter_start(row["quarter_end"]), row["quarter_end"],
                       key=f"tx_{ticker}_{row['quarter_end']}")
        except Exception as e:
            print(f"  [drivers] {ticker}: failed ({e})")
            continue
        drivers[ticker] = {"quarter_end": row["quarter_end"],
                           "fired": row["fired"], "rows": rows}
    print(f"  drivers for {len(drivers)} tickers")

    # recent: last 60 days for current picks/fades
    today = dt.date.today()
    start = (today - dt.timedelta(days=60)).isoformat()
    recent = {}
    for r in picks["picks"] + picks["fades"]:
        t = r["ticker"]
        pats = recipients.get(t, {}).get("patterns")
        if not pats:
            continue
        try:
            recent[t] = _tx(pats, start, today.isoformat(),
                            key=f"txr_{t}_{today.isoformat()}", limit=8)
        except Exception as e:
            print(f"  [recent] {t}: failed ({e})")
    n_recent = sum(len(v) for v in recent.values())
    print(f"  {n_recent} recent transactions across {len(recent)} picked tickers")

    out = {"drivers": drivers, "recent": recent, "fetched": today.isoformat()}
    (config.DERIVED_DIR / "awards.json").write_text(json.dumps(out))
    return out
