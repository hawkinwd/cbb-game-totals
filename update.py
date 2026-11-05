#!/usr/bin/env python3
"""
Pull from ESPN, update the game log, rebuild the site's data file.

  python update.py                    # normal run: last 2 days + today + tomorrow
  python update.py --from 20261101    # backfill from the season's first day
  python update.py --build-only       # no network; just rebuild docs/data/slate.json
"""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone

from cbb import config, espn, model, store


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", help="first date to pull, YYYYMMDD (backfill)")
    ap.add_argument("--days-back", type=int, default=2)
    ap.add_argument("--days-ahead", type=int, default=1)
    ap.add_argument("--build-only", action="store_true")
    args = ap.parse_args()

    games = store.load()
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")

    if not args.build_only:
        today = datetime.now(model.ET).date()
        if args.start:
            start = datetime.strptime(args.start, "%Y%m%d").date()
        else:
            start = today - timedelta(days=args.days_back)
        end = today + timedelta(days=args.days_ahead)

        ok_days = bad_days = 0
        d = start
        while d <= end:
            ymd = d.strftime("%Y%m%d")
            try:
                fetched = espn.parse_events(espn.fetch_scoreboard(ymd))
                added, changed = store.merge(games, fetched, now_iso)
                with_line = sum(1 for g in fetched if g["line"] is not None)
                print(f"{ymd}: {len(fetched)} games, {with_line} with a line "
                      f"(+{added} new, {changed} updated)")
                ok_days += 1
            except Exception as e:
                print(f"{ymd}: FAILED - {e}", file=sys.stderr)
                bad_days += 1
            d += timedelta(days=1)
        if ok_days == 0:
            sys.exit("Every fetch failed; leaving data untouched.")
        store.save(games)

    slate = model.build_slate(games)
    config.SLATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.SLATE_FILE.write_text(json.dumps(slate, separators=(",", ":")), encoding="utf-8")
    n = sum(len(day["games"]) for day in slate["days"])
    print(f"slate: {n} games over {len(slate['days'])} days -> {config.SLATE_FILE}")


if __name__ == "__main__":
    main()
