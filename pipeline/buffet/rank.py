"""Stage 5: apply the signal to the newest usable quarter.

The ranking quarter is the most recent quarter end at least RANK_MIN_AGE_DAYS
old — a quarter that ended days ago has almost no reported awards yet. If its
knowledge date hasn't passed, the ranking is built on provisional
(incomplete) data and is labeled as such everywhere downstream.

The ranking is the raw backtested signal, unadorned: news and the Claude
narrative are presentation, never inputs to the score.
"""
import datetime as dt
import json

from . import config, mapping


def run():
    signals = json.loads((config.DERIVED_DIR / "signals.json").read_text())
    backtest = json.loads((config.DERIVED_DIR / "backtest.json").read_text())
    recipients = mapping.load_recipients()
    sectors = {s["sector_id"]: s for s in mapping.load_sectors()}
    today = dt.date.today()

    cutoff = (today - dt.timedelta(days=config.RANK_MIN_AGE_DAYS)).isoformat()
    usable = [r for r in signals["tickers"] if r["quarter_end"] <= cutoff and r["z"] is not None]
    if not usable:
        raise RuntimeError("no usable signal rows to rank")
    rank_q = max(r["quarter_end"] for r in usable)
    rows = [r for r in usable if r["quarter_end"] == rank_q
            and r["trailing4"] >= config.DOLLAR_FLOOR]

    def enrich(r):
        info = recipients.get(r["id"], {})
        return {
            **r,
            "ticker": r["id"],
            "parent": info.get("parent", r["id"]),
            "sector": info.get("sector", ""),
            "delta": round(r["obligations"] - r["trailing_mean"], 2),
            "track": backtest["track"].get(r["id"]),
        }

    buys = sorted((r for r in rows if r["z"] > 0), key=lambda r: -r["z"])[:config.PICKS_N]
    fades = sorted((r for r in rows if r["z"] < 0), key=lambda r: r["z"])[:config.FADES_N]
    picks = [enrich(r) for r in buys]
    fade_rows = [enrich(r) for r in fades]

    sector_rows = [
        {**r, "label": sectors[r["id"]]["label"], "etf": sectors[r["id"]]["etf"]}
        for r in signals["sectors"] if r["quarter_end"] == rank_q
    ]

    provisional = any(r["provisional"] for r in buys + fades)
    print(f"  ranking quarter {rank_q} (provisional={provisional}): "
          f"{len(picks)} picks, {len(fade_rows)} fades; "
          f"top pick {picks[0]['ticker'] if picks else '—'} "
          f"z={picks[0]['z'] if picks else '—'}")

    out = {"quarter_end": rank_q, "provisional": provisional,
           "generated": today.isoformat(),
           "picks": picks, "fades": fade_rows, "sectors": sector_rows}
    (config.DERIVED_DIR / "picks.json").write_text(json.dumps(out))
    return out
