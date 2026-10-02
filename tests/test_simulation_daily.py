import os
import sys
import unittest
from unittest.mock import MagicMock, patch

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from src.task.BaseWWTask import BaseWWTask
from src.task.DomainTask import DomainTask
from src.task.SimulationTask import SimulationTask
from src.task.DailyTask import DailyTask


class TestUseStaminaQuota(unittest.TestCase):
    """Tests for BaseWWTask.use_stamina quota completion and looping prevention."""

    def setUp(self):
        self.task = BaseWWTask.__new__(BaseWWTask)
        self.task.sleep = MagicMock()
        self.task.click_dialog_left_button = MagicMock(return_value='left_btn')
        self.task.click_dialog_right_button = MagicMock(return_value='right_btn')
        self.task.wait_feature = MagicMock(return_value=False)
        self.task.click_relative = MagicMock()
        self.task.back = MagicMock()
        self.task.click = MagicMock()

    def test_run_once_quota_stops_immediately_when_stamina_abundant(self):
        """When player has 240 stamina and must_use=40 (run once),

        it should use single stamina (40) and return can_continue=False.
        Prior bug: returned can_continue=True because current (200) >= once (40),
        causing endless loops until all 240 stamina was burned.
        """
        self.task.get_stamina = MagicMock(return_value=(240, 0, 240))

        can_continue, used = self.task.use_stamina(once=40, must_use=40)

        self.assertEqual(used, 40)
        self.assertFalse(can_continue, "can_continue must be False after 40 stamina quota is met")
        self.task.click_dialog_left_button.assert_called_once()
        self.task.click_dialog_right_button.assert_not_called()

    def test_double_claim_quota_stops_immediately(self):
        """When must_use=80 (double claim run once),

        it should use double stamina (80) and return can_continue=False.
        """
        self.task.get_stamina = MagicMock(return_value=(240, 0, 240))

        can_continue, used = self.task.use_stamina(once=40, must_use=80)

        self.assertEqual(used, 80)
        self.assertFalse(can_continue, "can_continue must be False after 80 stamina quota is met")
        self.task.click_dialog_right_button.assert_called_once()

    def test_daily_180_quota_stops_when_quota_exhausted(self):
        """When must_use=180, it should continue while quota remains,

        then stop once quota is met even if stamina remains.
        """
        # Run 1: 240 stamina, must_use=180 -> uses 80, 100 remaining
        self.task.get_stamina = MagicMock(return_value=(240, 0, 240))
        can_continue1, used1 = self.task.use_stamina(once=40, must_use=180)
        self.assertEqual(used1, 80)
        self.assertTrue(can_continue1)

        # Run 2: 160 stamina, must_use=100 -> uses 80, 20 remaining
        self.task.get_stamina = MagicMock(return_value=(160, 0, 160))
        can_continue2, used2 = self.task.use_stamina(once=40, must_use=100)
        self.assertEqual(used2, 80)
        self.assertTrue(can_continue2)

        # Run 3: 80 stamina, must_use=20 -> uses 40 (since 20 < 80), -20 remaining <= 0
        self.task.get_stamina = MagicMock(return_value=(80, 0, 80))
        can_continue3, used3 = self.task.use_stamina(once=40, must_use=20)
        self.assertEqual(used3, 40)
        self.assertFalse(can_continue3, "can_continue must be False once 180 quota is completed")

    def test_burn_all_stops_when_current_stamina_depleted(self):
        """When must_use=0 (burn all), continue until current stamina < once."""
        self.task.get_stamina = MagicMock(return_value=(80, 0, 80))
        can_continue1, used1 = self.task.use_stamina(once=40, must_use=0)
        self.assertEqual(used1, 80)
        self.assertFalse(can_continue1, "current remaining is 0 < 40, must stop without backup")

    def test_low_stamina_stops(self):
        """When total stamina < once, can_continue is False."""
        self.task.get_stamina = MagicMock(return_value=(20, 0, 20))
        can_continue, used = self.task.use_stamina(once=40, must_use=40)
        self.assertFalse(can_continue)


class TestDomainTaskMaxRuns(unittest.TestCase):
    """Tests for DomainTask max_runs enforcement and domain loop behavior."""

    def test_farm_in_domain_stops_after_max_runs_even_if_can_continue_was_true(self):
        task = DomainTask.__new__(DomainTask)
        task.stamina_once = 40
        task.walk_until_f = MagicMock()
        task.pick_f = MagicMock()
        task.combat_once = MagicMock()
        task.sleep = MagicMock()
        task.walk_to_treasure = MagicMock()
        task.info_incr = MagicMock()
        task.log_info = MagicMock()
        task.click = MagicMock()
        task.wait_feature = MagicMock(return_value=False)
        task.wait_in_team_and_world = MagicMock()
        task.teleport_timeout = 30
        task.make_sure_in_world = MagicMock()

        # Simulate use_stamina returning can_continue=True (e.g. infinite stamina)
        task.use_stamina = MagicMock(return_value=(True, 40))

        finished, remaining_must_use = task.farm_in_domain(must_use=0, max_runs=1)

        self.assertTrue(finished)
        self.assertEqual(task.use_stamina.call_count, 1, "Should only run use_stamina once when max_runs=1")
        # Should click back to world (0.42, 0.84), NOT click farm again (0.68, 0.84)
        farm_again_calls = [c for c in task.click.call_args_list if c.args and abs(c.args[0] - 0.68) < 0.05]
        self.assertEqual(len(farm_again_calls), 0, "Should not click 'farm again' when max_runs=1")


