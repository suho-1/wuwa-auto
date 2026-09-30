import glob
import re
import unittest

from src.combat.TeamAdvisor import TeamAdvisor
from src.task.AutoTeamTask import AutoTeamTask


class RexlentTeamAdvisorTests(unittest.TestCase):
    """Unit tests for Rexlent Team Advisor and character synergy engine."""

    def setUp(self):
        self.advisor = TeamAdvisor()

    def test_database_loads_successfully(self):
        self.assertGreater(len(self.advisor.characters), 20)
        self.assertGreater(len(self.advisor.meta_teams), 5)

    def test_character_aliases_normalized(self):
        self.assertEqual(self.advisor.normalize_name("Jinhsi"), "char_jinhsi")
        self.assertEqual(self.advisor.normalize_name("jinshi"), "char_jinhsi")
        self.assertEqual(self.advisor.normalize_name("Labels.char_jinhsi"), "char_jinhsi")
        self.assertEqual(self.advisor.normalize_name("Camellya"), "char_camellya")
        self.assertEqual(self.advisor.normalize_name("shorekeeper"), "char_shorekeeper")
        self.assertEqual(self.advisor.normalize_name("Changli"), "chang_changli")
        self.assertEqual(self.advisor.normalize_name("Xiangli Yao"), "char_xiangliyao")

    def test_jinhsi_standard_team_selected(self):
        roster = ["char_jinhsi", "char_yuanwu", "char_verina", "char_rover"]
        recommendations = self.advisor.recommend_teams(roster)
        self.assertGreater(len(recommendations), 0)
        best = recommendations[0]
        self.assertIn("Jinhsi", best["name"])
        self.assertEqual(best["tier"], "S+")

        # Slot 1 must be Healer, Slot 2 SubDPS, Slot 3 MainDPS
        slots = best["slots"]
        self.assertEqual(slots[0]["role"], "Healer")
        self.assertEqual(slots[0]["character"], "char_verina")
        self.assertEqual(slots[1]["role"], "SubDPS")
        self.assertEqual(slots[1]["character"], "char_yuanwu")
        self.assertEqual(slots[2]["role"], "MainDPS")
        self.assertEqual(slots[2]["character"], "char_jinhsi")

    def test_camellya_hypercarry_team(self):
        roster = ["char_camellya", "char_sanhua", "char_shorekeeper", "char_baizhi"]
        recommendations = self.advisor.recommend_teams(roster)
        self.assertGreater(len(recommendations), 0)
        best = recommendations[0]
        self.assertIn("Camellya", best["name"])
        slots = best["slots"]
        self.assertEqual(slots[0]["character"], "char_shorekeeper")
        self.assertEqual(slots[1]["character"], "char_sanhua")
        self.assertEqual(slots[2]["character"], "char_camellya")

    def test_xiangli_yao_team(self):
        roster = ["char_xiangliyao", "char_yinlin", "char_verina"]
        recommendations = self.advisor.recommend_teams(roster)
        self.assertGreater(len(recommendations), 0)
        best = recommendations[0]
        self.assertIn("Xiangli Yao", best["name"])
        slots = best["slots"]
        self.assertEqual(slots[0]["character"], "char_verina")
        self.assertEqual(slots[1]["character"], "char_yinlin")
        self.assertEqual(slots[2]["character"], "char_xiangliyao")

    def test_carlotta_team(self):
        roster = ["char_carlotta", "char_zhezhi", "char_shorekeeper"]
        recommendations = self.advisor.recommend_teams(roster)
        self.assertGreater(len(recommendations), 0)
        best = recommendations[0]
        self.assertIn("Carlotta", best["name"])
        slots = best["slots"]
        self.assertEqual(slots[0]["character"], "char_shorekeeper")
        self.assertEqual(slots[1]["character"], "char_zhezhi")
        self.assertEqual(slots[2]["character"], "char_carlotta")

    def test_healer_fallback_resolution(self):
        # Roster with Baizhi instead of Verina/Shorekeeper
        roster = ["char_jinhsi", "char_yuanwu", "char_baizhi"]
        recommendations = self.advisor.recommend_teams(roster)
        self.assertGreater(len(recommendations), 0)
        best = recommendations[0]
        slots = best["slots"]
        self.assertEqual(slots[0]["character"], "char_baizhi")
        self.assertEqual(slots[1]["character"], "char_yuanwu")
        self.assertEqual(slots[2]["character"], "char_jinhsi")

    def test_f2p_starter_team_selection(self):
        roster = ["char_rover", "char_sanhua", "char_baizhi", "char_yangyang", "char_chixia"]
        recommendations = self.advisor.recommend_teams(roster)
        self.assertGreater(len(recommendations), 0)
        best = recommendations[0]
        self.assertEqual(best["slots"][0]["role"], "Healer")
        self.assertEqual(best["slots"][1]["role"], "SubDPS")
        self.assertEqual(best["slots"][2]["role"], "MainDPS")

    def test_prefer_main_dps_override(self):
        roster = ["char_jinhsi", "char_camellya", "char_sanhua", "char_yuanwu", "char_verina", "char_shorekeeper"]
        # Force Camellya even if Jinhsi is also available
        recommendations = self.advisor.recommend_teams(roster, prefer_main_dps="Camellya")
        self.assertGreater(len(recommendations), 0)
        best = recommendations[0]
        self.assertEqual(best["slots"][2]["character"], "char_camellya")

    def test_dynamic_team_synthesis(self):
        # Roster with no exact meta template match
        roster = ["char_chixia", "char_danjin", "char_jianxin"]
        recommendations = self.advisor.recommend_teams(roster)
        self.assertGreater(len(recommendations), 0)
        best = recommendations[0]
        self.assertEqual(len(best["slots"]), 3)

    def test_formatted_display_output(self):
        roster = ["char_jinhsi", "char_yuanwu", "char_verina"]
        team = self.advisor.recommend_teams(roster)[0]
        output = self.advisor.format_team_display(team)
        self.assertIn("Jinhsi", output)
        self.assertIn("Yuanwu", output)
        self.assertIn("Verina", output)
        self.assertIn("Slot 1", output)
        self.assertIn("Slot 2", output)
        self.assertIn("Slot 3", output)


