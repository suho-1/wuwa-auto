import time

from src.char.BaseChar import BaseChar


class Xiangliyao(BaseChar):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.liberation_time = 0

    def do_perform(self):
        self.wait_down()
        if self.click_liberation():
            self.liberation_time = time.time()
        if self.still_in_liberation():
            start = time.time()
            while self.still_in_liberation() and time.time() - start < 25:
                # Liberation state combo: Normal attack -> Resonance skill -> Jump mid-air attack
                self.continues_normal_attack(0.8)
                if self.click_resonance(send_click=True)[0]:
                    self.task.jump(after_sleep=0.1)  # Jump to build Performance Capacity
                    self.continues_normal_attack(0.5)  # Mid-air attack
                if self.is_con_full():
                    break
                self.check_combat()
                self.task.next_frame()
        elif self.echo_available():
            self.logger.debug('click_echo')
            self.click_echo()
        else:
            self.click_resonance(send_click=True)
        self.switch_next_char()

    def still_in_liberation(self):
        return self.time_elapsed_accounting_for_freeze(self.liberation_time) < 25
