"""The game log: one JSON object per line in data/games.jsonl, sorted so git diffs stay small."""
import json

from . import config


def load(path=None):
    path = path or config.DATA_FILE
    games = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                g = json.loads(line)
                games[g["id"]] = g
    return games


def save(games, path=None):
    path = path or config.DATA_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(games.values(), key=lambda g: (g["date"], g["id"]))
    text = "\n".join(json.dumps(g, separators=(",", ":"), sort_keys=True) for g in rows)
    path.write_text(text + ("\n" if rows else ""), encoding="utf-8")


def merge(existing, fetched, now_iso):
    """Fold freshly fetched games into the log. Returns (added, changed).

    Line rules (this is what keeps the pre-game total from being overwritten by live odds):
      - while a game is still 'pre', keep taking ESPN's latest line
      - once it tips off, the line is frozen
      - a completed game with no saved line may take ESPN's leftover line (labelled 'post')
      - a line is never replaced by an empty value
    """
    added = changed = 0
    for new in fetched:
        old = existing.get(new["id"])
        rec = dict(new)
        line, book = rec.pop("line"), rec.pop("line_book")

        if old is None:
            rec.update(line=None, line_book=None, line_state=None, line_ts=None)
            if line is not None and new["state"] in ("pre", "post"):
                rec.update(line=line, line_book=book, line_state=new["state"], line_ts=now_iso)
            existing[new["id"]] = rec
            added += 1
            continue

        rec.update({k: old.get(k) for k in ("line", "line_book", "line_state", "line_ts")})
        if line is not None:
            if new["state"] == "pre" and old["state"] == "pre":
                rec.update(line=line, line_book=book, line_state="pre", line_ts=now_iso)
            elif new["state"] == "post" and rec["line"] is None:
                rec.update(line=line, line_book=book, line_state="post", line_ts=now_iso)
        if rec != old:
            existing[new["id"]] = rec
            changed += 1
    return added, changed
