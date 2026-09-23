import json
import os
import time

from ok import Logger
from src.task.BaseCombatTask import BaseCombatTask
from src.task.ChestPlaybook import ChestPlaybook
from src.task.WWOneTimeTask import WWOneTimeTask

logger = Logger.get_logger(__name__)


class ChestExplorationTask(WWOneTimeTask, BaseCombatTask):
    """Systematic region-by-region chest and collectible autofarming task."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "📦 Chest & Exploration Auto-Farm"
        self.description = "Systematic overworld chest and collectible farming guided by route datasets."
        self.default_config.update({
            'Region Route': 'Gorges of Spirits',
            'Auto Combat Guarded Chests': True,
            'Skip Complex Puzzles': True,
            'Starting Stop': 1,
            'Max Stops per Run': 58,
        })
        self.config_description.update({
            'Region Route': 'Exploration route to farm.',
            'Auto Combat Guarded Chests': 'Automatically defeat enemy guards around sealed chests.',
            'Skip Complex Puzzles': 'Skip multi-step spatial/interactive puzzles to avoid hanging.',
            'Starting Stop': 'Stop number to begin execution from (useful for resuming).',
            'Max Stops per Run': 'Maximum number of stops to execute in this session.',
        })
        self.config_type['Region Route'] = {
            'type': 'drop_down',
            'options': ['Gorges of Spirits']
        }
        self.playbook = ChestPlaybook(self)
        self.collected_count = 0
        self.skipped_count = 0
        self.current_stop = 0

    def load_route_data(self):
        """Loads the route JSON dataset from configs/routes."""
        route_name = self.config.get('Region Route', 'Gorges of Spirits').lower().replace(' ', '_')
        path = os.path.join('configs', 'routes', f'{route_name}.json')
        if not os.path.exists(path):
            # Fallback to local working directory path
            path = os.path.join(os.path.dirname(__file__), '..', '..', 'configs', 'routes', f'{route_name}.json')

        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        raise FileNotFoundError(f"Route dataset not found at: {path}")

    def run(self):
        WWOneTimeTask.run(self)
        try:
            self.do_run()
        except Exception as e:
            self.log_error(f"Chest exploration encountered an error: {e}", e)
            raise

    def do_run(self):
        route_data = self.load_route_data()
        companion_route = route_data.get('labeled_companion_route', {})
        entries = companion_route.get('entries', [])
        total_entries = len(entries)

        start_stop = max(1, int(self.config.get('Starting Stop', 1)))
        max_stops = int(self.config.get('Max Stops per Run', 58))
        self.log_info(f"Loaded {route_data.get('region')} route with {total_entries} total points (Starting at #{start_stop})")

        self.collected_count = 0
        self.skipped_count = 0

        for index, entry in enumerate(entries, 1):
            if index < start_stop:
                continue
            if self.collected_count + self.skipped_count >= max_stops:
                self.log_info(f"Reached configured limit of {max_stops} stops. Ending session.")
                break

            pts, timestamp, collectible, location, puzzle, playbook_key = entry
            self.current_stop = index
            location_desc = f" ({location})" if location else ""
            self.log_info(f">>> Stop [{index}/{total_entries}] | Point {pts}: {collectible}{location_desc} [Video @ {timestamp}]")

            # Check for combat before attempting interaction
            if self.in_combat():
                self.log_info("Combat detected: clearing area")
                self.combat_once(wait_combat_time=5, raise_if_not_found=False, target=True)
                self.sleep(1.0)

            # Execute playbook action
            success = self.playbook.execute(playbook_key, details={'pts': pts, 'collectible': collectible, 'location': location})

            if success:
                self.collected_count += 1
                self.log_info(f"✓ Stop {pts} completed successfully! Total collected: {self.collected_count}")
            else:
                self.skipped_count += 1
                self.log_info(f"⚠ Stop {pts} marked skipped or requires manual intervention.")

            self.save_progress_manifest(route_data.get('region'))
            self.sleep(1.0)

        self.log_info(f"=== Session Finished! Collected: {self.collected_count} | Skipped: {self.skipped_count} ===")

    def save_progress_manifest(self, region_name):
        """Persists current progress manifest to logs for audit and resumption."""
        manifest = {
            'region': region_name,
            'last_stop_index': self.current_stop,
            'collected_count': self.collected_count,
            'skipped_count': self.skipped_count,
            'timestamp': time.strftime("%Y-%m-%d %H:%M:%S")
        }
        os.makedirs('logs', exist_ok=True)
        try:
            with open(os.path.join('logs', 'chest_exploration_progress.json'), 'w', encoding='utf-8') as f:
                json.dump(manifest, f, indent=4)
        except Exception:
            pass


from ok import run_task
from config import config

if __name__ == "__main__":
    run_task(config, task=ChestExplorationTask, debug=True)
