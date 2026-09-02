from src.char.BaseChar import BaseChar


class Youhu(BaseChar):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def do_perform(self):
        if self.has_intro:
            self.continues_normal_attack(0.6)  # Normal attack chain after intro
        # Quickswap Sub-DPS loop: Skill -> Echo -> Liberation -> Heavy
        self.click_resonance()
        self.click_echo(time_out=0)
        self.click_liberation()
        if self.is_forte_full():
            self.heavy_click_forte()
        self.switch_next_char()
