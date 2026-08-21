import time
from src.char.BaseChar import BaseChar


class Jianxin(BaseChar):
    def do_perform(self):
        if self.has_intro:
            self.continues_normal_attack(0.6)
        # Cast resonance skill, then hold heavy attack for shield ("blender" combo)
        if self.click_resonance()[0]:
            self.sleep(0.2)
        # Hold heavy attack to activate Forte shield
        self.heavy_attack(duration=2.0)
        self.click_liberation()
        self.click_echo()
        self.switch_next_char()
