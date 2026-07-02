"""Load and validate the hand-curated recipient/sector mapping tables."""
import csv
from collections import defaultdict

from . import config


def load_recipients():
    """Returns {ticker: {"patterns": [...], "parent": str, "sector": str,
    "history_starts": "YYYY-MM-DD" | None, "notes": [...]}}"""
    path = config.MAPPING_DIR / "recipients.csv"
    tickers = {}
    seen_patterns = defaultdict(set)
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            t = row["ticker"].strip().upper()
            pattern = row["pattern"].strip().upper()
            if not t or not pattern:
                raise ValueError(f"recipients.csv: empty ticker/pattern in {row}")
            if pattern in seen_patterns[t]:
                raise ValueError(f"recipients.csv: duplicate pattern {pattern} for {t}")
            seen_patterns[t].add(pattern)
            entry = tickers.setdefault(t, {
                "patterns": [], "parent": row["parent_name"].strip(),
                "sector": row["sector"].strip(),
                "history_starts": row["history_starts"].strip() or None,
                "notes": [],
            })
            entry["patterns"].append(pattern)
            if row.get("notes", "").strip():
                entry["notes"].append(row["notes"].strip())
    if len(tickers) < 20:
        raise ValueError(f"recipients.csv suspiciously small ({len(tickers)} tickers)")
    return tickers


def load_overrides():
    """Curated include/exclude verdicts for recipient names the automatic
    word-boundary rule gets wrong (parent-linked subsidiaries, GOCO pass-
    throughs, cross-company fuzz). Returns {ticker: [(name_contains, verdict)]}."""
    path = config.MAPPING_DIR / "recipient_overrides.csv"
    out = defaultdict(list)
    if path.exists():
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                out[row["ticker"].strip().upper()].append(
                    (row["name_contains"].strip().upper(), row["verdict"].strip()))
    return out


def load_sectors():
    """Returns [{sector_id, agency, etf, label}]"""
    path = config.MAPPING_DIR / "sectors.csv"
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError("sectors.csv is empty")
    return rows


def all_price_symbols(recipients, sectors):
    syms = (set(recipients) | {s["etf"] for s in sectors}
            | {config.BENCHMARK} | set(config.EXTRA_BENCHMARKS))
    return sorted(syms)
