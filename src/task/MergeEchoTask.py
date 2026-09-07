import re

from src.Labels import Labels
from src.task.BaseWWTask import BaseWWTask

FULL_BATCH_PATTERN = re.compile(r"100\s*/\s*100")


class MergeEchoTask(BaseWWTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "♻️ Merge Discarded Echoes"
        self.description = (
            "Must have 1000 discarded Echo to Run, "
            "Merge discarded Echoes in full batches of 100."
        )
        self.notify_if_not_enough = True

    def run(self):
        self.ensure_main()
        hotkey = self.key_config.get("Bag Key", "b")
        self.send_key(hotkey)
        opened_bag = self.wait_until(
            lambda: not self.in_team_and_world(),
            time_out=5,
            raise_if_not_found=False,
        )
        if opened_bag:
            self.sleep(3)
            if self.click_dialog_left_button():
                self.sleep(2)
                self.click_relative(0.034, 0.293, after_sleep=1)
                self.click_relative(0.580, 0.911, after_sleep=4)
                self.merge_echoes()
                return

        # Fallback: Navigate to Data Bank directly from ESC menu
        self.log_info("Bag full dialog not present, navigating to Data Bank via menu...")
        self.ensure_main()
        self.sleep(0.5)
        self.send_key('esc', after_sleep=1.5)
        if self.wait_click_ocr(match=re.compile(r'(数据坞|Data Bank)'), box="right", raise_if_not_found=False, settle_time=0.2):
            self.sleep(1)
            self.click_relative(0.04, 0.56, after_sleep=0.5)
            self.wait_click_ocr(match=re.compile(r'(批量融合|Batch Merge|融合|Merge)'), box="bottom_right", raise_if_not_found=False, settle_time=0.2, after_sleep=1)
            self.merge_echoes()
        else:
            if self.notify_if_not_enough:
                self.log_error(
                    "Could not open merge screen (need 1000 discarded Echo or Data Bank unlocked)",
                    notify=True,
                )
            self.ensure_main()

    def merge_echoes(self):
        self.open_merge_page()
        while self.merge_full_batch():
            pass

        self.ensure_main()

    def open_merge_page(self):
        self.click_relative(0.602, 0.124, after_sleep=0.5, hcenter=True)
        self.click_relative(0.520, 0.904, after_sleep=2, hcenter=True)
        self.click_relative(0.041, 0.918, after_sleep=1)
        self.click_relative(0.826, 0.840, after_sleep=0.5)
        self.click_relative(0.717, 0.204, after_sleep=0.5)
        self.click_relative(0.041, 0.918, after_sleep=0.5)

    def merge_full_batch(self):
        self.click_relative(0.310, 0.915, after_sleep=0.5)
        self.wait_click_feature(Labels.echo_select_all, horizontal_variance=0.3, after_sleep=1)
        full_batch = self.ocr(
            0.670,
            0.660,
            0.895,
            0.958,
            match=FULL_BATCH_PATTERN,
        )
        if not full_batch:
            self.log_info("All full batches of discarded Echoes have been merged.")
            return False

        self.click_relative(0.782, 0.910)
        self.wait_click_skip_dialog_confirm()
        self.sleep(3)
        self.click_relative(0.496, 0.972, after_sleep=1, hcenter=True)
        return True