class AutoTeamTaskTests(unittest.TestCase):
    """Unit tests for AutoTeamTask automation task."""

    def test_task_initialization(self):
        task = AutoTeamTask()
        self.assertEqual(task.name, "👥 Auto Team Builder")
        self.assertIn("Auto Apply Party", task.default_config)
        self.assertIn("Prefer Main DPS", task.default_config)
        self.assertIn("Jinhsi", task.PREFER_OPTIONS)
        self.assertIn("Camellya", task.PREFER_OPTIONS)

    def test_known_roster_includes_starters(self):
        task = AutoTeamTask()
        roster = task.get_known_roster()
        self.assertIn("char_rover", roster)
        self.assertIn("char_baizhi", roster)
        self.assertIn("char_yangyang", roster)
        self.assertIn("char_sanhua", roster)
        self.assertIn("char_yuanwu", roster)

    def test_task_run_produces_valid_team(self):
        task = AutoTeamTask()
        task.config = {"Auto Apply Party": False, "Prefer Main DPS": "None", "Min Tier": "A"}
        # Provide a known roster with Jinhsi and Yuanwu
        task.discovered_roster = {"char_jinhsi", "char_yuanwu", "char_verina"}
        team = task.run()
        self.assertIsNotNone(team)
        self.assertEqual(len(team["slots"]), 3)
        self.assertEqual(team["slots"][2]["character"], "char_jinhsi")


class CharacterNoChineseCommentTests(unittest.TestCase):
    """Verify that all files in src/char/*.py are strictly free of Chinese characters."""

    def test_zero_chinese_in_src_char(self):
        cjk_re = re.compile(r'[\u4e00-\u9fff]')
        violations = []
        for path in glob.glob("src/char/*.py"):
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for line_num, line in enumerate(f, 1):
                    if cjk_re.search(line):
                        violations.append(f"{path}:{line_num}: {line.strip()}")
        self.assertEqual(
            violations,
            [],
            f"Found {len(violations)} Chinese character violations in src/char/*.py"
        )


if __name__ == "__main__":
    unittest.main()
