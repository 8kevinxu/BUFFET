"""Stage 1c: quantify the survivorship bias instead of just disclosing it.

The universe was curated in 2026 from today's public contractors, so companies
that shrank, delisted, or were acquired after a spending collapse are invisible
to the backtest. This stage measures how much of the contracting economy the
universe actually covers, per fiscal year: pull the top 100 contract recipients
for each FY and mark which ones any universe pattern matches. The published
coverage series + the biggest never-matched names turn an unquantifiable
caveat into a number (and a to-do list for missing tickers).

Coverage will never be 100% — states, universities, FFRDC operators (MITRE,
Aerospace Corp) and private firms are legitimately unmatchable. The signal to
watch is coverage DECLINING back in time: that gap is the survivorship bias.
"""
import datetime as dt
import json

from . import cache, config, mapping
from .audit_recipients import strict_match

BY_RECIPIENT_API = "https://api.usaspending.gov/api/v2/search/spending_by_category/recipient/"
FIRST_FY = 2009
TOP_N = 100


def _fy_window(fy):
    return {"start_date": f"{fy - 1}-10-01", "end_date": f"{fy}-09-30"}


def run():
    recipients = mapping.load_recipients()
    overrides = mapping.load_overrides()
    today = dt.date.today()
    last_fy = today.year + (1 if today.month >= 10 else 0)

    years = []
    unmatched_totals = {}
    for fy in range(FIRST_FY, last_fy + 1):
        body = {"category": "recipient", "limit": TOP_N, "page": 1,
                "filters": {"time_period": [_fy_window(fy)],
                            "award_type_codes": ["A", "B", "C", "D"]}}
        data = cache.post_json(BY_RECIPIENT_API, body, key=f"survivor_fy{fy}",
                               max_age_days=60)
        rows = data.get("results", [])
        matched = unmatched = 0.0
        for r in rows:
            name = r.get("name") or ""
            amt = float(r.get("amount") or 0)
            if amt <= 0:
                continue
            hit = any(strict_match(name, info["patterns"], overrides.get(t, []))
                      for t, info in recipients.items())
            if hit:
                matched += amt
            else:
                unmatched += amt
                u = unmatched_totals.setdefault(name, {"amount": 0.0, "years": 0})
                u["amount"] += amt
                u["years"] += 1
        total = matched + unmatched
        years.append({"fy": fy, "top_n": len(rows),
                      "matched": round(matched, 2), "total": round(total, 2),
                      "coverage": round(matched / total, 4) if total else None})
        cov = years[-1]["coverage"]
        print(f"  FY{fy}: top-{len(rows)} coverage {cov:.0%}" if cov else f"  FY{fy}: no data")

    top_unmatched = sorted(
        ({"name": n, **v, "amount": round(v["amount"], 2)}
         for n, v in unmatched_totals.items()),
        key=lambda x: -x["amount"])[:40]

    out = {"years": years, "top_unmatched": top_unmatched,
           "note": ("Share of each FY's top-100 contract dollars that the "
                    "universe's recipient patterns match. Unmatched includes "
                    "legitimately untrackable recipients (states, universities, "
                    "FFRDCs, private firms); a DOWNWARD trend going back in time "
                    "measures the survivorship gap the backtest can't see.")}
    (config.DERIVED_DIR / "survivorship.json").write_text(json.dumps(out))
    covs = [y["coverage"] for y in years if y["coverage"]]
    print(f"  coverage range {min(covs):.0%}–{max(covs):.0%}; "
          f"top unmatched: {', '.join(u['name'][:28] for u in top_unmatched[:5])}")
    return out
