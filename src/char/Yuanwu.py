from src.char.BaseChar import BaseChar


class Yuanwu(BaseChar):
    def do_perform(self):
        if self.has_intro:
            self.continues_normal_attack(0.2)
        # Fast quickswap: Deploy Thunder Wedge -> Bell-Borne Echo -> Instant swap
        self.click_resonance()
        self.click_echo(time_out=0)
        self.switch_next_char()
