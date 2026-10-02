import re

from ok import Logger
from src.task.DomainTask import DomainTask

logger = Logger.get_logger(__name__)


class SimulationTask(DomainTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = '🧪 Simulation Challenge'
        self.description = 'Farms the selected Simulation Challenge. Must be able to teleport (F2).'
        self.support_schedule_task = True
        self.default_config = {
            'Material Selection': 'Shell Credit',
            'Farm Mode': 'Burn All Waveplates',
        }
        material_option_list = ['Resonator EXP', 'Weapon EXP', 'Shell Credit']
        self.config_type['Material Selection'] = {'type': 'drop_down', 'options': material_option_list}
        self.config_type['Farm Mode'] = {
            'type': 'drop_down',
            'options': [
                'Burn All Waveplates',
                'Run Once (Daily Quest)',
                'Run Once (Double Claim, 80 Waveplates)',
                'Spend Waveplates (up to 180)',
            ],
        }
        self.config_description = {
            'Material Selection': 'Resonator EXP / Weapon EXP / Shell Credit',
            'Farm Mode': 'Burn all waveplates, run once (for daily quest), or spend waveplates up to 180.',
        }
        self.stamina_once = 40

    def run(self):
        super().run()
        self.make_sure_in_world()
        self.farm_simulation()

    def farm_simulation(self, daily=False, used_stamina=0, config=None, once=False, max_runs=0):
        if config is None:
            config = self.config
        selection = config.get('Material Selection', 'Shell Credit')

        mode = config.get('Simulation Challenge Runs in Daily' if daily else 'Farm Mode', None)
        if mode is None and daily:
            mode = config.get('Simulation Challenge Runs in Daily', 'Run Once (Daily Quest)')

        if once or mode in ('Run Once (Daily Quest)', 'Run Once (40 Waveplates)', 'Run Once (1 time)', 'Run Once'):
            must_use = self.stamina_once
            max_runs = 1
        elif mode in ('Run Once (Double Claim, 80 Waveplates)', 'Run Once (Double Claim)'):
            must_use = self.stamina_once * 2
            max_runs = 1
        elif mode == 'Spend Waveplates (up to 180)':
            must_use = max(0, 180 - used_stamina)
            max_runs = 0
        elif mode == 'Burn All Waveplates':
            must_use = 0
            max_runs = 0
        elif daily:
            must_use = self.stamina_once
            max_runs = 1
        else:
            must_use = 0
            max_runs = 0

        logger.info(f"farm_simulation: daily={daily}, mode={mode}, must_use={must_use}, max_runs={max_runs}")

        def teleport_once():
            self.teleport_into_domain(selection)

        self.farm_domain_with_recovery_loop(must_use, teleport_once, max_runs=max_runs)

    def teleport_into_domain(self, selection):
        self.open_boss_book('moni')
        self.info_set('Target Simulation Challenge', selection)
        if selection == 'Resonator EXP':
            index = 0
        elif selection == 'Weapon EXP':
            index = 1
        else:  # selection == 'Shell Credit'
            index = 2
        # go buttom
        self.click(0.9730, 0.8806, after_sleep=1)
        # click target
        self.click(0.898, 0.533 + index * 0.14, after_sleep=1)
        self.click_relative(0.93, 0.90, after_sleep=1)
        self.click_team_challenge()
        self.wait_in_team_and_world(time_out=self.teleport_timeout)
