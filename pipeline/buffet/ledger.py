"""Stage 5d: the paper-trading ledger — the un-gameable forward test.

The first refresh after a new ranking quarter becomes usable freezes that
quarter's fired buy picks with real entry prices (the latest close at freeze
time). Frozen cohorts are never edited; every later refresh only re-marks
them to market vs SPY. The ledger lives in data/ledger.json (committed), so
the strategy's live out-of-sample record accumulates in git history.
"""
import bisect
import json

from . import config

LEDGER_PATH = config.REPO_ROOT / "data" / "ledger.json"


def run():
    picks = json.loads((config.DERIVED_DIR / "picks.json").read_text())
    prices = json.loads((config.DERIVED_DIR / "prices.json").read_text())["prices"]

    try:
        ledger = json.loads(LEDGER_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        ledger = {"cohorts": []}

    have = {c["quarter_end"] for c in ledger["cohorts"]}
    fired = [p for p in picks["picks"] if p["fired"] == "buy" and p["ticker"] in prices]
    if picks["quarter_end"] not in have and fired:
        cohort = {"quarter_end": picks["quarter_end"],
                  "frozen_on": picks["generated"],
                  "provisional_at_freeze": picks["provisional"],
                  "picks": []}
        for p in fired:
            rows = prices[p["ticker"]]
            cohort["picks"].append({
                "ticker": p["ticker"], "z": p["z"], "materiality": p["materiality"],
                "entry_date": rows[-1][0], "entry_price": rows[-1][1],
            })
        spy = prices[config.BENCHMARK]
        cohort["spy_entry"] = {"date": spy[-1][0], "price": spy[-1][1]}
        ledger["cohorts"].append(cohort)
        print(f"  froze cohort {picks['quarter_end']}: "
              f"{[p['ticker'] for p in cohort['picks']]}")
    else:
        print(f"  no new cohort (quarter {picks['quarter_end']} "
              f"{'already frozen' if picks['quarter_end'] in have else 'has no fired buys'})")

    LEDGER_PATH.parent.mkdir(exist_ok=True)
    LEDGER_PATH.write_text(json.dumps(ledger, indent=1))

    # mark every cohort to market (computed fresh each run, not stored)
    spy = prices[config.BENCHMARK]
    spy_dates = [r[0] for r in spy]

    def spy_at(date):
        i = bisect.bisect_left(spy_dates, date)
        return spy[min(i, len(spy) - 1)][1]

    marked = {"cohorts": [], "generated": picks["generated"]}
    for c in ledger["cohorts"]:
        rows = []
        rets, excesses = [], []
        for p in c["picks"]:
            series = prices.get(p["ticker"])
            if not series:
                continue
            last_date, last_px = series[-1]
            ret = last_px / p["entry_price"] - 1
            spy_ret = spy[-1][1] / spy_at(p["entry_date"]) - 1
            rets.append(ret)
            excesses.append(ret - spy_ret)
            rows.append({**p, "last_date": last_date, "last_price": last_px,
                         "ret": round(ret, 4), "spy_ret": round(spy_ret, 4),
                         "excess": round(ret - spy_ret, 4)})
        marked["cohorts"].append({
            "quarter_end": c["quarter_end"], "frozen_on": c["frozen_on"],
            "provisional_at_freeze": c.get("provisional_at_freeze", False),
            "picks": rows,
            "mean_ret": round(sum(rets) / len(rets), 4) if rets else None,
            "mean_excess": round(sum(excesses) / len(excesses), 4) if excesses else None,
        })
        if rows:
            cm = marked["cohorts"][-1]
            print(f"  cohort {c['quarter_end']}: {len(rows)} picks, "
                  f"mean {cm['mean_ret']:+.1%} ({cm['mean_excess']:+.1%} vs SPY)")

    (config.DERIVED_DIR / "ledger.json").write_text(json.dumps(marked))
    return marked
