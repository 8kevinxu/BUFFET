"""Stage 6: recent headlines for the picked tickers only (~15 queries).

Primary: Google News RSS (keyless, reliable). Secondary: GDELT DOC 2.0 —
strictly rate-limited (>=6s between hits, and it penalty-boxes IPs), so a
single failure trips a circuit breaker for the rest of the run. News is
enrichment: any failure leaves the ticker with an empty list, never fails
the refresh.
"""
import email.utils
import json
import urllib.parse
import xml.etree.ElementTree as ET

from . import cache, config

GNEWS = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
GDELT = ("https://api.gdeltproject.org/api/v2/doc/doc?query={q}"
         "&mode=artlist&format=json&maxrecords=10&timespan=7d")

_gdelt_dead = False


def _google_news(query, ticker):
    q = urllib.parse.quote(f'"{query}" when:7d')
    xml_text = cache.get_text(GNEWS.format(q=q), key=f"news_g_{ticker}", max_age_days=0.5)
    root = ET.fromstring(xml_text)
    items = []
    for item in root.iter("item"):
        title = item.findtext("title") or ""
        link = item.findtext("link") or ""
        pub = item.findtext("pubDate") or ""
        source = item.findtext("source") or ""
        try:
            when = email.utils.parsedate_to_datetime(pub).date().isoformat()
        except (TypeError, ValueError):
            when = None
        items.append({"title": title, "url": link, "source": source, "date": when})
        if len(items) >= config.NEWS_PER_TICKER:
            break
    return items


def _gdelt(query, ticker):
    global _gdelt_dead
    if _gdelt_dead:
        return []
    q = urllib.parse.quote(f'"{query}"')
    try:
        data = cache.get_json(GDELT.format(q=q), key=f"news_gd_{ticker}",
                              max_age_days=0.5, retries=1)
    except Exception as e:
        print(f"  [news] GDELT tripped circuit breaker ({e}); skipping for this run")
        _gdelt_dead = True
        return []
    arts = data.get("articles", []) if isinstance(data, dict) else []
    return [{"title": a.get("title", ""), "url": a.get("url", ""),
             "source": a.get("domain", ""), "date": (a.get("seendate", "") or "")[:8] or None}
            for a in arts[:config.NEWS_PER_TICKER]]


def run():
    picks = json.loads((config.DERIVED_DIR / "picks.json").read_text())
    targets = {}
    for r in picks["picks"] + picks["fades"]:
        targets[r["ticker"]] = r["parent"]

    news = {}
    for ticker, parent in targets.items():
        items = []
        try:
            items = _google_news(parent, ticker)
        except Exception as e:
            print(f"  [news] {ticker}: google news failed ({e})")
        if not items:
            try:
                items = _gdelt(parent, ticker)
            except Exception as e:
                print(f"  [news] {ticker}: gdelt failed ({e})")
        news[ticker] = items
        print(f"  [news] {ticker}: {len(items)} headlines")

    (config.DERIVED_DIR / "news.json").write_text(json.dumps(news))
    return news
