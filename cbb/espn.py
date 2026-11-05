"""Fetch ESPN's men's college basketball scoreboard and boil each game down to a small record."""
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from . import config

HEADERS = {"User-Agent": "Mozilla/5.0 (cbb-totals)"}


def fetch_scoreboard(yyyymmdd, retries=3):
    """One call per date. groups=50 = every Division I game; limit keeps ESPN from truncating."""
    params = {"dates": yyyymmdd, "groups": 50, "limit": 500}
    url = config.ESPN_SCOREBOARD + "?" + urllib.parse.urlencode(params)
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:  # network hiccup, 5xx, etc.
            last = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"ESPN fetch failed for {yyyymmdd}: {last}")


def _norm_date(s):
    """ESPN gives e.g. 2026-11-04T23:00Z. Normalise so string comparison sorts by time."""
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def _score(c):
    try:
        return int(float(c.get("score")))
    except (TypeError, ValueError):
        return None


def parse_events(data):
    """Turn a scoreboard payload into our compact game records. Skips anything malformed."""
    games = []
    for ev in data.get("events", []):
        try:
            comp = ev["competitions"][0]
            sides = {c["homeAway"]: c for c in comp["competitors"]}
            away, home = sides["away"], sides["home"]
            status = ev.get("status") or comp.get("status") or {}
            stype = status.get("type", {})
            state = stype.get("state", "pre")
            completed = bool(stype.get("completed")) and state == "post"

            def team(c):
                t = c["team"]
                return {
                    "id": str(t["id"]),
                    "name": t.get("shortDisplayName") or t.get("displayName") or t.get("location"),
                    "score": _score(c) if state != "pre" else None,
                }

            line = book = None
            for o in comp.get("odds") or []:
                ou = o.get("overUnder")
                if ou:
                    line = float(ou)
                    book = (o.get("provider") or {}).get("name")
                    break

            season_type = (ev.get("season") or {}).get("type")
            games.append({
                "id": str(ev["id"]),
                "date": _norm_date(ev["date"]),
                "status": stype.get("name"),
                "state": state,
                "completed": completed,
                "season_type": season_type if isinstance(season_type, int) else 2,
                "away": team(away),
                "home": team(home),
                "line": line,
                "line_book": book,
            })
        except (KeyError, IndexError, ValueError, TypeError):
            continue  # one weird event shouldn't sink the whole day
    return games
