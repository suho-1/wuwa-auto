import re


from ok import Logger, TaskDisabledException
from src.task.BaseWWTask import number_re
from src.task.FarmEchoTask import FarmEchoTask
from src.task.ForgeryTask import ForgeryTask, FORGERY_CHALLENGES
from src.task.GardenTask import GardenTask
from src.task.MergeEchoTask import MergeEchoTask
from src.task.NightmareNestTask import NightmareNestTask
from src.task.TacetTask import TacetTask, TACET_SUPPRESSIONS
from src.task.SimulationTask import SIMULATION_MATERIALS, SimulationTask
from src.task.WWOneTimeTask import WWOneTimeTask
from src.task.waveplates import should_spend_waveplates, verified_single_claim
from src.task.BaseCombatTask import BaseCombatTask
from src.task.BaseWWTask import AreaLockedException

logger = Logger.get_logger(__name__)

CHECK_WEEKLY_GARDEN = 'Check Weekly Garden'
AUTO_FARM_NIGHTMARE_NEST = 'Auto Farm all Nightmare Nest'
MERGE_ECHO_IF_DISCARDED_OVER_1000 = 'Merge Echo If discarded > 1000'
TELEPORT_AND_FARM_4C_ECHO = 'Teleport and Farm 4C Echo'
ADDITIONAL_TASKS = 'Additional Tasks to Run After Daily Task'
EXECUTION_MODE = 'Execution Mode'
READ_ONLY_GATE = 'Read Only (Guidebook Check)'
ONE_SIMULATION_GATE = 'One Simulation (40 Waveplates)'
FULL_DAILY_ROUTINE = 'Full Daily Routine'


