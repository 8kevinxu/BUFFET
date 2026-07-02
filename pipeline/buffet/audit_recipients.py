"""Stage 1b: recipient-matching audit.

Investigated and rejected: aggregating by parent-UEI recipient hashes. The
parent (-P) rollup undercounts badly on historical data (verified 2026-07-02:
LMT FY2024Q1 = $5.3B via parent hash vs $12.0B via pattern search) because
many older transactions carry no parent linkage. Pattern search is token-based
on the API side and demonstrably captures the full corporate family.

So the aggregation stays pattern-based, and this stage makes it auditable:
for every ticker pattern it resolves the actual recipient entities the API
matches (name, UEI, level, lifetime amount), flags suspicious matches (the
pattern not appearing as a whole word), and publishes the result so a bad
mapping is visible on the company page instead of silently poisoning a series.
"""
import datetime as dt
import json
import re

from . import cache, config, mapping

RECIPIENT_API = "https://api.usaspending.gov/api/v2/recipient/"
BY_RECIPIENT_API = "https://api.usaspending.gov/api/v2/search/spending_by_category/recipient/"


def strict_match(name, patterns, overrides=()):
    """The client-side truth rule: a recipient belongs to the ticker if any
    pattern appears at a word boundary OR the name starts with the pattern
    (keeps OPTUMSERVE→OPTUM, MODERNATX→MODERNA, KBRWYLE→KBR; rejects
    CADDELL→DELL, KALEIDOSCOPE→LEIDOS, SAN FRANCISCO→CISCO). Curated
    overrides win over the automatic rule (Sikorsky IS Lockheed)."""
    up = (name or "").upper()
    # normalize punctuation so "CACI, INC. - FEDERAL" matches phrase "CACI INC"
    norm = re.sub(r"\s+", " ", re.sub(r"[.,'\-&]", " ", up)).strip()
    for needle, verdict in overrides:
        if needle in up or re.sub(r"[.,'\-&]", " ", needle) in norm:
            return verdict == "include"
    for p in patterns:
        pn = re.sub(r"\s+", " ", re.sub(r"[.,'\-&]", " ", p)).strip()
        if norm.startswith(pn):
            return True
        if re.search(rf"(?<![A-Z0-9]){re.escape(pn)}(?![A-Z0-9])", norm):
            return True
    return False


def _contamination(ticker, patterns, overrides=()):
    """What the spending endpoint ACTUALLY aggregates for these patterns vs
    what strictly belongs — measured on a recent 2-year window (verified
    2026-07-02: recipient_search_text is fuzzy; 'CISCO' pulls in DELL FEDERAL
    SYSTEMS and San Francisco entities)."""
    end = dt.date.today().isoformat()
    start = (dt.date.today() - dt.timedelta(days=730)).isoformat()
    body = {"filters": {"time_period": [{"start_date": start, "end_date": end}],
                        "recipient_search_text": patterns,
                        "award_type_codes": ["A", "B", "C", "D"]},
            "limit": 100}
    data = cache.post_json(BY_RECIPIENT_API, body, key=f"contam_{ticker}", max_age_days=25)
    good = bad = 0.0
    leaks = []
    for r in data.get("results", []):
        amt = float(r.get("amount") or 0)
        if strict_match(r.get("name"), patterns, overrides):
            good += amt
        else:
            bad += amt
            leaks.append({"name": r.get("name"), "amount": amt})
    total = good + bad
    return {
        "good": round(good, 2), "leaked": round(bad, 2),
        "leak_pct": round(bad / total, 4) if total else 0.0,
        "top_leaks": sorted(leaks, key=lambda x: -x["amount"])[:5],
    }


def _match_entities(pattern):
    body = {"keyword": pattern, "limit": 50, "order": "desc", "sort": "amount"}
    data = cache.post_json(RECIPIENT_API, body, key=f"recip_{pattern}", max_age_days=25)
    out = []
    for r in data.get("results", []):
        name = (r.get("name") or "").upper()
        if pattern not in name:
            continue
        # suspicious if the pattern only ever appears mid-word (e.g. a short
        # pattern buried inside an unrelated company name)
        word = re.search(rf"(?<![A-Z0-9]){re.escape(pattern)}(?![A-Z0-9])", name) is not None
        out.append({"name": r.get("name"), "uei": r.get("uei"),
                    "level": r.get("recipient_level"),
                    "amount": r.get("amount"), "whole_word": word})
    return out


def run():
    recipients = mapping.load_recipients()
    overrides = mapping.load_overrides()
    audit = {}
    suspicious_total = 0
    for i, (ticker, info) in enumerate(sorted(recipients.items()), 1):
        entities = []
        for pattern in info["patterns"]:
            for e in _match_entities(pattern):
                entities.append({**e, "pattern": pattern})
        # dedupe by (name, uei), keep the largest-amount rows first
        seen = set()
        uniq = []
        for e in sorted(entities, key=lambda x: -(x["amount"] or 0)):
            k = (e["name"], e["uei"])
            if k in seen:
                continue
            seen.add(k)
            uniq.append(e)
        suspicious = [e for e in uniq if not e["whole_word"]]
        suspicious_total += len(suspicious)
        contam = _contamination(ticker, info["patterns"], overrides.get(ticker, []))
        audit[ticker] = {
            "matched": len(uniq),
            "top": uniq[:8],
            "suspicious": suspicious[:5],
            "contamination": contam,
        }
        flag = ""
        if contam["leak_pct"] > 0.02:
            flag = (f" 🚨 {contam['leak_pct']:.0%} leaked "
                    f"(top: {contam['top_leaks'][0]['name'] if contam['top_leaks'] else '—'})")
        print(f"  [{i}/{len(recipients)}] {ticker}: {len(uniq)} entities{flag}")

    dirty = [t for t, v in audit.items() if v["contamination"]["leak_pct"] > 0.02]
    print(f"  audit done — {suspicious_total} suspicious name matches; "
          f"{len(dirty)} tickers >2% contaminated: {dirty}")
    (config.DERIVED_DIR / "recipient_audit.json").write_text(json.dumps(audit))
    return audit
