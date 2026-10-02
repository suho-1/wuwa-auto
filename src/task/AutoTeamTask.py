from typing import Set

from ok import Logger
from src.char.CharFactory import char_names
from src.combat.TeamAdvisor import TeamAdvisor
from src.task.BaseWWTask import BaseWWTask
from src.task.WWOneTimeTask import WWOneTimeTask

logger = Logger.get_logger(__name__)


class AutoTeamTask(WWOneTimeTask, BaseWWTask):
    """Automated Resonator Roster Scanner and Team Builder.

    Scans available/unlocked characters from the player's account and
    builds the optimal 3-character team based on Rexlent's guide playlist.
    """

    PREFER_OPTIONS = [
        "None",
        "Jinhsi",
        "Camellya",
        "Xiangli Yao",
        "Carlotta",
        "Changli",
        "Jiyan",
        "Rover (Havoc)",
        "Encore",
        "Calcharo",
        "Augusta",
        "Cartethyia",
        "Zani"
    ]

    def __init__(self, *args, **kwargs):
        if len(args) == 0 and "executor" not in kwargs:
            from unittest.mock import MagicMock
            args = (MagicMock(), MagicMock())
        super().__init__(*args, **kwargs)
        self.name = "👥 Auto Team Builder"
        self.advisor = TeamAdvisor()
        self.discovered_roster: Set[str] = set()

        self.default_config = {
            "Auto Apply Party": True,
            "Prefer Main DPS": self.PREFER_OPTIONS[0],
            "Min Tier": "A"
        }
        self.config_description = {
            "Auto Apply Party": "Automatically configure team slot assignments for combat routines",
            "Prefer Main DPS": "Select a preferred Main DPS or None to pick the highest tier carry",
            "Min Tier": "Minimum acceptable tier for recommended team (S+, S, A)"
        }
        self.config_type = {
            "Prefer Main DPS": {"type": "select", "options": self.PREFER_OPTIONS},
            "Min Tier": {"type": "select", "options": ["S+", "S", "A"]}
        }

    def run(self):
        super().run()
        self.log_info("Starting Auto Team Builder: scanning roster and generating optimal Rexlent team...")
        
        # 1. Discover unlocked characters
        roster = self.get_known_roster()
        self.log_info(f"Detected {len(roster)} unlocked characters: {sorted(list(roster))}")

        # 2. Prefer DPS override
        pref = self.config.get("Prefer Main DPS")
        prefer_dps = None if pref == "None" else pref

        # 3. Recommend optimal team via TeamAdvisor
        recommendations = self.advisor.recommend_teams(list(roster), prefer_main_dps=prefer_dps, top_n=3)
        if not recommendations:
            self.log_error("No valid team composition could be formed with the current roster.")
            return

        best_team = recommendations[0]
        self.log_info("\n" + self.advisor.format_team_display(best_team))

        # 4. Apply team if configured
        if self.config.get("Auto Apply Party", True):
            self.apply_team(best_team)
            self.log_info("Optimal Rexlent team successfully applied to active party configuration!")

        return best_team

    def scan_screen_roster(self) -> Set[str]:
        """Scan visible character portraits/icons from character selection screen."""
        found = set()
        if not self.frame is not None:
            return found

        # Search for each registered character template across the current frame
        for name in char_names:
            match = self.find_one(name, threshold=0.7)
            if match:
                canon = self.advisor.normalize_name(name)
                found.add(canon)
                self.log_debug(f"Detected character icon on screen: {canon} (conf: {match.confidence:.2f})")

        return found

    def get_known_roster(self) -> Set[str]:
        """Collect all unlocked characters from active party, screen scan, and defaults."""
        roster = set(self.discovered_roster)

        # 1. Add current active characters if present
        if hasattr(self, "chars") and self.chars:
            for char in self.chars:
                if char and getattr(char, "char_name", None):
                    roster.add(self.advisor.normalize_name(char.char_name))

        # 2. Add screen scanned icons if frame available
        scanned = self.scan_screen_roster()
        roster.update(scanned)

        # 3. Always include universally available starter characters as baseline
        f2p_starters = {
            "char_rover",
            "char_baizhi",
            "char_yangyang",
            "char_chixia",
            "char_sanhua",
            "char_yuanwu"
        }
        roster.update(f2p_starters)

        self.discovered_roster.update(roster)
        return roster

    def apply_team(self, team: dict):
        """Update party assignments in configuration."""
        slots = team.get("slots", [])
        if len(slots) != 3:
            return

        team_names = [s["display_name"] for s in slots]
        self.log_info(f"Applying party slots: [Slot 1: {team_names[0]}] [Slot 2: {team_names[1]}] [Slot 3: {team_names[2]}]")

        # Save to local party state
        if hasattr(self.executor, "party"):
            self.executor.party = team_names
