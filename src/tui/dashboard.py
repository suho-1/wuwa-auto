"""The main dashboard: one fixed-height frame, redrawn in place.

The frame never scrolls.  Its height is chosen by :mod:`.layout` from the
terminal size before anything is drawn, and :func:`draw` writes the result
with a cursor-home escape so the previous frame is overwritten rather than
pushed down the scrollback.
"""

from __future__ import annotations

import time

from rich.markup import escape
from rich.table import Table
from rich.text import Text

from . import console, engine, game_setup, grid, layout, logs, routines
from .config_store import CONFIG_STORE

#: How often the frame is repainted when nothing else changed, in seconds.
REFRESH_INTERVAL = 0.5

TITLE = "WUWA-AUTO"
PROMPT = "wuwa-auto>"

RUNNING_LABEL = "[bold green]RUNNING[/bold green]"
PAUSED_LABEL = "[bold yellow]PAUSED[/bold yellow]"
OFFLINE_LABEL = "[dim]OFFLINE[/dim]"

#: The command reference shown on the main frame. Kept terse on purpose: it
#: competes with the log for rows, and `?` prints the long form.
HINT_ITEMS = (
    ("1-6", "toggle"),
    ("e d t f m n x", "run"),
    ("c", "config"),
    ("a", "Annotation GUI"),
    ("g", "display"),
    ("l", "logs"),
    ("k", "keys"),
    ("p", "pause"),
    ("v", "diag"),
    ("?", "help"),
    ("q", "quit"),
)

SEPARATOR = "   "


def _hints(width: int) -> list:
    """Pack the command hints into as few lines as `width` allows.

    Widths are measured on the *plain* text and the markup is produced
    afterwards, so the packing can never disagree with what gets drawn.
    """
    lines = []
    parts = []
    used = 0

    for key, description in HINT_ITEMS:
        entry = f"[magenta]{escape(key)}[/magenta] {escape(description)}"
        entry_len = len(key) + 1 + len(description)
        separator = len(SEPARATOR) if parts else 0
        if parts and used + separator + entry_len > width:
            lines.append(SEPARATOR.join(parts))
            parts, used, separator = [], 0, 0
        parts.append(entry)
        used += separator + entry_len

    if parts:
        lines.append(SEPARATOR.join(parts))
    return lines


def _status(plan: "layout.Plan", bridge: "engine.EngineBridge") -> list:
    """The status block as ``(label, value_markup, value_plain)`` rows."""
    rows = []
    if "game" in plan.status_lines:
        dev_st = bridge.device_status()
        skip_locked = CONFIG_STORE.get("FarmEchoTask", "Skip Locked Areas", True)
        locked_badge = "[bold green]ON[/bold green]" if skip_locked else "[dim red]OFF[/dim red]"
        plain_st = Text.from_markup(dev_st).plain if "[" in dev_st else dev_st
        if plan.width >= 72:
            rows.append(("Game", f"{dev_st}   [dim]SkipLocked:[/dim] {locked_badge}", f"{plain_st}   SkipLocked: {'ON' if skip_locked else 'OFF'}"))
        else:
            rows.append(("Game", dev_st, plain_st))
    if "party" in plan.status_lines:
        rows.append(("Party", bridge.party_status(), None))
    if "privilege" in plan.status_lines:
        admin = console.is_admin()
        rows.append(("Admin",
                     "[bold green]yes[/bold green]" if admin
                     else "[bold red]no - run as admin[/bold red]",
                     "yes" if admin else "no - run as admin"))
    if "triggers" in plan.status_lines:
        trigger_names = {
            "AutoCombatTask": "Combat",
            "AutoPickTask": "Pick",
            "AutoDialogTask": "Dialog",
            "AutoLoginTask": "Login",
            "FastTravelTask": "Travel",
            "MouseResetTask": "Mouse",
        }
        chips, plain = [], []
        for spec in routines.TRIGGERS:
            on = bridge.is_trigger_enabled(spec.class_name)
            name = trigger_names.get(spec.class_name, spec.key)
            tag = f"{spec.key}:{name}"
            if on:
                chips.append(f"[bold green]{tag}[/bold green]")
            else:
                chips.append(f"[dim]{tag}[/dim]")
            plain.append(tag)
        val_markup = "  ".join(chips)
        val_plain = "  ".join(plain)
        if len(val_plain) > plan.width - 14:
            compact_chips, compact_plain = [], []
            for spec in routines.TRIGGERS:
                on = bridge.is_trigger_enabled(spec.class_name)
                state = "[bold green]on[/bold green]" if on else "[dim]off[/dim]"
                compact_chips.append(f"[magenta]{spec.key}[/magenta] {state}")
                compact_plain.append(f"{spec.key} {'on' if on else 'off'}")
            val_markup = " ".join(compact_chips)
            val_plain = " ".join(compact_plain)
        rows.append(("Triggers", val_markup, val_plain))
    return rows


