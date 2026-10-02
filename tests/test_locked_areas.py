"""Unit tests for Skip Locked Areas detection and error handling."""

import os
import sys
import unittest
from unittest.mock import MagicMock

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from ok import Box
from src.task.BaseWWTask import BaseWWTask, AreaLockedException
from src.task.FarmEchoTask import FarmEchoTask
from src.task.NightmareNestTask import NightmareNestTask, NestTarget
from src.task.TacetTask import TacetTask
from src.task.ForgeryTask import ForgeryTask


class LockedAreaTests(unittest.TestCase):

    def test_log_warn_alias_real_call(self):
        """Verify log_warn exists and delegates to log_warning on BaseWWTask and NightmareNestTask."""
        task = NightmareNestTask.__new__(NightmareNestTask)
        task.log_warning = MagicMock()
        # Calling log_warn must not raise AttributeError and must route to log_warning
        task.log_warn("Test warning message")
        task.log_warning.assert_called_once_with("Test warning message")

    def test_area_locked_exception_raised_on_locked_keyword(self):
        task = BaseWWTask.__new__(BaseWWTask)
        task.config = {'Skip Locked Areas': True}
        task.send_key = MagicMock()

        # Mock OCR returning a locked keyword
        fake_box = MagicMock()
        fake_box.name = '信标未激活'
        task.ocr = MagicMock(return_value=[fake_box])

        self.assertTrue(task.is_area_or_beacon_locked())

    def test_area_locked_exception_not_raised_when_unlocked(self):
        task = BaseWWTask.__new__(BaseWWTask)
        task.config = {'Skip Locked Areas': True}
        task.ocr = MagicMock(return_value=[])

        self.assertFalse(task.is_area_or_beacon_locked())

    def test_wait_click_travel_raises_when_locked(self):
        task = BaseWWTask.__new__(BaseWWTask)
        task.config = {'Skip Locked Areas': True}
        task.click_traval_button = MagicMock(return_value=False)
        task.is_area_or_beacon_locked = MagicMock(return_value=True)
        task.send_key = MagicMock()
        task.sleep = MagicMock()
        task.next_frame = MagicMock()

        with self.assertRaises(AreaLockedException):
            task.wait_click_travel(raise_if_not_found=True, time_out=0.1, check_locked=True)

    def test_sweep_skips_locked_boss_and_continues(self):
        task = FarmEchoTask.__new__(FarmEchoTask)
        task.config = {
            'Sweep Count per Boss': 1,
            'Skip Locked Areas': True,
        }
        task.log_info = MagicMock()
        task.log_warning = MagicMock()
        task.log_warn = task.log_warning
        task.ensure_main = MagicMock()

        visited_bosses = []

        def fake_run_single_boss(boss_name, profile, max_count=1):
            visited_bosses.append(boss_name)
            if boss_name == 'Crownless':
                # First boss is locked
                raise AreaLockedException("Crownless beacon is locked")

        task.run_single_boss = fake_run_single_boss

        # Run sweep on overworld category
        task.run_4c_boss_sweep('sweep_overworld')

        # Crownless was skipped, and subsequent bosses were executed!
        self.assertIn('Crownless', visited_bosses)
        self.assertIn('Thundering Mephis', visited_bosses)
        self.assertIn('Tempest Mephis', visited_bosses)
        warning_calls = [str(call) for call in task.log_warning.call_args_list]
        self.assertTrue(any('Skipping Crownless' in w for w in warning_calls))

    def test_mob_tracking_skips_locked_species(self):
        task = FarmEchoTask.__new__(FarmEchoTask)
        task.config = {
            'Sweep Count per Boss': 1,
            'Skip Locked Areas': True,
        }
        task.log_info = MagicMock()
        task.log_warning = MagicMock()
        task.log_warn = task.log_warning
        task.ensure_main = MagicMock()

        visited_species = []

        def fake_track_and_farm(m_name, m_info, max_kills_per_species=20):
            visited_species.append(m_name)
            if 'Heron' in m_name:
                raise AreaLockedException("Heron waypoint in locked area")
            return 'completed_quota'

        task.track_and_farm_monster = fake_track_and_farm

        # Run track on 3-cost category
        task.run_guidebook_mob_tracking('track_3c')

        # At least Heron was visited, skipped, and other species followed
        self.assertTrue(len(visited_species) > 1)
        warning_calls = [str(call) for call in task.log_warning.call_args_list]
        self.assertTrue(any('Skipping' in w for w in warning_calls))

    def test_nightmare_nest_skips_when_wait_feature_fails(self):
        task = NightmareNestTask.__new__(NightmareNestTask)
        task.config = {'Skip Locked Nests': True}
        task._unreachable_nests = set()
        task._unreachable_targets = []
        task.click = MagicMock()
        task.is_area_or_beacon_locked = MagicMock(return_value=True)
        task.wait_feature = MagicMock(return_value=None)
        task._recover_to_guidebook = MagicMock()
        task.log_warning = MagicMock()
        task.log_warn = task.log_warning
        task.log_info = MagicMock()

        nest = NestTarget(box=MagicMock(), cache_key='go_nest:48:10')
        task.combat_nest(nest)

        self.assertIn('go_nest:48:10', task._unreachable_nests)
        self.assertTrue(task._recover_to_guidebook.called)
        warning_calls = [str(call) for call in task.log_warning.call_args_list]
        self.assertTrue(any('Skipping' in w for w in warning_calls))

    def test_nightmare_nest_skips_when_travel_button_remains_visible(self):
        task = NightmareNestTask.__new__(NightmareNestTask)
        task.config = {'Skip Locked Nests': True}
        task._unreachable_nests = set()
        task._unreachable_targets = []
        task.click = MagicMock()
        task.is_area_or_beacon_locked = MagicMock(return_value=False)
        mock_feature = MagicMock()
        mock_feature.name = 'fast_travel_custom'
        task.wait_feature = MagicMock(return_value=mock_feature)
        task.wait_until = MagicMock(return_value=mock_feature)
        task._find_first_feature = MagicMock(return_value=None)
        task.find_one = MagicMock(return_value=mock_feature)  # Button still visible
        task._recover_to_guidebook = MagicMock()
        task.log_warning = MagicMock()
        task.log_warn = task.log_warning
        task.log_info = MagicMock()

        nest = NestTarget(box=MagicMock(), cache_key='go_nest:48:18')
        task.combat_nest(nest)

        self.assertIn('go_nest:48:18', task._unreachable_nests)
        self.assertTrue(task._recover_to_guidebook.called)
        warning_calls = [str(call) for call in task.log_warning.call_args_list]
        self.assertTrue(any('Skipping' in w or 'failed' in w for w in warning_calls))

    def test_nightmare_nest_find_nest_skips_locked_row(self):
        task = NightmareNestTask.__new__(NightmareNestTask)
        task.config = {'Skip Locked Nests': True}
        task._unreachable_nests = set()
        task._unreachable_targets = []
        import re
        task.count_re = re.compile(r"(\d{1,2})/(\d{1,2})")

        fake_box = MagicMock()
        fake_box.name = '0/48'
        fake_box.x = 100
        fake_box.y = 200
        fake_box.width = 50
        fake_box.height = 20
        task.ocr = MagicMock(return_value=[fake_box])
        task._is_row_locked = MagicMock(return_value=True)

        mock_queue_action = MagicMock()
        mock_queue_action.__name__ = 'go_nest'
        task.queues = [mock_queue_action]
        task.height_of_screen = MagicMock(return_value=720)
        task.width_of_screen = MagicMock(return_value=1280)
        task.log_warning = MagicMock()
        task.log_warn = task.log_warning
        task.log_info = MagicMock()

        result = task.find_nest()
        self.assertIsNone(result)
        self.assertEqual(len(task._unreachable_nests), 1)
        warning_calls = [str(call) for call in task.log_warning.call_args_list]
        self.assertTrue(any('locked in guidebook' in w for w in warning_calls))

    def test_nightmare_nest_skipping_nest_1_proceeds_to_nest_2(self):
        """
        Verify that when Nest 1 is locked and skipped,
        the loop in run_capture_mode continues to check and process Nest 2.
        """
        task = NightmareNestTask.__new__(NightmareNestTask)
        task.config = {'Skip Locked Nests': True}
        task._capture_mode = True
        task._capture_success = False
        task._unreachable_nests = set()
        task._unreachable_targets = []
        import re
        task.count_re = re.compile(r"(\d{1,2})/(\d{1,2})")

        mock_queue_action = MagicMock()
        mock_queue_action.__name__ = 'go_nest'
        task.queues = [mock_queue_action]
        task.height_of_screen = MagicMock(return_value=720)
        task.width_of_screen = MagicMock(return_value=1280)
        task.box_of_screen = MagicMock(return_value=Box(name='box', x=0, y=0, width=10, height=10))
        task.ensure_main = MagicMock()
        task.openF2Book = MagicMock()
        task.find_one = MagicMock(return_value=None)
        task.find_feature = MagicMock(return_value=[])
        task.log_warning = MagicMock()
        task.log_warn = task.log_warning
        task.log_info = MagicMock()

        # Two nests in guidebook: Nest 1 (y=200), Nest 2 (y=300)
        box1 = Box(name='0/48', x=500, y=200, width=50, height=20)
        box2 = Box(name='0/48', x=500, y=300, width=50, height=20)
        task.ocr = MagicMock(return_value=[box1, box2])
        task._is_row_locked = MagicMock(return_value=False)

        combat_calls = []

        def fake_combat_nest(nest):
            combat_calls.append(nest.cache_key)
            if '200' in nest.cache_key or nest.row_y < 0.35:
                # Nest 1 is locked!
                task._mark_nest_unreachable(nest, reason='locked beacon')
                task._recover_to_guidebook()
            else:
                # Nest 2 is unlocked and combat succeeds!
                task._capture_success = True

        task.combat_nest = fake_combat_nest
        task._recover_to_guidebook = MagicMock()

        # Execute loop as in run_capture_mode
        while nest := task.get_nest_to_go():
            task.combat_nest(nest)
            if task._capture_success:
                break

        # Assert BOTH Nest 1 and Nest 2 were evaluated!
        self.assertEqual(len(combat_calls), 2)
        self.assertTrue(task._capture_success)
        # Nest 1 was skipped and marked unreachable
        self.assertEqual(len(task._unreachable_nests), 1)

    def test_is_nest_unreachable_coordinate_tolerance(self):
        """Verify coordinate-distance matching tolerates OCR jitter without false-positive row collisions."""
        task = NightmareNestTask.__new__(NightmareNestTask)
        task._unreachable_nests = set()
        task._unreachable_targets = []

        # Mark row at y=258 (row_y ≈ 0.358) unreachable
        nest1 = NestTarget(box=MagicMock(), cache_key='go_nest:48:18', action='go_nest', denominator=48, row_y=0.358)
        task._mark_nest_unreachable(nest1)

        # 1. Exact cache_key matches
        self.assertTrue(task._is_nest_unreachable('go_nest', 48, 0.358, 'go_nest:48:18'))

        # 2. Slight OCR jitter (row_y 0.358 -> 0.365, distance 0.007 < 0.04) matches even with different slot key
        self.assertTrue(task._is_nest_unreachable('go_nest', 48, 0.365, 'go_nest:48:19'))

        # 3. Next row (row_y 0.458, distance 0.100 >= 0.04) does NOT match!
        self.assertFalse(task._is_nest_unreachable('go_nest', 48, 0.458, 'go_nest:48:23'))

        # 4. Different action does NOT match
        self.assertFalse(task._is_nest_unreachable('go_nightmare', 48, 0.358, 'go_nightmare:48:18'))

    def test_tacet_task_skips_locked_field_and_tries_next(self):
        task = TacetTask.__new__(TacetTask)
        task.config = {
            'Which Tacet Suppression to Farm': 9,
            'Skip Locked Fields': True,
        }
        task.total_number = 9
        task.stamina_once = 60
        task.sleep = MagicMock()
        task.openF2Book = MagicMock()
        task.open_boss_book = MagicMock()
        task.ensure_main = MagicMock()
        task.click_team_challenge = MagicMock()
        task.wait_in_team_and_world = MagicMock()
        task.combat_once = MagicMock()
        task.walk_to_treasure = MagicMock()
        task.pick_f = MagicMock()
        task.has_claim_stamina = MagicMock(return_value=True)
        task.use_stamina = MagicMock(return_value=(False, 60))
        task.click_relative = MagicMock()
        task.info_incr = MagicMock()
        task.log_info = MagicMock()
        task.log_warning = MagicMock()
        task.log_warn = task.log_warning
        task.get_stamina = MagicMock(return_value=(100, 0, 100))

        # First candidate (index 8, 9th field) raises AreaLockedException; second (index 0) succeeds
        task.teleport_to_tacet = MagicMock(side_effect=[
            AreaLockedException("Black Shores is locked"),
            True
        ])

        task.farm_tacet()

        self.assertEqual(task.teleport_to_tacet.call_count, 2)
        warning_calls = [str(call) for call in task.log_warning.call_args_list]
        self.assertTrue(any('locked area' in w for w in warning_calls))

    def test_forgery_task_skips_locked_challenge_and_tries_next(self):
        task = ForgeryTask.__new__(ForgeryTask)
        task.config = {
            'Which Forgery Challenge to Farm': 6,
            'Skip Locked Challenges': True,
        }
        task.ensure_main = MagicMock()
        task.log_info = MagicMock()
        task.log_warning = MagicMock()
        task.log_warn = task.log_warning

        # Mock farm_domain_with_recovery_loop to execute the teleport_once lambda passed to it
        def fake_farm_domain_with_recovery_loop(must_use, teleport_into_domain_once, max_recovery_retries=3):
            teleport_into_domain_once()

        task.farm_domain_with_recovery_loop = fake_farm_domain_with_recovery_loop

        # First serial (6: Black Shores) raises AreaLockedException; second (serial 1) succeeds
        task.teleport_into_domain = MagicMock(side_effect=[
            AreaLockedException("Black Shores is locked"),
            None
        ])

        task.farm_forgery()

        self.assertEqual(task.teleport_into_domain.call_count, 2)
        warning_calls = [str(call) for call in task.log_warning.call_args_list]
        self.assertTrue(any('locked area' in w for w in warning_calls))

    def test_unlocked_text_is_not_treated_as_locked(self):
        """'Unlocked', 'Area Unlocked', ... must never trigger lock detection."""
        task = BaseWWTask.__new__(BaseWWTask)
        task.config = {'Skip Locked Areas': True}
        keywords = task.get_locked_keywords()

        def matches(text):
            for kw in keywords:
                if isinstance(kw, str):
                    if kw in text:
                        return True
                elif kw.search(text):
                    return True
            return False

        for benign in ['Unlocked', 'Area Unlocked', 'New Area Unlocked!',
                       'Resonator Unlocked', 'Available', 'Not available yet',
                       'Rewards unlocked at level 20']:
            self.assertFalse(matches(benign), f'false positive on {benign!r}')

        for locked in ['Locked', 'This beacon is locked', 'Area not unlocked',
                       'Beacon not activated', 'Unexplored region',
                       'Cannot fast travel', '\u4fe1\u6807\u672a\u6fc0\u6d3b']:
            self.assertTrue(matches(locked), f'missed lock text {locked!r}')

    def test_skip_locked_areas_respects_disabled_config(self):
        task = BaseWWTask.__new__(BaseWWTask)
        task.config = {'Skip Locked Areas': False}
        self.assertFalse(task.skip_locked_areas())
        task.config = {}
        self.assertTrue(task.skip_locked_areas())

    def test_nest_counter_filter_only_matches_real_nests(self):
        task = NightmareNestTask.__new__(NightmareNestTask)
        self.assertTrue(task._is_incomplete_nest('0', '24'))
        self.assertTrue(task._is_incomplete_nest('12', '48'))
        self.assertFalse(task._is_incomplete_nest('24', '24'))
        # Unrelated guidebook counters (boss / quest rows) must be ignored
        self.assertFalse(task._is_incomplete_nest('0', '10'))
        self.assertFalse(task._is_incomplete_nest('3', '5'))
        self.assertFalse(task._is_incomplete_nest('x', '24'))

    def test_nest_attempts_are_capped(self):
        task = NightmareNestTask.__new__(NightmareNestTask)
        task._nest_attempts = {}
        task._unreachable_nests = set()
        task._unreachable_targets = []
        task.log_info = MagicMock()
        nest = NestTarget(box=None, cache_key='go_nest:24:10', action='go_nest',
                          denominator=24, row_y=0.2)
        for _ in range(task.MAX_ATTEMPTS_PER_NEST):
            self.assertTrue(task._register_attempt(nest))
        self.assertFalse(task._register_attempt(nest))
        self.assertIn('go_nest:24:10', task._unreachable_nests)


if __name__ == '__main__':
    unittest.main()
