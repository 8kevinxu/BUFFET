"""Stage 8: assemble the web artifacts.

Validation gates raise (failing the run loudly, and any CI job with it)
rather than publishing suspiciously empty data — same self-alerting pattern
as the hoopmap refresh workflows.
"""
import datetime as dt
import json

from . import config, mapping

PRICE_TRIM_START = "2007-01-01"  # web charts don't need pre-FY2008 history


def _atomic_write(path, obj):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, separators=(",", ":"), sort_keys=True))
    tmp.replace(path)


def _load(name):
    return json.loads((config.DERIVED_DIR / f"{name}.json").read_text())


def run():
    spending = _load("spending")
    prices = _load("prices")["prices"]
    signals = _load("signals")
    backtest = _load("backtest")
    picks = _load("picks")
    growth = _load("growth")
    portfolio = _load("portfolio")
    try:
        audit = _load("recipient_audit")
    except FileNotFoundError:
        audit = {}
    try:
        awards = _load("awards")
    except FileNotFoundError:
        awards = {"drivers": {}, "recent": {}}
    try:
        survivorship = _load("survivorship")
    except FileNotFoundError:
        survivorship = {"years": [], "top_unmatched": []}
    try:
        announce = _load("announce")
    except FileNotFoundError:
        announce = {"awards": [], "n_alerts": 0, "days_covered": 0}
    ledger = _load("ledger")
    try:
        news = _load("news")
    except FileNotFoundError:
        news = {}
    try:
        thesis = _load("thesis")
    except FileNotFoundError:
        thesis = {"entries": {}, "stale": True}

    recipients = mapping.load_recipients()
    sectors = mapping.load_sectors()

    # --- validation gates ---
    priced = [t for t in recipients if t in prices]
    spent = [t for t, s in spending["tickers"].items() if s]
    fired = [r for r in signals["tickers"] if r["fired"]]
    checks = {
        "tickers with prices >= 40": len(priced) >= 40,
        "tickers with spending >= 30": len(spent) >= 30,
        "fired signals >= 50": len(fired) >= 50,
        "benchmark present": config.BENCHMARK in prices,
        "backtest outcomes >= 30": len(backtest["tickers"]) >= 30,
        "picks nonempty": len(picks["picks"]) > 0,
        "growth horizons complete": all(len(growth["horizons"].get(h, [])) >= 40
                                        for h in ("6m", "1y", "5y", "20y")),
        "portfolio history >= 100 months": portfolio["months"] >= 100,
        "portfolio sweep present": len(portfolio.get("sweep", [])) >= 6,
        # enrichment artifacts may be empty (blocked source) but not malformed
        "survivorship well-formed": isinstance(survivorship.get("years"), list),
        "announce well-formed": isinstance(announce.get("awards"), list),
    }
    failed = [k for k, ok in checks.items() if not ok]
    if failed:
        raise RuntimeError(f"publish validation failed: {failed}")

    web = config.WEB_DATA_DIR
    (web / "prices").mkdir(exist_ok=True)

    # per-symbol price files, lazy-loaded by the Company page
    quotes = {}
    for sym, rows in prices.items():
        trimmed = [r for r in rows if r[0] >= PRICE_TRIM_START]
        _atomic_write(web / "prices" / f"{sym}.json", trimmed)
        if len(rows) >= 2:
            last, prev = rows[-1], rows[-2]
            quotes[sym] = {"date": last[0], "price": last[1],
                           "chg": round(last[1] / prev[1] - 1, 4)}

    universe = {t: {"parent": info["parent"], "sector": info["sector"],
                    "patterns": info["patterns"], "notes": info["notes"]}
                for t, info in recipients.items()}

    _atomic_write(web / "universe.json", universe)
    _atomic_write(web / "spending.json", spending)
    _atomic_write(web / "signals.json", signals)
    _atomic_write(web / "backtest.json", backtest)
    _atomic_write(web / "picks.json", picks)
    _atomic_write(web / "growth.json", growth)
    _atomic_write(web / "portfolio.json", portfolio)
    _atomic_write(web / "audit.json", audit)
    _atomic_write(web / "awards.json", awards)
    _atomic_write(web / "survivorship.json", survivorship)
    _atomic_write(web / "announce.json", announce)
    _atomic_write(web / "ledger.json", ledger)
    _atomic_write(web / "news.json", news)
    _atomic_write(web / "thesis.json", thesis)
    _atomic_write(web / "quotes.json", quotes)
    _atomic_write(web / "meta.json", {
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
        "universe": sorted(recipients),
        "universe_size": len(recipients),
        "sectors": sectors,
        "spending_through": max((max(s) for s in spending["tickers"].values() if s), default=None),
        "prices_through": max((rows[-1][0] for rows in prices.values() if rows), default=None),
        "ranking_quarter": picks["quarter_end"],
        "ranking_provisional": picks["provisional"],
        "thesis_stale": thesis.get("stale", False),
        "announce_alerts": announce.get("n_alerts", 0),
        "fades_retired": bool(picks.get("fades_retired")),
        "signal_config": {
            "zscore_window": config.ZSCORE_WINDOW, "z_buy": config.Z_BUY,
            "z_fade": config.Z_FADE, "dollar_floor": config.DOLLAR_FLOOR,
            "knowledge_lag_days": config.KNOWLEDGE_LAG_DAYS,
            "train_end": config.TRAIN_END, "windows": config.FORWARD_WINDOWS,
        },
    })
    print(f"  published {len(quotes)} price files + 8 artifacts to {web}")
