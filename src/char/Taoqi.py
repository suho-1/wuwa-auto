from src.char.BaseChar import BaseChar


class Taoqi(BaseChar):
    def do_perform(self):
        if self.has_intro:
            self.wait_down()
        # Burst rotation: 3x normal attack -> skill -> liberation -> echo
        self.continues_normal_attack(1.0)
        self.click_resonance()
        self.click_liberation()
        self.click_echo()
        if self.is_forte_full():
            self.heavy_click_forte()
        self.switch_next_char()
