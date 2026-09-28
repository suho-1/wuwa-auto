"""Declarative descriptions of everything the dashboard can show or dispatch.

Trigger toggles, one-time routines and their target summaries are defined as
data rather than scattered ``if/elif`` branches, so the dashboard, the
configuration menu and the command registry all read from one source.
"""

from __future__ import annotations

from typing import Callable, NamedTuple, Optional

from rich.markup import escape

from .config_store import CONFIG_STORE
from .grid import Cell


class TriggerSpec(NamedTuple):
    key: str
    class_name: str
    label: str
    description: str


class RoutineSpec(NamedTuple):
    key: str
    class_name: str
    label: str
    description: str


class ConfigSpec(NamedTuple):
    key: str
    label: str
    class_name: str
    handler: str


TRIGGERS = (
    TriggerSpec("1", "AutoCombatTask", "Auto Combat", "Skill rotations, burst & dodge"),
    TriggerSpec("2", "AutoPickTask", "Auto Pick", "Loot & dropped item collection"),
    TriggerSpec("3", "AutoDialogTask", "Auto Dialog", "Skip cutscenes & story dialog"),
    TriggerSpec("4", "AutoLoginTask", "Auto Login", "Auto reconnect on disconnect"),
    TriggerSpec("5", "FastTravelTask", "Fast Travel", "Quick map waypoint travel"),
    TriggerSpec("6", "MouseResetTask", "Mouse Reset", "Prevents camera cursor drift"),
)

ROUTINES = (
    RoutineSpec("e", "FarmEchoTask", "Farm Echoes", "Boss / Echo farm"),
    RoutineSpec("d", "DailyTask", "Daily Routine", "Dailies & energy"),
    RoutineSpec("t", "TacetTask", "Tacet Fields", "Sonata Echo sets"),
    RoutineSpec("f", "ForgeryTask", "Forgery Area", "Ascension mats"),
    RoutineSpec("m", "SimulationTask", "Simulation", "EXP & Credits"),
    RoutineSpec("n", "NightmareNestTask", "Nightmare", "Nest challenges"),
    RoutineSpec("x", "ChestExplorationTask", "Chest Route", "Overworld chests"),
    RoutineSpec("b", "AutoTeamTask", "Auto Team", "Rexlent team advisor & builder"),
)

CONFIGURERS = (
    ConfigSpec("1", "Farm Echoes Target", "FarmEchoTask", "configure_echo_boss"),
    ConfigSpec("2", "Daily Routine Farming", "DailyTask", "configure_daily_task"),
    ConfigSpec("3", "Tacet Field Domain", "TacetTask", "configure_tacet_field"),
    ConfigSpec("4", "Forgery Challenge Domain", "ForgeryTask", "configure_forgery_domain"),
    ConfigSpec("5", "Simulation Domain", "SimulationTask", "configure_simulation"),
    ConfigSpec("6", "Chest Exploration Route", "ChestExplorationTask", "configure_chest_route"),
)

MATERIALS = ("Shell Credit", "Resonator EXP", "Weapon EXP")

WEEKLY_DIFFICULTIES = ("50", "60", "70", "80", "90")

FALLBACK_BOSSES = (
    "All Overworld Bosses (Sweep)",
    "All Weekly Bosses (Sweep)",
    "All 4-Cost Bosses (Complete Sweep)",
    "All 3-Cost Echoes (Guidebook Track)",
    "All 1-Cost Echoes (Guidebook Track)",
    "All 3C & 1C Echoes (Full Track)",
    "Current Location (No Teleport)",
    "Scar (Weekly)",
    "Bell-Borne Geochelone (Weekly)",
    "Dreamless (Weekly)",
    "Jue (Weekly)",
    "Hecate / Sentinel (Weekly)",
    "Crownless",
    "Thundering Mephis",
    "Tempest Mephis",
    "Inferno Rider",
    "Feilian Beringal",
    "Mourning Aix",
    "Impermanence Heron",
    "Mech Abomination",
    "Lampylumen Myriad",
    "Fallacy of No Return",
    "Sentry Construct",
    "Lorelei",
    "Lioness of Glory",
    "Fenrico",
    "Nameless Explorer",
)

