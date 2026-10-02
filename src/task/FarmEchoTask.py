import re
import cv2
import time

import numpy as np

from ok import Logger, TaskDisabledException, color_range_to_bound
from src.task.BaseCombatTask import BaseCombatTask, white_color
from src.task.WWOneTimeTask import WWOneTimeTask
from src.task.BaseWWTask import AreaLockedException
from ok import find_boxes_by_name

logger = Logger.get_logger(__name__)


OVERWORLD_BOSS_LIST = [
    'Crownless',
    'Thundering Mephis',
    'Tempest Mephis',
    'Inferno Rider',
    'Feilian Beringal',
    'Mourning Aix',
    'Impermanence Heron',
    'Mech Abomination',
    'Lampylumen Myriad',
    'Fallacy of No Return',
    'Sentry Construct',
    'Lorelei',
    'Lioness of Glory',
    'Fenrico',
    'Nameless Explorer',
]

WEEKLY_BOSS_LIST = [
    'Scar (Weekly)',
    'Bell-Borne Geochelone (Weekly)',
    'Dreamless (Weekly)',
    'Jue (Weekly)',
    'Hecate / Sentinel (Weekly)',
]

THREE_COST_MONSTERS = {
    'Violet-Feathered Heron': {'search_en': 'Violet-Feathered Heron', 'search_zh': '紫羽鹭'},
    'Cyan-Feathered Heron': {'search_en': 'Cyan-Feathered Heron', 'search_zh': '青羽鹭'},
    'Havoc Dreadmane': {'search_en': 'Havoc Dreadmane', 'search_zh': '暗鬃狼'},
    'Chasm Guardian': {'search_en': 'Chasm Guardian', 'search_zh': '巡哨机偶'},
    'Tambourinist': {'search_en': 'Tambourinist', 'search_zh': '手鼓乐手'},
    'Flautist': {'search_en': 'Flautist', 'search_zh': '鸣钟乐手'},
    'Autopuppet Scout': {'search_en': 'Autopuppet Scout', 'search_zh': '自动机偶'},
    'Geohide Saurian': {'search_en': 'Geohide Saurian', 'search_zh': '坚岩斗士'},
    'Stonewall Brute': {'search_en': 'Stonewall Brute', 'search_zh': '岩拳守卫'},
    'Spearback': {'search_en': 'Spearback', 'search_zh': '穿山兽'},
    'Hoochief': {'search_en': 'Hoochief', 'search_zh': '呼噜噜'},
    'Viridblaze Saurian': {'search_en': 'Viridblaze Saurian', 'search_zh': '绿熔蜥'},
    'Roseshroom': {'search_en': 'Roseshroom', 'search_zh': '刺玫菇'},
    'Glacio Dreadmane': {'search_en': 'Glacio Dreadmane', 'search_zh': '霜鬃狼'},
    'Lumahoof': {'search_en': 'Lumahoof', 'search_zh': '踏光兽'},
    'Lightcrusher': {'search_en': 'Lightcrusher', 'search_zh': '光耀裂隙兽'},
}

ONE_COST_MONSTERS = {
    'Glacio Prism': {'search_en': 'Glacio Prism', 'search_zh': '冰棱镜'},
    'Fusion Prism': {'search_en': 'Fusion Prism', 'search_zh': '火棱镜'},
    'Electro Prism': {'search_en': 'Electro Prism', 'search_zh': '雷棱镜'},
    'Havoc Prism': {'search_en': 'Havoc Prism', 'search_zh': '暗棱镜'},
    'Tick Tack': {'search_en': 'Tick Tack', 'search_zh': '发条怪'},
    'Zig Zag': {'search_en': 'Zig Zag', 'search_zh': '折线怪'},
    'Whiff Whaff': {'search_en': 'Whiff Whaff', 'search_zh': '风精灵'},
    'Snip Snap': {'search_en': 'Snip Snap', 'search_zh': '剪刀怪'},
    'Chirpuff': {'search_en': 'Chirpuff', 'search_zh': '风鸣鸟'},
    'Cruisewing': {'search_en': 'Cruisewing', 'search_zh': '浮游鸟'},
    'Fusion Dreadmane': {'search_en': 'Fusion Dreadmane', 'search_zh': '火狼'},
    'Baby Viridblaze Saurian': {'search_en': 'Baby Viridblaze Saurian', 'search_zh': '幼火蜥'},
    'Vanguard Junrock': {'search_en': 'Vanguard Junrock', 'search_zh': '尖晶石'},
    'Fission Junrock': {'search_en': 'Fission Junrock', 'search_zh': '裂晶石'},
    'Aero Predator': {'search_en': 'Aero Predator', 'search_zh': '风猎手'},
    'Gulpuff': {'search_en': 'Gulpuff', 'search_zh': '咕咕鸟'},
    'Sabyr Boar': {'search_en': 'Sabyr Boar', 'search_zh': '野猪'},
}

BOSS_PROFILES = {
    'All Overworld Bosses (Sweep)': {
        'category': 'sweep_overworld',
    },
    'All Weekly Bosses (Sweep)': {
        'category': 'sweep_weekly',
    },
    'All 4-Cost Bosses (Complete Sweep)': {
        'category': 'sweep_all_4c',
    },
    'All 3-Cost Echoes (Guidebook Track)': {
        'category': 'track_3c',
    },
    'All 1-Cost Echoes (Guidebook Track)': {
        'category': 'track_1c',
    },
    'All 3C & 1C Echoes (Full Track)': {
        'category': 'track_all',
    },
    'Current Location (No Teleport)': {
        'category': 'manual',
    },
    'Scar (Weekly)': {
        'category': 'weekly',
        'serial': 1,
        'search_en': 'Scar',
        'search_zh': '斯卡',
    },
    'Bell-Borne Geochelone (Weekly)': {
        'category': 'weekly',
        'serial': 2,
        'search_en': 'Bell-Borne Geochelone',
        'search_zh': '鸣钟之龟',
    },
    'Dreamless (Weekly)': {
        'category': 'weekly',
        'serial': 3,
        'search_en': 'Dreamless',
        'search_zh': '无妄者',
    },
    'Jue (Weekly)': {
        'category': 'weekly',
        'serial': 4,
        'search_en': 'Jue',
        'search_zh': '角',
    },
    'Hecate / Sentinel (Weekly)': {
        'category': 'weekly',
        'serial': 5,
        'search_en': 'Hecate',
        'search_zh': '赫卡忒',
    },
    'Crownless': {
        'category': 'overworld',
        'serial': 1,
        'search_en': 'Crownless',
        'search_zh': '无冠者',
    },
    'Thundering Mephis': {
        'category': 'overworld',
        'serial': 2,
        'search_en': 'Thundering Mephis',
        'search_zh': '云闪之鳞',
    },
    'Tempest Mephis': {
        'category': 'overworld',
        'serial': 3,
        'search_en': 'Tempest Mephis',
        'search_zh': '朔雷之鳞',
    },
    'Inferno Rider': {
        'category': 'overworld',
        'serial': 4,
        'search_en': 'Inferno Rider',
        'search_zh': '燎照之骑',
    },
    'Feilian Beringal': {
        'category': 'overworld',
        'serial': 5,
        'search_en': 'Feilian Beringal',
        'search_zh': '飞廉之猩',
    },
    'Mourning Aix': {
        'category': 'overworld',
        'serial': 6,
        'search_en': 'Mourning Aix',
        'search_zh': '哀声鸷',
    },
    'Impermanence Heron': {
        'category': 'overworld',
        'serial': 7,
        'search_en': 'Impermanence Heron',
        'search_zh': '无常凶鹭',
    },
    'Mech Abomination': {
        'category': 'overworld',
        'serial': 8,
        'search_en': 'Mech Abomination',
        'search_zh': '聚械机偶',
    },
    'Lampylumen Myriad': {
        'category': 'overworld',
        'serial': 9,
        'search_en': 'Lampylumen Myriad',
        'search_zh': '辉萤军势',
    },
    'Fallacy of No Return': {
        'category': 'overworld',
        'serial': 10,
        'search_en': 'Fallacy of No Return',
        'search_zh': '无归的谬误',
        'combat_wait': 5,
        'bypass_end_wait': True,
    },
    'Sentry Construct': {
        'category': 'overworld',
        'serial': 11,
        'search_en': 'Sentry Construct',
        'search_zh': '异构武装',
        'combat_wait': 5,
    },
    'Lorelei': {
        'category': 'overworld',
        'serial': 12,
        'search_en': 'Lorelei',
        'search_zh': '罗蕾莱',
        'set_night': True,
    },
    'Lioness of Glory': {
        'category': 'overworld',
        'serial': 13,
        'search_en': 'Lioness of Glory',
        'search_zh': '荣耀狮像',
        'combat_wait': 5,
    },
    'Fenrico': {
        'category': 'overworld',
        'serial': 14,
        'search_en': 'Fenrico',
        'search_zh': '加尔古耶',
        'bypass_end_wait': True,
    },
    'Nameless Explorer': {
        'category': 'overworld',
        'serial': 15,
        'search_en': 'Nameless Explorer',
        'search_zh': '无铭探索者',
        'bypass_end_wait': True,
    },
}


