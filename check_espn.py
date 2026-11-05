#!/usr/bin/env python3
"""
Quick check: does ESPN's unofficial scoreboard API give us what we need
for men's college basketball? (schedule, final scores, and totals lines)

No dependencies, Python 3.8+.

Usage:
  python check_espn.py                    # today, tomorrow, and yesterday (US Eastern-ish)
  python check_espn.py 20260105 20260106  # specific dates (YYYYMMDD)
  python check_espn.py --list 20260105    # also print every game
  python check_espn.py --team 150         # also show a team's recent results (150 = Duke)
"""
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball"
HEADERS = {"User-Agent": "Mozilla/5.0 (cbb-totals-check)"}


def get_json(url, params=None):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def scoreboard(date):
    # groups=50 -> all Division I games (not just featured); limit raised so nothing is cut off
    return get_json(f"{BASE}/scoreboard", {"dates": date, "groups": 50, "limit": 500})


def parse_event(ev):
    comp = ev["competitions"][0]
    teams = {c["homeAway"]: c for c in comp["competitors"]}
    away, home = teams.get("away"), teams.get("home")
    odds = (comp.get("odds") or [None])[0]
    status = ev["status"]["type"]
    return {
        "id": ev["id"],
        "date": ev["date"],
        "state": status["state"],  # pre / in / post
        "away": away["team"]["displayName"] if away else "?",
        "away_id": away["team"]["id"] if away else None,
        "home": home["team"]["displayName"] if home else "?",
        "home_id": home["team"]["id"] if home else None,
        "away_score": away.get("score") if away else None,
        "home_score": home.get("score") if home else None,
        "total": odds.get("overUnder") if odds else None,
        "book": (odds.get("provider") or {}).get("name") if odds else None,
    }


def check_date(date, list_games=False):
    data = scoreboard(date)
    with open("data.json", "w") as file:
        json.dump(data, file)
    games = [parse_event(e) for e in data.get("events", [])]
    n = len(games)
    with_total = [g for g in games if g["total"] is not None]
    by_state = {}
    for g in games:
        by_state[g["state"]] = by_state.get(g["state"], 0) + 1
    pct = (100 * len(with_total) / n) if n else 0
    print(f"\n=== {date} ===")
    print(f"games: {n}   states: {by_state}")
    print(f"with a totals line: {len(with_total)}/{n} ({pct:.0f}%)")
    if with_total:
        books = {}
        for g in with_total:
            books[g["book"]] = books.get(g["book"], 0) + 1
        print(f"books: {books}")
    missing = [g for g in games if g["total"] is None]
    if missing:
        sample = ", ".join(f"{g['away']} @ {g['home']}" for g in missing[:5])
        print(f"no line (first 5): {sample}")
    if list_games:
        print()
        for g in games:
            score = f"{g['away_score']}-{g['home_score']}" if g["state"] != "pre" else "  -  "
            print(f"  [{g['state']:4}] {g['away']} @ {g['home']:<28} score {score:<9} total {g['total']}")
    return games


def check_team(team_id):
    """Show a team's completed games -> proves we can build 'last 5' game logs."""
    data = get_json(f"{BASE}/teams/{team_id}/schedule")
    name = data.get("team", {}).get("displayName", team_id)
    print(f"\n=== Recent results: {name} (id {team_id}) ===")
    rows = []
    for ev in data.get("events", []):
        comp = ev["competitions"][0]
        if not comp["status"]["type"].get("completed"):
            continue
        parts = []
        for c in comp["competitors"]:
            sc = c.get("score")
            sc = sc.get("value") if isinstance(sc, dict) else sc
            parts.append((c["team"]["displayName"], int(float(sc))))
        total = sum(p[1] for p in parts)
        rows.append((ev["date"][:10], " vs ".join(f"{n} {s}" for n, s in parts), total))
    for r in rows[-5:]:
        print(f"  {r[0]}  {r[1]}  (total {r[2]})")
    if not rows:
        print("  no completed games yet (early season?)")


def main(argv):
    list_games = "--list" in argv
    team = None
    if "--team" in argv:
        team = argv[argv.index("--team") + 1]
    dates = [a for a in argv if a.isdigit() and len(a) == 8]
    if not dates:
        now = datetime.now(timezone.utc) - timedelta(hours=5)  # rough US Eastern
        dates = [(now + timedelta(days=d)).strftime("%Y%m%d") for d in (0, 1, -1)]
    for d in dates:
        try:
            check_date(d, list_games)
        except Exception as e:
            print(f"\n=== {d} ===\nFAILED: {e}")
    if team:
        try:
            check_team(team)
        except Exception as e:
            print(f"\nteam check FAILED: {e}")
    print("\nDone. Key things to look at: % with a totals line, and whether past dates (state=post) still show one.")


if __name__ == "__main__":
    main(sys.argv[1:])