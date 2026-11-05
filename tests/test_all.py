"""Run with:  python -m unittest discover -s tests -v   (from the repo root; no installs needed)"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cbb import espn, model, store  # noqa: E402

FIX = json.loads((Path(__file__).parent / "fixtures.json").read_text())


def mk_game(gid, day, away, home, a_score, h_score, state="post", line=None):
    return {
        "id": gid, "date": f"2026-11-{day:02d}T23:00Z", "status": "STATUS_FINAL" if state == "post" else "STATUS_SCHEDULED",
        "state": state, "completed": state == "post", "season_type": 2,
        "away": {"id": away, "name": f"Team{away}", "score": a_score},
        "home": {"id": home, "name": f"Team{home}", "score": h_score},
        "line": line, "line_book": "DK" if line else None, "line_state": "pre" if line else None, "line_ts": None,
    }


def games_from_totals(totals_a, totals_h, line, a_id="A", h_id="H"):
    """Previous games for each team (vs throwaway opponents), then the game to predict on Nov 20."""
    games = {}
    for tid, totals, k in ((a_id, totals_a, "a"), (h_id, totals_h, "h")):
        for i, t in enumerate(totals):
            own = t // 2
            gid = f"{k}{i}"
            games[gid] = mk_game(gid, 1 + i, tid, f"opp-{k}{i}", own, t - own)
    games["target"] = mk_game("target", 20, a_id, h_id, None, None, state="pre", line=line)
    return games


class SheetParity(unittest.TestCase):
    """Reproduce the real numbers your workbook produced for these game blocks."""

    def test_fixtures(self):
        self.assertGreaterEqual(len(FIX), 5)
        for f in FIX:
            games = games_from_totals(f["a"], f["b"], f["line"])
            res = model.compute_game(games["target"], model.build_index(games))
            label = f"sheet {f['sheet']} row {f['row']}"
            self.assertEqual(res["pick"], f["pick"], label)
            self.assertAlmostEqual(res["diff"], f["diff"], places=5, msg=label)
            self.assertAlmostEqual(res["asd"], f["asd"], places=5, msg=label)
            self.assertAlmostEqual(res["l10"], f["l10"], places=6, msg=label)


class Rules(unittest.TestCase):
    def test_l3_is_middle_three_not_last_three(self):
        totals = [100, 150, 120, 130, 110]  # sum 610, min 100, max 150 -> middle three = 360
        games = games_from_totals(totals, totals, 130.0)
        res = model.compute_game(games["target"], model.build_index(games))
        self.assertEqual(res["away"]["l3"], 360)
        self.assertEqual(res["away"]["l5"], 610)

    def test_ties_follow_sheet_strict_greater_than(self):
        # both averages exactly equal to the line -> not "over" -> pick 'u'
        totals = [140, 140, 140, 140, 140]
        games = games_from_totals(totals, totals, 140.0)
        res = model.compute_game(games["target"], model.build_index(games))
        self.assertEqual(res["pick"], "u")
        self.assertEqual(res["l10"], 0.0)

    def test_split_is_np(self):
        # last-5 avg above the line, L3 (middle three) below it
        a = [130, 130, 130, 200, 100]  # L3=130/3avg 130, L5avg 138
        games = games_from_totals(a, a, 135.0)
        res = model.compute_game(games["target"], model.build_index(games))
        self.assertEqual(res["pick"], "NP")

    def test_not_enough_games_is_flagged_not_guessed(self):
        games = games_from_totals([140, 150, 160], [140, 150, 160, 150], 145.0)
        res = model.compute_game(games["target"], model.build_index(games))
        self.assertIsNone(res["pick"])
        self.assertIn("5 games", res["reason"])
        self.assertEqual(res["away"]["available"], 3)
        self.assertEqual(res["home"]["available"], 4)
        self.assertEqual(len(res["away"]["prev"]), 3)  # still shows what exists

    def test_no_line_means_no_pick(self):
        games = games_from_totals([140] * 5, [140] * 5, None)
        res = model.compute_game(games["target"], model.build_index(games))
        self.assertIsNone(res["pick"])
        self.assertEqual(res["reason"], "no line yet")

    def test_only_games_before_tipoff_count(self):
        games = games_from_totals([140] * 5, [140] * 5, 140.0)
        games["later"] = mk_game("later", 25, "A", "zzz", 90, 90)  # after the target game
        games["same-day-final"] = mk_game("sdf", 20, "A", "q", 100, 100)  # same tip time -> excluded
        res = model.compute_game(games["target"], model.build_index(games))
        self.assertEqual([r["total"] for r in res["away"]["prev"]], [140] * 5)

    def test_preseason_excluded(self):
        games = games_from_totals([140] * 5, [140] * 5, 140.0)
        games["exh"] = mk_game("exh", 15, "A", "zzz", 50, 50)
        games["exh"]["season_type"] = 1
        res = model.compute_game(games["target"], model.build_index(games))
        self.assertEqual([r["total"] for r in res["away"]["prev"]], [140] * 5)

    def test_game_over_under_counts_use_saved_lines(self):
        games = games_from_totals([150, 150, 150, 150, 150], [150, 150, 150, 150, 150], 140.0)
        for k in ("a0", "a1", "h0"):
            games[k]["line"] = 145.0  # total 150 > 145 -> over
        games["a2"]["line"] = 155.0  # under
        res = model.compute_game(games["target"], model.build_index(games))
        self.assertEqual((res["g_over"], res["g_under"], res["g_known"], res["g_n"]), (3, 1, 4, 10))
        self.assertEqual(res["away"]["ou"], [2, 1, 3, 5])  # per-team record: 2 over, 1 under, 3 of 5 have lines
        self.assertEqual(res["home"]["ou"], [1, 0, 1, 5])

    def test_team_ou_record_shown_even_before_five_games(self):
        games = games_from_totals([150, 150, 150], [150] * 5, 140.0)
        games["a0"]["line"], games["a1"]["line"] = 145.0, 155.0
        res = model.compute_game(games["target"], model.build_index(games))
        self.assertIsNone(res["pick"])
        self.assertEqual(res["away"]["ou"], [1, 1, 2, 3])  # 3 games counted, 2 have lines
        self.assertEqual((res["g_over"], res["g_under"], res["g_known"], res["g_n"]), (1, 1, 2, 8))

    def test_push_counts_as_neither(self):
        games = games_from_totals([150] * 5, [150] * 5, 140.0)
        games["a0"]["line"] = 150.0
        res = model.compute_game(games["target"], model.build_index(games))
        self.assertEqual(res["away"]["ou"], [0, 0, 1, 5])


class Archive(unittest.TestCase):
    def test_every_day_with_games_is_built_point_in_time(self):
        from datetime import date
        games = games_from_totals([140, 150, 160, 145, 155], [140] * 5, 145.0)
        index, days = model.build_site(games, today=date(2026, 11, 20))
        dates = [d["date"] for d in index["dates"]]
        self.assertEqual(dates, sorted(dates))
        self.assertEqual(dates[0], "2026-11-01")
        self.assertEqual(dates[-1], "2026-11-20")
        self.assertEqual(index["today"], "2026-11-20")
        self.assertEqual(set(dates), set(days))
        # the Nov 3 game for team A only had 2 earlier games at the time
        nov3 = {g["id"]: g for g in days["2026-11-03"]["games"]}["a2"]
        self.assertEqual(nov3["away"]["available"], 2)
        self.assertIsNone(nov3["pick"])
        # the game on the 20th sees all five
        self.assertEqual(days["2026-11-20"]["games"][0]["away"]["available"], 5)
        self.assertIsNotNone(days["2026-11-20"]["games"][0]["pick"])

    def test_days_beyond_the_ahead_limit_are_left_out(self):
        from datetime import date, timedelta
        from cbb import config
        games = games_from_totals([140] * 5, [140] * 5, 145.0)  # the game being predicted is on 2026-11-20
        target = date(2026, 11, 20)
        ahead = config.SLATE_DAYS_AHEAD
        # target is exactly `ahead` days away -> shown
        _, days = model.build_site(games, today=target - timedelta(days=ahead))
        self.assertIn("2026-11-20", days)
        # one day further out -> not shown
        _, days = model.build_site(games, today=target - timedelta(days=ahead + 1))
        self.assertNotIn("2026-11-20", days)


class LineFreezing(unittest.TestCase):
    def fetched(self, state, line, book="DK"):
        g = mk_game("g1", 5, "A", "B", None if state == "pre" else 70, None if state == "pre" else 72, state=state)
        g.pop("line_state"), g.pop("line_ts")
        g["line"], g["line_book"] = line, (book if line else None)
        g["state"] = state
        g["completed"] = state == "post"
        return g

    def test_line_updates_pregame_then_freezes(self):
        db = {}
        store.merge(db, [self.fetched("pre", 140.5)], "t1")
        store.merge(db, [self.fetched("pre", 141.5)], "t2")
        self.assertEqual(db["g1"]["line"], 141.5)
        store.merge(db, [self.fetched("in", 120.5)], "t3")  # live-game total must be ignored
        store.merge(db, [self.fetched("post", 150.0)], "t4")  # leftover odds must not overwrite
        self.assertEqual(db["g1"]["line"], 141.5)
        self.assertEqual(db["g1"]["state"], "post")

    def test_empty_line_never_erases(self):
        db = {}
        store.merge(db, [self.fetched("pre", 140.5)], "t1")
        store.merge(db, [self.fetched("pre", None)], "t2")
        self.assertEqual(db["g1"]["line"], 140.5)

    def test_post_game_can_fill_a_missing_line(self):
        db = {}
        store.merge(db, [self.fetched("post", None)], "t1")
        store.merge(db, [self.fetched("post", 139.5)], "t2")
        self.assertEqual((db["g1"]["line"], db["g1"]["line_state"]), (139.5, "post"))

    def test_save_load_roundtrip(self):
        import tempfile
        db = {}
        store.merge(db, [self.fetched("pre", 140.5)], "t1")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "g.jsonl"
            store.save(db, p)
            self.assertEqual(store.load(p), db)


class EspnParsing(unittest.TestCase):
    def payload(self, state="pre", completed=False, odds=True):
        comp = {
            "competitors": [
                {"homeAway": "home", "score": "75", "team": {"id": "2", "shortDisplayName": "Home U"}},
                {"homeAway": "away", "score": "70", "team": {"id": "1", "shortDisplayName": "Away U"}},
            ],
            "odds": [{"provider": {"name": "DraftKings"}, "overUnder": 145.5}] if odds else [],
        }
        return {"events": [{
            "id": "401", "date": "2026-11-05T23:00Z", "season": {"type": 2},
            "status": {"type": {"state": state, "completed": completed, "name": "STATUS_X"}},
            "competitions": [comp],
        }, {"id": "bad"}]}

    def test_pregame(self):
        g = espn.parse_events(self.payload())[0]
        self.assertEqual((g["line"], g["line_book"], g["state"]), (145.5, "DraftKings", "pre"))
        self.assertIsNone(g["away"]["score"])  # pregame zeros are not real scores
        self.assertEqual(g["away"]["name"], "Away U")

    def test_final_and_malformed_event_skipped(self):
        games = espn.parse_events(self.payload("post", True, odds=False))
        self.assertEqual(len(games), 1)  # the malformed one was dropped
        self.assertTrue(games[0]["completed"])
        self.assertEqual((games[0]["away"]["score"], games[0]["home"]["score"]), (70, 75))
        self.assertIsNone(games[0]["line"])


if __name__ == "__main__":
    unittest.main()