FALLBACK_TACET = (
    "1 - Desorock Highland (Celestial Light & Havoc Eclipse)",
    "2 - Central Plains (Sierra Gale & Molten Rift)",
    "3 - Port City Guixu (Molten Rift & Sun-sinking Eclipse)",
    "4 - Dim Forest (Void Thunder & Moonlit Clouds)",
    "5 - Waving Hills (Freezing Frost & Sierra Gale)",
    "6 - Whining Aix's Mire (Sun-sinking Eclipse & Celestial Light)",
    "7 - Norfall Barrens (Void Thunder & Freezing Frost)",
    "8 - Mt. Firmament (Midnight Frost & Celestial Light)",
    "9 - Black Shores (Endless Resonance & Deep Ocean)",
)

FALLBACK_FORGERY = (
    "1 - Misty Coast: Sword & Broadblade (Metallic Drip)",
    "2 - Port City Guixu: Pistols (Phlogiston)",
    "3 - Qichi Village: Rectifier (Helix)",
    "4 - Dim Forest: Gauntlets (Cadence)",
    "5 - Mt. Firmament: Broadblade & Sword (Monumental Wave)",
    "6 - Black Shores: Pistols & Rectifier (Abyssal Core)",
)


def _from_module(attribute: str, module: str, fallback) -> tuple:
    try:
        source = __import__(module, fromlist=[attribute])
        values = tuple(getattr(source, attribute))
        if values:
            return values
    except Exception:
        pass
    return tuple(fallback)


def boss_profiles() -> tuple:
    return _from_module("BOSS_PROFILES", "src.task.FarmEchoTask", FALLBACK_BOSSES)


def tacet_suppressions() -> tuple:
    return _from_module("TACET_SUPPRESSIONS", "src.task.TacetTask", FALLBACK_TACET)


def forgery_challenges() -> tuple:
    return _from_module("FORGERY_CHALLENGES", "src.task.ForgeryTask", FALLBACK_FORGERY)


def ordered_bosses() -> tuple:
    """Sweep modes first, weekly bosses, then overworld, then manual."""
    bosses = boss_profiles()
    sweeps = [b for b in bosses if "(Sweep)" in b or "(Guidebook Track)" in b or "(Full Track)" in b or "(Complete Sweep)" in b]
    weekly = [b for b in bosses if "(Weekly)" in b and b not in sweeps]
    overworld = [b for b in bosses if "(Weekly)" not in b and b != "Current Location (No Teleport)" and b not in sweeps]
    manual = [b for b in bosses if b == "Current Location (No Teleport)"]
    return tuple(sweeps + weekly + overworld + manual)


# -- target summaries -----------------------------------------------------
# Every renderer receives the task config plus a character budget and returns
# a :class:`~.grid.Cell`, which carries both the visible text (used for column
# padding) and the markup (used for display).  Values coming from user-editable
# JSON are escaped, so a stray "[" can never be parsed as a style tag.

def _choice_head(value) -> str:
    """'3 - Port City Guixu (Molten Rift & ...)' -> 'Port City Guixu'."""
    text = str(value or "")
    head = text.split("(", 1)[0].strip()
    if " - " in head:
        head = head.split(" - ", 1)[1].strip()
    return head


def short_choice(value) -> str:
    return _choice_head(value)


def short_challenge(value) -> str:
    """Adds the primary material: 'Port City Guixu (Pistols)'."""
    head = _choice_head(value)
    domain, separator, materials = head.partition(":")
    if separator:
        primary = materials.split("&")[0].strip()
        if primary:
            return f"{domain.strip()} ({primary})"
    return head


def _clip(text, limit: int) -> str:
    text = str(text or "")
    if limit and len(text) > limit:
        return text[: max(1, limit - 1)] + "…"
    return text


def _green(text, limit: int = 0) -> Cell:
    text = _clip(text, limit)
    return Cell(text, f"[green]{escape(text)}[/green]")


def _label(prefix: str, value, limit: int) -> Cell:
    """A dimmed prefix followed by a highlighted value, e.g. 'Tacet: X'."""
    clipped = _clip(value, limit)
    return Cell(f"{prefix}{clipped}",
                f"[cyan]{escape(prefix)}[/cyan][green]{escape(clipped)}[/green]")


SWEEP_SHORT_NAMES = {
    "All Overworld Bosses (Sweep)": "All Overworld",
    "All Weekly Bosses (Sweep)": "All Weekly",
    "All 4-Cost Bosses (Complete Sweep)": "All 4-Cost",
    "All 3-Cost Echoes (Guidebook Track)": "3-Cost Track",
    "All 1-Cost Echoes (Guidebook Track)": "1-Cost Track",
    "All 3C & 1C Echoes (Full Track)": "All 3C/1C Track",
}


