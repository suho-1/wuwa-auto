"""Interactive screens for choosing what each one-time routine farms.

Every screen is built from the same two helpers -- :func:`select` and
:func:`menu` -- so a new farm target is a data change plus a short handler
instead of a twenty-line screen.
"""

from __future__ import annotations

from . import console, engine, logs, routines
from .config_store import CONFIG_STORE
from .routines import MATERIALS, WEEKLY_DIFFICULTIES


def select(title: str, subtitle: str, options, formatter=None) -> int:
    """Print a numbered list and return the chosen index (0 = cancelled)."""
    options = list(options)
    console.banner(title, subtitle)
    for index, option in enumerate(options, 1):
        label = formatter(option, index) if formatter else str(option)
        console.print(f"  [bold magenta]{index:>2}[/bold magenta]. {label}")
    console.print(console.thin_rule(), style="dim")
    answer = console.ask(f"\n[bold cyan]Select 1-{len(options)} (Enter to cancel):[/bold cyan] ")
    if not answer.isdigit():
        return 0
    number = int(answer)
    return number if 1 <= number <= len(options) else 0


def menu(title: str, rows) -> None:
    """Print a simple key/label list from ``(key, label)`` pairs."""
    console.banner(title)
    for key, label in rows:
        console.print(f"  [bold magenta]{key:>2}[/bold magenta]. {label}")
    console.print(console.thin_rule(), style="dim")


def _commit(bridge: engine.EngineBridge, class_name: str, values: dict, message: str) -> None:
    """Persist to disk, push into the live task, and log the outcome."""
    CONFIG_STORE.update(class_name, values)
    rejected = bridge.set_live_config(class_name, values)
    if rejected:
        console.warn(f"The running task rejected: {', '.join(rejected)} (saved for the next launch)")
    logs.info(f"{class_name}: " + ", ".join(f"{k}={v}" for k, v in values.items()))
    console.success(message)


# -- screens --------------------------------------------------------------

def _configure_echo_sweeps(bridge: engine.EngineBridge) -> None:
    sweep_options = (
        "All Overworld Bosses (Sweep)",
        "All Weekly Bosses (Sweep)",
        "All 4-Cost Bosses (Complete Sweep)",
    )
    index = select("4-COST BOSS SWEEPS", "Sequential multi-boss farming", sweep_options)
    if not index:
        return
    boss = sweep_options[index - 1]
    values = {"Target Boss": boss}
    current_sweep = CONFIG_STORE.get("FarmEchoTask", "Sweep Count per Boss", 1)
    try:
        default_sweep = int(current_sweep)
    except (ValueError, TypeError):
        default_sweep = 1
    sweep_count = console.ask_number(
        "[bold cyan]Enter count per boss (1-50)[/bold cyan]",
        1, 50, default=default_sweep,
    )
    values["Sweep Count per Boss"] = sweep_count
    if "Weekly" in boss:
        current = CONFIG_STORE.get("FarmEchoTask", "Weekly Boss Difficulty", "80")
        console.print(f"\nWeekly domain level currently: [bold]{current}[/bold]")
        level = console.ask(f"[bold cyan]Difficulty {', '.join(WEEKLY_DIFFICULTIES)} "
                            f"(Enter keeps {current}):[/bold cyan] ")
        values["Weekly Boss Difficulty"] = level if level in WEEKLY_DIFFICULTIES else str(current or "80")
        values["Teleport to Boss"] = "Weekly Challenge"
    else:
        values["Teleport to Boss"] = "Boss Challenge"
    _commit(bridge, "FarmEchoTask", values, f"Echo target set to: {boss} (x{sweep_count})")


def _configure_echo_tracking(bridge: engine.EngineBridge) -> None:
    track_options = (
        "All 3-Cost Echoes (Guidebook Track)",
        "All 1-Cost Echoes (Guidebook Track)",
        "All 3C & 1C Echoes (Full Track)",
    )
    index = select("GUIDEBOOK MOB TRACKING", "In-game Guidebook tracking for 3C/1C echoes", track_options)
    if not index:
        return
    boss = track_options[index - 1]
    values = {"Target Boss": boss, "Teleport to Boss": "Boss Challenge"}
    current_sweep = CONFIG_STORE.get("FarmEchoTask", "Sweep Count per Boss", 1)
    try:
        default_sweep = int(current_sweep)
    except (ValueError, TypeError):
        default_sweep = 1
    sweep_count = console.ask_number(
        "[bold cyan]Enter runs/quota multiplier (1-50)[/bold cyan]",
        1, 50, default=default_sweep,
    )
    values["Sweep Count per Boss"] = sweep_count
    _commit(bridge, "FarmEchoTask", values, f"Echo target set to: {boss} (x{sweep_count})")


