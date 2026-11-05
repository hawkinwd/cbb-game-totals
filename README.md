# CBB Totals (phase 1)

Replicates the daily sheet (e.g. tab `1231`): each team's previous 5 totals, L3/L5 math, the pick, and the diff. Data comes from ESPN's public scoreboard. No API keys, no installs beyond Python.

## One-time setup

1. **Create a GitHub repo.** Public is simplest. GitHub Pages on a *private* repo needs a paid plan. (The repo only holds public scores and lines.)
2. **Upload the files.** Unzip, then on the repo page: *Add file → Upload files* and drag in everything inside the folder.
   - The `.github` folder is hidden on Mac (Finder: `Cmd+Shift+.` to show it). If it won't upload, use *Add file → Create new file*, name it `.github/workflows/update.yml`, and paste in that file's contents.
3. **Settings → Pages → Source: GitHub Actions.**
4. **Settings → Actions → General → Workflow permissions: Read and write permissions.** Save.
5. **Actions tab → "Update site" → Run workflow**, and type `20261101` in the backfill box. This pulls the season's first days.
6. After it finishes (a minute or two), the site is at `https://<your-username>.github.io/<repo-name>/`.

From then on it refreshes itself every hour.

## What happens each run

1. Tests run (a failing test stops the update so bad math never goes live).
2. `update.py` pulls ESPN's scoreboard for the last 2 days, today, and tomorrow, and merges it into `data/games.jsonl` (one game per line).
3. It rebuilds the site's data from the log (`docs/data/`: an index plus one small file per day) and the site deploys.

The browser only loads those slim files, one day at a time. It never talks to ESPN.

## The archive

The page opens on today. Use the arrows or the dropdown to jump to any earlier day that has games, or to tomorrow. Nothing extra is stored for this: every day is rebuilt from the game log each run, as it stood going into that day. Each game only sees games that finished before its tip-off, and the line that was saved for it.

## How it maps to the sheet

| Sheet | App |
|---|---|
| "Prev 5" totals (score + opponent score) | each team's 5 most recent finished games before tip-off |
| min / max / **L3** / L5 | L3 = sum minus min minus max (middle three of five), same as the sheet |
| L3 avg, L5 avg, Standard Dev. | same (sample standard deviation, like `STDEV`) |
| 2 team L3 / L5 | average of the two teams' averages |
| Pick | `o` if both are above the line, `u` if both are at/below, `NP` if split (strictly greater than, like the sheet) |
| diff, A.S.D, L10 vs line (o%) | same formulas |
| O/U record (e.g. 4–1) next to each team | each team's previous 5 games vs the line saved for each of those games |
| Games over / Games under | the two teams' records added together (out of up to 10 games) |

Checked against your workbook: the same math reproduces the saved results on 3,067 of 3,075 game blocks (the rest look like hand-edited cells).

## Rules and limits to know about

- **Fewer than 5 games:** the game is listed with whatever games exist and the note "Need 5 games for each team." No pick is shown.
- **No line:** no pick. The totals still show.
- **Lines are frozen at tip-off.** While a game is upcoming, each run takes ESPN's latest total. Once it starts, the saved line stops changing, so live odds never overwrite it. A game the app first sees after it has started has no line.
- **O/U records and Games over / under:** your sheet has these typed in by hand. Here they're counted from each team's previous 5 games against the line saved for *that* game. A game with no saved line isn't counted, and a push counts as neither. The page shows how many of the games had a line (e.g. "3 of 5 lines"), so early on the records will be partial until more days of lines are stored.
- **Preseason games are left out** of the previous 5 (ESPN's season type 1). Games vs. non-D1 teams count if ESPN lists them.
- Dates and "today" use US Eastern time.
- On each game row, the opponent and date next to a past score are shown so you can check the numbers against your sheet.

## Run it locally

```
python update.py --from 20261101      # pull + build (first run with an empty log starts at the season start in cbb/config.py)
python -m http.server -d docs         # open http://localhost:8000
python -m unittest discover -s tests  # tests
```

## Files

- `cbb/espn.py` fetches and trims ESPN's data.
- `cbb/store.py` is the game log and the line-freezing rules.
- `cbb/model.py` is the sheet math and the day-by-day site build.
- `cbb/config.py` has settings (season start, games per team, etc.).
- `docs/index.html` is the site.
- `.github/workflows/update.yml` is the hourly job.
