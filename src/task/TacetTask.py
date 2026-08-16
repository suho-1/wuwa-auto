
from ok import Logger
from src.task.BaseCombatTask import BaseCombatTask, CharRevivedException, CharDeadException, NotInCombatException
from src.task.WWOneTimeTask import WWOneTimeTask
from src.task.BaseWWTask import AreaLockedException

logger = Logger.get_logger(__name__)


TACET_SUPPRESSIONS = [
    '1 - Desorock Highland (Celestial Light & Havoc Eclipse)',
    '2 - Central Plains (Sierra Gale & Molten Rift)',
    '3 - Port City Guixu (Molten Rift & Sun-sinking Eclipse)',
    '4 - Dim Forest (Void Thunder & Moonlit Clouds)',
    '5 - Waving Hills (Freezing Frost & Sierra Gale)',
    "6 - Whining Aix's Mire (Sun-sinking Eclipse & Celestial Light)",
    '7 - Norfall Barrens (Void Thunder & Freezing Frost)',
    '8 - Mt. Firmament (Midnight Frost & Celestial Light)',
    '9 - Black Shores (Endless Resonance & Deep Ocean)',
]


class TacetTask(WWOneTimeTask, BaseCombatTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.description = "Farms the selected Tacet Suppression, until no stamina. Must be able to teleport (F2)."
        self.name = "🌊 Tacet Suppression"
        self.support_schedule_task = True
        default_config = {
            'Which Tacet Suppression to Farm': TACET_SUPPRESSIONS[0],
            'Skip Locked Fields': True,
        }
        self.structure = [2, 5, 5, 7]
        self.total_number = sum(self.structure)
        self.target_enemy_time_out = 10
        default_config.update(self.default_config)
        self.config_description = {
            'Which Tacet Suppression to Farm': 'Select the Tacet Field to farm based on target Echo Sonata sets and region.',
            'Skip Locked Fields': 'Automatically try other Tacet Fields if the selected field is in a locked area.',
        }
        self.config_type['Which Tacet Suppression to Farm'] = {
            'type': 'drop_down',
            'options': TACET_SUPPRESSIONS,
        }
        self.config_type['Skip Locked Fields'] = {
            'type': 'check_box',
        }
        self.default_config = default_config
        self.door_walk_method = {  # starts with 0
            0: [],
            1: [],
            2: [],
            3: [],
            4: [],
            5: [],
            6: [],
            7: [["a", 0.3]],
            8: [["d", 0.6]],
            9: [["a", 1.5], ["w", 3], ["a", 2.5]],
        }
        self.stamina_once = 60

    def run(self):
        super().run()
        self.ensure_main(time_out=180)
        self.wait_in_team_and_world(esc=True)
        try:
            self.farm_tacet()
        except AreaLockedException as e:
            self.log_warning(f"Selected Tacet Suppression field is in a locked area: {e}. Please unlock the area or select another field.")
            self.ensure_main(time_out=10)
            return

    def farm_tacet(self, daily=False, used_stamina=0, config=None):
        if config is None:
            config = self.config
        if daily:
            must_use = 180 - used_stamina
        else:
            must_use = 0
        self.info_incr('used stamina', 0)
        while True:
            self.sleep(1)
            self.openF2Book("gray_book_boss")
            current, back_up, total = self.get_stamina()
            if current == -1:
                self.click_relative(0.04, 0.4, after_sleep=1)
                current, back_up, total = self.get_stamina()
            if total < self.stamina_once:
                return self.not_enough_stamina()

            self.open_boss_book('wuyin')
            target_val = config.get('Which Tacet Suppression to Farm', 1)
            if isinstance(target_val, str) and '-' in target_val:
                try:
                    index = int(target_val.split('-')[0].strip()) - 1
                except Exception:
                    index = 0
            elif isinstance(target_val, int):
                index = target_val - 1
            else:
                index = 0

            skip_locked = config.get('Skip Locked Fields', config.get('Skip Locked Areas', True))
            candidates = [index]
            if skip_locked:
                candidates += [i for i in range(self.total_number) if i != index]

            teleported = False
            for cand_index in candidates:
                try:
                    if cand_index != candidates[0]:
                        self.openF2Book("gray_book_boss")
                        self.open_boss_book('wuyin')
                    self.teleport_to_tacet(cand_index)
                    teleported = True
                    if cand_index != index:
                        self.log_info(f"Farming alternative Tacet Suppression #{cand_index + 1} because preferred field was locked.")
                    break
                except AreaLockedException as e:
                    self.log_warning(f"Tacet Suppression #{cand_index + 1} is in a locked area: {e}.")
                    if not skip_locked:
                        raise
                    self.ensure_main(time_out=10)

            if not teleported:
                raise AreaLockedException("All candidate Tacet Suppression fields are in locked areas.")

            self.click_team_challenge()
            while True:
                self.wait_in_team_and_world(time_out=120)
                try:
                    self.combat_once(target=True)
                except (NotInCombatException, CharDeadException, CharRevivedException):
                    self.log_info('Tacet combat ended due to death/revive, recovering')
                    self.close_revive_popup()
                    self.send_key('esc', after_sleep=1)
                    self.wait_click_feature('gray_confirm_exit_button', relative_x=-1, raise_if_not_found=False,
                                            time_out=3, click_after_delay=0.5)
                    self.wait_in_team_and_world(time_out=120)
                    self.revive_at_tower_and_heal()
                    break
                self.walk_to_treasure()
                self.pick_f(handle_claim=False)
                self.sleep(2)
                if not self.has_claim_stamina():
                    self.walk_to_treasure()
                    self.pick_f(handle_claim=False)
                    self.sleep(1)
                if not self.has_claim_stamina():
                    self.esc_cancel()
                    self.log_info('is not claim treasure, restart challenge')
                    continue
                can_continue, used = self.use_stamina(once=self.stamina_once, must_use=must_use)
                self.info_incr('used stamina', used)
                self.sleep(4)
                if not can_continue:
                    self.click_relative(0.365, 0.853, hcenter=True)
                    self.wait_in_team_and_world(time_out=120)
                    return None
                else:
                    self.click_relative(0.640, 0.851, hcenter=True, after_sleep=0.2)
                    self.wait_click_skip_dialog_confirm()
                must_use -= used

    def not_enough_stamina(self, back=True):
        self.log_info(f"used all stamina")
        if back:
            self.ensure_main(time_out=10)

    def teleport_to_tacet(self, index):
        self.info_set('Teleport to Tacet Suppression', index)
        if index >= self.total_number:
            raise IndexError(f'Index out of range, max is {self.total_number}')
        return self.click_on_book_target(index + 1, self.total_number, self.structure)
