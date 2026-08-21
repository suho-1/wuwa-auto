import time
from src.char.BaseChar import BaseChar, SwitchPriority


class Calcharo(BaseChar):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.liberation_time = 0

    def still_in_liberation(self):
        return self.time_elapsed_accounting_for_freeze(self.liberation_time) < 10

    def do_perform(self):
        if self.has_intro:
            self.continues_normal_attack(1.0)  # Normal attack chain after intro
        self.click_echo(time_out=0)
        if self.click_liberation(wait_if_cd_ready=0.3):
            self.liberation_time = time.time()
            # Resonance Liberation state: 5-hit normal attack + Heavy attack loop (Death Messenger)
            start = time.time()
            while self.time_elapsed_accounting_for_freeze(start) < 10:
                self.click_resonance(send_click=False, time_out=0.3)
                self.continues_normal_attack(1.8)  # 5-hit normal attack string
                self.heavy_attack(0.6)  # Death Messenger heavy attack
                if self.is_con_full():
                    break
                self.check_combat()
            return self.switch_next_char()
        if self.click_resonance()[0]:
            self.continues_normal_attack(0.5)
        if self.is_forte_full():
            self.heavy_click_forte()
        self.switch_next_char()

    def get_switch_priority(self, current_char=None, has_intro=False, target_low_con=False):
        if self.still_in_liberation():
            return SwitchPriority.MUST
        return super().get_switch_priority(current_char, has_intro, target_low_con)
