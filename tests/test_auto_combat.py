"""Regression tests for auto-combat control flow without a live game client."""

import importlib
import time
import unittest
from unittest.mock import patch

import numpy as np

from src.char.BaseChar import BaseChar
from src.combat.CombatCheck import CombatCheck
from src.task.AutoCombatTask import AutoCombatTask
from src.task.BaseCombatTask import BaseCombatTask

base_char_module = importlib.import_module('src.char.BaseChar')


class _Scene:
    def in_team(self, check):
        return check()


class AutoCombatTaskRunTests(unittest.TestCase):
    def test_illusive_realm_uses_the_realm_rotation(self):
        """Realm combat has no regular enemy HUD, so it must bypass in_combat."""
        task = type("RealmTask", (), {})()
        task.scene = _Scene()
        task.warmed = 0
        task.realm_actions = 0
        task.warm_up_char_features = lambda: setattr(task, "warmed", task.warmed + 1)
        task.in_team_and_world = lambda: True
        task.in_illusive_realm = lambda: True
        task.realm_perform = lambda: setattr(task, "realm_actions", task.realm_actions + 1)
        task.in_combat = lambda: self.fail("normal combat detection must not run in the Realm")

        self.assertTrue(AutoCombatTask.run(task))
        self.assertEqual(task.warmed, 1)
        self.assertEqual(task.realm_actions, 1)

    def test_missing_current_character_stops_cleanly(self):
        """A party-HUD transition must not become an AttributeError in a trigger."""
        task = type("NormalTask", (), {})()
        task.scene = _Scene()
        task.config = {"Use Liberation": True}
        task.reset_reasons = []
        task.healer_switches = 0
        task.combat_end_calls = 0
        task.warm_up_char_features = lambda: None
        task.in_team_and_world = lambda: True
        task.in_illusive_realm = lambda: False
        task.in_world = lambda: True
        task.in_combat = iter((True, False)).__next__
        task.switch_healer = lambda: setattr(task, "healer_switches", task.healer_switches + 1)
        task.get_current_char = lambda raise_exception=False: None
        task.reset_to_false = lambda reason: task.reset_reasons.append(reason) or False
        task.combat_end = lambda: setattr(task, "combat_end_calls", task.combat_end_calls + 1)

        self.assertTrue(AutoCombatTask.run(task))
        self.assertEqual(task.reset_reasons, ["current character is unavailable"])
        self.assertEqual(task.combat_end_calls, 1)
        self.assertEqual(task.healer_switches, 2)  # before and after combat


class CombatCheckRecoveryTests(unittest.TestCase):
    def test_check_error_resets_stale_combat_state(self):
        task = type("BrokenCombatCheck", (), {})()
        task.in_sleep_check = False
        task.reset_reasons = []

        def fail(_target):
            raise RuntimeError("capture failed")

        task.do_check_in_combat = fail
        task.reset_to_false = lambda reason: task.reset_reasons.append(reason) or False

        self.assertFalse(CombatCheck.in_combat(task))
        self.assertEqual(task.reset_reasons, ["combat check failed: RuntimeError"])
        self.assertFalse(task.in_sleep_check)


class CombatCheckStreakTests(unittest.TestCase):
    def test_transient_capture_failures_are_reset_after_a_clean_frame(self):
        task = type("FlakyCombatCheck", (), {})()
        task.in_sleep_check = False
        task.reset_reasons = []
        outcomes = iter([RuntimeError('capture'), RuntimeError('capture'), RuntimeError('capture'), True])

        def check(_target):
            outcome = next(outcomes)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        task.do_check_in_combat = check
        task.reset_to_false = lambda reason: task.reset_reasons.append(reason) or False

        self.assertFalse(CombatCheck.in_combat(task))
        self.assertFalse(CombatCheck.in_combat(task))
        self.assertFalse(CombatCheck.in_combat(task))
        self.assertEqual(task.combat_check_failures, 3)
        self.assertTrue(CombatCheck.in_combat(task))
        self.assertEqual(task.combat_check_failures, 0)
        self.assertEqual(task.combat_check_failure_notice_at, 0)


