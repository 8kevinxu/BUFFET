"""Stage 6c: the EARLY-SIGNAL tier — same-day DoD contract announcements.

The quarterly signal can't see an award until the FPDS embargo clears
(knowledge date = quarter end + 135 days). But DoD publicly announces every
contract action over ~$7.5M the day it happens, at war.gov/News/Contracts
(formerly defense.gov). This stage scans those daily announcements, matches
each award paragraph against the universe's recipient patterns, and flags
awards that are MATERIAL (>= MATERIALITY_MIN of the ticker's latest annual
revenue) — surfacing months before the obligations data can.

These are context, not backtested signals: the announcement archive reachable
from the RSS covers only ~3 months, so no historical backtest of
announcement-dated entries exists (yet). The dashboard labels the tier
accordingly.

This tier is also the CEILING indicator: announced values are the full
contract/IDIQ ceiling, which leads obligations by quarters-to-years (verified
2026-07-02: AVAV's $500M counter-UAS IDIQ shows $0 obligated in USAspending —
IDV "Award Amount" is zero until task orders land, and the search API exposes
no base-and-all-options field — yet it alerts here at 25% of revenue on
day one). A historical ceiling backtest isn't feasible with free structured
data; the per-award detail endpoint has the field but would need thousands of
calls per ticker.

Plumbing notes (verified 2026-07-02):
- The RSS index (ContentType=400, Site=945) is fetchable from plain Python.
- Article BODIES are Akamai TLS-fingerprint-gated: curl/urllib get 403 even
  with a browser User-Agent; headless system Chrome with a real UA works.
  Bodies are fetched via web/scripts/fetch-page.mjs (playwright-core) and
  cached forever — announcements are immutable once published.
- Non-fatal stage: no node/Chrome, or Akamai blocking the runner's IP,
  degrades to the cached articles (or the previous announce.json).
"""
import datetime as dt
import email.utils
import json
import re
import shutil
import subprocess

from . import cache, config, mapping
from .audit_recipients import strict_match

RSS_URL = ("https://www.war.gov/DesktopModules/ArticleCS/RSS.ashx"
           "?ContentType=400&Site=945&max=60")
WEB_DIR = config.REPO_ROOT / "web"

AWARD_VERBS = re.compile(
    r"\b(?:was|is being|has been|are being|were)\s+awarded\b", re.I)
AMOUNT = re.compile(r"\$([\d,]+(?:\.\d+)?)")


def _rss_items():
    xml = cache.get_text(RSS_URL, key="dod_contracts_rss", max_age_days=0.5)
    items = []
    for m in re.finditer(r"<item>(.*?)</item>", xml, re.S):
        block = m.group(1)
        link = re.search(r"<link>(.*?)</link>", block, re.S)
        pub = re.search(r"<pubDate>(.*?)</pubDate>", block, re.S)
        if not link or not pub:
            continue
        url = link.group(1).strip()
        date = email.utils.parsedate_to_datetime(pub.group(1).strip()).date()
        items.append({"url": url, "date": date.isoformat()})
    return items


def _article_cache_path(url):
    aid = re.search(r"/Article/(\d+)/", url)
    return config.RAW_DIR / f"dod_article_{aid.group(1) if aid else 'x'}.txt"


def _fetch_articles(urls):
    """Fetch article bodies through headless Chrome; permanent per-URL cache."""
    texts = {}
    missing = []
    for url in urls:
        p = _article_cache_path(url)
        if p.exists():
            texts[url] = p.read_text()
        else:
            missing.append(url)
    if missing:
        if not shutil.which("node"):
            print("  [announce] node not found — using cached articles only")
            return texts
        # batches keep a single browser launch per call
        for i in range(0, len(missing), 15):
            batch = missing[i:i + 15]
            try:
                out = subprocess.run(
                    ["node", "scripts/fetch-page.mjs", *batch],
                    cwd=WEB_DIR, capture_output=True, text=True, timeout=600)
                fetched = json.loads(out.stdout or "{}")
            except (subprocess.SubprocessError, json.JSONDecodeError) as e:
                print(f"  [announce] article fetch failed ({e}) — continuing with cache")
                break
            for url, text in fetched.items():
                if text:
                    _article_cache_path(url).write_text(text)
                    texts[url] = text
    return texts


def _parse_awards(text):
    """Split an announcement into per-award paragraphs.

    Format (stable for years): branch headers in CAPS (ARMY / NAVY / ...),
    then one paragraph per award: 'Company Name, City, State, was awarded a
    $X,XXX,XXX <type> contract for <description>. ...'
    """
    awards = []
    for para in re.split(r"\n\s*\n|\n(?=[A-Z][a-z])", text):
        para = " ".join(para.split())
        if len(para) < 80 or not AWARD_VERBS.search(para):
            continue
        m = AMOUNT.search(para)
        if not m:
            continue
        amount = float(m.group(1).replace(",", ""))
        company = AWARD_VERBS.split(para)[0].strip().rstrip(",").rstrip("*").strip()
        if len(company) > 120:   # merged paragraphs; take the last sentence head
            company = company.split(". ")[-1]
        awards.append({"company": company, "amount": amount,
                       "text": para[:400], "modification": "modification" in para.lower()})
    # the same award paragraph can appear twice in one article (joint awards
    # re-listed per branch, or split artifacts) — keep one
    seen = set()
    uniq = []
    for a in awards:
        k = (a["company"], a["amount"], a["text"][:120])
        if k not in seen:
            seen.add(k)
            uniq.append(a)
    return uniq


def _latest_revenue(revenue_rows):
    if not revenue_rows:
        return None
    return max(revenue_rows, key=lambda r: r[0])[2]


def run():
    recipients = mapping.load_recipients()
    overrides = mapping.load_overrides()
    try:
        revenue = json.loads((config.DERIVED_DIR / "fundamentals.json").read_text())["revenue"]
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        revenue = {}

    items = _rss_items()
    if not items:
        raise RuntimeError("announce: RSS returned no items")
    texts = _fetch_articles([i["url"] for i in items])

    matched = []
    parsed_days = 0
    for item in items:
        text = texts.get(item["url"])
        if not text:
            continue
        parsed_days += 1
        for a in _parse_awards(text):
            ticker = next((t for t, info in recipients.items()
                           if strict_match(a["company"], info["patterns"],
                                           overrides.get(t, []))), None)
            if not ticker:
                continue
            rev = _latest_revenue(revenue.get(ticker))
            pct = round(a["amount"] / rev, 5) if rev else None
            matched.append({
                "date": item["date"], "url": item["url"], "ticker": ticker,
                "company": a["company"], "amount": a["amount"],
                "modification": a["modification"], "text": a["text"],
                "pct_revenue": pct,
                "alert": bool(pct is not None and pct >= config.MATERIALITY_MIN),
            })

    matched.sort(key=lambda r: (r["date"], -r["amount"]), reverse=True)
    alerts = [r for r in matched if r["alert"]]
    out = {"generated": dt.date.today().isoformat(),
           "source": "war.gov/News/Contracts (DoD daily announcements, $7.5M+)",
           "days_covered": parsed_days,
           "since": min((i["date"] for i in items), default=None),
           "awards": matched, "n_alerts": len(alerts)}
    (config.DERIVED_DIR / "announce.json").write_text(json.dumps(out))
    print(f"  {parsed_days} announcement days parsed, {len(matched)} universe awards, "
          f"{len(alerts)} material alerts "
          f"({', '.join(f'{a['ticker']} ${a['amount']/1e6:.0f}M' for a in alerts[:5])})")
    return out
