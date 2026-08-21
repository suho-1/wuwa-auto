from src.char.BaseChar import BaseChar


class Mortefi(BaseChar):
    def do_perform(self):
        self.wait_down()
        # Cast skill and echo to build energy, then liberation for coordinated attacks
        self.click_resonance()
        self.click_echo()
        self.click_liberation(wait_if_cd_ready=0.5)
        self.switch_next_char()