def _configure_single_overworld_boss(bridge: engine.EngineBridge) -> None:
    bosses = [b for b in routines.ordered_bosses()
              if "(Weekly)" not in b and "(Sweep)" not in b and "Track" not in b and b != "Current Location (No Teleport)"]
    index = select("SELECT OVERWORLD BOSS", "Bosses teleport directly to arena", bosses)
    if not index:
        return
    boss = bosses[index - 1]
    _commit(bridge, "FarmEchoTask", {"Target Boss": boss, "Teleport to Boss": "Boss Challenge"},
            f"Echo target set to: {boss}")


def _configure_single_weekly_boss(bridge: engine.EngineBridge) -> None:
    bosses = [b for b in routines.ordered_bosses() if "(Weekly)" in b and "(Sweep)" not in b]
    index = select("SELECT WEEKLY BOSS DOMAIN", "Weekly challenges require domain entry", bosses)
    if not index:
        return
    boss = bosses[index - 1]
    values = {"Target Boss": boss, "Teleport to Boss": "Weekly Challenge"}
    current = CONFIG_STORE.get("FarmEchoTask", "Weekly Boss Difficulty", "80")
    console.print(f"\nWeekly domain level currently: [bold]{current}[/bold]")
    level = console.ask(f"[bold cyan]Difficulty {', '.join(WEEKLY_DIFFICULTIES)} "
                        f"(Enter keeps {current}):[/bold cyan] ")
    values["Weekly Boss Difficulty"] = level if level in WEEKLY_DIFFICULTIES else str(current or "80")
    _commit(bridge, "FarmEchoTask", values, f"Echo target set to: {boss} (Lv{values['Weekly Boss Difficulty']})")


def configure_echo_boss(bridge: engine.EngineBridge) -> None:
    skip_locked = CONFIG_STORE.get("FarmEchoTask", "Skip Locked Areas", True)
    locked_state = "[bold green]ENABLED[/bold green]" if skip_locked else "[dim red]DISABLED[/dim red]"
    menu("CONFIGURE ECHO FARMING TARGET", [
        ("1", "4-Cost Boss Sweeps (Overworld / Weekly / Complete 4C)"),
        ("2", "Guidebook Mob Tracking (3-Cost Elites / 1-Cost Commons / Full)"),
        ("3", "Single Overworld Boss (Crownless, Inferno Rider, Mourning Aix, etc.)"),
        ("4", "Single Weekly Boss Domain (Scar, Jue, Dreamless, Bell-Borne, Hecate)"),
        ("5", "Current Location (Farm at player position, no teleport)"),
        ("6", f"Toggle Skip Locked Areas (Currently: {locked_state})"),
        ("b", "Back"),
    ])
    choice = console.ask("\n[bold cyan]Select category (1-6, b):[/bold cyan] ").strip().lower()
    if choice == "1":
        _configure_echo_sweeps(bridge)
    elif choice == "2":
        _configure_echo_tracking(bridge)
    elif choice == "3":
        _configure_single_overworld_boss(bridge)
    elif choice == "4":
        _configure_single_weekly_boss(bridge)
    elif choice == "5":
        _commit(bridge, "FarmEchoTask",
                {"Target Boss": "Current Location (No Teleport)", "Teleport to Boss": "No"},
                "Echo target set to: Current Location (No Teleport)")
    elif choice == "6":
        new_val = not bool(skip_locked)
        _commit(bridge, "FarmEchoTask", {"Skip Locked Areas": new_val},
                f"Skip Locked Areas set to: {'ENABLED' if new_val else 'DISABLED'}")


def _configure_daily_tacet(bridge: engine.EngineBridge) -> None:
    options = routines.tacet_suppressions()
    index = select("DAILY ROUTINE - TACET SUPPRESSION", "Sonata Echo sets", options)
    if not index:
        return
    _commit(bridge, "DailyTask",
            {"Which to Farm": "Tacet Suppression",
             "Which Tacet Suppression to Farm": options[index - 1]},
            f"Daily routine set to Tacet: {options[index - 1]}")


def _configure_daily_forgery(bridge: engine.EngineBridge) -> None:
    options = routines.forgery_challenges()
    index = select("DAILY ROUTINE - FORGERY CHALLENGE", "Weapon & skill ascension mats", options)
    if not index:
        return
    _commit(bridge, "DailyTask",
            {"Which to Farm": "Forgery Challenge",
             "Which Forgery Challenge to Farm": options[index - 1]},
            f"Daily routine set to Forgery: {options[index - 1]}")


def _configure_daily_simulation(bridge: engine.EngineBridge) -> None:
    index = select("DAILY ROUTINE - SIMULATION CHALLENGE", "EXP and Shell Credits", MATERIALS)
    if not index:
        return
    _commit(bridge, "DailyTask",
            {"Which to Farm": "Simulation Challenge", "Material Selection": MATERIALS[index - 1]},
            f"Daily routine set to Simulation: {MATERIALS[index - 1]}")


