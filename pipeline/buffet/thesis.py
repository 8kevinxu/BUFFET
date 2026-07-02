"""Stage 7: Claude-written thesis narrative per current pick.

Presentation only — the ranking is already fixed by the quant signal before
this stage runs. Degrades gracefully: no ANTHROPIC_API_KEY (or no `anthropic`
package) keeps the previous thesis.json and flags it stale. Calls are cached
by (ticker, quarter, input-hash) so unchanged inputs never re-bill.
"""
import hashlib
import json

from . import config

SYSTEM = (
    "You are the narrative engine of a hobbyist stock-research dashboard that "
    "cross-references US federal contract spending with stock performance. "
    "Given the quantitative signal facts for one stock, write a sober, concrete "
    "investment thesis. Never overstate: the backtest stats provided are noisy "
    "and the tool's own UI warns users this is not financial advice. Cite the "
    "specific spending numbers you are given. Keep the thesis to ~120 words."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "thesis": {"type": "string", "description": "~120 word investment thesis"},
        "risks": {"type": "array", "items": {"type": "string"},
                  "description": "exactly 3 short risk bullets"},
    },
    "required": ["thesis", "risks"],
    "additionalProperties": False,
}


def _facts(pick, headlines, side):
    lines = [
        f"Ticker: {pick['ticker']} ({pick['parent']}), sector: {pick['sector']}",
        f"Signal: {side.upper()} — quarterly federal contract obligations z-score "
        f"{pick['z']:+.2f} vs trailing 8-quarter baseline",
        f"Quarter ending {pick['quarter_end']}: ${pick['obligations']/1e6:,.0f}M obligated "
        f"(trailing-8q mean ${pick['trailing_mean']/1e6:,.0f}M, "
        f"delta ${pick['delta']/1e6:+,.0f}M)",
        f"Data is {'PROVISIONAL (recent quarters under-reported due to 90-day DoD publication lag)' if pick['provisional'] else 'final'}",
    ]
    if pick.get("track"):
        t = pick["track"]
        lines.append(f"This ticker's historical signal record: {t['n']} signals, "
                     f"{t['hit_rate']:.0%} hit rate, mean 6-month excess return vs SPY "
                     f"{t['mean_excess']:+.1%}")
    else:
        lines.append("No historical signal track record for this ticker.")
    if pick.get("_drivers"):
        lines.append("Largest actual awards behind the surge quarter:")
        for a in pick["_drivers"][:3]:
            lines.append(f"- ${(a['amount'] or 0)/1e6:,.0f}M {a['agency']}: {a['desc'] or a['award_id']}")
    if headlines:
        lines.append("Recent headlines:")
        lines.extend(f"- {h['title']}" for h in headlines[:8])
    return "\n".join(lines)


def _cache_key(pick, headlines):
    payload = json.dumps([pick["ticker"], pick["quarter_end"], pick["z"],
                          [h["title"] for h in (headlines or [])[:8]]], sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def run():
    picks = json.loads((config.DERIVED_DIR / "picks.json").read_text())
    try:
        news = json.loads((config.DERIVED_DIR / "news.json").read_text())
    except FileNotFoundError:
        news = {}
    try:
        drivers = json.loads((config.DERIVED_DIR / "awards.json").read_text())["drivers"]
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        drivers = {}
    for row in picks["picks"] + picks["fades"]:
        d = drivers.get(row["ticker"])
        if d and d["quarter_end"] == row["quarter_end"]:
            row["_drivers"] = d["rows"]

    out_path = config.DERIVED_DIR / "thesis.json"
    try:
        existing = json.loads(out_path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        existing = {"entries": {}}

    if not config.ANTHROPIC_API_KEY:
        print("  [thesis] ANTHROPIC_API_KEY unset — keeping previous thesis (stale)")
        existing["stale"] = True
        out_path.write_text(json.dumps(existing))
        return existing

    try:
        import anthropic
    except ImportError:
        print("  [thesis] anthropic package not installed — keeping previous thesis (stale)")
        existing["stale"] = True
        out_path.write_text(json.dumps(existing))
        return existing

    client = anthropic.Anthropic()
    entries = {}
    targets = [("buy", p) for p in picks["picks"]] + [("fade", p) for p in picks["fades"]]
    for side, pick in targets:
        t = pick["ticker"]
        key = _cache_key(pick, news.get(t))
        prev = existing.get("entries", {}).get(t)
        if prev and prev.get("cache_key") == key:
            entries[t] = prev
            continue
        try:
            resp = client.messages.create(
                model=config.THESIS_MODEL,
                max_tokens=1024,
                system=SYSTEM,
                output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
                messages=[{"role": "user", "content": _facts(pick, news.get(t), side)}],
            )
            body = json.loads(resp.content[0].text)
            entries[t] = {"thesis": body["thesis"], "risks": body["risks"][:3],
                          "model": config.THESIS_MODEL, "cache_key": key,
                          "quarter_end": pick["quarter_end"]}
            print(f"  [thesis] {t}: generated ({config.THESIS_MODEL})")
        except anthropic.APIError as e:
            print(f"  [thesis] {t}: API error ({e}); keeping previous if any")
            if prev:
                entries[t] = prev
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            print(f"  [thesis] {t}: bad response shape ({e}); skipping")

    out = {"entries": entries, "stale": False}
    out_path.write_text(json.dumps(out))
    return out
