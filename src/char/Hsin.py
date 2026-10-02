import time

from src.char.BaseChar import BaseChar


class Hsin(BaseChar):
    """Hsin auto combat (5-star Electro Rectifier, Main DPS — Prydwen ToA T0.5).

    Kit summary (prydwen.gg/wuthering-waves/characters/hsin):
    - Dual form: Answering Form (melee strings) and Illumining Form
      (Xuanfang Mechanism commands) unlocked via Formshift.
    - Mid-air Heavy (Reign at Ease) channels Electro damage; releasing it
      performs a plunging attack.
    - Partner synergy with Rover (Electro); tags: Flare, Unison, Coord.

    Rotation here is intentionally conservative: forms are visually similar
    to the recognizer, so we run a bounded Skill -> Echo -> Liberation loop
    with normal-attack filler and heavy when the forte gauge is full.
    """

    FIELD_TIME_OUT: float = 10.0
    HEAVY_ATTACK_TIME: float = 0.7
    NORMAL_ATTACK_TIME: float = 0.7

    def do_perform(self):
        self.wait_intro()
        start = time.time()
        self.click_liberation()
        if self.resonance_available():
            self.click_resonance(time_out=0.5)
        self.click_echo(time_out=0)
        while self.time_elapsed_accounting_for_freeze(start) < self.FIELD_TIME_OUT:
            self.check_combat()
            if self.is_con_full():
                break
            if self.is_mouse_forte_full():
                self.heavy_attack(self.HEAVY_ATTACK_TIME)
            elif self.resonance_available():
                self.click_resonance(time_out=0.5)
            elif self.liberation_available():
                self.click_liberation()
            else:
                self.continues_normal_attack(self.NORMAL_ATTACK_TIME)
            self.task.next_frame()
        self.switch_next_char()
