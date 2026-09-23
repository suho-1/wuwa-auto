import time
from ok import Logger

logger = Logger.get_logger(__name__)


class ChestPlaybook:
    """Dispatches specialized interaction and puzzle-solving routines for exploration items."""

    def __init__(self, task):
        self.task = task

    def execute(self, playbook_key, details=None):
        """Executes the specific playbook action based on the key."""
        method_name = f"handle_{playbook_key}"
        handler = getattr(self, method_name, self.handle_fallback)
        self.task.log_info(f"Executing playbook: {playbook_key}")
        try:
            return handler(details)
        except Exception as e:
            self.task.log_warning(f"Playbook execution failed for {playbook_key}: {e}")
            return False

    def handle_inspect_and_open(self, details=None):
        """Standard direct chest: clear combat if guarded, then approach and interact."""
        if self.task.in_combat():
            self.task.log_info("Guards detected: engaging in combat before opening chest")
            self.task.combat_once(wait_combat_time=5, raise_if_not_found=False, target=True)
            self.task.sleep(1.0)

        # Approach and interact
        self.task.walk_until_f(time_out=4, raise_if_not_found=False)
        if self.task.find_f_with_text(['Open', 'Supply Chest', 'Investigate', 'Chest']):
            self.task.send_key('f', after_sleep=0.8)
            self.task.sleep(0.5)
            return True
        return self.task.pick_f()

    def handle_claim_tidal_heritage(self, details=None):
        """Tidal Heritage: clear combat guards if sealed, then claim."""
        if self.task.in_combat():
            self.task.log_info("Tidal Heritage guarded: clearing enemies")
            self.task.combat_once(wait_combat_time=5, raise_if_not_found=False, target=True)
            self.task.sleep(1.0)

        self.task.walk_until_f(time_out=4, raise_if_not_found=False)
        return self.task.pick_f()

    def handle_break_rock(self, details=None):
        """Breakable rock: deliver heavy attack swings to destroy obstacle, then claim chest."""
        self.task.log_info("Breaking rock obstacle with heavy attack")
        self.task.heavy_attack(duration=0.8)
        self.task.sleep(0.6)
        self.task.click(interval=0.2)
        self.task.sleep(0.8)
        self.task.walk_until_f(time_out=3, raise_if_not_found=False)
        return self.task.pick_f()

    def handle_break_three_rocks(self, details=None):
        """Three-rock puzzle: sweep area with consecutive attacks, then open revealed chest."""
        self.task.log_info("Breaking three rocks around cliffside")
        for _ in range(3):
            self.task.heavy_attack(duration=0.6)
            self.task.sleep(0.4)
            self.task.send_key('w', after_sleep=0.2)
        self.task.sleep(1.0)
        self.task.walk_until_f(time_out=4, raise_if_not_found=False)
        return self.task.pick_f()

    def handle_catch_blobfly(self, details=None):
        """Blobfly: quick lock-on and ranged attack before evasion."""
        self.task.log_info("Blobfly detected: locking on and executing quick strike")
        self.task.middle_click(after_sleep=0.1)
        self.task.click(interval=0.1)
        self.task.sleep(0.3)
        self.task.click(interval=0.1)
        self.task.sleep(0.5)
        return True

    def handle_activate_viewpoint(self, details=None):
        """Viewpoint telescope: interact to register scenic vista, then exit menu."""
        self.task.log_info("Activating scenic viewpoint telescope")
        self.task.walk_until_f(time_out=3, raise_if_not_found=False)
        if self.task.find_f_with_text():
            self.task.send_key('f', after_sleep=2.0)
            self.task.send_key('esc', after_sleep=0.5)
            return True
        return False

    def handle_collect_dragon_caskets(self, details=None):
        """Sonance Casket on stone dragon: walk into hitbox and pick up."""
        self.task.log_info("Collecting Sonance Casket on stone dragon")
        self.task.walk_until_f(time_out=3, raise_if_not_found=False)
        self.task.send_key('f', after_sleep=0.5)
        return True

    def handle_training_dummy(self, details=None):
        """Training dummies: attack all nearby dummies to solve puzzle."""
        self.task.log_info("Hitting training dummies")
        for _ in range(4):
            self.task.click(interval=0.2)
            self.task.sleep(0.3)
        self.task.sleep(1.0)
        self.task.walk_until_f(time_out=3, raise_if_not_found=False)
        return self.task.pick_f()

    def handle_training_dummy_and_separate_page(self, details=None):
        """Training dummy and optional torn page."""
        self.handle_training_dummy()
        self.task.walk_until_f(time_out=2, raise_if_not_found=False)
        self.task.pick_f()
        return True

    def handle_follow_mutterflies(self, details=None):
        """Mutterfly trail: follow glowing trajectory to destination."""
        self.task.log_info("Following Mutterfly path to spawn chest")
        start = time.time()
        while time.time() - start < 15:
            if self.task.find_f_with_text():
                self.task.send_key('f', after_sleep=0.5)
                return True
            self.task.send_key('w', after_sleep=0.3)
        return self.task.pick_f()

    def handle_three_mutterflies(self, details=None):
        """Three-mutterfly puzzle group."""
        self.task.log_info("Three Mutterflies area: sweeping for interact prompts")
        self.task.walk_until_f(time_out=6, raise_if_not_found=False)
        return self.task.pick_f()

    def handle_grapple_hidden_chest(self, details=None):
        """Grapple traversal: trigger T key utility to swing to hidden ledge."""
        self.task.log_info("Using grapple mechanism to reach hidden ledge")
        self.task.send_key('t', after_sleep=1.5)
        self.task.walk_until_f(time_out=3, raise_if_not_found=False)
        return self.task.pick_f()

    def handle_hidden_trigger_unverified(self, details=None):
        """Environmental breakable crates/logs."""
        self.task.log_info("Destroying environmental crates/logs to reveal hidden chest")
        self.task.click(interval=0.1)
        self.task.sleep(0.3)
        self.task.click(interval=0.1)
        self.task.sleep(0.6)
        self.task.walk_until_f(time_out=3, raise_if_not_found=False)
        return self.task.pick_f()

    def handle_time_trial(self, details=None):
        """Time-trial speed challenge."""
        self.task.log_info("Time-trial challenge encountered")
        if self.task.config.get('Skip Complex Puzzles', True):
            self.task.log_info("Skipping time-trial per configuration")
            return False
        self.task.walk_until_f(time_out=2, raise_if_not_found=False)
        self.task.send_key('f', after_sleep=1.0)
        return True

    def handle_magnetic_cube(self, details=None):
        """Magnetic cube conveyor puzzle."""
        if self.task.config.get('Skip Complex Puzzles', True):
            self.task.log_info("Magnetic cube puzzle skipped for manual completion")
            return False
        self.task.click(after_sleep=0.5)
        return False

    def handle_corroder_spikes(self, details=None):
        """Corroder spikes puzzle."""
        if self.task.config.get('Skip Complex Puzzles', True):
            self.task.log_info("Corroder spikes puzzle skipped for manual completion")
            return False
        return False

    def handle_encryption_block(self, details=None):
        """Encryption block with Key Repeaters."""
        if self.task.config.get('Skip Complex Puzzles', True):
            self.task.log_info("Encryption block puzzle skipped for manual completion")
            return False
        return False

    def handle_color_match_sequence_unverified(self, details=None):
        """Color match puzzle."""
        if self.task.config.get('Skip Complex Puzzles', True):
            self.task.log_info("Color match puzzle skipped for manual completion")
            return False
        return False

    def handle_fallback(self, details=None):
        """Fallback: checks for immediate interaction prompt or logs skip."""
        if self.task.find_f_with_text():
            return self.task.pick_f()
        self.task.log_info("Point completed or puzzle requires manual intervention")
        return False
