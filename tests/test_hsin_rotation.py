"""Hsin rotation and guide-data tests.

The rotation encoded in :mod:`src.char.Hsin` is transcribed from Rexlent's
"How to Hsin for Dummies" (video id ``-JiixPs82UI``). These tests pin the input
order so a future refactor cannot silently drift away from the guide, and they
check that the structured guide data stays consistent with the repo.

The game-coupled primitives (liberation, resonance, echo, switching) are
stubbed; Hsin's own sequencing methods run for real.
"""

import json
import os
import sys
import unittest
from unittest.mock import MagicMock

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from src.char.Hsin import Hsin  # noqa: E402

GUIDE_PATH = os.path.join(REPO_ROOT, "training", "char_guides", "hsin.json")
COCO_PATH = os.path.join(REPO_ROOT, "assets", "coco_annotations.json")
TRANSCRIPT_PATH = os.path.join(REPO_ROOT, "training", "transcripts",
                               "hsin_-JiixPs82UI.en.txt")


def build_hsin(unison=False, forte_ready=True, e_forte_ready=True):
    """Hsin instance whose game I/O is recorded into ``char.actions``."""
    task = MagicMock()
    task.char_config = {"Hsin Unison Mode": unison}
    task.wait_until = MagicMock(side_effect=lambda cond, **kw: bool(cond()))

    char = Hsin(task, 2, char_name="char_hsin")
    char.actions = []

    # --- gauge cues -------------------------------------------------------
    char.is_mouse_forte_full = MagicMock(side_effect=lambda: forte_ready)
    char.is_e_forte_full = MagicMock(side_effect=lambda: e_forte_ready)
    char.resonance_available = MagicMock(return_value=True)

    # --- inputs we want to observe ---------------------------------------
    def rec(name, result=True):
        def _inner(*a, **k):
            char.actions.append(name)
            return result
        return _inner

    char.click = MagicMock(side_effect=rec("basic"))
    char.heavy_click_forte = MagicMock(side_effect=rec("enhanced_heavy"))
    char.click_resonance = MagicMock(side_effect=lambda *a, **k: (
        char.actions.append("resonance") or (True, 0, False)))
    char.click_liberation = MagicMock(side_effect=rec("liberation"))
    char.click_echo = MagicMock(side_effect=rec("echo"))
    char.switch_next_char = MagicMock(side_effect=rec("switch"))

    # --- neutralise timing / world state ---------------------------------
    char.wait_intro = MagicMock()
    char.wait_down = MagicMock()
    char.flying = MagicMock(return_value=False)
    char.check_combat = MagicMock()
    char.sleep = MagicMock()
    char.time_elapsed_accounting_for_freeze = MagicMock(return_value=0.0)
    return char


class HsinModeConfigTests(unittest.TestCase):

    def test_defaults_to_electro_flare(self):
        self.assertFalse(build_hsin(unison=False).is_unison_mode())

    def test_unison_flag_is_read_from_char_config(self):
        self.assertTrue(build_hsin(unison=True).is_unison_mode())

    def test_missing_char_config_is_safe(self):
        char = build_hsin()
        char.task.char_config = None
        self.assertFalse(char.is_unison_mode())

    def test_config_key_matches_config_py_default(self):
        import config
        self.assertIn(Hsin.UNISON_CONFIG_KEY, config.char_config_option.default_config)


class HsinElectroFlareRotationTests(unittest.TestCase):
    """Guide 3:58 - intro, 1 basic, heavy, echo, ult, filler, enhanced E,
    4 basics, heavy, big ult."""

    def setUp(self):
        self.char = build_hsin(unison=False)
        self.char.do_perform()
        self.acts = self.char.actions

    def test_opens_with_single_basic_then_enhanced_heavy(self):
        self.assertEqual(self.acts[0], "basic")
        self.assertEqual(self.acts[1], "enhanced_heavy")

    def test_echo_is_used_between_heavy_and_first_liberation(self):
        head = self.acts[:4]
        self.assertEqual(head, ["basic", "enhanced_heavy", "echo", "liberation"])

    def test_casts_two_liberations(self):
        self.assertEqual(self.acts.count("liberation"), 2)

    def test_uses_two_enhanced_heavy_attacks(self):
        self.assertEqual(self.acts.count("enhanced_heavy"), 2)

    def test_finisher_is_four_basics_then_heavy_then_liberation(self):
        # Anchor on the final enhanced heavy rather than a fixed slice.
        last_heavy = len(self.acts) - 1 - self.acts[::-1].index("enhanced_heavy")
        self.assertEqual(self.acts[last_heavy - 4:last_heavy], ["basic"] * 4,
                         "four unlock taps must precede the final enhanced heavy")
        self.assertEqual(self.acts[last_heavy + 1], "liberation")

    def test_switches_out_at_the_end(self):
        self.assertEqual(self.acts[-1], "switch")

    def test_enhanced_e_happens_before_the_finisher(self):
        self.assertIn("resonance", self.acts)
        last_res = len(self.acts) - 1 - self.acts[::-1].index("resonance")
        last_heavy = len(self.acts) - 1 - self.acts[::-1].index("enhanced_heavy")
        self.assertLess(last_res, last_heavy)