def _echo_target(config, limit: int) -> Cell:
    boss = str(config.get("Target Boss") or config.get("Boss") or "Crownless")
    if boss in SWEEP_SHORT_NAMES:
        short = SWEEP_SHORT_NAMES[boss]
        sweep_count = escape(str(config.get("Sweep Count per Boss", 1)))
        label = f"{short} (x{sweep_count})"
        return Cell(_clip(label, limit), f"[green]{escape(short)}[/green] [dim](x{sweep_count})[/dim]")
    if "(Sweep)" in boss or "(Guidebook Track)" in boss or "(Full Track)" in boss or "(Complete Sweep)" in boss:
        sweep_count = escape(str(config.get("Sweep Count per Boss", 1)))
        cleaned = boss.replace("(Sweep)", "").replace("(Guidebook Track)", "").replace("(Full Track)", "").replace("(Complete Sweep)", "").strip()
        label = f"{cleaned} (x{sweep_count})"
        return Cell(_clip(label, limit), f"[green]{escape(_clip(cleaned, limit))}[/green] [dim](x{sweep_count})[/dim]")
    if "(Weekly)" in boss:
        level = escape(str(config.get("Weekly Boss Difficulty") or config.get("Boss Level") or "80"))
        name = _clip(boss.replace("(Weekly)", "").strip(), limit)
        return Cell(f"{name} (Lv{level})", f"[green]{escape(name)}[/green] [dim](Lv{level})[/dim]")
    if boss == "Current Location (No Teleport)":
        return Cell("Current Pos", "[dim]Current Pos[/dim]")
    return _green(boss, limit)


def _daily_target(config, limit: int) -> Cell:
    mode = config.get("Which to Farm", "Tacet Suppression")
    if mode == "Tacet Suppression":
        return _label("Tacet: ", short_choice(config.get("Which Tacet Suppression to Farm", FALLBACK_TACET[0])), limit)
    if mode == "Forgery Challenge":
        return _label("Forge: ", short_challenge(config.get("Which Forgery Challenge to Farm", FALLBACK_FORGERY[0])), limit)
    return _label("Sim: ", config.get("Material Selection", MATERIALS[0]), limit)


def _tacet_target(config, limit: int) -> Cell:
    return _green(short_choice(config.get("Which Tacet Suppression to Farm", FALLBACK_TACET[0])), limit)


def _forgery_target(config, limit: int) -> Cell:
    return _green(short_challenge(config.get("Which Forgery Challenge to Farm", FALLBACK_FORGERY[0])), limit)


def _simulation_target(config, limit: int) -> Cell:
    return _green(config.get("Material Selection", MATERIALS[0]), limit)


def _nightmare_target(config, limit: int) -> Cell:
    return Cell("All Configured Nests", "[green]All Configured Nests[/green]")


def _chest_target(config, limit: int) -> Cell:
    region = _clip(config.get("Region Route", "Gorges of Spirits"), limit)
    stop = escape(str(config.get("Starting Stop", 1)))
    return Cell(f"{region} (#{stop})", f"[green]{escape(region)}[/green] [dim](#{stop})[/dim]")


def _team_target(config, limit: int) -> Cell:
    pref = config.get("Prefer Main DPS", "Auto")
    label = pref if pref and pref != "None" else "Auto (Tier S+)"
    return _label("Meta: ", label, limit)


TARGET_RENDERERS: dict = {
    "FarmEchoTask": _echo_target,
    "DailyTask": _daily_target,
    "TacetTask": _tacet_target,
    "ForgeryTask": _forgery_target,
    "SimulationTask": _simulation_target,
    "NightmareNestTask": _nightmare_target,
    "ChestExplorationTask": _chest_target,
    "AutoTeamTask": _team_target,
}

UNKNOWN_CELL = Cell("Default", "[dim]Default[/dim]")


def target_cell(class_name: str, limit: int = 0) -> Cell:
    """Render a routine's active target, clipped to ``limit`` visible chars."""
    renderer: Optional[Callable] = TARGET_RENDERERS.get(class_name)
    if renderer is None:
        return UNKNOWN_CELL
    try:
        config = CONFIG_STORE.load(class_name)
    except Exception:
        config = {}
    try:
        return renderer(config, limit)
    except Exception:
        return Cell("Unknown", "[dim]Unknown[/dim]")
