"""Application shell: command registry, live REPL loop and shutdown.

Command dispatch is a dictionary lookup built from the declarative spec tables
in :mod:`.routines`, so adding a routine or a configuration screen is a data
change plus one handler.  The previous version was a 57-branch ``if/elif``
chain in which an unrecognised key was silently swallowed.

The main loop polls the keyboard instead of blocking in ``input()``, which is
what lets the dashboard repaint itself -- updating its log block and clock
while the operator is still typing.
"""

from __future__ import annotations

import difflib
import time

from . import (config_menu, console, dashboard, engine, game_setup, keys, livestream, logs,
               routines, templates)
from .config_store import CONFIG_STORE
from .dashboard import PROMPT


class OKWWAdvancedTUI:
    #: Seconds a feedback message stays visible in the frame.
    MESSAGE_TTL = 8.0

    def __init__(self):
        self.bridge = engine.EngineBridge()
        self.running = True
        self.active_task = None
        self.live = False
        self.message = ""
        self.message_at = 0.0
        self._commands = {}
        self._build_commands()

    def _feedback(self, markup: str) -> None:
        """Show transient feedback inside the frame instead of printing it.

        Printing underneath a live frame would scroll the terminal, which is
        exactly what the single-frame contract forbids. Sub-views keep printing
        directly because they own the whole screen while they run.
        """
        self.message = markup
        self.message_at = time.monotonic()

    def _take_message(self) -> str:
        """Consume the feedback message if it has not expired yet."""
        if not self.message:
            return ""
        if time.monotonic() - self.message_at > self.MESSAGE_TTL:
            self.message = ""
            return ""
        return self.message

    # -- command registry -------------------------------------------------
    def _build_commands(self) -> None:
        commands = {}
        for spec in routines.TRIGGERS:
            commands[spec.key] = lambda spec=spec: self._toggle_trigger(spec)
        for spec in routines.ROUTINES:
            commands[spec.key] = lambda spec=spec: self._run_routine(spec)

        commands["c"] = self._configure
        commands["a"] = self._launch_annotation_gui
        commands["g"] = self._game_display
        commands["p"] = self._toggle_pause
        commands["l"] = self._watch_logs
        commands["k"] = self._show_hotkeys
        commands["v"] = self._show_diagnostics
        commands["?"] = self._show_help
        commands["r"] = self._refresh
        commands["q"] = self._quit

        commands["sweep"] = self._quick_sweep
        commands["sw"] = self._quick_sweep
        commands["track"] = self._quick_track
        commands["tr"] = self._quick_track

        commands["skip"] = self._toggle_skip_locked
        commands["skiplocked"] = self._toggle_skip_locked
        commands["locked"] = self._toggle_skip_locked

        commands["team"] = self._quick_team
        commands["teams"] = self._quick_team
        commands["autoteam"] = self._quick_team
        commands["advisor"] = self._quick_team

        for alias, target in (("cfg", "c"), ("config", "c"), ("configure", "c"),
                              ("ann", "a"), ("annotate", "a"), ("annotation", "a"),
                              ("gui", "a"), ("templates", "a"), ("template", "a"), ("markup", "a"),
                              ("studio", "a"),
                              ("game", "g"), ("display", "g"), ("graphics", "g"),
                              ("s", "p"), ("pause", "p"),
                              ("log", "l"), ("logs", "l"),
                              ("keys", "k"), ("hotkeys", "k"),
                              ("diag", "v"), ("diagnostics", "v"),
                              ("help", "?"), ("h", "?"),
                              ("refresh", "r"), ("", "r"),
                              ("quit", "q"), ("exit", "q"),
                              ("echo", "e"), ("farm", "e"),
                              ("daily", "d"),
                              ("tacet", "t"),
                              ("forgery", "f"), ("forge", "f"),
                              ("simulation", "m"), ("sim", "m"),
                              ("nightmare", "n"), ("nest", "n"),
                              ("chest", "x"), ("chests", "x"),
                              ("combat", "1"),
                              ("pick", "2"), ("loot", "2"),
                              ("dialog", "3"),
                              ("login", "4"),
                              ("travel", "5"),
                              ("mouse", "6"), ("reset", "6")):
            commands[alias] = commands[target]
        self._commands = commands

    # -- command handlers -------------------------------------------------
    def _toggle_skip_locked(self) -> None:
        current = CONFIG_STORE.get("FarmEchoTask", "Skip Locked Areas", True)
        new_val = not bool(current)
        CONFIG_STORE.update("FarmEchoTask", {"Skip Locked Areas": new_val})
        self.bridge.set_live_config("FarmEchoTask", {"Skip Locked Areas": new_val})
        state = "[bold green]ENABLED[/bold green]" if new_val else "[dim red]DISABLED[/dim red]"
        self._feedback(f"Skip Locked Areas is now {state}")

    def _toggle_trigger(self, spec) -> None:
        result = self.bridge.toggle_trigger(spec.class_name)
        if result is None:
            self._feedback(f"[bold red][!][/bold red] Trigger task not found: {spec.class_name}")
            return
        name, enabled = result
        state = "[bold green]ACTIVE[/bold green]" if enabled else "[dim red]OFF[/dim red]"
        self._feedback(f"[bold magenta]{name}[/bold magenta] is now {state}")

    def _run_routine(self, spec) -> None:
        if not self.bridge.ready:
            self._feedback("[bold red][!][/bold red] The engine is not running.")
            return
        task = self.bridge.onetime_task(spec.class_name)
        if task is None:
            self._feedback(f"[bold red][!][/bold red] Routine not available: {spec.class_name}")
            return
        if self.bridge.run_state(task) == engine.STATE_RUNNING:
            self._feedback(f"[bold yellow][*][/bold yellow] {self.bridge.task_name(task)} is already running.")
            return
        if self.bridge.paused:
            self._feedback("[bold yellow][*][/bold yellow] The executor is paused - press p to resume first.")
            return

        self.active_task = None
        dispatched = self.bridge.dispatch(spec.class_name)
        if dispatched is None:
            self._feedback(f"[bold red][!][/bold red] Could not start {spec.class_name}.")
            return
        self.active_task = dispatched
        try:
            livestream.monitor(self.bridge, dispatched)
        finally:
            # Keep showing the finished routine on the dashboard until the next
            # dispatch, then drop it so the header does not lie.
            if self.bridge.run_state(dispatched) == engine.STATE_FINISHED:
                self.active_task = None

    def _configure(self) -> None:
        config_menu.run(self.bridge)

    def _quick_sweep(self) -> None:
        options = (
            "All Overworld Bosses (Sweep)",
            "All Weekly Bosses (Sweep)",
            "All 4-Cost Bosses (Complete Sweep)",
        )
        index = config_menu.select("4-COST BOSS SWEEPS", "Sequential multi-boss farming", options)
        if not index:
            return
        boss = options[index - 1]
        values = {"Target Boss": boss}
        current_sweep = CONFIG_STORE.get("FarmEchoTask", "Sweep Count per Boss", 1)
        sweep_count = console.ask_number(
            "[bold cyan]Enter count per boss (1-50)[/bold cyan]",
            1, 50, default=int(current_sweep) if str(current_sweep).isdigit() else 1,
        )
        values["Sweep Count per Boss"] = sweep_count
        if "Weekly" in boss:
            current = CONFIG_STORE.get("FarmEchoTask", "Weekly Boss Difficulty", "80")
            console.print(f"\nWeekly domain level currently: [bold]{current}[/bold]")
            level = console.ask(f"[bold cyan]Difficulty {', '.join(routines.WEEKLY_DIFFICULTIES)} "
                                f"(Enter keeps {current}):[/bold cyan] ")
            values["Weekly Boss Difficulty"] = level if level in routines.WEEKLY_DIFFICULTIES else str(current or "80")
            values["Teleport to Boss"] = "Weekly Challenge"
        else:
            values["Teleport to Boss"] = "Boss Challenge"
        CONFIG_STORE.update("FarmEchoTask", values)
        self.bridge.set_live_config("FarmEchoTask", values)
        echo_spec = next((s for s in routines.ROUTINES if s.class_name == "FarmEchoTask"), None)
        if echo_spec:
            self._run_routine(echo_spec)

    def _quick_track(self) -> None:
        options = (
            "All 3-Cost Echoes (Guidebook Track)",
            "All 1-Cost Echoes (Guidebook Track)",
            "All 3C & 1C Echoes (Full Track)",
        )
        index = config_menu.select("GUIDEBOOK MOB TRACKING", "In-game Guidebook tracking for 3C/1C echoes", options)
        if not index:
            return
        boss = options[index - 1]
        values = {"Target Boss": boss, "Teleport to Boss": "Boss Challenge"}
        current_sweep = CONFIG_STORE.get("FarmEchoTask", "Sweep Count per Boss", 1)
        sweep_count = console.ask_number(
            "[bold cyan]Enter runs/quota multiplier (1-50)[/bold cyan]",
            1, 50, default=int(current_sweep) if str(current_sweep).isdigit() else 1,
        )
        values["Sweep Count per Boss"] = sweep_count
        CONFIG_STORE.update("FarmEchoTask", values)
        self.bridge.set_live_config("FarmEchoTask", values)
        echo_spec = next((s for s in routines.ROUTINES if s.class_name == "FarmEchoTask"), None)
        if echo_spec:
            self._run_routine(echo_spec)

    def _quick_team(self) -> None:
        from src.combat.TeamAdvisor import TeamAdvisor
        advisor = TeamAdvisor()

        options = (
            "Scan Roster & Build Optimal Rexlent Team",
            "Browse Rexlent Meta Teams (Tier S+ / S)",
            "Analyze Roster for Preferred Main DPS",
            "View Character Outro Synergies & Echoes",
        )
        index = config_menu.select("REXLENT TEAM ADVISOR", "Team scanning & meta builder", options)
        if not index:
            return

        choice = options[index - 1]
        if "Scan Roster" in choice:
            team_spec = next((s for s in routines.ROUTINES if s.class_name == "AutoTeamTask"), None)
            if team_spec:
                self._run_routine(team_spec)
        elif "Browse Rexlent Meta Teams" in choice:
            console.banner("REXLENT TOP META TEAMS", "Rexlent guide playlist tier compositions")
            for t in advisor.meta_teams[:6]:
                console.print(f"[bold green]{t['name']}[/bold green] [yellow]({t['tier']})[/yellow]")
                console.print(f"  [dim]Synergy:[/dim] {t['synergy_summary']}")
                for s in t.get("slots", []):
                    console.print(f"    Slot {s.get('slot')} [{s.get('role')}]: [bold]{s.get('character')}[/bold] | Echo: {s.get('echo_set', '')}")
                console.print("")
            console.ask("[bold cyan]Press Enter to return to dashboard...[/bold cyan]")
        elif "Analyze Roster" in choice:
            dps_options = [
                "Jinhsi", "Camellya", "Xiangli Yao", "Carlotta", "Changli", "Jiyan", "Rover (Havoc)", "Encore"
            ]
            dps_idx = config_menu.select("SELECT MAIN DPS", "Pick your carry resonator", dps_options)
            if dps_idx:
                pref_dps = dps_options[dps_idx - 1]
                teams = advisor.recommend_teams(list(advisor.characters.keys()), prefer_main_dps=pref_dps, top_n=2)
                if teams:
                    console.banner(f"OPTIMAL TEAM FOR {pref_dps.upper()}", "Synergy breakdown")
                    console.print(advisor.format_team_display(teams[0]))
                console.ask("\n[bold cyan]Press Enter to return to dashboard...[/bold cyan]")
        elif "Outro Synergies" in choice:
            console.banner("REXLENT OUTRO SYNERGY REFERENCE", "Buffer & Sub-DPS outro deepen values")
            for k, c in advisor.characters.items():
                if c.get("role") in ("SubDPS", "Healer") and c.get("outro_buff"):
                    console.print(f"[bold cyan]{c['display_name']}[/bold cyan] ({c['role']}): {c['outro_buff']}")
            console.ask("\n[bold cyan]Press Enter to return to dashboard...[/bold cyan]")

    def _game_display(self) -> None:
        game_setup.run(self.bridge)

    def _launch_annotation_gui(self) -> None:
        templates.launch_studio(self.bridge)

    def _annotation_studio(self) -> None:
        while True:
            console.banner("TEMPLATE ANNOTATION STUDIO", "capture, annotate, test and export")
            for key, label in (
                ("1", "Launch the Qt Task Annotation Studio"),
                ("2", "Capture a game screenshot"),
                ("3", "Visual ROI annotation"),
                ("4", "Manual coordinate annotation"),
                ("5", "List workspace annotations"),
                ("6", "Test a template against the live game"),
                ("7", "Merge and export templates to assets"),
                ("8", "Delete a workspace annotation"),
                ("b", "Back to the dashboard"),
            ):
                console.print(f"  [bold magenta]{key}[/bold magenta]. {label}")
            console.print(console.thin_rule(), style="dim")
            choice = console.ask("\n[bold cyan]Select option or b:[/bold cyan] ").strip().lower()
            actions = {
                "1": lambda: templates.launch_studio(self.bridge),
                "2": lambda: templates.capture_screenshot(self.bridge),
                "3": lambda: templates.annotate_roi(self.bridge),
                "4": lambda: templates.manual_annotate(self.bridge),
                "5": lambda: templates.list_annotations(self.bridge),
                "6": lambda: templates.test_live(self.bridge),
                "7": lambda: templates.export_to_assets(self.bridge),
                "8": lambda: templates.delete_annotation(self.bridge),
            }
            if choice in ("b", "q", ""):
                return
            action = actions.get(choice)
            if action is None:
                console.invalid("Unknown option.")
                continue
            try:
                action()
            except (EOFError, KeyboardInterrupt):
                return
            except Exception as exc:
                console.report_exception("Operation failed", exc)

    def _toggle_pause(self) -> None:
        paused = self.bridge.toggle_paused()
        self._feedback(f"Executor [bold yellow]{'PAUSED' if paused else 'RESUMED'}[/bold yellow]")

    def _watch_logs(self) -> None:
        livestream.show(self.bridge, self.active_task)

    def _show_hotkeys(self) -> None:
        dashboard.show_hotkeys()

    def _show_diagnostics(self) -> None:
        dashboard.show_diagnostics(self.bridge)

    def _refresh(self) -> None:
        pass

    def _quit(self) -> None:
        self.running = False

    def _show_help(self) -> None:
        console.banner("COMMAND REFERENCE")
        groups = (
            ("Triggers (Key or Name)", [
                ("1", "toggle Auto Combat (alias: combat)"),
                ("2", "toggle Auto Pick / Loot (alias: pick, loot)"),
                ("3", "toggle Auto Dialog / Skip (alias: dialog)"),
                ("4", "toggle Auto Login / Reconnect (alias: login)"),
                ("5", "toggle Fast Travel (alias: travel)"),
                ("6", "toggle Mouse Reset (alias: mouse, reset)"),
            ]),
            ("Farming Routines", [
                ("e", "run active Echo Farming routine (alias: echo, farm)"),
                ("sweep", "quick launch 4-Cost Boss Sweep (alias: sw)"),
                ("track", "quick launch Guidebook Mob Tracking (alias: tr)"),
                ("d", "run Daily Routine (alias: daily)"),
                ("t", "run Tacet Field Suppression (alias: tacet)"),
                ("f", "run Forgery Domain (alias: forgery, forge)"),
                ("m", "run Simulation Challenge (alias: simulation, sim)"),
                ("x", "run Chest Exploration Route (alias: chest, chests)"),
                ("n", "run Nightmare Nests (alias: nightmare, nest)"),
            ]),
            ("Controls & Tools", [
                ("c", "configure routine targets (alias: config, cfg)"),
                ("skip", "toggle skip locked areas (alias: skiplocked, locked)"),
                ("a", "template annotation studio (alias: gui, annotate)"),
                ("g", "game display profile & resolution (alias: display)"),
                ("p", "pause / resume automation (alias: pause, s)"),
                ("l", "follow live log stream (alias: logs, log)"),
                ("k", "in-game hotkey reference (alias: keys)"),
                ("v", "runtime diagnostics (alias: diag)"),
                ("?", "this help command reference (alias: help)"),
                ("q", "quit application (alias: exit)"),
            ]),
        )
        for title, rows in groups:
            console.print(f"[bold yellow]{title}[/bold yellow]")
            for key, label in rows:
                console.print(f"  [bold magenta]{key:>6}[/bold magenta]. {label}")
            console.print()
        console.pause("Press Enter to return...")

    def _on_unknown(self, command: str) -> None:
        suggestions = difflib.get_close_matches(command, list(self._commands), n=3, cutoff=0.5)
        hint = f" Did you mean: {', '.join(suggestions)}?" if suggestions else " Press ? for help."
        self._feedback(f"[bold red][!][/bold red] Unknown command '{command}'.{hint}")

    def _dispatch(self, command: str) -> bool:
        """Run one command. Returns ``False`` when the app should stop."""
        # A submitted line supersedes whatever feedback is showing.
        self.message = ""
        handler = self._commands.get(command)
        if handler is None:
            if command:
                self._on_unknown(command)
            return True
        try:
            handler()
        except (EOFError, KeyboardInterrupt):
            return False
        except Exception as exc:
            self._feedback(f"[bold red][x][/bold red] Command '{command}' failed: "
                           f"{exc.__class__.__name__}: {exc}")
        return self.running

    # -- main loop --------------------------------------------------------
    def _blocking_loop(self) -> None:
        """Fallback for a non-interactive stdin, where no key can ever arrive."""
        while self.running:
            dashboard.draw(self.bridge, self.active_task, message=self._take_message())
            try:
                command = console.ask(f"\n{PROMPT} ").lower()
            except EOFError:
                return
            if not self._dispatch(command):
                return

    def _live_loop(self, reader: "keys.KeyReader") -> None:
        """Repaint on a timer while polling for keys, so the frame stays live.

        The frame is fully redrawn in place, so the log block keeps updating
        and the terminal never scrolls.
        """
        editor = keys.LineEditor(reader)
        seen_cursor = -1
        last_paint = 0.0
        try:
            while self.running:
                console.refresh_size()
                cursor = logs.LOG_STORE.cursor
                now = time.monotonic()
                if (cursor != seen_cursor or now - last_paint >= dashboard.REFRESH_INTERVAL):
                    dashboard.draw(self.bridge, self.active_task, editor.text,
                                   message=self._take_message())
                    seen_cursor = cursor
                    last_paint = now

                key = reader.poll()
                if key is None:
                    time.sleep(0.03)
                    continue
                if key == keys.CTRL_C:
                    raise KeyboardInterrupt
                line = editor.feed(key)
                if line is None:
                    # Redraw right away so typed characters echo without lag.
                    dashboard.draw(self.bridge, self.active_task, editor.text,
                                   message=self._take_message())
                    last_paint = time.monotonic()
                    continue
                # A sub-view may have taken over the screen; repaint immediately.
                seen_cursor = -1
                if not self._dispatch(line.lower()):
                    return
        finally:
            reader.close()

    def run(self) -> None:
        console.print("[bold cyan]Starting wuwa-auto...[/bold cyan]")
        try:
            self.bridge.start()
        except Exception as exc:
            console.error(f"The OK-WW engine failed to start: {exc.__class__.__name__}: {exc}")
            return
        console.countdown(0.6)

        reader = keys.KeyReader()
        try:
            self.live = reader.interactive
            if self.live:
                self._live_loop(reader)
            else:
                console.warn("No interactive keyboard - falling back to line input")
                self._blocking_loop()
        except KeyboardInterrupt:
            console.notice("\n[yellow]Interrupted.[/yellow]")
        finally:
            self.live = False
            self.shutdown()

    def shutdown(self) -> None:
        if not self.running and self.bridge.ok is None and self.bridge.executor is None:
            return
        self.running = False
        console.notice("\n[bold yellow]Shutting down wuwa-auto...[/bold yellow]")
        self.bridge.shutdown()


def run_tui() -> None:
    OKWWAdvancedTUI().run()
