import time

from src.char.BaseChar import BaseChar, SwitchPriority


class Jiyan(BaseChar):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.liberation_time = 0

    def still_in_liberation(self):
        return self.time_elapsed_accounting_for_freeze(self.liberation_time) < 10

    def do_perform(self):
        if self.has_intro:
            self.logger.debug('jiyan wait intro')
            self.continues_normal_attack(duration=1.5)
        if self.click_liberation():
            self.liberation_time = time.time()
            start = time.time()
            while self.time_elapsed_accounting_for_freeze(start) < 12:
                # Qingloong mode: Heavy attacks are primary DPS, weave in resonance skills
                if self.click_resonance(send_click=False, time_out=0.3)[0]:
                    self.task.middle_click_relative(0.5, 0.5)
                self.heavy_attack(duration=1.0)  # Qingloong heavy attack lance thrusts
                if self.is_con_full():
                    break
                self.check_combat()
            return self.switch_next_char()
        i = 0
        while not self.is_forte_full() and not self.is_con_full():
            if i % 4 == 0:
                self.heavy_attack()
                if self.resonance_available() or self.echo_available():
                    self.task.middle_click_relative(0.5, 0.5)
                    break
                i = 0
            self.normal_attack()
            i += 1
        if not self.is_forte_full() and self.resonance_available():
            self.click_resonance(post_sleep=1.0)
        if self.echo_available():
            self.click_echo()
        self.switch_next_char()

    def get_switch_priority(self, current_char=None, has_intro=False, target_low_con=False):
        if self.still_in_liberation():
            return SwitchPriority.MUST
        return super().get_switch_priority(current_char, has_intro, target_low_con)