class TestSimulationTaskDaily(unittest.TestCase):
    """Tests for SimulationTask configuration and farm_simulation modes."""

    def test_daily_defaults_to_run_once_40_stamina(self):
        task = SimulationTask.__new__(SimulationTask)
        task.stamina_once = 40
        task.config = {
            'Material Selection': 'Shell Credit',
        }
        task.farm_domain_with_recovery_loop = MagicMock()
        task.teleport_into_domain = MagicMock()

        # Calling farm_simulation with daily=True
        task.farm_simulation(daily=True)

        task.farm_domain_with_recovery_loop.assert_called_once()
        must_use_arg = task.farm_domain_with_recovery_loop.call_args.args[0]
        max_runs_kwarg = task.farm_domain_with_recovery_loop.call_args.kwargs.get('max_runs')
        self.assertEqual(must_use_arg, 40, "Default daily must_use should be 40 (stamina_once)")
        self.assertEqual(max_runs_kwarg, 1, "Default daily max_runs should be 1")

    def test_daily_spend_180_waveplates(self):
        task = SimulationTask.__new__(SimulationTask)
        task.stamina_once = 40
        task.config = {
            'Material Selection': 'Shell Credit',
            'Simulation Challenge Runs in Daily': 'Spend Waveplates (up to 180)',
        }
        task.farm_domain_with_recovery_loop = MagicMock()

        task.farm_simulation(daily=True, used_stamina=40)

        task.farm_domain_with_recovery_loop.assert_called_once()
        must_use_arg = task.farm_domain_with_recovery_loop.call_args.args[0]
        max_runs_kwarg = task.farm_domain_with_recovery_loop.call_args.kwargs.get('max_runs')
        self.assertEqual(must_use_arg, 140, "Should spend 180 - 40 = 140 waveplates")
        self.assertEqual(max_runs_kwarg, 0, "max_runs should be 0 (unlimited up to must_use quota)")

    def test_daily_double_claim_run_once(self):
        task = SimulationTask.__new__(SimulationTask)
        task.stamina_once = 40
        task.config = {
            'Material Selection': 'Shell Credit',
            'Simulation Challenge Runs in Daily': 'Run Once (Double Claim, 80 Waveplates)',
        }
        task.farm_domain_with_recovery_loop = MagicMock()

        task.farm_simulation(daily=True)

        task.farm_domain_with_recovery_loop.assert_called_once()
        must_use_arg = task.farm_domain_with_recovery_loop.call_args.args[0]
        max_runs_kwarg = task.farm_domain_with_recovery_loop.call_args.kwargs.get('max_runs')
        self.assertEqual(must_use_arg, 80, "Double claim must_use should be 80")
        self.assertEqual(max_runs_kwarg, 1, "Double claim run once max_runs should be 1")

    def test_standalone_burn_all_waveplates(self):
        task = SimulationTask.__new__(SimulationTask)
        task.stamina_once = 40
        task.config = {
            'Material Selection': 'Shell Credit',
            'Farm Mode': 'Burn All Waveplates',
        }
        task.farm_domain_with_recovery_loop = MagicMock()

        task.farm_simulation(daily=False)

        task.farm_domain_with_recovery_loop.assert_called_once()
        must_use_arg = task.farm_domain_with_recovery_loop.call_args.args[0]
        max_runs_kwarg = task.farm_domain_with_recovery_loop.call_args.kwargs.get('max_runs')
        self.assertEqual(must_use_arg, 0)
        self.assertEqual(max_runs_kwarg, 0)


class TestDailyTaskConfig(unittest.TestCase):
    """Tests for DailyTask config options."""

    def test_daily_task_defaults(self):
        mock_executor = MagicMock()
        mock_app = MagicMock()
        mock_app.config = {}
        task = DailyTask(mock_executor, mock_app)
        self.assertEqual(task.default_config.get('Simulation Challenge Runs in Daily'), 'Run Once (Daily Quest)')
        sub_configs = task.config_type['Which to Farm']['sub_configs']['Simulation Challenge']
        self.assertIn('Simulation Challenge Runs in Daily', sub_configs)
        self.assertIn('Run Once (Daily Quest)', task.config_type['Simulation Challenge Runs in Daily']['options'])


if __name__ == '__main__':
    unittest.main()
