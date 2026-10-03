"""Pure policy tests for daily Waveplate spending."""

import unittest

from src.task.waveplates import (
    DAILY_ACTIVITY_WAVEPLATE_TARGET,
    REGULAR_WAVEPLATE_CAP,
    can_start_waveplate_run,
    daily_waveplate_quota,
    should_spend_waveplates,
    verified_single_claim,
)


class DailyWaveplatePolicyTests(unittest.TestCase):
    def test_game_limits_are_kept_distinct(self):
        self.assertEqual(DAILY_ACTIVITY_WAVEPLATE_TARGET, 180)
        self.assertEqual(REGULAR_WAVEPLATE_CAP, 240)

    def test_daily_quota_only_spends_remaining_activity_progress(self):
        self.assertEqual(daily_waveplate_quota(0), 180)
        self.assertEqual(daily_waveplate_quota(40), 140)
        self.assertEqual(daily_waveplate_quota(180), 0)
        self.assertEqual(daily_waveplate_quota(240), 0)

    def test_burn_all_uses_domain_engine_sentinel(self):
        self.assertEqual(daily_waveplate_quota(180, burn_all=True), 0)
        self.assertEqual(daily_waveplate_quota(240, burn_all=True), 0)

    def test_completed_dailies_skip_spending_when_burn_all_is_disabled(self):
        self.assertFalse(should_spend_waveplates(
            daily_rewards_ready=True,
            used_waveplates=20,
            burn_all=False,
        ))

    def test_burn_all_runs_even_after_daily_rewards_are_ready(self):
        self.assertTrue(should_spend_waveplates(
            daily_rewards_ready=True,
            used_waveplates=180,
            burn_all=True,
        ))

    def test_incomplete_daily_runs_only_while_quota_remains(self):
        self.assertTrue(should_spend_waveplates(
            daily_rewards_ready=False,
            used_waveplates=120,
            burn_all=False,
        ))
        self.assertFalse(should_spend_waveplates(
            daily_rewards_ready=False,
            used_waveplates=180,
            burn_all=False,
        ))

    def test_burn_all_does_not_start_a_claim_from_reserve_crystals(self):
        self.assertFalse(can_start_waveplate_run(
            current=20, total=500, cost=40, quota=0))
        self.assertTrue(can_start_waveplate_run(
            current=40, total=520, cost=40, quota=0))

    def test_explicit_daily_quota_may_use_reserve_crystals(self):
        self.assertTrue(can_start_waveplate_run(
            current=20, total=500, cost=40, quota=40))
        self.assertFalse(can_start_waveplate_run(
            current=20, total=20, cost=40, quota=40))

    def test_single_claim_verification_allows_one_regenerated_point(self):
        self.assertTrue(verified_single_claim(244, 204, 0, 0))
        self.assertTrue(verified_single_claim(244, 205, 0, 0))
        self.assertTrue(verified_single_claim(244, 203, 0, 0))

    def test_single_claim_verification_rejects_no_spend_or_reserve_use(self):
        self.assertFalse(verified_single_claim(244, 244, 0, 0))
        self.assertFalse(verified_single_claim(244, 204, 0, 40))
        self.assertFalse(verified_single_claim('unread', 204, 0, 0))


if __name__ == '__main__':
    unittest.main()