class HsinUnisonRotationTests(unittest.TestCase):
    """Guide 4:39 - the rotation is split over two visits."""

    def test_visit_one_is_two_basics_heavy_echo_liberation_then_outro(self):
        char = build_hsin(unison=True)
        char.do_perform()
        self.assertEqual(char.actions,
                         ["basic", "basic", "enhanced_heavy", "echo", "liberation", "switch"])

    def test_visit_one_does_not_run_the_finisher(self):
        char = build_hsin(unison=True)
        char.do_perform()
        self.assertEqual(char.actions.count("liberation"), 1)
        self.assertEqual(char.actions.count("enhanced_heavy"), 1)

    def test_visit_two_skips_the_filler_and_finishes(self):
        char = build_hsin(unison=True)
        char.do_perform()          # visit 1
        char.actions.clear()
        char.do_perform()          # visit 2
        self.assertEqual(char.actions[:4], ["basic"] * 4)
        self.assertEqual(char.actions[4], "enhanced_heavy")
        self.assertEqual(char.actions[5], "liberation")
        self.assertEqual(char.actions[-1], "switch")
        # The basic/E filler belongs to Electro Flare only.
        self.assertNotIn("resonance", char.actions)

    def test_visits_alternate(self):
        char = build_hsin(unison=True)
        self.assertEqual(char.unison_visit, 0)
        char.do_perform()
        self.assertEqual(char.unison_visit, 1)
        char.do_perform()
        self.assertEqual(char.unison_visit, 0)

    def test_reset_state_restarts_at_visit_one(self):
        char = build_hsin(unison=True)
        char.do_perform()
        self.assertEqual(char.unison_visit, 1)
        char.reset_state()
        self.assertEqual(char.unison_visit, 0)

    def test_combat_end_restarts_at_visit_one(self):
        char = build_hsin(unison=True)
        char.do_perform()
        char.task.send_key = MagicMock()
        char.on_combat_end([char])
        self.assertEqual(char.unison_visit, 0)

    def test_unison_opener_has_one_more_basic_than_electro_flare(self):
        flare = build_hsin(unison=False)
        flare.do_perform()
        unison = build_hsin(unison=True)
        unison.do_perform()
        flare_opener = flare.actions[:flare.actions.index("enhanced_heavy")]
        unison_opener = unison.actions[:unison.actions.index("enhanced_heavy")]
        self.assertEqual(len(unison_opener), len(flare_opener) + 1)


class HsinDegradedCueTests(unittest.TestCase):
    """The rotation must not hang when a gauge cue never shows up."""

    def test_enhanced_heavy_is_skipped_when_forte_never_fills(self):
        char = build_hsin(unison=False, forte_ready=False)
        char.do_perform()
        self.assertNotIn("enhanced_heavy", char.actions)
        self.assertEqual(char.actions[-1], "switch")

    def test_enhanced_e_is_skipped_when_second_bar_never_fills(self):
        char = build_hsin(unison=False, e_forte_ready=False)
        char.do_perform()
        self.assertEqual(char.actions[-1], "switch")

    def test_perform_enhanced_heavy_reports_failure(self):
        char = build_hsin(forte_ready=False)
        self.assertFalse(char.perform_enhanced_heavy())

    def test_perform_enhanced_e_reports_failure(self):
        char = build_hsin(e_forte_ready=False)
        self.assertFalse(char.perform_enhanced_e())


class HsinGuideDataTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open(GUIDE_PATH, encoding="utf-8") as fh:
            cls.guide = json.load(fh)

    def test_guide_points_at_the_right_video(self):
        self.assertEqual(self.guide["source"]["video_id"], "-JiixPs82UI")
        self.assertEqual(self.guide["character"], "char_hsin")

    def test_transcript_file_exists(self):
        self.assertTrue(os.path.exists(TRANSCRIPT_PATH))

    def test_capture_points_are_ordered_and_in_range(self):
        pts = self.guide["capture_points"]
        self.assertGreater(len(pts), 10)
        seconds = [p["seconds"] for p in pts]
        self.assertEqual(seconds, sorted(seconds), "capture points must be in time order")
        duration = self.guide["source"]["duration_seconds"]
        for p in pts:
            self.assertGreaterEqual(p["seconds"], 0)
            self.assertLessEqual(p["seconds"], duration, f"{p['id']} past end of video")

    def test_capture_point_ids_are_unique(self):
        ids = [p["id"] for p in self.guide["capture_points"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_chapter_exact_points_match_a_real_chapter(self):
        chapter_seconds = {c["seconds"] for c in self.guide["chapters"]}
        for p in self.guide["capture_points"]:
            if p.get("anchor") == "chapter_exact":
                self.assertIn(p["seconds"], chapter_seconds,
                              f"{p['id']} claims to be an exact chapter mark")

    def test_interpolated_points_sit_inside_their_chapter(self):
        chapters = sorted(self.guide["chapters"], key=lambda c: c["seconds"])
        duration = self.guide["source"]["duration_seconds"]
        bounds = {}
        for i, ch in enumerate(chapters):
            end = chapters[i + 1]["seconds"] if i + 1 < len(chapters) else duration
            bounds[ch["title"]] = (ch["seconds"], end)
        for p in self.guide["capture_points"]:
            if p.get("anchor") != "interpolated":
                continue
            lo, hi = bounds[p["chapter"]]
            self.assertTrue(lo <= p["seconds"] <= hi,
                            f"{p['id']} at {p['seconds']}s is outside chapter "
                            f"{p['chapter']} ({lo}-{hi})")

    def test_rotation_steps_match_the_implemented_detectors(self):
        detectors = set()
        rot = self.guide["rotations"]
        for step in rot["electro_flare"]["steps"]:
            if step.get("detector"):
                detectors.add(step["detector"])
        for key in ("pass_1", "pass_2"):
            for step in rot["unison"][key]:
                if step.get("detector"):
                    detectors.add(step["detector"])
        self.assertEqual(detectors, {"mouse_forte", "e_forte"})

    def test_candidate_categories_are_registered_in_coco(self):
        with open(COCO_PATH, encoding="utf-8") as fh:
            coco = json.load(fh)
        names = {c["name"] for c in coco["categories"]}
        for p in self.guide["capture_points"]:
            cat = p.get("candidate_category")
            if cat:
                self.assertIn(cat, names, f"{cat} missing from coco_annotations.json")

    def test_existing_detectors_referenced_by_the_guide_are_annotated(self):
        with open(COCO_PATH, encoding="utf-8") as fh:
            coco = json.load(fh)
        by_name = {c["name"]: c["id"] for c in coco["categories"]}
        annotated = {a["category_id"] for a in coco["annotations"]}
        for name in ("mouse_forte", "e_forte"):
            self.assertIn(name, by_name)
            self.assertIn(by_name[name], annotated,
                          f"{name} is used by Hsin's rotation but has no annotation")


class HsinTeamDataTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from src.combat.TeamAdvisor import TeamAdvisor
        cls.advisor = TeamAdvisor()

    def test_hsin_is_known(self):
        self.assertEqual(self.advisor.normalize_name("Hsin"), "char_hsin")
        info = self.advisor.get_character("char_hsin")
        self.assertEqual(info["best_echo_set"], "Heart of Sworn Vigil (5pc)")
        self.assertIn("Blooming Jadehaven", info["weapon_recommendation"])

    def test_unison_team_is_recommended_for_the_guide_roster(self):
        best = self.advisor.recommend_teams(
            ["char_hsin", "char_jinhsi", "char_shorekeeper"])[0]
        self.assertEqual([s["character"] for s in best["slots"]],
                         ["char_shorekeeper", "char_jinhsi", "char_hsin"])

    def test_electro_flare_team_is_recommended(self):
        best = self.advisor.recommend_teams(
            ["char_hsin", "char_rover", "char_douling"])[0]
        self.assertEqual([s["character"] for s in best["slots"]],
                         ["char_douling", "char_rover", "char_hsin"])

    def test_hsin_teams_link_back_to_the_guide(self):
        teams = [t for t in self.advisor.meta_teams if t["id"].startswith("hsin_")]
        self.assertEqual(len(teams), 2)
        for t in teams:
            self.assertEqual(t["guide_url"], "https://www.youtube.com/watch?v=-JiixPs82UI")


if __name__ == "__main__":
    unittest.main()
