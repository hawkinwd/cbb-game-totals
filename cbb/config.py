"""Settings in one place."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ESPN_SCOREBOARD = (
    "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard"
)

# Where the game log (committed to the repo) and the site's data file live.
DATA_FILE = ROOT / "data" / "games.jsonl"
SLATE_FILE = ROOT / "docs" / "data" / "slate.json"

# First day to pull when backfilling (YYYYMMDD). Days with no games are harmless.
SEASON_START = "20261101"

# The sheet uses each team's previous 5 games.
GAMES_PER_TEAM = 5

# ESPN season types: 1 = preseason/exhibition, 2 = regular season, 3 = postseason.
# Exhibitions are left out of the "previous 5".
EXCLUDE_SEASON_TYPES = {1}

# Slate on the site: today plus this many days ahead (US Eastern dates).
SLATE_DAYS_AHEAD = 1

# Games with these ESPN statuses are not shown on the slate.
HIDDEN_STATUSES = {"STATUS_POSTPONED", "STATUS_CANCELED", "STATUS_CANCELLED"}
