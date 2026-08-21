import time

from src.char.BaseChar import BaseChar


class Danjin(BaseChar):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def do_perform(self):
        if self.has_intro:
            self.continues_normal_attack(0.6)  # Normal attack chain after intro
        # Cast resonance skills to build Forte
        if self.resonance_available():
            self.continues_click(self.get_resonance_key(), 1.2, interval=0.2)
        self.click_echo(time_out=0)
        # Resonance liberation for Havoc damage boost
        self.click_liberation()
        # Consume Forte with Heavy Attack (Chaos Cleave)
        if self.is_forte_full():
            self.heavy_attack(0.8)
            self.sleep(0.2)
        elif not self.is_con_full():
            # Build Forte with normals and skills
            start = time.time()
            while time.time() - start < 2.5:
                if self.is_forte_full():
                    self.heavy_attack(0.8)
                    break
                if self.resonance_available():
                    self.continues_click(self.get_resonance_key(), 0.8, interval=0.2)
                else:
                    self.click(interval=0.1)
                if self.is_con_full():
                    break
                self.task.next_frame()
        self.switch_next_char()
