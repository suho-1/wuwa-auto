from ok import TriggerTask, Logger
from src.Labels import Labels
from src.scene.WWScene import WWScene
from src.task.BaseWWTask import BaseWWTask

logger = Logger.get_logger(__name__)


class AutoLoginTask(BaseWWTask, TriggerTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.default_config = {'_enabled': True}
        self.trigger_interval = 5
        self.name = "🔑 Auto Login"
        self.description = "Auto Login After Game Starts"

    def is_login_screen_detected(self):
        if self.find_one('login_close', horizontal_variance=0.15, vertical_variance=0.1):
            return True
        if self.find_one(Labels.switch_account, vertical_variance=0.1, threshold=0.7):
            return True
        return False

    def run(self):
        if self.scene.in_team(self.in_team_and_world):
            self.logged_in = True
        elif not self.logged_in or self.is_login_screen_detected():
            self.logged_in = False
            return self.wait_login()
