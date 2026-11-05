#!/usr/bin/env python3
"""
Pull from ESPN, update the game log, rebuild the site's data files.

  python update.py                    # normal run: last 2 days + today + tomorrow
  python update.py --from 20261101    # backfill from a specific day
  python update.py --build-only       # no network; just rebuild docs/data/
"""
import argparse
import json
import shutil
import sys
from datetime import datetime, timedelta, timezone

from cbb import config, espn, model, store


def write_site(index, days):
    out = config.SITE_DATA_DIR
    days_dir = out / "days"
    if days_dir.exists():
        shutil.rmtree(days_dir)  # rebuilt from scratch every run, so nothing stale lingers
    days_dir.mkdir(parents=True, exist_ok=True)
    for date, payload in days.items():
        (days_dir / f"{date}.json").write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    (out / "index.json").write_text(json.dumps(index, separators=(",", ":")), encoding="utf-8")


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
        elif not games:  # very first run: pull the season so far
            start = datetime.strptime(config.SEASON_START, "%Y%m%d").date()
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

    index, days = model.build_site(games)
    write_site(index, days)
    n = sum(len(v["games"]) for v in days.values())
    print(f"site: {len(days)} days, {n} games -> {config.SITE_DATA_DIR}")


if __name__ == "__main__":
    main()