class DailyTask(WWOneTimeTask, BaseCombatTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "📅 Daily Task"
        self.support_schedule_task = True
        self.support_tasks = ["Tacet Suppression", "Forgery Challenge", "Simulation Challenge"]
        self.default_config = {
            EXECUTION_MODE: READ_ONLY_GATE,
            'Which to Farm': self.support_tasks[0],
            'Which Tacet Suppression to Farm': TACET_SUPPRESSIONS[0],
            'Which Forgery Challenge to Farm': FORGERY_CHALLENGES[0],
            'Material Selection': 'Shell Credit',
            'Simulation Challenge Runs in Daily': 'Run Once (Daily Quest)',
            'Farm Nightmare Nest for Daily Echo': True,
            'Always Burn Waveplates': False,
            ADDITIONAL_TASKS: [CHECK_WEEKLY_GARDEN],
        }
        self.config_description = {
            EXECUTION_MODE: 'Recovery gate. Start with a read-only Guidebook check, then explicitly test one 40-Waveplate Simulation before enabling the full routine.',
            'Which Tacet Suppression to Farm': 'Select target Tacet Field by Echo Sonata sets and region.',
            'Which Forgery Challenge to Farm': 'Select target Forgery Challenge by weapon and ascension material.',
            'Material Selection': 'Resonator EXP, Weapon EXP, Shell Credits, or Echo EXP (Sealed Tubes).',
            'Simulation Challenge Runs in Daily': 'Run once, double-claim once, or spend enough to finish the 180-Waveplate daily activity.',
            'Farm Nightmare Nest for Daily Echo': 'Farm 1 Echo from Nightmare Nest to complete Daily Task when needed.',
            'Always Burn Waveplates': 'Opt in to spending all currently regenerated Waveplates. Leave disabled until the one-Simulation recovery gate passes. Reserve Waveplate Crystals are never consumed.',
            ADDITIONAL_TASKS: 'Select optional tasks. Nightmare Nest runs before stamina farming to help complete '
                              'the daily task; the other tasks run afterward.',
        }
        self.config_type = {
            EXECUTION_MODE: {
                'type': 'drop_down',
                'options': [READ_ONLY_GATE, ONE_SIMULATION_GATE, FULL_DAILY_ROUTINE],
            },
            'Which to Farm': {
                'type': "drop_down",
                'options': self.support_tasks,
                'sub_configs': {
                    'Tacet Suppression': ['Which Tacet Suppression to Farm'],
                    'Forgery Challenge': ['Which Forgery Challenge to Farm'],
                    'Simulation Challenge': [
                        'Material Selection',
                        'Simulation Challenge Runs in Daily'],
                }
            },
            'Which Tacet Suppression to Farm': {
                'type': 'drop_down',
                'options': TACET_SUPPRESSIONS,
            },
            'Which Forgery Challenge to Farm': {
                'type': 'drop_down',
                'options': FORGERY_CHALLENGES,
            },
            'Material Selection': {
                'type': 'drop_down',
                'options': SIMULATION_MATERIALS,
            },
            'Simulation Challenge Runs in Daily': {
                'type': 'drop_down',
                'options': [
                    'Run Once (Daily Quest)',
                    'Run Once (Double Claim, 80 Waveplates)',
                    'Spend Waveplates (up to 180)',
                    'Burn All Waveplates',
                ],
            },
            ADDITIONAL_TASKS: {
                'type': 'multi_selection',
                'options': [
                    CHECK_WEEKLY_GARDEN,
                    AUTO_FARM_NIGHTMARE_NEST,
                    MERGE_ECHO_IF_DISCARDED_OVER_1000,
                    TELEPORT_AND_FARM_4C_ECHO,
                ],
            },
        }
        self.add_exit_after_config()
        self.description = "Login, claim monthly card, farm echo, and claim daily reward"

    def run(self):
        WWOneTimeTask.run(self)
        self.logged_in = False
        self.ensure_main(time_out=180)

        additional_tasks = self.config.get(ADDITIONAL_TASKS) or []
        condition1 = AUTO_FARM_NIGHTMARE_NEST in additional_tasks
        condition2 = self.config.get('Farm Nightmare Nest for Daily Echo')

        used_stamina, daily_reward_ready = self.open_daily()
        execution_mode = self.config.get(EXECUTION_MODE, READ_ONLY_GATE)
        if execution_mode == READ_ONLY_GATE:
            self._finish_read_only_gate(used_stamina, daily_reward_ready)
            return
        if execution_mode == ONE_SIMULATION_GATE:
            self._run_one_simulation_gate(used_stamina, daily_reward_ready)
            return

        self.validate_additional_tasks()
        burn_all_waveplates = bool(self.config.get('Always Burn Waveplates', False))
        need_stamina = should_spend_waveplates(
            daily_rewards_ready=daily_reward_ready,
            used_waveplates=used_stamina,
            burn_all=burn_all_waveplates,
        )
        need_nightmare = condition1 or (
                condition2
                and not daily_reward_ready
                and self.config.get('Which to Farm', self.support_tasks[0]) != self.support_tasks[0]
        )

        if need_nightmare:
            nightmare_task = self.get_task_by_class(NightmareNestTask)
            orig_ensure_main = nightmare_task.ensure_main
            try:
                # Intercept ensure_main only when already in the guidebook to avoid closing book
                nightmare_task.ensure_main = lambda *args, **kwargs: None if nightmare_task.find_one("gray_book_boss", box='box_gray_book', threshold=0.3) else orig_ensure_main(*args, **kwargs)

                if condition1:
                    self.log_debug('Auto Farm all Nightmare Nest')
                    self.run_task_by_class(NightmareNestTask)
                elif condition2:
                    self.log_debug('Farm Nightmare Nest for Daily Echo')
                    nightmare_task.run_capture_mode()
            except TaskDisabledException:
                raise
            except Exception as e:
                self.log_error("NightmareNestTask Failed", e)
                self.screenshot('NightmareNestTask')
                self.ensure_main(time_out=180)
            finally:
                # Restore ensure_main to avoid instance pollution
                nightmare_task.ensure_main = orig_ensure_main

        if need_stamina:
            target = self.config.get('Which to Farm', self.support_tasks[0])
            try:
                if target == self.support_tasks[0]:
                    self.get_task_by_class(TacetTask).farm_tacet(
                        daily=True, used_stamina=used_stamina,
                        config=self.config, burn_all=burn_all_waveplates)
                elif target == self.support_tasks[1]:
                    self.get_task_by_class(ForgeryTask).farm_forgery(
                        daily=True, used_stamina=used_stamina,
                        config=self.config, burn_all=burn_all_waveplates)
                else:
                    self.get_task_by_class(SimulationTask).farm_simulation(
                        daily=True, used_stamina=used_stamina,
                        config=self.config, burn_all=burn_all_waveplates)
            except AreaLockedException as e:
                self.log_warning(f"Selected daily farming domain is in a locked area ({e}). Falling back to Simulation Challenge...")
                self.ensure_main(time_out=10)
                try:
                    self.get_task_by_class(SimulationTask).farm_simulation(
                        daily=True, used_stamina=used_stamina,
                        config=self.config, burn_all=burn_all_waveplates)
                except Exception as sim_err:
                    self.log_error(f"Fallback simulation also failed: {sim_err}")
            self.sleep(4)

        self.claim_daily()

        self.claim_mail()
        self.sleep(1)
        self.claim_battle_pass()
        self.run_additional_tasks()
        self._verify_full_routine_result()

    def _daily_points(self):
        return self.info_get('total daily points', 0)

    def _daily_points_detected(self):
        return bool(self.info_get('daily points OCR detected', False))

    def _finish_read_only_gate(self, used_stamina, daily_reward_ready):
        """Finish the non-destructive first recovery gate with observable state."""
        points = self._daily_points()
        detected = self._daily_points_detected()
        if detected:
            self.log_info(
                'Daily read-only gate passed: '
                f'activity={points}/100, waveplate_activity={used_stamina}/180, '
                f'rewards_ready={daily_reward_ready}. No reward was claimed and no Waveplates were spent.',
                notify=True,
            )
        else:
            self.log_warning(
                'Daily read-only gate could not verify Activity points: OCR found no total in the '
                'expected Guidebook region. No reward was claimed and no Waveplates were spent.',
                notify=True,
                screenshot=True,
            )
        self.ensure_main(time_out=30)

    def _read_regular_waveplates(self):
        """Read regular/reserve Waveplates without claiming or spending either currency."""
        self.openF2Book('gray_book_boss')
        current, reserve, total = self.get_stamina()
        self.log_info(
            f'Daily recovery Waveplate read: regular={current}, reserve={reserve}, total={total}')
        self.ensure_main(time_out=30)
        return current, reserve, total

    def _run_one_simulation_gate(self, used_stamina, daily_reward_ready):
        """Run exactly one Simulation claim and verify the real Waveplate delta."""
        points_before = self._daily_points()
        points_before_detected = self._daily_points_detected()
        self.ensure_main(time_out=30)

        try:
            regular_before, reserve_before, _ = self._read_regular_waveplates()
            simulation = self.get_task_by_class(SimulationTask)
            simulation.farm_simulation(
                daily=True,
                used_stamina=used_stamina,
                config=self.config,
                once=True,
                max_runs=1,
                burn_all=False,
            )
            self.sleep(2)
            regular_after, reserve_after, _ = self._read_regular_waveplates()
            final_used_stamina, final_reward_ready = self.open_daily()
            points_after = self._daily_points()
            points_after_detected = self._daily_points_detected()
        except AreaLockedException as e:
            self.log_warning(
                f'One-Simulation recovery gate failed because the selected challenge is locked: {e}',
                notify=True,
                screenshot=True,
            )
            self.ensure_main(time_out=30)
            return False
        except Exception as e:
            self.log_error(
                'One-Simulation recovery gate failed before it could be verified',
                e,
                notify=True,
                screenshot=True,
            )
            self.ensure_main(time_out=30)
            return False

        spent = regular_before - regular_after
        verified = verified_single_claim(
            regular_before, regular_after, reserve_before, reserve_after)
        report = (
            'One-Simulation recovery report: '
            f'regular_waveplates={regular_before}->{regular_after} (spent={spent}), '
            f'reserve={reserve_before}->{reserve_after}, '
            f'activity_waveplates={used_stamina}->{final_used_stamina}, '
            f'activity_points={points_before if points_before_detected else "unread"}'
            f'->{points_after if points_after_detected else "unread"}, '
            f'rewards_ready={daily_reward_ready}->{final_reward_ready}.'
        )
        if verified:
            self.log_info(f'{report} Gate passed; exactly one 40-Waveplate claim was verified.', notify=True)
        else:
            self.log_warning(
                f'{report} Gate failed: expected a 40-Waveplate regular-currency decrease and no '
                'reserve-currency change. Full Routine remains unsafe.',
                notify=True,
                screenshot=True,
            )
        self.ensure_main(time_out=30)
        return verified

    def _verify_full_routine_result(self):
        """Never announce Daily completion without rereading Activity points."""
        try:
            final_used_stamina, final_reward_ready = self.open_daily()
            points = self._daily_points()
            detected = self._daily_points_detected()
        except Exception as e:
            self.log_error(
                'Daily routine actions finished, but final Guidebook verification failed',
                e,
                notify=True,
                screenshot=True,
            )
            self.ensure_main(time_out=30)
            return False

        if detected and final_reward_ready:
            self.log_info(
                f'Daily Activity verified complete: activity={points}/100, '
                f'waveplate_activity={final_used_stamina}/180. '
                'Reward-button collection is not yet independently verified.',
                notify=True,
            )
            self.ensure_main(time_out=30)
            return True
        if detected:
            self.log_warning(
                f'Daily routine finished but is incomplete: activity={points}/100, '
                f'waveplate_activity={final_used_stamina}/180. The task will not report completion.',
                notify=True,
                screenshot=True,
            )
        else:
            self.log_warning(
                'Daily routine actions finished, but Activity-point OCR could not verify completion. '
                'The task will not report completion.',
                notify=True,
                screenshot=True,
            )
        self.ensure_main(time_out=30)
        return False

    def validate_additional_tasks(self):
        additional_tasks = self.config.get(ADDITIONAL_TASKS) or []
        if TELEPORT_AND_FARM_4C_ECHO in additional_tasks:
            farm_echo_task = self.get_task_by_class(FarmEchoTask)
            if not farm_echo_task.teleport_to_boss_enabled():
                raise Exception(
                    self.tr(
                        'Teleport and Farm 4C Echo requires "Target Boss" (or "Teleport to Boss") to be enabled in Farm Echo Task.'
                    )
                )
        if AUTO_FARM_NIGHTMARE_NEST in additional_tasks:
            nightmare_task = self.get_task_by_class(NightmareNestTask)
            if not nightmare_task.config.get('Which to Farm'):
                raise Exception(
                    self.tr(
                        'Auto Farm all Nightmare Nest requires at least one "Which to Farm" option.'
                    )
                )
        return True

    def run_additional_tasks(self):
        additional_tasks = self.config.get(ADDITIONAL_TASKS) or []
        if CHECK_WEEKLY_GARDEN in additional_tasks:
            self.check_weekly_garden()
        if MERGE_ECHO_IF_DISCARDED_OVER_1000 in additional_tasks:
            self.check_discarded_echo()
        if TELEPORT_AND_FARM_4C_ECHO in additional_tasks:
            self.log_info('Daily task completed, start teleport to farm 4C echo', notify=True)
            self.run_task_by_class(FarmEchoTask)

    def check_weekly_garden(self):
        self.info_set('current task', 'check weekly garden')
        self.log_info('check weekly garden')
        try:
            garden_task = self.get_task_by_class(GardenTask)
            garden_task.open_garden_weekly_page()
            if garden_task.is_weekly_garden_completed():
                self.log_info('weekly garden already completed')
                return
            self.log_info('weekly garden not completed, run GardenTask')
            self.run_task_by_class(GardenTask)
        except TaskDisabledException:
            raise
        except Exception as e:
            self.log_error("GardenTask Failed", e)
            self.screenshot('GardenTask')
            self.ensure_main(time_out=180)

    def check_discarded_echo(self):
        self.info_set('current task', 'check discarded echo')
        self.log_info('check discarded echo')
        merge_echo_task = self.get_task_by_class(MergeEchoTask)
        old_notify_if_not_enough = merge_echo_task.notify_if_not_enough
        try:
            merge_echo_task.notify_if_not_enough = False
            self.run_task_by_class(MergeEchoTask)
        except TaskDisabledException:
            raise
        except Exception as e:
            self.log_error("MergeEchoTask Failed", e)
            self.screenshot('MergeEchoTask')
            self.ensure_main(time_out=180)
        finally:
            merge_echo_task.notify_if_not_enough = old_notify_if_not_enough

    def claim_battle_pass(self):
        self.log_info('battle pass')
        try:
            self.send_key_down('alt')
            self.sleep(0.05)
            self.click_relative(0.86, 0.05)
        finally:
            self.send_key_up('alt')
        if not self.wait_ocr(0.2, 0.13, 0.32, 0.22, match=re.compile(r'\d+'), settle_time=1, raise_if_not_found=False):
            self.log_error('can not battle pass, maybe ended')
        else:
            self.click_relative(0.04, 0.3, after_sleep=1)
            self.click_relative(0.68, 0.91, hcenter=True, after_sleep=3)
            self.click_relative(0.04, 0.17, after_sleep=2)
            self.click_relative(0.68, 0.91, hcenter=True, after_sleep=2)
            self.wait_ocr(0.2, 0.13, 0.32, 0.22, match=re.compile(r'\d+'),
                          post_action=lambda: self.click(0.68, 0.91, after_sleep=1), settle_time=1,
                          raise_if_not_found=False)
        self.ensure_main()

    def open_daily(self):
        self.log_info('open_daily')
        self.openF2Book("gray_book_quest")
        self.click(0.17, 0.12, after_sleep=1)
        stamina_pattern = re.compile(r'(\d+)\s*/\s*180')
        progress = self.ocr(0.1, 0.1, 0.5, 0.75, match=stamina_pattern)
        if not progress:
            self.click(0.974, 0.6, after_sleep=1)
            progress = self.ocr(0.1, 0.1, 0.5, 0.75, match=stamina_pattern)
        if progress:
            try:
                current = int(re.search(r'\d+', progress[0].name.split('/')[0]).group())
            except Exception:
                current = 0
        else:
            current = 0
        self.info_set('current daily progress', current)
        return current, self.get_total_daily_points() >= 100
        # Note: If the 180 waveplates task is completed, current may also be 0 after scrolling.

    def get_total_daily_points(self):
        # Scan daily_activity_point bounding box [246, 598, 76, 43]
        points_boxes = self.ocr(0.18, 0.82, 0.26, 0.90, match=number_re)
        if points_boxes:
            try:
                points = int(re.sub(r'\D', '', points_boxes[0].name))
            except Exception:
                points = 0
        else:
            points_boxes = self.ocr(0.15, 0.80, 0.30, 0.93, match=number_re)
            if points_boxes:
                try:
                    points = int(re.sub(r'\D', '', points_boxes[0].name))
                except Exception:
                    points = 0
            else:
                points = 0
        self.info_set('daily points OCR detected', bool(points_boxes))
        self.info_set('total daily points', points)
        return points

    def claim_daily(self):
        self.info_set('current task', 'claim daily')
        self.openF2Book('gray_book_quest')
        if not self.find_one('boss_proceed', box=self.box_of_screen(0.803, 0.189, 0.960, 0.312)):
            self.log_info('no_boss_proceed, click claim')
            # Click [Guidebook] in [Terminal] interface
            self.click(0.885, 0.250, after_sleep=2)
        self.log_info('Claiming daily milestone reward chests (20, 40, 60, 80, 100 points)...')
        # Exact annotated milestone chest coordinates (from ChestExplorationTask scene 5)
        milestones = [
            (0.395, 0.886),  # 20 pts: daily_milestone_1 [477, 609, 58, 59]
            (0.529, 0.889),  # 40 pts: daily_milestone_2 [641, 605, 72, 70]
            (0.662, 0.893),  # 60 pts: daily_milestone_3 [809, 612, 76, 62]
            (0.793, 0.890),  # 80 pts: daily_milestone_4 [981, 610, 69, 62]
            (0.925, 0.893),  # 100 pts: daily_milestone_final [1151, 616, 66, 55]
        ]
        for rel_x, rel_y in milestones:
            self.click(rel_x, rel_y, after_sleep=0.6)
        self.sleep(1.0)
        self.ensure_main(time_out=10)

    def claim_mail(self):
        self.info_set('current task', 'claim mail')
        self.ensure_main(time_out=10)
        self.send_key('esc', after_sleep=1.5)
        self.click(0.64, 0.95, after_sleep=1)
        self.click(0.14, 0.9, after_sleep=1)
        self.ensure_main(time_out=10)


from ok import run_task
from config import config

if __name__ == "__main__":
    run_task(config, task=DailyTask, debug=True)
