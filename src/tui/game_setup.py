"""The "game display" screens: apply the profile, resize, launch, verify.

Everything here funnels through :mod:`.game_display`, which owns the settings
file. The screens only decide what to ask for and how to report the answer.
"""

from __future__ import annotations

import os

from . import console, game_display as gd
from .config_menu import menu
from .console import escape

BACK = "b"

#: Profiles offered on the setup screen. The first is the default.
#:
#: The last one also drops ``sg.ResolutionQuality``, the game's internal render
#: scale. It is kept out of the default because this app finds its targets by
#: template matching against the captured image, and a soft internal render
#: makes those matches less reliable -- so it is offered, but not assumed.
PROFILES = (
    gd.DisplayProfile(1280, 720, gd.WINDOW_MODE_WINDOWED, 0, 0, 100,
                      label="1280x720 windowed, lowest effects (sharp render)"),
    gd.DisplayProfile(1920, 1080, gd.WINDOW_MODE_WINDOWED, 0, 0, 100,
                      label="1920x1080 windowed, lowest effects (sharp render)"),
    gd.DisplayProfile(1280, 720, gd.WINDOW_MODE_BORDERLESS, 0, 0, 100,
                      label="1280x720 borderless, lowest effects (sharp render)"),
    gd.DisplayProfile(1280, 720, gd.WINDOW_MODE_WINDOWED, 0, 0, 70,
                      label="1280x720 windowed, lowest + soft render (may hurt matching)"),
)


def _state_line():
    state = gd.read_state()
    if not state:
        return "[bold red]settings file not found[/bold red]"
    return f"[green]{escape(gd.summarise_state(state))}[/green]"


def _run(bridge, rows, subtitle):
    menu("GAME DISPLAY PROFILE", rows)
    choice = console.ask(f"\n[bold cyan]Select or {BACK} to go back:[/bold cyan] ").strip().lower()
    return choice


def _show_settings(pause=True):
    console.banner("CURRENT GAME DISPLAY SETTINGS")
    state = gd.read_state()
    if not state:
        console.invalid("GameUserSettings.ini not found. Is the game installed?")
    else:
        console.notice(f"[bold]File   :[/bold] {escape(state['path'])}")
        console.notice(f"[bold]State  :[/bold] {escape(gd.summarise_state(state))}")
        levels = state.get("scalability") or {}
        if levels:
            console.print("[bold]Scalability groups[/bold]")
            for key in sorted(levels):
                value = levels[key]
                style = "green" if not value else "yellow"
                console.print(f"  {escape(key):38} [dim]=[/dim] [{style}]{value}[/{style}]")
        backups = gd.list_backups(state.get("path"))
        console.print(f"\n[dim]backups kept: {len(backups)}[/dim]")
    if pause:
        console.pause()


def _apply(bridge, profile):
    console.banner("APPLY DISPLAY PROFILE", profile.describe())
    console.notice(f"Target : [bold]{escape(profile.describe())}[/bold]")
    console.notice(f"File   : {escape(gd.find_settings_file() or 'not found')}")
    if not console.confirm("Write these settings?", default=True):
        return
    ok, message = gd.apply_profile(profile)
    if ok:
        console.success(message)
        console.notice(f"[dim]Now: {escape(gd.summarise_state(gd.read_state()))}[/dim]")
        if gd.is_game_running():
            console.warn("The game is running and will overwrite this on exit. "
                         "Close it and re-apply, or use 'resize the live window'.")
    else:
        console.invalid(message)
    console.pause()


def _resize(bridge, profile):
    console.banner("RESIZE THE LIVE GAME WINDOW", profile.describe())
    ok, message = gd.resize_running_window(bridge, profile)
    (console.success if ok else console.invalid)(message)
    if ok and not console.confirm("Also write the profile to the settings file?", default=False):
        return
    if ok:
        applied, detail = gd.apply_profile(profile)
        (console.success if applied else console.invalid)(detail)
    console.pause()


def _launch(bridge, rhi):
    console.banner("LAUNCH THE GAME", gd.RHI_LABELS.get(rhi, rhi))
    state = gd.read_state()
    if state:
        console.notice(f"Current profile: [dim]{escape(gd.summarise_state(state))}[/dim]")
    args = gd.rhi_args(rhi)
    console.notice(f"Launch flags: [dim]{escape(' '.join(args)) if args else '(none)'}[/dim]")
    if not console.confirm(f"Launch with {rhi}?", default=True):
        return
    ok, message = gd.launch(rhi)
    (console.success if ok else console.invalid)(message)
    console.pause()