def configure_daily_task(bridge: engine.EngineBridge) -> None:
    menu("CONFIGURE DAILY ROUTINE ACTIVITY", [
        ("1", "Tacet Suppression (Echo Sonata sets)"),
        ("2", "Forgery Challenge (Weapon & Skill mats)"),
        ("3", "Simulation Challenge (EXP & Shell Credits)"),
        ("b", "Back"),
    ])
    choice = console.ask("\n[bold cyan]Select activity (1-3) or b:[/bold cyan] ").lower()
    if choice == "1":
        _configure_daily_tacet(bridge)
    elif choice == "2":
        _configure_daily_forgery(bridge)
    elif choice == "3":
        _configure_daily_simulation(bridge)


def configure_tacet_field(bridge: engine.EngineBridge) -> None:
    options = routines.tacet_suppressions()
    index = select("CONFIGURE TACET SUPPRESSION FIELD", "Choose the field to farm", options)
    if not index:
        return
    _commit(bridge, "TacetTask", {"Which Tacet Suppression to Farm": options[index - 1]},
            f"Tacet field set to: {options[index - 1]}")


def configure_forgery_domain(bridge: engine.EngineBridge) -> None:
    options = routines.forgery_challenges()
    index = select("CONFIGURE FORGERY CHALLENGE DOMAIN", "Choose the domain to farm", options)
    if not index:
        return
    _commit(bridge, "ForgeryTask", {"Which Forgery Challenge to Farm": options[index - 1]},
            f"Forgery challenge set to: {options[index - 1]}")


def configure_simulation(bridge: engine.EngineBridge) -> None:
    index = select("CONFIGURE SIMULATION CHALLENGE", "Choose the material to farm", MATERIALS)
    if not index:
        return
    _commit(bridge, "SimulationTask", {"Material Selection": MATERIALS[index - 1]},
            f"Simulation material set to: {MATERIALS[index - 1]}")


CHEST_STOPS = 58


def configure_chest_route(bridge: engine.EngineBridge) -> None:
    config = CONFIG_STORE.load("ChestExplorationTask")
    menu("CONFIGURE CHEST & EXPLORATION ROUTE", [
        ("1", f"Set the starting stop (1-{CHEST_STOPS}, currently {config.get('Starting Stop', 1)})"),
        ("2", "Toggle 'Skip Complex Puzzles'"),
        ("b", "Back"),
    ])
    choice = console.ask("\n[bold cyan]Select setting (1-2) or b:[/bold cyan] ").strip().lower()
    if choice == "1":
        current = config.get("Starting Stop", 1)
        stop = console.ask_number(f"[bold cyan]Starting stop (1-{CHEST_STOPS})[/bold cyan]",
                                  1, CHEST_STOPS, default=int(current) if str(current).isdigit() else 1)
        _commit(bridge, "ChestExplorationTask", {"Starting Stop": stop}, f"Starting stop set to #{stop}")
    elif choice == "2":
        value = not config.get("Skip Complex Puzzles", True)
        _commit(bridge, "ChestExplorationTask", {"Skip Complex Puzzles": value},
                f"Skip complex puzzles: {'ENABLED' if value else 'DISABLED'}")


def configure_auto_team(bridge: engine.EngineBridge) -> None:
    from src.task.AutoTeamTask import AutoTeamTask
    options = AutoTeamTask.PREFER_OPTIONS
    index = select("AUTO TEAM PREFERENCE", "Rexlent team advisor carry selection", options)
    if not index:
        return
    pref = options[index - 1]
    _commit(bridge, "AutoTeamTask", {"Prefer Main DPS": pref}, f"Preferred Main DPS set to: {pref}")


#: Menu key -> screen function, derived from the declarative spec table.
HANDLERS_BY_KEY = {spec.key: globals()[spec.handler] for spec in routines.CONFIGURERS}


def run(bridge: engine.EngineBridge) -> None:
    """Top-level configuration menu."""
    while True:
        menu("ROUTINE TARGET CONFIGURATION & SELECTION", [
            (spec.key, f"{spec.label}: {routines.target_cell(spec.class_name, 28).markup}")
            for spec in routines.CONFIGURERS
        ] + [("b", "Back to the dashboard")])
        choice = console.ask(f"\n[bold cyan]Select option (1-{len(routines.CONFIGURERS)}, b):[/bold cyan] ").strip().lower()
        handler = HANDLERS_BY_KEY.get(choice)
        if handler is None:
            if choice in ("b", "q", "", "exit"):
                return
            console.invalid("Unknown option.")
        else:
            try:
                handler(bridge)
            except (EOFError, KeyboardInterrupt):
                return
            except Exception as exc:
                console.report_exception("Configuration failed", exc)
