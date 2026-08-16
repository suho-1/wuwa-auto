import cv2

from ok import Logger, find_color_rectangles
from src.task.DomainTask import DomainTask
from src.task.BaseWWTask import AreaLockedException

logger = Logger.get_logger(__name__)


FORGERY_CHALLENGES = [
    '1 - Misty Coast: Sword & Broadblade (Metallic Drip)',
    '2 - Port City Guixu: Pistols (Phlogiston)',
    '3 - Qichi Village: Rectifier (Helix)',
    '4 - Dim Forest: Gauntlets (Cadence)',
    '5 - Mt. Firmament: Broadblade & Sword (Monumental Wave)',
    '6 - Black Shores: Pistols & Rectifier (Abyssal Core)',
]


class ForgeryTask(DomainTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = '⚒️ Forgery Challenge'
        self.description = 'Farms the selected Forgery Challenge. Must be able to teleport (F2).'
        self.support_schedule_task = True
        self.default_config = {
            'Which Forgery Challenge to Farm': FORGERY_CHALLENGES[0],
            'Skip Locked Challenges': True,
        }
        self.config_description = {
            'Which Forgery Challenge to Farm': 'Select the Forgery Challenge by target weapon type and ascension material.',
            'Skip Locked Challenges': 'Automatically try other Forgery Challenges if the selected domain is in a locked area.',
        }
        self.config_type['Which Forgery Challenge to Farm'] = {
            'type': 'drop_down',
            'options': FORGERY_CHALLENGES,
        }
        self.config_type['Skip Locked Challenges'] = {
            'type': 'check_box',
        }
        self.stamina_once = 40
        self.structure = [5, 5, 5, 5]
        self.total_number = sum(self.structure)
        self.material_mat = None

    def run(self):
        super().run()
        self.make_sure_in_world()
        try:
            self.farm_forgery()
        except AreaLockedException as e:
            self.log_warning(f"Selected Forgery Challenge is in a locked area: {e}. Please unlock the area or select another domain.")
            self.ensure_main(time_out=10)
            return

    def farm_forgery(self, daily=False, used_stamina=0, config=None):
        if daily:
            must_use = 180 - used_stamina
        else:
            must_use = 0
        if config is None:
            config = self.config
        target_val = config.get('Which Forgery Challenge to Farm', 1)
        if isinstance(target_val, str) and '-' in target_val:
            try:
                serial = int(target_val.split('-')[0].strip())
            except Exception:
                serial = 1
        elif isinstance(target_val, int):
            serial = target_val
        else:
            serial = 1

        skip_locked = config.get('Skip Locked Challenges', config.get('Skip Locked Areas', True))
        candidates = [serial]
        if skip_locked:
            candidates += [i for i in range(1, len(FORGERY_CHALLENGES) + 1) if i != serial]

        teleported = False
        for cand_serial in candidates:
            try:
                def teleport_once():
                    self.teleport_into_domain(cand_serial, daily)
                self.farm_domain_with_recovery_loop(must_use, teleport_once)
                teleported = True
                if cand_serial != serial:
                    self.log_info(f"Farmed alternative Forgery Challenge #{cand_serial} because #{serial} was locked.")
                break
            except AreaLockedException as e:
                self.log_warning(f"Forgery Challenge #{cand_serial} is in a locked area: {e}.")
                if not skip_locked:
                    raise
                self.ensure_main(time_out=10)

        if not teleported:
            raise AreaLockedException("All candidate Forgery Challenges are in locked areas.")

    def purification_material(self):
        self.send_key("esc")
        self.sleep(1)
        self.click_relative(0.62, 0.7)
        self.sleep(1)
        box = self.box_of_screen(243 / 2560, 162 / 1440, 928 / 2560, 559 / 1440, name='ascension_materials')
        self.draw_boxes(box.name, box)
        self.wait_book()
        if self.material_mat is not None and \
            (target := self.wait_until(lambda: self.find_one(template=self.material_mat, box=box, threshold=0.7), time_out=1)):
            self.click_box(target, after_sleep=1)
        self.click_relative(0.75, 0.90, after_sleep=1)
        self.ensure_main()

    def teleport_into_domain(self, serial_number, daily=False):
        self.open_boss_book('ningsu')
        self.info_set('Teleport to Forgery Challenge', serial_number - 1)
        if serial_number > self.total_number:
            raise IndexError(f'Index out of range, max is {self.total_number}')
        self.click_on_book_target(serial_number, self.total_number, self.structure)
        self.click(0.891, 0.910, after_sleep=1)
        self.click_team_challenge()
        self.wait_in_team_and_world(time_out=self.teleport_timeout)

    def get_material_mat(self):
        min_width = self.width_of_screen(80 / 2560)
        min_height = self.height_of_screen(80 / 1440)
        box = self.box_of_screen(2205 / 2560, 566 / 1440, 2357 / 2560, 984 / 1440)
        self.draw_boxes(box.name, box)
        material_boxes = find_color_rectangles(self.frame, material_box_color, min_width, min_height,
                                               box=box, threshold=0.6)
        if material_boxes:
            box_start = self.width_of_screen(20 / 2560)
            box_len = self.width_of_screen(90 / 2560)
            target = min(material_boxes, key=lambda box: box.y)
            logger.info(f"Found {len(material_boxes)} material boxes, selected target at y={target.y}")
            mat_box = target.copy(box_start, box_start, box_len - target.width, box_len - target.height, 'material_mat')
            self.draw_boxes(mat_box.name, mat_box)
            self.material_mat = cv2.resize(mat_box.crop_frame(self.frame), None,
                                           fx=1.1, fy=1.1, interpolation=cv2.INTER_LINEAR)


material_box_color = {
    'r': (45, 75),  # Red range
    'g': (45, 75),  # Green range
    'b': (45, 75)  # Blue range
}
