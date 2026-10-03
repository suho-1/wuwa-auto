
from ok import Logger
from src.task.DomainTask import DomainTask
from src.task.waveplates import daily_waveplate_quota

logger = Logger.get_logger(__name__)

SIMULATION_MATERIALS = [
    'Resonator EXP',
    'Weapon EXP',
    'Shell Credit',
    'Echo EXP',
]
SIMULATION_MATERIAL_INDEX = {
    material: index for index, material in enumerate(SIMULATION_MATERIALS)
}


class SimulationTask(DomainTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = '🧪 Simulation Challenge'
        self.description = 'Farms the selected Simulation Challenge. Must be able to teleport (F2).'
        self.support_schedule_task = True
        self.default_config = {
            'Material Selection': 'Shell Credit',
            'Farm Mode': 'Run Once (Daily Quest)',
        }
        self.config_type['Material Selection'] = {
            'type': 'drop_down',
            'options': SIMULATION_MATERIALS,
        }
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
            'Material Selection': 'Resonator EXP, Weapon EXP, Shell Credits, or Echo EXP (Sealed Tubes).',
            'Farm Mode': 'Run once by default while recovering automation. Burn-all is an explicit opt-in after a single 40-Waveplate claim passes verification.',
        }
        self.stamina_once = 40

    def run(self):
        super().run()
        self.make_sure_in_world()
        self.farm_simulation()

    def farm_simulation(self, daily=False, used_stamina=0, config=None, once=False,
                        max_runs=0, burn_all=False):
        if config is None:
            config = self.config
        selection = config.get('Material Selection', 'Shell Credit')

        mode = config.get('Simulation Challenge Runs in Daily' if daily else 'Farm Mode', None)
        if daily and burn_all:
            # "Always Burn Waveplates" is a top-level Daily Task policy and
            # intentionally overrides the Simulation-only run count.
            mode = 'Burn All Waveplates'
        elif mode is None and daily:
            mode = config.get('Simulation Challenge Runs in Daily', 'Run Once (Daily Quest)')

        if once or mode in ('Run Once (Daily Quest)', 'Run Once (40 Waveplates)', 'Run Once (1 time)', 'Run Once'):
            must_use = self.stamina_once
            max_runs = 1
        elif mode in ('Run Once (Double Claim, 80 Waveplates)', 'Run Once (Double Claim)'):
            must_use = self.stamina_once * 2
            max_runs = 1
        elif mode == 'Spend Waveplates (up to 180)':
            must_use = daily_waveplate_quota(used_stamina)
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
        # Unknown values from an older config safely retain the historical
        # Shell Credit fallback instead of selecting an arbitrary row.
        index = SIMULATION_MATERIAL_INDEX.get(selection, 2)
        # go buttom
        self.click(0.9730, 0.8806, after_sleep=1)
        # click target
        self.click(0.898, 0.533 + index * 0.14, after_sleep=1)
        self.click_relative(0.93, 0.90, after_sleep=1)
        self.click_team_challenge()
        self.wait_in_team_and_world(time_out=self.teleport_timeout)
