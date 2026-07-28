from src.char.BaseChar import BaseChar


class Baizhi(BaseChar):

    def do_perform(self):
        if self.has_intro:
            self.logger.debug('has_intro wait click 1.2 sec')
            self.continues_normal_attack(1.2, click_resonance_if_ready_and_return=True)
        self.click_resonance()
        self.click_echo()
        self.click_liberation(con_less_than=1)
        if self.is_forte_full():
            self.heavy_click_forte()
        self.switch_next_char()
