from src.char.BaseChar import BaseChar


class Yinlin(BaseChar):
    def do_perform(self):
        if self.has_intro:
            self.sleep(0.4)
        # Cast resonance skill to build Judgement Points, then liberation, skill follow-up, and heavy attack
        self.click_resonance(send_click=False)
        self.click_liberation()
        if self.click_resonance(send_click=False)[0]:
            self.sleep(0.1)
        if self.is_mouse_forte_full():
            self.heavy_attack()
            self.sleep(0.4)
        elif self.echo_available():
            self.click_echo()
        else:
            self.heavy_attack()
        self.switch_next_char()