def _choose_rhi(bridge):
    console.banner("LAUNCH THE GAME", "choose the graphics API")
    for index, rhi in enumerate(gd.RHI_CHOICES, 1):
        console.notice(f"  [bold magenta]{index}[/bold magenta]. {escape(gd.RHI_LABELS[rhi])}")
    console.print("[dim]DX11 normally costs the least CPU, which matters for a capture-bound "
                  "automation loop.[/dim]")
    choice = console.ask(f"\n[bold cyan]1-{len(gd.RHI_CHOICES)} or {BACK}:[/bold cyan] ").strip().lower()
    if not choice.isdigit() or not 1 <= int(choice) <= len(gd.RHI_CHOICES):
        return
    _launch(bridge, gd.RHI_CHOICES[int(choice) - 1])


def _choose_profile(bridge):
    console.banner("APPLY DISPLAY PROFILE", "choose a target")
    for index, profile in enumerate(PROFILES, 1):
        current = ""
        state = gd.read_state()
        if state and (state.get("width"), state.get("height")) == (profile.width, profile.height):
            current = "  [dim](matches the current resolution)[/dim]"
        console.notice(f"  [bold magenta]{index}[/bold magenta]. "
                       f"{escape(profile.label)}{current}")
    console.print("[dim]The window size is where the saving matters. Internal render scale is left "
                  "sharp by default because template matching depends on a clear capture.[/dim]")
    choice = console.ask(f"\n[bold cyan]1-{len(PROFILES)} or {BACK}:[/bold cyan] ").strip().lower()
    if not choice.isdigit() or not 1 <= int(choice) <= len(PROFILES):
        return
    _apply(bridge, PROFILES[int(choice) - 1])


def _restore(bridge):
    console.banner("RESTORE THE LAST SETTINGS BACKUP")
    path = gd.find_settings_file()
    backups = gd.list_backups(path)
    if not backups:
        console.invalid("No backups have been taken yet.")
        console.pause()
        return
    console.notice(f"Newest backup: [bold]{escape(os.path.basename(backups[0]))}[/bold]")
    if not console.confirm("Restore it over the current settings?", default=False):
        return
    name = gd.restore_backup(path)
    if name:
        console.success(f"Restored {name}")
    console.pause()


def run(bridge):
    """The ``g`` menu."""
    while True:
        state = gd.read_state()
        running = gd.is_game_running()
        rows = [
            ("1", "Apply a display profile to the settings file"),
            ("2", "Resize the live game window now"),
            ("3", "Launch the game (choose DX11 / DX12 / default)"),
            ("4", "Show the current game display settings"),
            ("5", "Restore the last settings backup"),
            (BACK, "Back to the dashboard"),
        ]
        menu("GAME DISPLAY PROFILE", rows)
        console.print(f"  [bold]File   :[/bold] {escape(state.get('path', 'not found'))}")
        console.print(f"  [bold]State  :[/bold] {escape(gd.summarise_state(state))}")
        console.print(f"  [bold]Game   :[/bold] "
                      f"{'[bold green]running[/bold green]' if running else '[dim]not running[/dim]'}")
        if running:
            console.print("  [yellow]settings writes are blocked while the game is running; "
                          "use option 2 instead[/yellow]")
        console.print(console.thin_rule(), style="dim")
        choice = console.ask(f"\n[bold cyan]Select option or {BACK}:[/bold cyan] ").strip().lower()
        if choice in (BACK, "q", ""):
            return
        try:
            if choice == "1":
                _choose_profile(bridge)
            elif choice == "2":
                _resize(bridge, gd.DEFAULT_PROFILE)
            elif choice == "3":
                _choose_rhi(bridge)
            elif choice == "4":
                _show_settings()
            elif choice == "5":
                _restore(bridge)
            else:
                console.invalid("Unknown option.")
        except (EOFError, KeyboardInterrupt):
            return
        except Exception as exc:
            console.report_exception("Game display operation failed", exc)
            console.pause()


def summary() -> str:
    """One line for the diagnostics view."""
    state = gd.read_state()
    if not state:
        return "settings file not found"
    running = "game running" if gd.is_game_running() else "game stopped"
    return f"{gd.summarise_state(state)} ({running})"
