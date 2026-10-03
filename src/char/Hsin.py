import time

from src.char.BaseChar import BaseChar


class Hsin(BaseChar):
    """Hsin auto combat - 5-star Electro Rectifier main DPS.

    Rotation transcribed from Rexlent's "How to Hsin for Dummies"
    (https://www.youtube.com/watch?v=-JiixPs82UI, playlist PLT669jfZO0z9sA1RCWuQfIpufrIkI3s3f).
    The structured source of truth lives in ``training/char_guides/hsin.json``.

    Hsin has two player-selected resonance modes and they do NOT share a
    rotation, so the mode is exposed as the ``Hsin Unison Mode`` character
    config flag.

    Electro Flare (video 3:58, default)::

        intro -> basic x1 -> enhanced heavy -> echo -> Liberation #1
              -> basic/E/basic/E (fills the second bar)
              -> enhanced E -> basic x4 (opens the locks)
              -> enhanced heavy -> Liberation #2 (big) -> switch

    Unison (video 4:39) splits across two visits, because after the first
    Liberation she holds Unison for ~5s and must outro inside that window to
    fire the Unison Response. Coming back she skips the filler entirely::

        visit 1: intro -> basic x2 -> enhanced heavy -> echo -> Liberation #1 -> outro
        visit 2: intro -> basic x4 -> enhanced heavy -> Liberation #2 (big) -> switch

    Team order for Unison is 1-2-3-2-3-1, e.g. Shorekeeper, Jinhsi, Hsin.

    Both of her gates are generic ok-ww detections rather than Hsin-specific
    templates, which is why this needs no new annotations:

    * ``mouse_forte`` - "the basic attack is glowing" (video 2:26), the cue for
      either enhanced heavy attack.
    * ``e_forte`` - "your E skill is shining" (video 3:31), the cue for the
      enhanced Resonance Skill.
    """

    UNISON_CONFIG_KEY = 'Hsin Unison Mode'

    # Whole-rotation budget for the single-visit Electro Flare rotation.
    FIELD_TIME_OUT: float = 16.0

    # Her combo must be tapped - holding turns it into the heavy attack.
    BASIC_ATTACK_INTERVAL: float = 0.22
    # How long to wait for a forte gauge cue before giving up on that phase.
    FORTE_CUE_TIME_OUT: float = 2.0

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.unison_visit = 0

    # ------------------------------------------------------------------ #
    # mode / state
    # ------------------------------------------------------------------ #

    def is_unison_mode(self) -> bool:
        """True when the player set Hsin's in-game resonance mode to Unison."""
        char_config = getattr(self.task, 'char_config', None)
        if not char_config:
            return False
        return bool(char_config.get(self.UNISON_CONFIG_KEY))

    def reset_state(self):
        super().reset_state()
        self.unison_visit = 0

    def on_combat_end(self, chars):
        self.unison_visit = 0
        super().on_combat_end(chars)

    # ------------------------------------------------------------------ #
    # building blocks
    # ------------------------------------------------------------------ #

    def normal_attack_chain(self, count: int, interval: float = None):
        """Tap the basic attack ``count`` times.

        The guide is explicit that the combo is tapped, never held, because
        holding converts it into her heavy attack.
        """
        interval = self.BASIC_ATTACK_INTERVAL if interval is None else interval
        for i in range(count):
            self.check_combat()
            self.click()
            if i < count - 1:
                self.sleep(interval)

    def perform_enhanced_heavy(self, wait: float = None) -> bool:
        """Hold basic attack once the gauge glows, spending the forte bar."""
        wait = self.FORTE_CUE_TIME_OUT if wait is None else wait
        if not self.is_mouse_forte_full():
            if not self.task.wait_until(self.is_mouse_forte_full,
                                        post_action=self.click, time_out=wait):
                self.logger.debug('Hsin enhanced heavy skipped: forte not full')
                return False
        if self.flying():
            self.wait_down()
        performed = bool(self.heavy_click_forte(check_fun=self.is_mouse_forte_full))
        self.logger.debug(f'Hsin enhanced heavy performed={performed}')
        return performed

    def perform_enhanced_e(self, wait: float = None) -> bool:
        """Cast the enhanced Resonance Skill once the E icon shines."""
        wait = self.FORTE_CUE_TIME_OUT if wait is None else wait
        if not self.is_e_forte_full():
            if not self.task.wait_until(self.is_e_forte_full,
                                        post_action=self.click, time_out=wait):
                self.logger.debug('Hsin enhanced E skipped: second bar not full')
                return False
        clicked = self.click_resonance(time_out=1.5)[0]
        self.logger.debug(f'Hsin enhanced E clicked={clicked}')
        return clicked

    def fill_second_bar(self, max_cycles: int = 3) -> bool:
        """Alternate one basic and one Resonance Skill to charge the second bar.

        Per the guide this pairing fills the bar "straight away", which is why
        it beats spamming basic attacks.
        """
        for _ in range(max_cycles):
            if self.is_e_forte_full():
                return True
            self.normal_attack_chain(1)
            if self.is_e_forte_full():
                return True
            if self.resonance_available():
                self.click_resonance(time_out=0.8)
            self.task.next_frame()
        return bool(self.is_e_forte_full())

    def cast_liberation(self) -> bool:
        return self.click_liberation(wait_if_cd_ready=0.2)

    # ------------------------------------------------------------------ #
    # rotations
    # ------------------------------------------------------------------ #

    def do_perform(self):
        if self.is_unison_mode():
            return self.do_unison_perform()
        return self.do_electro_flare_perform()

    def do_electro_flare_perform(self):
        self.wait_intro()
        if self.flying():
            self.wait_down()
        start = time.time()

        def out_of_time() -> bool:
            return self.time_elapsed_accounting_for_freeze(start) > self.FIELD_TIME_OUT

        # Opener: one basic into the first enhanced heavy, echo, first Liberation.
        self.normal_attack_chain(1)
        self.perform_enhanced_heavy()
        self.click_echo(time_out=0)
        self.cast_liberation()

        if out_of_time():
            return self.switch_next_char()

        # Filler: basic / E / basic / E charges the second bar, then enhanced E.
        self.fill_second_bar()
        self.perform_enhanced_e()

        # Finisher: four taps open the locks, hold for the last enhanced heavy,
        # then the big Liberation.
        self.finish_rotation()
        return self.switch_next_char()

    def do_unison_perform(self):
        if self.unison_visit == 0:
            self.unison_visit = 1
            return self.perform_unison_opener()
        self.unison_visit = 0
        return self.perform_unison_finisher()

    def perform_unison_opener(self):
        """Visit 1: build to the first Liberation and leave inside the Unison window."""
        self.wait_intro()
        if self.flying():
            self.wait_down()
        start = time.time()

        # One EXTRA basic compared to Electro Flare.
        self.normal_attack_chain(2)
        self.perform_enhanced_heavy()
        self.click_echo(time_out=0)
        self.cast_liberation()

        elapsed = self.time_elapsed_accounting_for_freeze(start)
        self.logger.debug(f'Hsin unison opener done in {elapsed:.2f}s, outro for unison response')
        # Leave immediately: the Unison Response window is only ~5s.
        return self.switch_next_char()

    def perform_unison_finisher(self):
        """Visit 2: Manifold Unison intro, skip the filler, straight to the finisher."""
        self.wait_intro()
        if self.flying():
            self.wait_down()
        self.finish_rotation()
        return self.switch_next_char()

    def finish_rotation(self):
        """Four taps to open the locks, final enhanced heavy, big Liberation.

        The four basic attacks unlock the gauge during the 14s final window, so
        this block is deliberately short and unconditional.
        """
        self.normal_attack_chain(4)
        self.perform_enhanced_heavy()
        self.cast_liberation()
        # Opportunistic: spend the echo before leaving if it came back up.
        self.click_echo(time_out=0)