class BossTextMaskTests(unittest.TestCase):
    def test_sparse_white_pixels_fall_back_to_the_visible_orange_boss_text(self):
        """Coverage must be area / (height * width), not area / height * width."""
        frame = np.zeros((10, 10, 3), dtype=np.uint8)
        frame[0, 0] = (255, 255, 255)  # 1% white, below the 5% cutoff
        frame[1:2, :10] = (68, 178, 218)  # 10% orange in BGR order

        task = type("BossTextTask", (), {})()
        task.frame = frame
        task.boss_lv_box = type("Box", (), {"crop_frame": lambda _self, _frame: _frame})()

        _cropped, mask = CombatCheck.keep_boss_text_white(task)

        self.assertEqual(np.count_nonzero(mask), 10)


class ResonanceTimeoutTests(unittest.TestCase):
    def test_default_resonance_timeout_reports_a_possible_keybind_failure(self):
        task = type("ResonanceTask", (), {"in_liberation": False})()
        char = type("TimedOutCharacter", (), {})()
        char.task = task
        char.alerted = 0
        char.alert_skill_failed = lambda: setattr(char, "alerted", char.alerted + 1)
        char.logger = type("Logger", (), {"debug": lambda _self, _message: None})()

        with patch.object(base_char_module.time, "time", side_effect=(0, 16, 16)):
            clicked, duration, animated = BaseChar.click_resonance(char)

        self.assertFalse(clicked)
        self.assertEqual(duration, 0)
        self.assertFalse(animated)
        self.assertEqual(char.alerted, 1)


class _Character:
    def __init__(self, index):
        self.index = index
        self.char_type = "MainDps"
        self.has_intro = False
        self.has_sub_dps_intro = False
        self.is_current_char = index == 0
        self.last_switch_time = time.time()
        self.last_switch_in_time = -1
        self.intro_motion_freeze_duration = 0.9
        self.switched_out = False

    def __repr__(self):
        return f"Character({self.index})"

    def get_current_con(self):
        return 0

    def is_con_full(self):
        return False

    def wait_switch(self):
        return False

    def f_break(self, **_kwargs):
        return False

    def switch_out(self, con_full=False):
        self.switched_out = True
        self.is_current_char = False
        self.last_switch_time = time.time()

    def continues_normal_attack(self, _duration):
        raise AssertionError("a valid switch target should have been selected")


class _SwitchTask:
    def __init__(self):
        self.current = _Character(0)
        self.target = _Character(1)
        self.debug = False
        self.switch_char_time_out = 1
        self.in_liberation = True
        self.next_frame_calls = 0
        self.sent_keys = []
        # The first pass represents the party HUD disappearing for a switch
        # animation; it is visible again on the next frame at the target slot.
        self._team_states = iter(((False, -1, 3), (False, -1, 3),
                                  (False, -1, 3), (True, 1, 3)))

    def update_lib_portrait_icon(self):
        pass

    def _choose_switch_target(self, _current, _has_intro, target_low_con=False):
        return self.target

    def _apply_intro_flags(self, _current, target, has_intro):
        target.has_intro = has_intro
        target.has_sub_dps_intro = False

    def check_combat(self):
        pass

    def in_team(self):
        return next(self._team_states)

    def send_key(self, key):
        self.sent_keys.append(key)

    def click(self):
        pass

    def sleep(self, _duration):
        pass

    def next_frame(self):
        self.next_frame_calls += 1

    def log_debug(self, _message):
        pass

    def raise_not_in_combat(self, message):
        raise AssertionError(f"unexpected combat abort: {message}")


class CharacterSwitchTests(unittest.TestCase):
    def test_transient_missing_party_hud_does_not_abort_switch(self):
        task = _SwitchTask()

        BaseCombatTask.switch_next_char(task, task.current)

        self.assertEqual(task.next_frame_calls, 1)
        self.assertIn(2, task.sent_keys)
        self.assertTrue(task.current.switched_out)
        self.assertTrue(task.target.is_current_char)
        self.assertFalse(task.in_liberation)


if __name__ == "__main__":
    unittest.main(verbosity=2)
