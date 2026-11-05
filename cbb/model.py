"""The daily-sheet math, replicated cell for cell.

Sheet cell -> what it is here
  D4:D8 / H4:H8   "total"        prev[i]["total"]            (team score + opponent score)
  E4:E8 / I4:I8   over flag      prev[i]["over"]             (total > line, strictly)
  D9, D10         min, max       team["min"], team["max"]
  D11             "L3"           team["l3"]   = sum - min - max   (the MIDDLE three of five)
  D12             "L5"           team["l5"]   = sum
  D13, D14        L3 avg, L5 avg team["l3a"], team["l5a"]
  D15             Standard Dev.  team["sd"]   (sample standard deviation, like STDEV)
  K3, K4          2 team L3/L5   game["k3"], game["k4"]  = average of the two teams' averages
  K5:K7           Pick           game["pick"]  'o' both above line, 'u' both at/below, 'NP' split
  K8              diff           game["diff"]  = average(k3, k4) - line
  K9              A.S.D          game["asd"]   = average of the two standard deviations
  K10             L10 vs line    game["l10"]   = overs among the 10 totals / 10
  K11, K12        Games over/under  game["g_over"], game["g_under"]
                  (sheet: typed in by hand; here: counted from each team's previous-5 games
                   against the line saved for that game, where we have one)
"""
import statistics
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import config

ET = ZoneInfo("America/New_York")


def et_date(iso_utc):
    d = datetime.strptime(iso_utc, "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)
    return d.astimezone(ET).date()


def build_index(games):
    """team id -> that team's completed, countable games, newest first."""
    idx = {}
    for g in games.values():
        if not g["completed"] or g["season_type"] in config.EXCLUDE_SEASON_TYPES:
            continue
        if g["away"]["score"] is None or g["home"]["score"] is None:
            continue
        for side in ("away", "home"):
            idx.setdefault(g[side]["id"], []).append(g)
    for lst in idx.values():
        lst.sort(key=lambda g: (g["date"], g["id"]), reverse=True)
    return idx


def prior_rows(idx, team_id, before_iso, exclude_id):
    """The team's games that finished before this one tips off, newest first."""
    rows = []
    for g in idx.get(team_id, []):
        if g["id"] == exclude_id or g["date"] >= before_iso:
            continue
        me, opp = (g["away"], g["home"]) if g["away"]["id"] == team_id else (g["home"], g["away"])
        rows.append({
            "d": g["date"][5:10],  # MM-DD
            "opp": opp["name"],
            "own": me["score"],
            "oppp": opp["score"],
            "total": me["score"] + opp["score"],
            "gline": g.get("line"),  # the line that game itself had, if we saved one
        })
    return rows


def team_block(idx, team, game, line):
    rows = prior_rows(idx, team["id"], game["date"], game["id"])
    out = {"id": team["id"], "name": team["name"], "available": len(rows)}
    use = rows[: config.GAMES_PER_TEAM]
    out["prev"] = [
        {"d": r["d"], "opp": r["opp"], "own": r["own"], "oppp": r["oppp"], "total": r["total"],
         "over": (r["total"] > line) if line is not None else None}
        for r in use
    ]
    out["ok"] = len(use) == config.GAMES_PER_TEAM
    if not out["ok"]:
        return out, None
    totals = [r["total"] for r in use]
    s, mn, mx = sum(totals), min(totals), max(totals)
    l3 = s - mn - mx
    out.update(
        min=mn, max=mx, l3=l3, l5=s,
        l3a=l3 / 3, l5a=s / 5,
        sd=statistics.stdev(totals),
    )
    # Over/under record vs each game's own line (sheet's hand-typed C2/D2/G2/H2).
    over = under = known = 0
    for r in use:
        if r["gline"] is None:
            continue
        known += 1
        if r["total"] > r["gline"]:
            over += 1
        elif r["total"] < r["gline"]:
            under += 1
    out["ou"] = [over, under, known]
    return out, totals


def compute_game(game, idx):
    line = game.get("line")
    a, a_tot = team_block(idx, game["away"], game, line)
    h, h_tot = team_block(idx, game["home"], game, line)
    res = {
        "id": game["id"], "tip": game["date"], "state": game["state"], "status": game["status"],
        "line": line, "book": game.get("line_book"),
        "away": a, "home": h,
        "pick": None, "reason": None,
    }
    if not (a["ok"] and h["ok"]):
        res["reason"] = "need 5 games for each team"
        return res
    if line is None:
        res["reason"] = "no line yet"
        return res

    k3 = (a["l3a"] + h["l3a"]) / 2
    k4 = (a["l5a"] + h["l5a"]) / 2
    n = (1 if k3 > line else 0) + (1 if k4 > line else 0)
    res["k3"], res["k4"] = k3, k4
    res["pick"] = "o" if n == 2 else ("NP" if n == 1 else "u")
    res["diff"] = (k3 + k4) / 2 - line
    res["asd"] = (a["sd"] + h["sd"]) / 2
    overs = sum(1 for t in a_tot + h_tot if t > line)
    res["l10"] = overs / 10
    res["g_over"] = a["ou"][0] + h["ou"][0]
    res["g_under"] = a["ou"][1] + h["ou"][1]
    res["ou_known"] = a["ou"][2] + h["ou"][2]
    return res


def _round(o):
    if isinstance(o, float):
        return round(o, 4)
    if isinstance(o, dict):
        return {k: _round(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_round(v) for v in o]
    return o


def build_slate(games, today=None):
    """Slim JSON for the site: today (US Eastern) plus SLATE_DAYS_AHEAD days."""
    idx = build_index(games)
    today = today or datetime.now(ET).date()
    days = []
    for offset in range(config.SLATE_DAYS_AHEAD + 1):
        day = today + timedelta(days=offset)
        todays = [
            g for g in games.values()
            if et_date(g["date"]) == day
            and g["status"] not in config.HIDDEN_STATUSES
            and g["season_type"] not in config.EXCLUDE_SEASON_TYPES
        ]
        todays.sort(key=lambda g: (g["date"], g["id"]))
        days.append({"date": day.isoformat(), "games": [compute_game(g, idx) for g in todays]})
    return _round({
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "days": days,
    })