def _routines(panel: grid.Panel, plan: "layout.Plan") -> None:
    panel.rule()
    panel.add("[bold yellow]ROUTINES[/bold yellow]")
    columns = layout.routine_columns(panel.inner_width)
    cell_width = (panel.inner_width - (columns - 1) * 2) // columns
    specs = routines.ROUTINES
    rows = -(-len(specs) // columns)
    for row in range(rows):
        pieces = []
        for column in range(columns):
            index = row * columns + column
            if index >= len(specs):
                continue
            spec = specs[index]
            head = len(spec.key) + 1 + len(spec.label)
            target = routines.target_cell(spec.class_name, max(8, cell_width - head - 1))
            gap = max(1, cell_width - head - len(target.text))
            pieces.append(f"[bold magenta]{spec.key}[/bold magenta] {escape(spec.label)}"
                          f"{' ' * gap}{target.markup}")
        panel.add("  ".join(pieces))


def _activity(panel: grid.Panel, plan: "layout.Plan") -> None:
    panel.rule()
    panel.add(f"[bold yellow]ACTIVITY[/bold yellow] "
              f"[dim]last {plan.log_rows} - auto-refreshing[/dim]")
    entries = logs.LOG_STORE.tail(plan.log_rows)
    if not entries:
        panel.add("[dim]waiting for engine activity...[/dim]")
        return
    for entry in entries:
        panel.add(logs.format_line(entry, sender_limit=8))


def _prompt(buffer: str) -> tuple:
    """The prompt line, with a real cursor so the visible width is honest.

    Returns ``(markup, plain)``. A reverse-video block is drawn over the last
    character (or an empty cell), which keeps the frame exactly ``width`` wide
    instead of one column short.
    """
    if buffer:
        head, tail = buffer[:-1], buffer[-1]
    else:
        head, tail = "", " "
    return (f"[bold cyan]{PROMPT}[/bold cyan] {escape(head)}"
            f"[reverse]{escape(tail)}[/reverse]",
            f"{PROMPT} {head}{tail}")


def build(bridge: "engine.EngineBridge", active_task=None, buffer: str = "",
          width: int = None, height: int = None, message: str = "") -> tuple:
    """Assemble the frame. Returns ``(markup, plan)`` without drawing anything.

    ``message`` is transient feedback (a toggle confirmation, an error) shown
    as its own row above the prompt, so quick actions never print underneath
    the frame and scroll the terminal.
    """
    width = width or console.width()
    height = height or console.height()
    inner = max(16, width - 4)
    hint_rows = len(_hints(inner))
    plan = layout.fit(width, height, len(routines.ROUTINES), hint_rows,
                      message_rows=1 if message else 0)
    panel = grid.Panel(plan.width)

    if not bridge.ready:
        state = OFFLINE_LABEL
    else:
        state = PAUSED_LABEL if bridge.paused else RUNNING_LABEL
    clock = time.strftime("%H:%M:%S")
    status = f"{state}  {clock}"
    if active_task is not None:
        status = f"{bridge.task_name(active_task)}[{bridge.run_state(active_task)}]  {clock}"

    for label, markup, plain in _status(plan, bridge):
        panel.add_row(label, markup, plain, label_width=8)

    if plan.show_routines:
        _routines(panel, plan)

    _activity(panel, plan)

    if plan.dropped:
        panel.add(f"[dim]hidden: {', '.join(plan.dropped)} - resize for more[/dim]")

    if plan.show_hints:
        for line in _hints(panel.inner_width):
            panel.add(line)

    if plan.show_message:
        panel.add(message)

    prompt_markup, prompt_plain = _prompt(buffer)
    panel.add(prompt_markup, plain=prompt_plain)

    return "\n".join(panel.frame(TITLE, status)), plan


def draw(bridge: "engine.EngineBridge", active_task=None, buffer: str = "",
         message: str = "") -> "layout.Plan":
    """Render one frame in place. Returns the layout that was used."""
    markup, plan = build(bridge, active_task, buffer, message=message)
    console.draw_frame(markup)
    return plan


# ------------------------------------------------------- reference views ---
def show_hotkeys() -> None:
    """Static table of the in-game key bindings."""
    console.banner("IN-GAME HOTKEY CONFIGURATION")
    try:
        from config import key_config_option

        table = Table(border_style="cyan", expand=True, title="Game Hotkey")
        table.add_column("Action / Skill", style="bold white", ratio=3)
        table.add_column("Assigned Key", style="bold magenta", ratio=1)
        for action, key in key_config_option.default_config.items():
            table.add_row(action, str(key).upper())
        console.print(table)
    except Exception as exc:
        console.report_exception("Could not load the key config", exc)
    console.pause()


def show_diagnostics(bridge: "engine.EngineBridge") -> None:
    """Config-cache, log-buffer and inference-backend counters."""
    console.banner("RUNTIME DIAGNOSTICS")
    store = logs.LOG_STORE
    triggers, onetime = bridge.task_counts()
    rows = [
        ("Engine", "ready" if bridge.ready else "not started"),
        ("Executor", "paused" if bridge.paused else "running"),
        ("Trigger tasks", str(triggers)),
        ("One-time tasks", str(onetime)),
        ("Log buffer", f"{store.capacity} slots, cursor {store.cursor}"),
        ("Config reads", CONFIG_STORE.stats()),
        ("YOLO backend", engine.yolo_backend_summary()),
        ("DirectML", engine.directml_summary()),
        ("Game display", game_setup.summary()),
    ]
    table = Table(border_style="cyan", expand=True)
    table.add_column("Metric", style="bold white", ratio=1)
    table.add_column("Value", ratio=2)
    for name, value in rows:
        table.add_row(name, value)
    console.print(table)
    console.pause()
