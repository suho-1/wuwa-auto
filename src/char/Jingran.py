import time

from src.char.BaseChar import BaseChar


class Jingran(BaseChar):
    """Jingran auto combat (5-star Fusion Broadblade, Main DPS — Prydwen ToA T0).

    Kit summary (prydwen.gg/wuthering-waves/characters/jingran):
    - Builds Qi with Basic Attack stages 3/4 (+50), Dodge Counters (+100)
      and mid-air Resonance Skills (+100).
    - At 300 Qi, holding Normal Attack casts Heavy Attack - Soul Raid /
      Stardome Meander, swapping between Yin Vessel and Yang Font states.
    - Liberation (Burial of Thousand Souls) grants 200 Qi, 3 Wayfarer's
      Marks and the Yinghuo state, during which Heavy Attacks summon
      Chimei Wangliang follow-up hits.

    The loop therefore prioritizes: Liberation -> Heavy when forte (Qi) is
    charged -> Resonance Skill -> normal attacks as Qi filler, bounded by
    concerto fill and a field timeout.
    """

    FIELD_TIME_OUT: float = 12.0
    HEAVY_ATTACK_TIME: float = 0.9
    NORMAL_ATTACK_TIME: float = 0.8

    def do_perform(self):
        self.wait_intro()
        start = time.time()
        self.click_liberation()
        self.click_echo(time_out=0)
        while self.time_elapsed_accounting_for_freeze(start) < self.FIELD_TIME_OUT:
            self.check_combat()
            if self.is_con_full():
                break
            if self.is_mouse_forte_full():
                # 300 Qi charged: Soul Raid / Stardome Meander (also swaps state,
                # and triggers Chimei Wangliang during Yinghuo).
                self.heavy_attack(self.HEAVY_ATTACK_TIME)
            elif self.liberation_available():
                self.click_liberation()
            elif self.resonance_available():
                self.click_resonance(time_out=0.5)
            else:
                # Basic Attack stages 3/4 restore Qi.
                self.continues_normal_attack(self.NORMAL_ATTACK_TIME)
            self.task.next_frame()
        self.switch_next_char()
