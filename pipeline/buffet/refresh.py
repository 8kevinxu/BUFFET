"""Orchestrate the pipeline: python -m buffet.refresh [--stage NAME]

Stage order matters: news/thesis run after rank (they only cover the picked
tickers). News and thesis failures never fail the run; everything else does.
"""
import argparse
import time

from . import (backtest, fetch_news, fetch_prices, fetch_spending, growth,
               publish, rank, signals, thesis)

STAGES = [
    ("fetch_spending", fetch_spending.run, True),
    ("fetch_prices", fetch_prices.run, True),
    ("signals", signals.run, True),
    ("backtest", backtest.run, True),
    ("rank", rank.run, True),
    ("growth", growth.run, True),
    ("news", fetch_news.run, False),
    ("thesis", thesis.run, False),
    ("publish", publish.run, True),
]


def main():
    parser = argparse.ArgumentParser(prog="python -m buffet.refresh")
    parser.add_argument("--stage", choices=[n for n, _, _ in STAGES],
                        help="run a single stage instead of the full pipeline")
    args = parser.parse_args()

    todo = [(n, fn, req) for n, fn, req in STAGES
            if args.stage is None or n == args.stage]
    t_all = time.monotonic()
    for name, fn, required in todo:
        print(f"== {name} ==")
        t0 = time.monotonic()
        try:
            fn()
        except Exception as e:
            if required:
                raise
            print(f"  [{name}] non-fatal failure: {e}")
        print(f"   ({time.monotonic() - t0:.1f}s)")
    print(f"done in {time.monotonic() - t_all:.1f}s")


if __name__ == "__main__":
    main()