class FarmEchoTask(WWOneTimeTask, BaseCombatTask):
    owns_switch_healer_config = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.description = "Automates farming 4C Echoes from Weekly and Overworld Bosses."
        self.name = "🌀 Farm 4C Echo in Dungeon/World"
        self.default_config.update({
            'Target Boss': 'Current Location (No Teleport)',
            'Teleport to Boss': 'No',
            'Weekly Boss Difficulty': "80",
            'Repeat Farm Count': 100,
            'Skip Locked Areas': True,
            'Sweep Count per Boss': 1,
            'Combat Wait Time': 0,
            'Echo Pickup Method': 'Yolo',
            'Use Liberation': True,
            'Switch to Healer before and after Combat': True,
            'Claim Boss Rewards': False,
        })
        self.config_description.update({
            'Target Boss': 'Select target boss or multi-target sweep mode (4C bosses, 3C/1C Guidebook tracking).',
            'Weekly Boss Difficulty': 'Choose level (50-90) for Weekly Challenge domains.',
            'Repeat Farm Count': 'Repeat count for single boss farming (default 100).',
            'Skip Locked Areas': 'Automatically skip bosses or tracking targets in locked/unactivated map areas without failing the routine.',
            'Sweep Count per Boss': 'Number of times to defeat each boss/target in sweep modes (default 1).',
            'Combat Wait Time': 'Wait time before each combat (seconds), 0 uses profile default.',
            'Echo Pickup Method': 'Yolo vision detection or walking circle sweep.',
            'Use Liberation': 'Use Resonance Liberation during combat.',
            'Switch to Healer before and after Combat': 'Switch to healer before and after combat to ensure survival.',
            'Claim Boss Rewards': 'Claim Sonance Sphere / flower rewards using Waveplates if enabled.',
        })
        self.find_echo_method = ['Yolo', 'Run in Circle', 'Walk']
        self.boss_list = list(BOSS_PROFILES.keys())
        self.config_type['Target Boss'] = {'type': "drop_down", 'options': self.boss_list}
        self.config_type['Weekly Boss Difficulty'] = {'type': "drop_down", 'options': ['50', '60', '70', '80', '90']}
        self.config_type['Echo Pickup Method'] = {'type': "drop_down", 'options': self.find_echo_method}
        self.config_type['Sweep Count per Boss'] = {'type': "int", 'min': 1, 'max': 50}
        self.config_type['Skip Locked Areas'] = {'type': "check_box"}
        self.combat_end_condition = self.find_echos
        self.total_weekly_number = 9
        self.total_boss_number = 20
        self.add_exit_after_config()
        self._has_treasure = False
        self._in_realm = False
        self._farm_start_time = time.time()
        self.last_night_change = 0
        self.aim_boss = None
        self.combat_wait_time = 0
        self.set_night = False
        self.bypass_end_wait = False
        self._teleport_walk_result = None
        self._just_entered_boss_realm = False
        self.boss_dict = {
            '伪作的神王': {'name': r'伪作的神王'},
            '异构武装': {'name': r'(异构武装|加尔古耶)', 'set_combat_wait': 5},
            '荣耀狮像': {'name': r'(狮像|亚狮诺索)', 'set_combat_wait': 5},
            '罗蕾莱': {'name': r'(罗蕾莱|夜之女皇)', 'set_night': True},
        }
        self.is_revived = False

    def on_combat_check(self):
        if not self._in_realm:
            self.incr_drop(self.pick_f(handle_claim=True))
        self.in_realm_check(20)
        return True

    def revive_action(self):
        if self._in_realm:
            return False
        self.teleport_to_heal()
        self.run_until(lambda: False, 's', 1, running=True)
        if self.teleport_to_boss_enabled():
            self.teleport_to_nearest_boss()
            self.sleep(0.5)
            self.run_until(lambda: self.in_combat() or self.find_treasure_icon(), 'w', time_out=12, running=True,
                           target=True)
            self.execute_treasure_hunt()
        self.is_revived = True
        return True

    def run(self):
        WWOneTimeTask.run(self)
        self.use_liberation = self.config.get('Use Liberation')
        try:
            return self.do_run()
        except TaskDisabledException:
            pass
        except Exception as e:
            logger.error('farm 4c error, try handle monthly card', e)
            if self.handle_claim_button() or self.handle_monthly_card():
                self.run()
            else:
                raise

    def do_run(self):
        target_name, profile = self.get_selected_boss_profile()
        category = profile.get('category')

        if category in ('sweep_overworld', 'sweep_weekly', 'sweep_all_4c'):
            return self.run_4c_boss_sweep(category)
        elif category in ('track_3c', 'track_1c', 'track_all'):
            return self.run_guidebook_mob_tracking(category)
        else:
            return self.run_single_boss(target_name, profile)

    def run_4c_boss_sweep(self, sweep_category):
        sweep_count = max(1, int(self.config.get('Sweep Count per Boss', 1)))

        if sweep_category == 'sweep_weekly':
            boss_list = list(WEEKLY_BOSS_LIST)
        elif sweep_category == 'sweep_overworld':
            boss_list = list(OVERWORLD_BOSS_LIST)
        else:
            boss_list = list(WEEKLY_BOSS_LIST) + list(OVERWORLD_BOSS_LIST)

        self.log_info(f'Starting 4-Cost Boss Sweep across {len(boss_list)} bosses ({sweep_count} runs each)...')

        total = len(boss_list)
        for idx, boss_name in enumerate(boss_list, 1):
            self.log_info(f'=== [Sweep {idx}/{total}] Target: {boss_name} ({sweep_count} runs) ===')
            profile = BOSS_PROFILES[boss_name]
            try:
                self.run_single_boss(boss_name, profile, max_count=sweep_count)
            except AreaLockedException as e:
                if self.config.get('Skip Locked Areas', True):
                    self.log_warning(f'⚠️ [Sweep {idx}/{total}] Skipping {boss_name}: {e}. Advancing to next boss in sweep...')
                    self.ensure_main(time_out=10)
                    continue
                raise
            except Exception as e:
                err_str = str(e).lower()
                if self.config.get('Skip Locked Areas', True) and any(w in err_str for w in ['locked', 'teleport to boss', 'travel', 'proceed']):
                    self.log_warning(f'⚠️ [Sweep {idx}/{total}] Skipping {boss_name} due to unreachable/locked area ({e}). Advancing...')
                    self.ensure_main(time_out=10)
                    continue
                raise

        self.log_info('4-Cost Boss Sweep completed successfully!')

    def run_guidebook_mob_tracking(self, track_category):
        sweep_count = max(1, int(self.config.get('Sweep Count per Boss', 1)))

        if track_category == 'track_3c':
            queue = list(THREE_COST_MONSTERS.items())
        elif track_category == 'track_1c':
            queue = list(ONE_COST_MONSTERS.items())
        else:
            queue = list(THREE_COST_MONSTERS.items()) + list(ONE_COST_MONSTERS.items())

        self.log_info(f'Starting Guidebook Mob Tracking across {len(queue)} species (quota: {sweep_count * 20} per species)...')

        total = len(queue)
        for idx, (m_name, m_info) in enumerate(queue, 1):
            self.log_info(f'=== [Guidebook Mob {idx}/{total}] Tracking: {m_name} ===')
            try:
                status = self.track_and_farm_monster(m_name, m_info, max_kills_per_species=sweep_count * 20)
                self.log_info(f'Completed tracking for {m_name}: result={status}')
            except AreaLockedException as e:
                if self.config.get('Skip Locked Areas', True):
                    self.log_warning(f'⚠️ [Guidebook Mob {idx}/{total}] Skipping {m_name}: {e}. Advancing to next species...')
                    self.ensure_main(time_out=10)
                    continue
                raise
            except Exception as e:
                err_str = str(e).lower()
                if self.config.get('Skip Locked Areas', True) and any(w in err_str for w in ['locked', 'teleport', 'travel']):
                    self.log_warning(f'⚠️ [Guidebook Mob {idx}/{total}] Skipping {m_name} due to unreachable area ({e}). Advancing...')
                    self.ensure_main(time_out=10)
                    continue
                raise

        self.log_info('Guidebook Mob Tracking completed for today!')

    def track_and_farm_monster(self, monster_name, monster_info, max_kills_per_species=20):
        search_query = monster_info.get('search_zh') if self.game_lang == 'zh_CN' else monster_info.get('search_en')
        kills = 0
        consecutive_failures = 0

        while kills < max_kills_per_species and consecutive_failures < 3:
            self.ensure_main(time_out=60)
            self.log_info(f'Opening Guidebook to detect {monster_name} ({search_query})...')

            # 1. Open F2 Guidebook All Monsters tab
            self.openF2Book("gray_book_all_monsters")
            self.sleep(0.5)

            # 2. Search for the monster
            self.click(0.13, 0.14, after_sleep=0.5)
            self.input_text(search_query)
            self.sleep(0.3)
            self.click(0.20, 0.14, after_sleep=0.3)
            self.send_key('enter', after_sleep=0.5)
            self.click(0.13, 0.24, after_sleep=0.5)

            # 3. Click Detect / Track button at (0.89, 0.92)
            self.click(0.89, 0.92, after_sleep=1.0)

            if self.is_area_or_beacon_locked():
                if self.config.get('Skip Locked Areas', True):
                    self.log_warning(f'{monster_name}: Detect showed locked area. Skipping...')
                    self.ensure_main(time_out=5)
                    return 'skipped_locked_area'

            # 4. Check if map opened (i.e. tracking target is available)
            map_opened = self.wait_until(
                lambda: self.find_best_match_in_box(
                    self.box_of_screen(0.1, 0.1, 0.9, 0.9),
                    ['map_way_point', 'map_way_point_big'], 0.6
                ) is not None,
                time_out=3.5,
                raise_if_not_found=False
            )

            if not map_opened:
                if self.is_area_or_beacon_locked():
                    if self.config.get('Skip Locked Areas', True):
                        self.log_warning(f'{monster_name}: Target is located in a locked area. Skipping...')
                        self.ensure_main(time_out=5)
                        return 'skipped_locked_area'
                self.log_info(f'{monster_name}: Detect did not open map. Checking if tracking limit reached...')
                texts = self.ocr(log=self.debug)
                exhausted_found = self.find_boxes(
                    texts,
                    match=['All targets', 'No targets', '暂无可探测', '已探测完', '已全部追踪', 'Limit reached']
                )
                self.log_info(f'{monster_name}: Daily overworld tracking exhausted ({exhausted_found})! Moving to next species.')
                self.ensure_main(time_out=5)
                return 'exhausted'

            # 5. Fast travel to the highlighted beacon
            try:
                self.wait_click_travel()
            except AreaLockedException as e:
                if self.config.get('Skip Locked Areas', True):
                    self.log_warning(f'{monster_name}: Destination waypoint is in a locked area ({e}). Skipping...')
                    self.ensure_main(time_out=5)
                    return 'skipped_locked_area'
                raise
            self.wait_in_team_and_world(time_out=120)
            self.sleep(1.5)

            # 6. Follow minimap track marker to the monster
            self.log_info(f'Navigating via minimap towards {monster_name}...')
            self.go_to_boss_minimap(threshold=0.35, time_out=40)

            # 7. Close distance if not yet engaged
            if not self.in_combat(target=True) and not self.in_combat():
                self.run_until(lambda: self.in_combat(target=True) or self.in_combat(), 'w', time_out=5, running=True, target=True)
                if not self.in_combat(target=True) and not self.in_combat():
                    self.middle_click(after_sleep=0.2)
                    self.click(after_sleep=0.3)
                    self.run_until(lambda: self.in_combat(target=True) or self.in_combat(), 'w', time_out=3, running=True, target=True)

            # 8. Engage combat rotation
            if self.in_combat(target=True) or self.in_combat():
                self.middle_click(after_sleep=0.2)
                self.combat_once(wait_combat_time=2, raise_if_not_found=False, target=True)
                self.sleep(1.2)

                # 9. Absorb Echo drop
                dropped = self.pick_echo()
                if not dropped:
                    if self.config.get('Echo Pickup Method', 'Yolo') == 'Yolo':
                        dropped = self.yolo_find_echo(turn=True, use_color=False, time_out=4, threshold=0.55)[0]
                    elif self.config.get('Echo Pickup Method') == 'Run in Circle':
                        dropped = self.run_in_circle_to_find_echo(circle_count=1)
                    else:
                        dropped = self.walk_find_echo(time_out=3)
                self.incr_drop(dropped)
                kills += 1
                consecutive_failures = 0
                self.log_info(f'{monster_name} defeated (kill #{kills}). Dropped echo: {dropped}')

                # 10. Check if a secondary spawn is nearby on the same beacon
                start_check = time.time()
                while time.time() - start_check < 4:
                    angle = self.find_boss_minimap_angle(threshold=0.35)
                    if angle is not None:
                        self.log_info(f'Secondary {monster_name} spawn found on minimap! Navigating...')
                        self.go_to_boss_minimap(threshold=0.35, time_out=25)
                        if self.in_combat(target=True) or self.in_combat():
                            self.combat_once(wait_combat_time=2, raise_if_not_found=False, target=True)
                            self.sleep(1.0)
                            self.incr_drop(self.pick_echo())
                            kills += 1
                        break
                    self.sleep(0.5)
            else:
                consecutive_failures += 1
                self.log_warning(f'{monster_name}: Did not find target after navigating to marker (attempt {consecutive_failures}/3)')

        return 'completed_quota'

    def run_single_boss(self, boss_name=None, profile=None, max_count=None):
        if boss_name is None or profile is None:
            boss_name, profile = self.get_selected_boss_profile()
        count = 0
        limit = max_count if max_count is not None else self.config.get("Repeat Farm Count", 100)
        self._in_realm = self.in_realm()
        self.manage_boss_parameters(boss_name, profile)
        self.log_info(f'in_realm: {self._in_realm}')
        self._farm_start_time = time.time()
        self._has_treasure = False
        self.is_revived = False
        self.init_parameters()
        category = profile.get('category')

        if self.teleport_to_boss_enabled():
            try:
                self.teleport_to_configured_boss_and_prepare(boss_name, profile)
            except AreaLockedException as e:
                if self.config.get('Skip Locked Areas', True):
                    self.log_warning(f"⚠️ Target boss '{boss_name}' cannot be accessed: {e}. Skipping...")
                    self.ensure_main(time_out=10)
                    return
                raise

        while count < limit:
            try:
                self.in_realm_check(60)
                self.log_debug(f'start farming iteration {count} on {boss_name}, in_realm: {self._in_realm}')
                if count > 0 and not self.is_revived:
                    if self._in_realm:
                        if not self.in_combat():
                            self.log_info('Weekly boss realm: restarting challenge...')
                            if not self.restart_realm_challenge():
                                self.log_warning('In-realm restart failed; falling back to re-enter realm from outside')
                                self.reenter_realm_from_outside(boss_name, profile)
                    elif category == 'overworld' and self.teleport_to_boss_enabled():
                        if not self.in_combat():
                            self.log_info(f'Overworld boss: re-teleporting to reset and spawn {boss_name}...')
                            self.teleport_to_configured_boss_and_prepare(boss_name, profile)
                    else:
                        if not self.in_combat():
                            self.manage_boss_interactions(boss_name, profile)
                            if self._has_treasure:
                                self.execute_treasure_hunt()

                if not self.is_revived:
                    self.manage_boss_interactions(boss_name, profile)
                else:
                    self.is_revived = False

                if self._just_entered_boss_realm:
                    self._just_entered_boss_realm = False
                elif not self.in_combat():
                    if not self._in_realm:
                        if self._has_treasure:
                            self.wait_until(
                                lambda: self.find_treasure_icon() or self.in_combat(
                                    target=True) or self.find_f_with_text(),
                                time_out=5, raise_if_not_found=False)
                        if not self.in_combat():
                            self.log_info('not in combat try click restart')
                            if self.walk_to_treasure_and_restart():
                                self.handle_boss_restart_after_treasure(boss_name, profile)
                            else:
                                self.scroll_and_click_buttons()

                count += 1
                self.log_info(f'Start combat sequence for iteration {count}/{limit} on {boss_name}...')
                if not self._in_realm and not self._has_treasure and not self.in_combat():
                    self.go_to_boss_minimap()
                    self.execute_treasure_hunt()

                self.sleep(self.combat_wait_time)
                self.log_info(f'combat_wait_time: {self.combat_wait_time}')
                self.check_boss_name()

                # Lock onto boss and start combat rotation
                self.middle_click(after_sleep=0.2)
                self.combat_once(wait_combat_time=5, raise_if_not_found=False, target=True)
                if self.is_revived:
                    continue

                # Settle for boss death dissolve animation (~1.2s)
                self.sleep(1.2)
                self.log_info('Locating and absorbing Echo drop...')
                dropped = False
                if self.pick_echo():
                    self.log_info('Echo absorbed directly!')
                    dropped = True
                elif self.config.get('Echo Pickup Method', "Yolo") == "Yolo":
                    dropped = \
                        self.yolo_find_echo(turn=True, use_color=False, time_out=self.yolo_time_out,
                                            threshold=self.yolo_threshold)[0]
                    self.log_info(f'Echo pickup via YOLO: {dropped}')
                    if not dropped and not self._in_realm:
                        dropped = self.walk_find_echo(time_out=3)
                        self.log_info(f'Echo pickup fallback walk: {dropped}')
                elif self.config.get('Echo Pickup Method', "Yolo") == "Run in Circle":
                    dropped = self.run_in_circle_to_find_echo(circle_count=2)
                    self.log_info(f'Echo pickup circle sweep: {dropped}')
                else:
                    dropped = self.walk_find_echo()
                    self.log_info(f'Echo pickup walk search: {dropped}')
                self.incr_drop(dropped)

                # Locate and claim rewards if enabled
                if self.config.get('Claim Boss Rewards', False):
                    self.log_info('Locating and claiming boss rewards...')
                    self.claim_boss_rewards()
                if not self.bypass_end_wait:
                    if dropped and not self._has_treasure:
                        self.wait_until(self.in_combat, raise_if_not_found=False, time_out=5)
                    else:
                        self.wait_until(self.in_combat, raise_if_not_found=False, time_out=1)
            except TaskDisabledException:
                raise
            except Exception as e:
                if self.should_reteleport_after_farm_exception():
                    self.log_error(f'Farm failed after walking into boss combat for {boss_name}, teleporting again', e)
                    self.is_revived = False
                    self.teleport_to_configured_boss_and_prepare(boss_name, profile)
                    continue
                raise

        # If we finished runs and are still inside a domain realm, leave realm to overworld
        if self._in_realm:
            self.log_info(f'Finished {count} runs on {boss_name}. Exiting realm to overworld...')
            self.send_key('esc', after_sleep=0.8)
            self.wait_click_feature('claim_cancel_button_hcenter_vcenter', relative_x=2,
                                    raise_if_not_found=False, time_out=3,
                                    post_action=lambda: self.send_key('esc', after_sleep=1),
                                    settle_time=1)
            self.wait_in_team_and_world(time_out=120)
            self.sleep(1.0)
            self._in_realm = False

    def claim_boss_rewards(self):
        try:
            if self.find_treasure_icon():
                self.log_info('Approaching reward claim sphere...')
                self.walk_to_treasure(send_f=True, raise_if_not_found=False)
                self.sleep(0.5)
                if not self.in_team()[0]:
                    if confirm := self.wait_feature(['confirm_btn_hcenter_vcenter', 'confirm_btn_highlight_hcenter_vcenter'], time_out=2, raise_if_not_found=False):
                        self.click(confirm, after_sleep=0.5)
                        self.log_info('Claimed boss rewards successfully')
        except Exception as e:
            self.log_warning(f'Claim boss rewards skipped: {e}')

    def execute_treasure_hunt(self):
        if not self.in_combat() and self.find_treasure_icon() and self.walk_to_treasure_and_restart():
            self.handle_boss_restart_after_treasure()

    def in_realm_check(self, time_threshold):
        if not self._in_realm and time.time() - self._farm_start_time < time_threshold:
            self._in_realm = self.in_realm()
            if self._in_realm:
                self.init_parameters()
                self.log_info(f'in_realm: {self._in_realm}')

    def get_selected_boss_profile(self):
        target = self.config.get('Target Boss')
        if target and target in BOSS_PROFILES and target != 'Current Location (No Teleport)':
            return target, BOSS_PROFILES[target]
        legacy_teleport = self.config.get('Teleport to Boss', 'No')
        legacy_boss = self.config.get('Boss', 'Other')
        if legacy_teleport == 'Weekly Challenge':
            weekly_num = self.config.get('Which Weekly Boss to Teleport', 1)
            for name, p in BOSS_PROFILES.items():
                if p.get('category') == 'weekly' and p.get('serial') == weekly_num:
                    return name, p
            return 'Scar (Weekly)', BOSS_PROFILES['Scar (Weekly)']
        elif legacy_teleport == 'Boss Challenge':
            for name, p in BOSS_PROFILES.items():
                if name == legacy_boss:
                    return name, p
            return 'Crownless', BOSS_PROFILES['Crownless']
        if target and target in BOSS_PROFILES:
            return target, BOSS_PROFILES[target]
        return 'Current Location (No Teleport)', BOSS_PROFILES['Current Location (No Teleport)']

    def teleport_to_boss_enabled(self):
        target_name, profile = self.get_selected_boss_profile()
        category = profile.get('category')
        if category in ('weekly', 'overworld', 'sweep_overworld', 'sweep_weekly', 'sweep_all_4c', 'track_3c', 'track_1c', 'track_all'):
            return True
        teleport = self.config.get('Teleport to Boss', 'No')
        return teleport in ('Weekly Challenge', 'Boss Challenge')

    def should_reteleport_after_farm_exception(self):
        return self.teleport_to_boss_enabled() and self._teleport_walk_result == 'combat'

    def teleport_to_configured_boss_and_prepare(self, target_name=None, profile=None):
        if target_name is None or profile is None:
            target_name, profile = self.get_selected_boss_profile()
        self.manage_boss_parameters(target_name, profile)
        self._teleport_walk_result = None
        try:
            is_team = self.teleport_to_configured_boss(target_name, profile)
            if is_team:
                walk_result = 'realm'
                self._just_entered_boss_realm = True
            else:
                walk_result = self.walk_after_boss_teleport(target_name, profile)
        except AreaLockedException:
            raise
        except Exception as e:
            if self.config.get('Skip Locked Areas', True) and any(w in str(e).lower() for w in ['locked', 'teleport', 'travel', 'proceed']):
                raise AreaLockedException(f"Boss {target_name} is in a locked or unreachable area") from e
            raise RuntimeError(f'Teleport to boss {target_name} failed') from e

        self._teleport_walk_result = walk_result
        self._has_treasure = False
        if walk_result == 'combat':
            self._in_realm = False
            self.treat_as_not_in_realm = True
        elif walk_result == 'realm':
            self._in_realm = True
            self.treat_as_not_in_realm = False
        else:
            raise RuntimeError(f'Teleport to boss {target_name} failed')
        self.init_parameters()
        self.log_info(f'teleport_to_boss prepared as {walk_result}')

    def teleport_to_configured_boss(self, target_name=None, profile=None):
        if target_name is None or profile is None:
            target_name, profile = self.get_selected_boss_profile()
        category = profile.get('category')
        self.ensure_main(time_out=180)

        if category == 'weekly':
            self.info_set('Teleport to Boss', target_name)
            self.openF2Book('gray_book_boss')
            self.open_boss_book('zhange')
            is_team = self.click_on_book_target(profile.get('serial', 1), self.total_weekly_number)
            if is_team:
                self.click_configured_boss_level()
                self.click(0.880, 0.911, after_sleep=2)
                self.click_team_challenge()
            else:
                self.wait_click_travel()
            self.wait_in_team_and_world(time_out=120)
            self.sleep(2)
            return is_team
        elif category == 'overworld':
            self.info_set('Teleport to Boss', target_name)
            search_query = profile.get('search_zh') if self.game_lang == 'zh_CN' else profile.get('search_en')
            if search_query:
                self.openF2Book("gray_book_all_monsters")
                self.click(0.13, 0.14, after_sleep=0.5)
                self.input_text(search_query)
                self.sleep(0.3)
                self.click(0.20, 0.14, after_sleep=0.3)
                self.send_key('enter', after_sleep=0.5)
                self.click(0.13, 0.24, after_sleep=0.5)
                self.click(0.89, 0.92, after_sleep=1)
                if self.is_area_or_beacon_locked():
                    raise AreaLockedException(f"Boss '{target_name}' is located in a locked area")
                self.wait_click_travel()
                self.wait_in_team_and_world(time_out=120)
                self.sleep(2)
                return False
            self.openF2Book('gray_book_boss')
            self.open_boss_book('qiangdi')
            is_team = self.click_on_book_target(profile.get('serial', 1), self.total_boss_number)
            self.wait_click_travel()
            self.wait_in_team_and_world(time_out=120)
            self.sleep(2)
            return is_team
        return False

    def walk_after_boss_teleport(self, target_name=None, profile=None):
        if target_name is None or profile is None:
            target_name, profile = self.get_selected_boss_profile()
        self.log_info(f'walk after boss teleport for {target_name} until combat or F')
        if self.in_combat(target=True) or self.in_combat():
            return 'combat'

        category = profile.get('category')

        if category == 'weekly':
            if self.find_f_with_text():
                self.enter_configured_boss_realm_from_f()
                return 'realm'
            result = self.walk_until_f_or_combat(time_out=15)
            if result == 'f' or self.find_f_with_text():
                self.enter_configured_boss_realm_from_f()
                return 'realm'
            return 'combat'

        # category == 'overworld'
        self.log_info(f'Navigating to {target_name} via minimap...')
        self.go_to_boss_minimap(time_out=35)
        if self.in_combat(target=True) or self.in_combat():
            return 'combat'

        # Step forward into arena to ensure combat aggro
        self.run_until(lambda: self.in_combat(target=True) or self.in_combat(), 'w', time_out=6, running=True, target=True)
        if not self.in_combat(target=True) and not self.in_combat():
            self.click(after_sleep=0.5)
            self.run_until(lambda: self.in_combat(target=True) or self.in_combat(), 'w', time_out=4, running=True, target=True)
        return 'combat'

    def walk_until_f_or_combat(self, direction='w', time_out=20):
        if self.wait_until(lambda: self.in_combat(target=True) or self.in_combat() or self.find_f_with_text(),
                           time_out=1.5, raise_if_not_found=False):
            if self.in_combat(target=True) or self.in_combat():
                return 'combat'
            return 'f'

        self.middle_click(after_sleep=0.2)
        self.send_key_down(direction)
        self.sleep(0.1)
        self.mouse_down(key='right')
        start = time.time()
        try:
            while time.time() - start < time_out:
                if self.in_combat(target=True) or self.in_combat():
                    return 'combat'
                if self.find_f_with_text():
                    return 'f'
                self.middle_click(interval=0.5)
                self.sleep(0.02)
        finally:
            self.send_key_up(direction)
            self.sleep(0.1)
            self.mouse_up(key='right')
        raise RuntimeError('Teleport to boss failed: can not walk to combat or F')

    def enter_configured_boss_realm_from_f(self):
        if not self.wait_until(self.find_f_with_text, time_out=2, raise_if_not_found=False):
            raise RuntimeError('Teleport to boss failed: can not find F before entering realm')
        self.send_key('f', after_sleep=3)
        self.click_configured_boss_level()
        self.sleep(1)
        self.click(0.880, 0.911, after_sleep=2)
        self.click(0.908, 0.919, after_sleep=5)
        self.wait_in_team_and_world(time_out=120)
        self._in_realm = True
        self.treat_as_not_in_realm = False
        self._has_treasure = False
        self._just_entered_boss_realm = True
        self.init_parameters()

    def click_configured_boss_level(self):
        boss_level = str(self.config.get('Weekly Boss Difficulty', self.config.get('Boss Level', '80')))
        level_boxes = self.wait_ocr(0.030, 0.113, 0.323, 0.660, match=re.compile(re.escape(boss_level)),
                                    raise_if_not_found=True, time_out=10, settle_time=1)
        if isinstance(level_boxes, list):
            level_box = level_boxes[0] if level_boxes else None
        else:
            level_box = level_boxes
        if not level_box:
            raise RuntimeError(f'Can not find boss level {boss_level}')
        self.click_box(level_box)

    def handle_boss_restart_after_treasure(self, target_name=None, profile=None):
        if target_name is None or profile is None:
            target_name, profile = self.get_selected_boss_profile()
        self._has_treasure = True
        self.log_info('_has_treasure = True')
        if self._in_realm:
            if not self.restart_realm_challenge():
                self.reenter_realm_from_outside(target_name, profile)
        elif self.teleport_to_boss_enabled():
            if profile.get('category') == 'weekly':
                self.enter_configured_boss_realm_from_f()
            else:
                self.teleport_to_configured_boss_and_prepare(target_name, profile)
        else:
            self.scroll_and_click_buttons()

    def manage_boss_parameters(self, target_name=None, profile=None):
        if target_name is None or profile is None:
            target_name, profile = self.get_selected_boss_profile()
        self.combat_wait_time = self.config.get("Combat Wait Time", 0) or profile.get('combat_wait', 0)
        self.bypass_end_wait = profile.get('bypass_end_wait', False)
        self.treat_as_not_in_realm = (target_name == 'Hecate / Sentinel (Weekly)')
        self.aim_boss = profile.get('search_zh') if self.game_lang == 'zh_CN' else profile.get('search_en')
        self.log_info(
            f"Selected boss: {target_name} ({profile.get('category')}) | "
            f"combat_wait: {self.combat_wait_time}s | bypass_end_wait: {self.bypass_end_wait}"
        )

    def manage_boss_interactions(self, target_name=None, profile=None):
        if self.in_combat():
            return
        if target_name is None or profile is None:
            target_name, profile = self.get_selected_boss_profile()
        if profile.get('set_night'):
            night_elapsed = time.time() - self.last_night_change
            self.log_info(f"Night elapsed: {night_elapsed:.1f}s")
            if night_elapsed > 660:
                self.change_time_to_night()
                self.last_night_change = time.time()
        if target_name == 'Fallacy of No Return':
            if not self.find_f_with_text():
                self.teleport_to_nearest_boss()
                self.send_key('d', down_time=0.25, after_sleep=0.5)
                self.send_key('w', after_sleep=0.5)
            if self.walk_until_f(time_out=20, check_combat=True, running=True):
                self.scroll_and_click_buttons()
            self.wait_until(self.in_combat, raise_if_not_found=False, time_out=300)
        elif target_name == 'Fenrico':
            while self.find_f_with_text():
                self.sleep(1)
                self.incr_drop(self.pick_echo())
            try:
                self.teleport_to_nearest_boss()
                self.sleep(2)
            except Exception:
                self.log_info('Fenrico teleport_to_nearest_boss failed')
                self.ensure_main()
            self.run_until(lambda: self.find_treasure_icon() or self.in_combat() or self.find_f_with_text(), 'w',
                           time_out=5, target=True)
            self.execute_treasure_hunt()
            self.wait_until(self.in_combat, raise_if_not_found=False, time_out=300)
        elif target_name == 'Nameless Explorer':
            self._handle_unnamed_explorer()

    def _handle_unnamed_explorer(self):
        """Nameless Explorer handler: navigates from beacon/restart to arena via minimap."""
        if self.in_combat(target=True) or self.in_combat():
            return

        # 1. Interact with restart treasure if present
        if self.find_treasure_icon() or self.find_f_with_text():
            if self.walk_to_treasure_and_restart():
                self._has_treasure = True
            self.scroll_and_click_buttons()
            self.sleep(1)

        if self.in_combat(target=True) or self.in_combat():
            return

        # 2. Use minimap tracking to turn and sprint directly towards Nameless Explorer
        self.log_info('Nameless Explorer: tracking and navigating to arena via minimap')
        self.go_to_boss_minimap(threshold=0.45, time_out=35)

        # 3. If reached arena area but boss is idling/not triggered, close the distance to aggro
        if not self.in_combat(target=True) and not self.in_combat():
            self.log_info('Nameless Explorer: approaching arena center to trigger combat')
            self.run_until(lambda: self.in_combat(target=True) or self.in_combat(), 'w', time_out=6, running=True, target=True)
            if not self.in_combat(target=True) and not self.in_combat():
                self.click(after_sleep=0.5)
                self.run_until(lambda: self.in_combat(target=True) or self.in_combat(), 'w', time_out=4, running=True, target=True)

        self.execute_treasure_hunt()
        self.wait_until(self.in_combat, raise_if_not_found=False, time_out=10)

    def init_parameters(self):
        self.target_enemy_time_out = 3 if self._in_realm else 1.2
        self.switch_char_time_out = 5 if self._in_realm else 3
        self.yolo_threshold = 0.25 if self._in_realm else 0.65
        self.yolo_time_out = 12 if self._in_realm else 4

    def find_boss_minimap_angle(self, threshold=0.45):
        # Check primary boss / tracked mob markers on minimap
        features = ['boss_check_mark_minimap', 'big_map_diamond', 'boss_no_check_mark', 'big_map_skull', 'boss_check_mark', 'boss_proceed']
        for feat in features:
            angle = self.get_mini_map_turn_angle(feat, threshold=threshold, x_offset=0, y_offset=0)
            if angle is not None:
                return angle
        if threshold > 0.30:
            for feat in features:
                angle = self.get_mini_map_turn_angle(feat, threshold=0.30, x_offset=0, y_offset=0)
                if angle is not None:
                    return angle
        return None

    def go_to_boss_minimap(self, threshold=0.45, time_out=35):
        start_time = time.time()
        current_direction = None
        current_adjust = None
        last_valid_angle = None
        consecutive_misses = 0
        self.center_camera()
        self.log_info(f'Navigating via minimap towards boss (timeout: {time_out}s)...')

        while time.time() - start_time < time_out:
            self.sleep(0.02)
            if self.in_combat(target=True) or self.in_combat():
                self.log_info('Engaged in combat! Locking on target...')
                self.middle_click(after_sleep=0.1)
                break
            if self.find_f_with_text():
                self.log_info('Found interactable prompt (F) while navigating!')
                break

            angle = self.find_boss_minimap_angle(threshold=threshold)
            if angle is not None:
                last_valid_angle = angle
                consecutive_misses = 0
            else:
                consecutive_misses += 1
                if last_valid_angle is not None and consecutive_misses < 30:
                    # Maintain heading towards boss
                    angle = last_valid_angle
                else:
                    if consecutive_misses % 20 == 0:
                        self.middle_click(after_sleep=0.1)
                    angle = None

            if angle is not None:
                current_direction, current_adjust, should_continue = self._navigate_based_on_angle(
                    angle, current_direction, current_adjust
                )
                if should_continue:
                    continue
            else:
                # If marker temporarily lost, continue forward in current heading
                if current_direction != 'w':
                    self.send_key_down('w')
                    self.mouse_down(key='right')
                    current_direction = 'w'

        self._stop_movement(current_direction, current_adjust)
        if not self.in_combat(target=True) and not self.in_combat():
            if self.teleport_to_boss_enabled():
                self.teleport_to_nearest_boss()
                self.sleep(0.5)
                self.run_until(lambda: self.in_combat(target=True) or self.in_combat() or self.find_treasure_icon(), 'w', time_out=12, running=True,
                               target=True)
            else:
                self.log_info('Current Location mode: skipping teleport, waiting for boss in place')
                self.center_camera()
                self.sleep(1)

    def find_boss_check_mark(self):
        box = self.find_best_match_in_box(self.box_of_screen(0.3, 0.3, 0.7, 0.7),
                                          ['boss_check_mark'], threshold=0.8)
        if not box:
            boss_template = self.get_feature_by_name('boss_no_check_mark')
            original_mat = boss_template.mat
            (h, w) = boss_template.mat.shape[:2]
            center = (w // 2, h // 2)
            targets = []
            for angle in range(0, 270, 90):
                # Rotate the template image
                rotation_matrix = cv2.getRotationMatrix2D(center, -angle, 1.0)
                template = cv2.warpAffine(original_mat, rotation_matrix, (w, h))
                boxes = self.find_feature(box=self.box_of_screen(0.3, 0.3, 0.7, 0.7), template=template, threshold=0.7)
                targets.extend(boxes)
                box = max(targets, key=lambda box: box.confidence, default=None)
            if box is None:
                raise Exception("boss not found")
        return box

    def teleport_to_nearest_boss(self):
        if not self.teleport_to_boss_enabled():
            self.log_info('Current Location mode: skipping teleport, remaining at current position')
            return
        if self.aim_boss is not None:
            self.log_info(f'teleport_to_nearest_boss {self.aim_boss}')
            self.ensure_main(time_out=180)
            self.openF2Book("gray_book_all_monsters")
            self.click(0.13, 0.14, after_sleep=0.5)
            self.input_text(self.aim_boss)
            self.click(0.39, 0.13, after_sleep=0.5)
            self.click(0.13, 0.24, after_sleep=0.5)
            self.click(0.89, 0.92, after_sleep=1)
            self.click(0.89, 0.92)
            self.wait_in_team_and_world(time_out=30, raise_if_not_found=False)
            return

        target_name, profile = self.get_selected_boss_profile()
        if profile.get('category') == 'weekly':
            self.teleport_to_configured_boss()
            return

        try:
            self.send_key('m', after_sleep=2)
            boss = self.config.get('Boss')
            if boss == 'Nameless Explorer':
                self.click(0.06, 0.50, after_sleep=0.5)

            box = self.find_boss_check_mark()
            self.log_info(f'teleport_to_nearest_boss {box}')
            if box:
                self.click_box(box)
                if self.wait_until(self.click_traval_button, raise_if_not_found=False, time_out=6):
                    self.wait_in_team_and_world(time_out=30, raise_if_not_found=False)
        except Exception as e:
            self.log_warning(f'teleport_to_nearest_boss fallback failed: {e}')
        finally:
            self.ensure_main(time_out=5)

    def click_boss_octagon(self):
        # === 1. Read image ===
        img = self.box_of_screen(0.3, 0.3, 0.7, 0.7).crop_frame(self.frame)

        # === 2. Extract white border ===
        lower_white, upper_white = color_range_to_bound(white_color)
        mask = cv2.inRange(img, lower_white, upper_white)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))

        # Find contours
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Generate ideal trapezoid contour for shape comparison
        h, w = self.frame.shape[:2]

        # Scale ratio
        scale_x = w / 2560
        scale_y = h / 1440

        # Original trapezoid contour
        trapezoid = np.array([
            [35, 0], [0, 35], [92, 36], [56, 0]
        ], np.int32).reshape((-1, 1, 2))

        # Scale proportionally
        trapezoid_scaled = np.zeros_like(trapezoid, dtype=np.int32)
        trapezoid_scaled[:, 0, 0] = (trapezoid[:, 0, 0] * scale_x).astype(np.int32)
        trapezoid_scaled[:, 0, 1] = (trapezoid[:, 0, 1] * scale_y).astype(np.int32)

        # Define match threshold
        best_match = None
        best_ratio = 0
        trapezoid_area = cv2.contourArea(trapezoid_scaled)
        if trapezoid_area <= 0:
            raise RuntimeError('Invalid scaled trapezoid template for boss octagon search')
        trapezoid_f32 = trapezoid_scaled.astype(np.float32)

        for cnt in contours:
            cnt = cv2.convexHull(cnt)
            cnt_f32 = cnt.astype(np.float32)
            x, y, _, _ = cv2.boundingRect(cnt)
            for dx in range(-10, 11, 2):
                for dy in range(-10, 11, 2):
                    shifted = trapezoid_f32 + np.float32([x + dx, y + dy])
                    area_i, _ = cv2.intersectConvexConvex(cnt_f32, shifted)
                    ratio = area_i / trapezoid_area
                    if ratio > best_ratio:
                        best_ratio = ratio
                        best_match = cnt

        # Click contour center
        if best_match is None:
            raise RuntimeError('Can not find the boss octagon on map')

        x0, y0 = self.width_of_screen(0.3), self.height_of_screen(0.3)
        x, y, w, h = cv2.boundingRect(best_match)
        cx = x0 + x + w // 2
        cy = y0 + y + h // 2
        self.click(cx, cy, after_sleep=1)

    def teleport_to_octagon_boss(self):
        """Teleport to octagon Boss icon."""
        self.log_info('click m to open the map')
        self.send_key('m', after_sleep=2)

        self.click_boss_octagon()
        travel = self.wait_feature('gray_teleport', raise_if_not_found=True, time_out=3)
        if not travel:
            pop_up = self.find_feature('map_way_point', box='map_way_point_pop_up_box')
            if pop_up:
                self.click(pop_up, after_sleep=1)
                travel = self.wait_feature('gray_teleport', raise_if_not_found=True, time_out=3)
        if not travel:
            raise RuntimeError('Can not find the travel button')
        self.click_box(travel, relative_x=1.5)
        self.wait_in_team_and_world(time_out=20)
        self.sleep(2)

    def scroll_and_click_buttons(self):
        self.sleep(0.2)
        start = time.time()
        if rechallenge := self.find_one('challenge_again', threshold=0.65):
            self.click_box(rechallenge, after_sleep=0.8)
            self._confirm_rechallenge_popup()
            return
        if self._has_treasure and not self.find_f_with_text():
            self.scroll_relative(0.5, 0.5, 1)
            self.sleep(0.2)
        while self.find_f_with_text() and not self.in_combat() and time.time() - start < 5:
            self.log_info('scroll_and_click_buttons')
            if rechallenge := self.find_one('challenge_again', threshold=0.65):
                self.click_box(rechallenge, after_sleep=0.8)
                self._confirm_rechallenge_popup()
                return
            self.scroll_relative(0.5, 0.5, 1)
            self.sleep(0.2)
            self.send_key('f')
            if self.handle_claim_button():
                self._has_treasure = True

    def restart_realm_challenge(self):
        """Attempts to restart the weekly boss realm challenge from within the domain."""
        self.log_info('Attempting realm rechallenge from within domain...')

        # 1. Approach the reward sphere if present and not yet in interaction range
        if not self.find_f_with_text() and not self.find_one('challenge_again', threshold=0.65):
            if self.find_treasure_icon():
                self.log_info('Approaching Sonance Sphere for rechallenge...')
                self.walk_to_treasure_and_restart()
                self.sleep(0.5)

        # 2. Check if challenge_again template is directly visible on screen
        rechallenge = self.find_one('challenge_again', threshold=0.65)
        if rechallenge:
            self.log_info(f'Found challenge_again template button: {rechallenge}')
            self.click_box(rechallenge, after_sleep=0.8)
            self._confirm_rechallenge_popup()
            return self._wait_realm_reset()

        # 3. If F prompt is present, interact and select Rechallenge
        if self.find_f_with_text():
            self.log_info('Interacting with domain sphere (scroll to Challenge Again)...')
            self.scroll_relative(0.67, 0.55, -2)
            self.sleep(0.3)
            rechallenge = self.find_one('challenge_again', threshold=0.65)
            if rechallenge:
                self.click_box(rechallenge, after_sleep=0.8)
            else:
                self.send_key('f', after_sleep=0.8)
            self._confirm_rechallenge_popup()
            return self._wait_realm_reset()

        # 4. Try standard claim handling if open
        if self.handle_claim_button():
            self.sleep(0.5)
            rechallenge = self.find_one('challenge_again', threshold=0.65)
            if rechallenge:
                self.click_box(rechallenge, after_sleep=0.8)
                self._confirm_rechallenge_popup()
                return self._wait_realm_reset()

        return False

    def _confirm_rechallenge_popup(self):
        """Confirms the domain rechallenge confirmation modal if present."""
        self.sleep(0.5)
        confirm = self.wait_feature(
            ['confirm_btn_hcenter_vcenter', 'confirm_btn_highlight_hcenter_vcenter'],
            time_out=2.5, raise_if_not_found=False
        )
        if confirm:
            self.click(confirm, after_sleep=1.0)
            return True
        texts = self.ocr(log=self.debug)
        confirm_boxes = self.find_boxes(texts, boundary='bottom_right', match=['确认', 'Confirm', 'Restart'])
        if confirm_boxes:
            self.click(confirm_boxes[0], after_sleep=1.0)
            return True
        return False

    def _wait_realm_reset(self):
        """Waits for the domain realm to reload/reset after rechallenging."""
        self.log_info('Waiting for realm reload/reset...')
        self.sleep(1.0)
        in_team = self.wait_in_team_and_world(time_out=60, raise_if_not_found=False)
        if in_team:
            self._in_realm = True
            self._just_entered_boss_realm = True
            self._has_treasure = False
            self.log_info('Realm rechallenge successful, ready for combat!')
            return True
        return False

    def reenter_realm_from_outside(self, target_name=None, profile=None):
        """Fallback: exits domain realm to overworld, then re-enters domain via portal."""
        self.log_info('Exiting realm to overworld...')
        self.send_key('esc', after_sleep=0.8)
        self.wait_click_feature('claim_cancel_button_hcenter_vcenter', relative_x=2,
                                raise_if_not_found=False, time_out=3,
                                post_action=lambda: self.send_key('esc', after_sleep=1),
                                settle_time=1)
        self.wait_in_team_and_world(time_out=120)
        self.sleep(1.5)
        if self.wait_until(self.find_f_with_text, time_out=6, raise_if_not_found=False):
            self.enter_configured_boss_realm_from_f()
        else:
            self.teleport_to_configured_boss_and_prepare(target_name, profile)

    def walk_to_treasure_and_restart(self):
        if self.find_treasure_icon():
            self.walk_to_box(self.find_treasure_icon, end_condition=self.find_f_with_text, y_offset=0.1)
            return True

    def choose_level(self, start):
        y = 0.17
        x = 0.15
        distance = 0.08

        logger.info(f'choose level {start}')
        self.click_relative(x, y + (start - 1) * distance)
        self.sleep(0.5)

        self.wait_click_feature('gray_button_challenge', raise_if_not_found=True,
                                click_after_delay=0.5)
        self.wait_click_feature('gray_confirm_exit_button', relative_x=-1, raise_if_not_found=False,
                                time_out=3, click_after_delay=0.5, threshold=0.8)
        self.wait_click_feature('gray_start_battle', relative_x=-1, raise_if_not_found=True,
                                click_after_delay=0.5, threshold=0.8)

    def check_boss_name(self):
        # self.combat_wait_time = self.config.get("Combat Wait Time", 0)
        # self.set_night = self.config.get('Change Time to Night')
        if self.game_lang != 'zh_CN':
            return
        texts = self.ocr(box=self.box_of_screen(1269 / 3840, 10 / 2160, 2533 / 3840, 140 / 2160, hcenter=True),
                         target_height=540, name='boss_lv_text')
        for key, value in self.boss_dict.items():
            s = value.get('name')
            fps_text = find_boxes_by_name(texts, re.compile(s, re.IGNORECASE))
            if fps_text:
                self.aim_boss = key
                # if value.get('set_combat_wait'):
                #     self.combat_wait_time = value.get('set_combat_wait')
                # if value.get('set_night'):
                #     self.set_night = True
                break
        if self.aim_boss is not None:
            logger.info(f'combat with {self.aim_boss}')
        else:
            logger.info(f"boss_string is {find_boxes_by_name(texts, [re.compile(r'(?i)^L[Vv].*')])}")


from ok import run_task
from config import config

if __name__ == "__main__":
    run_task(config, task=FarmEchoTask, debug=True)
