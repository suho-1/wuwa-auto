import time

from src.char.BaseChar import BaseChar, SwitchPriority


class Lucilla(BaseChar):
    """Lucilla auto combat: Forte charge + Liberation transformation character.

    Mechanic: Hold E or charged heavy builds 1 Forte bar, full at 3 bars for liberation; transform into special mode
    (skill bar/liberation icons disappear), output for fixed duration then switch.
    """
    HOLD_TIME: float = 1.4
    LIBERATION_ANIMATION_TIME: float = 3.0
    LIBERATION_HEAVY_TIME: float = 15.0
    HEAVY_PULSE_TIME: float = 0.6
    CHARGE_TIME_OUT: float = 7.2
    LIBERATION_CD_SKIP: float = 1.5
    SWITCH_IN_SETTLE: float = 0.5

    def do_perform(self):
        if not self.perform_combat():
            self.switch_next_char()

    def perform_combat(self):
        """Build energy -> cast liberation if available then attack.

        Returns:
            bool: Returns True if liberation cast (and switched inside try_liberation), else False.
        """
        start = time.time()

        self.task.wait_until(lambda: self.task.in_team()[0], time_out=0.8)
        self.sleep(self.SWITCH_IN_SETTLE, check_combat=False)  # Wait for skill bar to stabilize before checking liberation
        self.task.next_frame()

        if self.try_liberation():
            return True

        while time.time() - start < self.CHARGE_TIME_OUT:
            # If energy is full but liberation is not castable, switch
            if self.energy_full() and not self.liberation_available():
                self.logger.info('Lucilla energy full but liberation not castable, switch')
                break

            # If liberation on cooldown, switch to save field time
            if not self.liberation_available() and self.task.get_cd('liberation') > self.LIBERATION_CD_SKIP:
                self.logger.info('Lucilla liberation on long cd, switch to save time')
                break    

            if self.try_liberation():
                return True

            self.charge_once()

        return False

    def charge_once(self):
        """Charge once: Hold resonance skill or heavy attack."""
        if self.resonance_available():
            self.hold_resonance(self.HOLD_TIME)
        else:
            self.heavy_attack(self.HOLD_TIME)
        self.task.next_frame()

    def try_liberation(self):
        """Try casting liberation and echo if available."""
        if not self.liberation_available():
            return False

        if self.echo_available():
            self.click_echo(time_out=0)
            
        self.perform_liberation()
        self.switch_next_char()
        return True

    def energy_full(self):
        """Check if liberation energy is full."""
        return self.available('liberation', check_color=True, check_cd=False)

    def perform_liberation(self):
        """Cast liberation and start pulse heavy attack loop."""
        if not self.task.use_liberation:
            return

        start = time.time()
        while self.liberation_available() and time.time() - start < 1.5:
            self.send_liberation_key()
            self.sleep(0.1, check_combat=False)
        self.record_liberation_use()
        self.logger.info('Lucilla perform lib')

        self.sleep(self.LIBERATION_ANIMATION_TIME, check_combat=False)
        
        self.pulse_heavy_attack(self.LIBERATION_HEAVY_TIME)
        self.logger.info('Lucilla perform lib end')

    def pulse_heavy_attack(self, total_time):
        """Pulse heavy attacks during transformation state."""
        end = time.time() + total_time
        seen_active = False
        while time.time() < end:
            self.task.mouse_down()
            try:
                self.sleep(min(self.HEAVY_PULSE_TIME, end - time.time()), check_combat=False)
            finally:
                self.task.mouse_up()
            
            con = self.task.get_current_con()
            if con > 0.1:
                seen_active = True
            elif seen_active and con < 0.05:
                self.logger.info('Lucilla transform ended, stop pulse heavy early')
                break
                
            self.sleep(0.02, check_combat=False) 

    def hold_resonance(self, duration):
        """Hold resonance skill for specified duration."""
        self.task.send_key_down(self.get_resonance_key())
        try:
            self.sleep(duration, check_combat=False)
        finally:
            self.task.send_key_up(self.get_resonance_key())
        self.record_resonance_use()

    def get_switch_priority(self, current_char=None, has_intro=False, target_low_con=False):
        if has_intro and current_char and current_char.char_name in {'char_verina', 'char_shorekeeper'}:
            return SwitchPriority.MUST
        return super().get_switch_priority(current_char, has_intro, target_low_con)