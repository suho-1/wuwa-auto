"""Benchmark: the previous dashboard hot path vs the refactored one.

The old implementation's self-contained parts are reproduced verbatim and
driven against the same fake engine bridge and the same ``configs/`` directory
as the new renderer, so the two numbers are directly comparable.

    python tests/bench_tui.py [path-to-working-tree]
"""

import io
import json
import os
import sys
import threading
import time
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
for path in (REPO,):
    if path not in sys.path:
        sys.path.insert(0, path)

WORKING = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "..", "working")
WORKING = os.path.abspath(WORKING)
if not os.path.isdir(os.path.join(WORKING, "configs")):
    WORKING = REPO
if os.path.isdir(os.path.join(WORKING, "configs")):
    os.chdir(WORKING)

from rich.console import Console
from rich.table import Table

from src.tui import console as tui_console
from src.tui import dashboard, engine

ITERATIONS = 200
REFERENCE_WIDTH = 72


# ------------------------------------------------------- the previous code
def old_load_config_json(task_name):
    path = os.path.join("configs", f"{task_name}.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as stream:
                return json.load(stream)
        except Exception:
            pass
    return {}


def old_get_task_target_display(class_name):
    cfg = old_load_config_json(class_name)
    if class_name == "FarmEchoTask":
        boss = cfg.get("Target Boss", cfg.get("Boss", "Crownless"))
        if "(Weekly)" in boss:
            level = cfg.get("Weekly Boss Difficulty", cfg.get("Boss Level", "80"))
            return f"[green]{boss.replace(' (Weekly)', '').strip()}[/green] [dim](Lv{level})[/dim]"
        if boss == "Current Location (No Teleport)":
            return "[dim]Current Pos[/dim]"
        return f"[green]{boss}[/green]"
    if class_name == "TacetTask":
        target = cfg.get("Which Tacet Suppression to Farm", "1 - Desorock Highland")
        short = target.split("(")[0].strip()
        if " - " in short:
            short = short.split(" - ", 1)[1].strip()
        return f"[green]{short[:24]}[/green]"
    return "[dim]Default[/dim]"


def old_is_admin():
    try:
        import ctypes

        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def old_get_trigger_task(executor, class_name):
    for task in executor.trigger_tasks:
        if task.__class__.__name__ == class_name:
            return task
    return None


LOG_BUFFER = deque(maxlen=100)
LOG_LOCK = threading.Lock()
for i in range(4):
    LOG_BUFFER.append(("12:00:00", "INFO", "Engine", f"event {i}"))


def old_print_dashboard(self, console):
    os.system('cls' if os.name == 'nt' else 'clear')
    console.clear()
    console.print("=" * 72, style="cyan")
    console.print("                  WUWA-AUTO ADVANCED TERMINAL SUITE", style="bold cyan")
    console.print("=" * 72, style="cyan")
    console.print("[bold white]Game Target :[/bold white] Connected (HWND: 1 | 1920x1080)")
    console.print("[bold white]Active Party:[/bold white] [dim]Standby[/dim]")
    privilege = "[bold green]Admin[/bold green]" if old_is_admin() else "[bold red]Non-Admin[/bold red]"
    state = "[bold red]PAUSED[/bold red]" if self.executor.paused else "[bold green]RUNNING[/bold green]"
    console.print(f"[bold white]Privilege   :[/bold white] {privilege}"
                  f"  [bold white]Executor:[/bold white] {state}")
    console.print("-" * 72, style="dim")

    trigger_table = Table(title="[bold yellow]Continuous Autoplay Triggers[/bold yellow]",
                          border_style="green", expand=False, padding=(0, 1))
    trigger_table.add_column("Key", style="bold magenta", width=3, justify="center")
    trigger_table.add_column("Task Name", style="bold white", width=14)
    trigger_table.add_column("Status", width=10, justify="center")
    trigger_table.add_column("Description", style="dim", width=32)
    for key, class_name, label, description in [
        ("1", "AutoCombatTask", "Auto Combat", "Skill rotations, burst & dodge"),
        ("2", "AutoPickTask", "Auto Pick", "Loot & dropped item collection"),
        ("3", "AutoDialogTask", "Auto Dialog", "Skip cutscenes & story dialog"),
        ("4", "AutoLoginTask", "Auto Login", "Auto reconnect on disconnect"),
        ("5", "FastTravelTask", "Fast Travel", "Quick map waypoint travel"),
        ("6", "MouseResetTask", "Mouse Reset", "Prevents camera cursor drift"),
    ]:
        task = old_get_trigger_task(self.executor, class_name)
        on = task.enabled if task else False
        trigger_table.add_row(key, label,
                              "[bold green][ACTIVE][/bold green]" if on else "[dim red][OFF][/dim red]",
                              description)
    console.print(trigger_table)
    console.print()

    routine_table = Table(title="[bold yellow]One-Time Automation Routines[/bold yellow]",
                          border_style="yellow", expand=False, padding=(0, 1))
    routine_table.add_column("Key", style="bold magenta", width=3, justify="center")
    routine_table.add_column("Routine", style="bold white", width=13)
    routine_table.add_column("Active Target", width=26)
    routine_table.add_column("Description", style="dim", width=16)
    for key, class_name in [("e", "FarmEchoTask"), ("d", "DailyTask"), ("t", "TacetTask"),
                            ("f", "ForgeryTask"), ("m", "SimulationTask"),
                            ("n", "NightmareNestTask"), ("x", "ChestExplorationTask")]:
        routine_table.add_row(key, class_name, old_get_task_target_display(class_name), "desc")
    console.print(routine_table)
    console.print("-" * 72, style="dim")
    console.print("[bold yellow]RECENT ACTIVITY LOGS (Last 4 events):[/bold yellow]")
    with LOG_LOCK:
        recent = list(LOG_BUFFER)[-4:]
    for timestamp, level, sender, message in recent:
        console.print(f"  [dim]{timestamp}[/dim] INFO  [bold]{sender}[/bold]: {message}")
    console.print("-" * 72, style="dim")
    console.print("[bold]Triggers:[/bold] [magenta]1-6[/magenta]=Toggle")
    console.print("[bold]Controls:[/bold] [magenta]q[/magenta]=Quit")


# ------------------------------------------------------------------ harness
class FakeTask:
    def __init__(self, name, enabled=False):
        self.name = name
        self._enabled = enabled

    @property
    def enabled(self):
        return self._enabled


class FakeExecutor:
    def __init__(self):
        self.trigger_tasks = [FakeTask(name) for name in
                              ("AutoCombatTask", "AutoPickTask", "AutoDialogTask",
                               "AutoLoginTask", "FastTravelTask", "MouseResetTask")]
        self.onetime_tasks = []
        self.paused = False


class OldDashboard:
    def __init__(self):
        self.executor = FakeExecutor()


class NewBridge(engine.EngineBridge):
    def __init__(self):
        super().__init__()
        self.executor = FakeExecutor()
        self.ok = None

    def device_status(self):
        return "[bold green]Connected[/bold green] (HWND: 1 | 1920x1080)"

    def party_status(self):
        return "[dim]Standby (detects in combat)[/dim]"


def main():
    sink = io.StringIO()
    bench_console = Console(file=sink, width=REFERENCE_WIDTH, highlight=False)
    saved = tui_console.console
    saved_detect = tui_console.detect_width
    tui_console.console = bench_console
    tui_console.detect_width = lambda: REFERENCE_WIDTH

    old = OldDashboard()
    new = NewBridge()
    try:
        old_print_dashboard(old, bench_console)
        dashboard.draw(new, None)

        start = time.perf_counter()
        for _ in range(ITERATIONS):
            old_print_dashboard(old, bench_console)
        old_total = time.perf_counter() - start

        start = time.perf_counter()
        for _ in range(ITERATIONS):
            dashboard.draw(new, None)
        new_total = time.perf_counter() - start
    finally:
        tui_console.console = saved
        tui_console.detect_width = saved_detect

    from src.tui.config_store import CONFIG_STORE

    print(f"config directory : {os.path.join(os.getcwd(), 'configs')}")
    print(f"frames measured  : {ITERATIONS}")
    print()
    print(f"old dashboard : {old_total * 1000:9.1f} ms total  {old_total / ITERATIONS * 1000:7.3f} ms/frame")
    print(f"new dashboard : {new_total * 1000:9.1f} ms total  {new_total / ITERATIONS * 1000:7.3f} ms/frame")
    print()
    print(f"speedup        : {old_total / new_total:.1f}x faster "
          f"({(old_total - new_total) * 1000 / ITERATIONS:.3f} ms saved per frame)")
    print()
    print(f"config reads   : {CONFIG_STORE.stats()}")


if __name__ == "__main__":
    main()
