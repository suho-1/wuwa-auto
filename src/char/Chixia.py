import time
from src.char.BaseChar import BaseChar


class Chixia(BaseChar):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def do_perform(self):
        if self.has_intro:
            self.continues_normal_attack(0.8)  # Normal attack chain after intro
        self.click_echo(time_out=0)
        # Resonance skill: Enter DAKA DAKA rapid fire mode
        if self.resonance_available():
            self.send_resonance_key()
            self.sleep(0.2)
            # Hold resonance skill to fire bullets
            start = time.time()
            while time.time() - start < 3.0:
                self.send_resonance_key(interval=0.1)
                if self.is_forte_full():
                    break
                self.task.next_frame()
            self.sleep(0.1)
        if self.is_forte_full():
            self.heavy_click_forte()
        # Cast resonance liberation as finisher
        self.click_liberation()
        self.switch_next_char()
