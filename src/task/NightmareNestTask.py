import re
import cv2
from dataclasses import dataclass

from ok import Logger
from src.task.BaseCombatTask import BaseCombatTask, CharRevivedException, CharDeadException
from src.task.BaseWWTask import BaseWWTask
from src.task.WWOneTimeTask import WWOneTimeTask

logger = Logger.get_logger(__name__)
TRAVEL_FEATURES = ['fast_travel_custom', 'gray_teleport', 'remove_custom']
CONFIRM_FEATURES = ['confirm_btn_hcenter_vcenter', 'confirm_btn_highlight_hcenter_vcenter']


@dataclass
class NestTarget:
    box: object
    cache_key: str
    action: str = ''
    denominator: int = 0
    row_y: float = 0.0


class NightmareNestTask(WWOneTimeTask, BaseCombatTask):
    _unreachable_nests = set()
    _unreachable_targets = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.default_config = {'_enabled': True}
        self.trigger_interval = 0.1
        self.target_enemy_time_out = 10
        self.name = "🌙 Nightmare Nest Task"
        self.description = "Auto Farm all Nightmare Nest"
        self.support_schedule_task = True
        self.count_re = re.compile(r"(\d{1,2})/(\d{1,2})")
        self.queues = []
        self._capture_success = False
        self._capture_mode = False
        self._unreachable_nests = set()
        self._unreachable_targets = []
        self._nest_tab_of_current_nest = 'go_nest'
        self.default_config.update({
            'Which to Farm': ['Nightmare Purification', 'Tacet Discord Nest'],
            'Skip Locked Nests': True,
        })
        self.config_description = {
            'Which to Farm': 'Select which types of nests to farm.',
            'Skip Locked Nests': 'Automatically skip nests that are locked, in unexplored areas, or cannot be fast traveled to.',
        }
        self.config_type['Which to Farm'] = {'type': "multi_selection",
                                             'options': ['Nightmare Purification', 'Tacet Discord Nest']}
        self.config_type['Skip Locked Nests'] = {'type': 'check_box'}

    def _should_skip_locked(self):
        return self.config.get('Skip Locked Nests', self.config.get('Skip Locked Areas', True))

    def _mark_nest_unreachable(self, nest, reason=None):
        cache_key = nest.cache_key if isinstance(nest, NestTarget) else getattr(nest, 'cache_key', str(nest))
        if not hasattr(self, '_unreachable_nests'):
            self._unreachable_nests = set()
        self._unreachable_nests.add(cache_key)
        if not hasattr(self, '_unreachable_targets'):
            self._unreachable_targets = []
        if isinstance(nest, NestTarget) and getattr(nest, 'action', None) and getattr(nest, 'row_y', None):
            self._unreachable_targets.append({
                'action': nest.action,
                'denominator': nest.denominator,
                'row_y': nest.row_y,
                'cache_key': cache_key,
            })
        reason_msg = f" ({reason})" if reason else ""
        self.log_info(f"Marked nightmare nest as unreachable/locked, will skip: {cache_key}{reason_msg}")

    def _is_nest_unreachable(self, action_name, denominator, row_y, cache_key):
        unreachable_set = getattr(self, '_unreachable_nests', set())
        if cache_key in unreachable_set:
            return True
        for target in getattr(self, '_unreachable_targets', []):
            if target['action'] == action_name and target['denominator'] == denominator:
                if abs(target['row_y'] - row_y) < 0.04:
                    return True
        return False

    def _recover_to_guidebook(self):
        """
        Safely recovers the game state back to the F2 Guidebook (gray_book_boss)
        or main world so the next nest can be processed without getting stuck on map or popups.
        """
        self.log_info('Recovering UI state back to guidebook/main...')
        for _ in range(3):
            if self.find_one(['confirm_btn_hcenter_vcenter', 'confirm_btn_highlight_hcenter_vcenter',
                             'cancel_button_hcenter_vcenter', 'cancel_button_highlight_hcenter_vcenter']):
                self.send_key('esc', after_sleep=0.5)
            else:
                break

        if self.find_one('gray_book_boss', box='box_gray_book', threshold=0.3):
            self.log_info('Already at guidebook')
            return True

        for _ in range(4):
            self.send_key('esc', after_sleep=1.0)
            if self.find_one('gray_book_boss', box='box_gray_book', threshold=0.3):
                self.log_info('Back to guidebook')
                return True
            if self.in_team_and_world():
                self.log_info('Back to main world, opening guidebook')
                self.openF2Book('gray_book_boss')
                return True

        BaseWWTask.ensure_main(self, time_out=15)
        self.openF2Book('gray_book_boss')
        return True

    def _is_row_locked(self, count_box):
        screen_h = max(self.height_of_screen(1), 1)
        y1 = max(0.0, (count_box.y - count_box.height * 1.5) / screen_h)
        y2 = min(1.0, (count_box.y + count_box.height * 2.5) / screen_h)
        row_box = self.box_of_screen(0.35, y1, 0.98, y2)
        try:
            texts = self.ocr(box=row_box, match=self.get_locked_keywords())
            if texts:
                clean_name = str(getattr(texts[0], 'name', '')).encode('ascii', errors='replace').decode('ascii')
                self.log_info(f'Detected locked row in guidebook: {clean_name}')
                return True
        except Exception as e:
            logger.debug(f'Row lock check failed: {e}')
        return False

    def run(self):
        self._capture_mode = False
        self._capture_success = False
        self._unreachable_nests.clear()
        self._unreachable_targets.clear()
        WWOneTimeTask.run(self)
        self.ensure_main(time_out=30)
        self._init_queue()
        self.log_info('opened gray_book_boss')
        while nest := self.get_nest_to_go():
            try:
                self.combat_nest(nest)
            except Exception as e:
                self.log_warning(f"Error processing nest {getattr(nest, 'cache_key', nest)}: {e}. Skipping and recovering...")
                self._mark_nest_unreachable(nest, reason=f'unexpected error: {e}')
                self._recover_to_guidebook()
        self.ensure_main(time_out=30)

    def run_capture_mode(self):
        self._capture_mode = True
        self._capture_success = False
        self._unreachable_nests.clear()
        self._unreachable_targets.clear()
        WWOneTimeTask.run(self)
        self.ensure_main(time_out=30)
        self._init_queue()
        self.log_info('opened gray_book_boss')
        while nest := self.get_nest_to_go():
            try:
                self.combat_nest(nest)
            except Exception as e:
                self.log_warning(f"Error processing nest {getattr(nest, 'cache_key', nest)}: {e}. Skipping and recovering...")
                self._mark_nest_unreachable(nest, reason=f'unexpected error: {e}')
                self._recover_to_guidebook()
            if self._capture_success:
                break
        self.ensure_main(time_out=30)

    def on_combat_check(self):
        if self._capture_mode:
            self.pick_f(handle_claim=False)
            if self.has_echo_notification():
                return self.reset_to_false(reason='echo captured')
        return True

    def has_echo_notification(self):
        if self.find_best_match_in_box(self.box_of_screen(0.078, 0.488, 0.094, 0.514),
                                       ['char_1_text', 'char_3_text'], 0.6,
                                       frame_processor=convert_image_to_negative):
            self._capture_success = True
        return self._capture_success

    def combat_nest(self, nest):
        target_box = nest.box if isinstance(nest, NestTarget) else nest
        self.click(target_box, after_sleep=2)

        if self._should_skip_locked() and self.is_area_or_beacon_locked():
            self.log_warning(f"Echo nest '{getattr(nest, 'cache_key', nest)}' detected as locked after click. Skipping...")
            self._mark_nest_unreachable(nest, reason='locked on click')
            self._recover_to_guidebook()
            return

        feature = self.wait_feature(['fast_travel_custom', 'gray_teleport', 'remove_custom', 'team_close'], time_out=6,
                                    settle_time=0.5, raise_if_not_found=False)
        if not feature:
            is_locked = self.is_area_or_beacon_locked()
            self.log_warning(f"Echo nest '{getattr(nest, 'cache_key', nest)}' travel or domain button not found (locked={is_locked}). Skipping...")
            self._mark_nest_unreachable(nest, reason='no travel button / locked')
            self._recover_to_guidebook()
            return

        is_team = feature.name == 'team_close'
        if is_team:
            try:
                self.click_team_challenge()
                if not self.wait_in_team_and_world(time_out=120, raise_if_not_found=False):
                    raise TimeoutError("Failed to enter team challenge world")
            except Exception as e:
                self.log_warning(f"Team challenge failed (possibly locked or inaccessible): {e}. Skipping...")
                self._mark_nest_unreachable(nest, reason=f'team challenge error: {e}')
                self._recover_to_guidebook()
                return
        else:
            if not self._travel_to_nest_or_skip(nest):
                return
            self.sleep(1)
            while self.find_f_with_text():
                self.send_key('f', after_sleep=1)
                self.wait_in_team_and_world(time_out=40, raise_if_not_found=False)
            self.sleep(2)
            self.run_until(self.in_combat, 'w', time_out=10, running=False, target=True)
        wait_combat_time = 10
        while True:
            try:
                need_find = self.combat_once(wait_combat_time=wait_combat_time, target=True,
                                             raise_if_not_found=False)
            except (CharDeadException, CharRevivedException):
                self.log_info('nightmare nest: death recovered, re-enter from F2 book')
                return
            captured_early = False
            if self._capture_mode:
                if self._capture_success or self.wait_until(self.has_echo_notification, time_out=3):
                    self.log_info("Captured echo during combat, skipping search.")
                    captured_early = True
            if not captured_early:
                self.sleep(3)
                if need_find and not self.walk_find_echo(time_out=5, backward_time=2.5):
                    dropped = self.yolo_find_echo(turn=True, use_color=False, time_out=30)[0]
                    logger.info(f'farm echo yolo find {dropped}')
                    if not dropped and not is_team:
                        # 保底：没有收取到声骸时，重新打开图鉴传送回当前聚落（传送点面朝金色声骸群），再搜索一次
                        self.log_info('no echo collected, re-teleport to current nest as fallback')
                        self.ensure_main(time_out=30)
                        self.openF2Book("gray_book_boss")
                        getattr(self, self._nest_tab_of_current_nest)()
                        self.sleep(1)
                        self.click(target_box, after_sleep=2)
                        if self.wait_feature(TRAVEL_FEATURES, time_out=5, settle_time=0.5,
                                            raise_if_not_found=False) and self._travel_to_nest_or_skip(nest):
                            self.sleep(2)
                            self.run_until(lambda: False, 'w', time_out=2, running=True)
                            if not self.walk_find_echo(time_out=5, backward_time=2.5):
                                dropped = self.yolo_find_echo(turn=True, use_color=False, time_out=30)[0]
                                logger.info(f'farm echo yolo find after re-teleport {dropped}')
                            else:
                                dropped = True
                                self.log_info('farm echo walk find true after re-teleport')
                else:
                    dropped = True
                    self.log_info('farm echo walk find true')
                self._capture_success = dropped
            if not self._should_continue_combat_after_pickup():
                break
            self.log_info('nightmare nest: combat detected after pickup')
            wait_combat_time = 1
        # 与刷全部一致：退本后再结束 combat_nest，避免还在巢穴内回 Daily/开书
        if is_team:
            self.esc_world_confirm()
        self.sleep(1)

    def _should_continue_combat_after_pickup(self):
        return not self._capture_mode and self.wait_combat(
            target=True, time_out=3, raise_if_not_found=False)

    def _travel_to_nest_or_skip(self, nest):
        if self._should_skip_locked() and self.is_area_or_beacon_locked():
            self.log_warning(f"Waypoint or area is locked on map. Skipping nest: {getattr(nest, 'cache_key', nest)}")
            self._mark_nest_unreachable(nest, reason='beacon locked on map')
            self._recover_to_guidebook()
            return False

        travel = self.wait_until(self._find_travel_button, raise_if_not_found=False, time_out=2)
        if travel:
            self.click(travel, after_sleep=1)
            if confirm := self._find_first_feature(CONFIRM_FEATURES, threshold=0.6):
                self.click(confirm, after_sleep=1)

        if self._should_skip_locked() and self.is_area_or_beacon_locked():
            self.log_warning("Area or beacon locked indicator appeared after travel click. Skipping nest...")
            self._mark_nest_unreachable(nest, reason='locked message after click')
            self._recover_to_guidebook()
            return False

        button_still_visible = travel and self.find_one(travel.name, threshold=0.7)
        if travel and not button_still_visible and self.wait_in_team_and_world(
                time_out=120, raise_if_not_found=False):
            return True

        self.log_warning(f"Nightmare nest travel failed (beacon likely locked or unreachable): {getattr(nest, 'cache_key', nest)}")
        self._mark_nest_unreachable(nest, reason='travel failed or beacon locked')
        self._recover_to_guidebook()
        return False

    def _find_travel_button(self):
        return self._find_first_feature(TRAVEL_FEATURES, threshold=0.7)

    def _find_first_feature(self, feature_names, threshold):
        for feature_name in feature_names:
            if feature := self.find_one(feature_name, threshold=threshold):
                return feature

    def get_nest_to_go(self):
        if not self.find_one("gray_book_boss", box='box_gray_book', threshold=0.3):
            self.openF2Book("gray_book_boss")

        while self.queues:
            self.queues[0]()
            if nest := self.find_nest():
                self._nest_tab_of_current_nest = self.queues[0].__name__
                return nest
            self.queues.pop(0)

    def _init_queue(self):
        quests = self.config.get('Which to Farm') or ['Nightmare Purification', 'Tacet Discord Nest']
        actions = []
        if 'Tacet Discord Nest' in quests:
            actions.append(self.go_nest)
            actions.append(self.go_nest_scroll)
        if 'Nightmare Purification' in quests:
            actions.append(self.go_nightmare)
            actions.append(self.go_nightmare_scroll)
        self.queues = actions

    def go_nightmare(self):
        self.open_boss_book('mengyan')
        self.log_info('go nightmare')

    def go_nightmare_scroll(self):
        self.open_boss_book('mengyan')
        self.click(3737 / 3840, 0.54, after_sleep=1)
        self.log_info('go nightmare scroll')

    def go_nest(self):
        self.open_boss_book('canxiang')
        self.log_info('go nest')

    def go_nest_scroll(self):
        self.open_boss_book('canxiang')
        self.click(3737 / 3840, 0.54, after_sleep=1)
        self.log_info('go nest scroll')

    def _is_incomplete_nest(self, numerator_str, denominator_str):
        try:
            num = int(numerator_str)
            denom = int(denominator_str)
            if num >= denom:
                return False
            return denom in (24, 36, 48, 41) or (10 <= denom <= 100)
        except ValueError:
            return False

    def find_nest(self):
        counts = self.ocr(0.35, 0.13, 1, 0.96, match=self.count_re)
        counts.sort(key=lambda b: getattr(b, 'y', 0))
        for count_box in counts:
            for match in re.finditer(self.count_re, count_box.name):
                numerator = match.group(1)
                denominator = match.group(2)
                if self._is_incomplete_nest(numerator, denominator):
                    denom_int = int(denominator)
                    screen_height = max(self.height_of_screen(1), 1)
                    row_y = (count_box.y + count_box.height / 2) / screen_height
                    cache_key = self._make_nest_cache_key(count_box, denominator)
                    action_name = self.queues[0].__name__ if self.queues else 'unknown'
                    if self._is_nest_unreachable(action_name, denom_int, row_y, cache_key):
                        self.log_info(f'skip cached unreachable nightmare nest: {cache_key}')
                        continue
                    nest_target = NestTarget(
                        box=None,
                        cache_key=cache_key,
                        action=action_name,
                        denominator=denom_int,
                        row_y=row_y
                    )
                    if self._should_skip_locked() and self._is_row_locked(count_box):
                        self.log_warning(f"Echo nest '{cache_key}' is locked in guidebook. Skipping...")
                        self._mark_nest_unreachable(nest_target, reason='locked in guidebook')
                        continue
                    self.log_info(f'{count_box} is not complete ({numerator}/{denominator})')
                    screen_h = max(self.height_of_screen(1), 1)
                    y1 = max(0.0, (count_box.y - count_box.height) / screen_h)
                    y2 = min(1.0, (count_box.y + count_box.height * 2) / screen_h)
                    row_proceed = self.find_feature('boss_proceed', box=self.box_of_screen(0.85, y1, 0.98, y2), threshold=0.7)
                    if row_proceed:
                        click_target = row_proceed[0]
                    else:
                        from ok import Box
                        click_target = Box(name=count_box.name, x=int(self.width_of_screen(0.9)),
                                           y=int(count_box.y - count_box.height * 0.9), width=1, height=1)
                    nest_target.box = click_target
                    return nest_target

    def _make_nest_cache_key(self, count_box, denominator):
        action_name = self.queues[0].__name__ if self.queues else 'unknown'
        screen_height = max(self.height_of_screen(1), 1)
        row_y = (count_box.y + count_box.height / 2) / screen_height
        row_slot = round(row_y / 0.02)
        # 使用粗粒度行槽位，避免 OCR 坐标轻微抖动导致同一目标被重复点击。
        return f'{action_name}:{denominator}:{row_slot}'


def convert_image_to_negative(img):
    to_gray = False
    _mat = img
    if len(_mat.shape) == 3:
        to_gray = True
        _mat = cv2.cvtColor(_mat, cv2.COLOR_BGR2GRAY)
    _, _mat = cv2.threshold(_mat, 80, 255, cv2.THRESH_BINARY)
    _mat = cv2.bitwise_not(_mat)
    if to_gray:
        _mat = cv2.cvtColor(_mat, cv2.COLOR_GRAY2BGR)
    return _mat


from ok import run_task
from config import config

if __name__ == "__main__":
    run_task(config, task=NightmareNestTask, debug=True)
