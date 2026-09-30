"""Unit tests for the wuwa-auto terminal interface.

Covers the parts of the TUI that can be exercised without a running engine:
the log ring buffer, the config cache, the engine task index, the grid
renderer, target formatting, the dashboard frame and the command registry.

    python tests/test_tui.py
"""

import io
import os
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from rich.console import Console
from rich.text import Text

from src.tui import app as app_module
from src.tui import config_menu, config_store, console as tui_console
from src.tui import dashboard, engine, grid, keys, logs, routines
from src.tui.config_store import TaskConfigStore

ELLIPSIS = "…"


class FakeTask:
    def __init__(self, name, running=False, enabled=False):
        self.name = name
        self.running = running
        self._enabled = enabled
        self.config = {}

    @property
    def enabled(self):
        return self._enabled

    def enable(self):
        self._enabled = True

    def disable(self):
        self._enabled = False


class FakeExecutor:
    def __init__(self, onetime=(), trigger=()):
        self.onetime_tasks = list(onetime)
        self.trigger_tasks = list(trigger)
        self.paused = False


class FakeBridge(engine.EngineBridge):
    """The real bridge with a stand-in executor, so the index code is exercised."""

    def __init__(self, onetime=(), trigger=()):
        super().__init__()
        self.executor = FakeExecutor(onetime, trigger)
        self.ok = None

    def device_status(self):
        return "[bold green]Connected[/bold green]"

    def party_status(self):
        return "[dim]Standby[/dim]"

    ready = True
    paused = False


def plain(text):
    return Text.from_markup(text).plain


class LogStoreTests(unittest.TestCase):
    def test_tail_returns_the_newest_entries(self):
        store = logs.LogStore(capacity=5)
        for i in range(5):
            store.append("INFO", "Test", f"message {i}")
        self.assertEqual([e.message for e in store.tail(2)], ["message 3", "message 4"])

    def test_saturated_buffer_still_delivers_new_lines(self):
        """The old stream diffed on len(deque), which pins at maxlen forever."""
        store = logs.LogStore(capacity=5)
        for i in range(5):
            store.append("INFO", "Test", f"message {i}")
        cursor = store.cursor
        for i in range(5, 12):
            store.append("INFO", "Test", f"message {i}")
        fresh = store.since(cursor)
        # 7 arrived, 5 fit; the two that scrolled out are reported as one line.
        self.assertEqual(len(fresh), 6)
        self.assertIn("scrolled out", fresh[0].message)
        self.assertEqual(fresh[-1].message, "message 11")

    def test_dropped_entries_are_reported_not_hidden(self):
        store = logs.LogStore(capacity=3)
        for i in range(10):
            store.append("INFO", "Test", f"m{i}")
        fresh = store.since(store.cursor - 10)
        self.assertTrue(any("scrolled out" in e.message for e in fresh))

    def test_since_is_idempotent(self):
        store = logs.LogStore(capacity=8)
        cursor = store.cursor
        store.append("INFO", "Test", "once")
        first = store.since(cursor)
        self.assertEqual(store.since(cursor), first)
        self.assertEqual(store.since(store.cursor), [])

    def test_level_styles(self):
        self.assertEqual(logs.LogEntry(1, "00:00:00", "ERROR", "X", "m").style(), "red")
        self.assertEqual(logs.LogEntry(1, "00:00:00", "WARNING", "X", "m").style(), "yellow")
        self.assertEqual(logs.LogEntry(1, "00:00:00", "DEBUG", "X", "m").style(), "dim")

    def test_sender_is_truncated_for_display(self):
        line = logs.format_line(logs.LogEntry(1, "00:00:00", "INFO", "AVeryLongSenderName", "m"),
                                sender_limit=8)
        self.assertEqual(line.count(ELLIPSIS), 1)

    def test_parses_the_ok_script_log_format(self):
        # '%(asctime)s %(levelname)s %(threadName)s %(message)s', message built
        # by Logger as '<TaskName>:<text>'.
        real = "2026-09-29 12:00:00,123 INFO MainThread FarmEchoTask: started farming"
        self.assertEqual(logs.split_sender(real), ("FarmEchoTask", "started farming"))

    def test_colons_inside_the_body_survive(self):
        self.assertEqual(logs.split_sender("t W MainThread X: a: b: c")[1], "a: b: c")

    def test_unformatted_message_keeps_its_text(self):
        self.assertEqual(logs.split_sender("plain message"), ("Engine", "plain message"))

    def test_noise_filter(self):
        self.assertTrue(logs.is_noise("RefreshAdb x"))
        self.assertFalse(logs.is_noise("Combat started"))

    def test_timestamp_is_stable_within_a_second(self):
        first = logs.timestamp()
        self.assertEqual(logs.timestamp(), first)


class ConfigStoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = TaskConfigStore(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_missing_file_is_empty(self):
        self.assertEqual(self.store.load("Nope"), {})

    def test_round_trip(self):
        self.store.save("Demo", {"A": 1})
        self.assertEqual(self.store.load("Demo"), {"A": 1})

    def test_repeat_reads_are_served_from_cache(self):
        self.store.save("Demo", {"A": 1})
        for _ in range(20):
            self.store.load("Demo")
        self.assertGreater(self.store.hits, 15)

    def test_load_returns_a_mutable_copy(self):
        self.store.save("Demo", {"A": 1})
        first = self.store.load("Demo")
        first["A"] = 999
        self.assertEqual(self.store.load("Demo"), {"A": 1})

    def test_update_merges(self):
        self.store.update("Demo", {"A": 1})
        self.store.update("Demo", {"B": 2})
        self.assertEqual(self.store.load("Demo"), {"A": 1, "B": 2})

    def test_external_edit_invalidates_the_cache(self):
        self.store.save("Demo", {"A": 1})
        self.store.load("Demo")
        path = os.path.join(self._tmp.name, "Demo.json")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write('{"A": 99}')
        os.utime(path, (time_future(), time_future()))
        self.assertEqual(self.store.load("Demo"), {"A": 99})

    def test_invalidate_forces_a_reparse(self):
        self.store.save("Demo", {"A": 1})
        self.store.load("Demo")
        before = self.store.misses
        self.store.invalidate()
        self.store.load("Demo")
        self.assertEqual(self.store.misses, before + 1)

    def test_no_temp_files_are_left_behind(self):
        self.store.save("Demo", {"A": 1})
        leftovers = [n for n in os.listdir(self._tmp.name) if n.startswith(".")]
        self.assertEqual(leftovers, [])


def time_future():
    import time

    return time.time() + 5


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.echo = FakeTask("FarmEchoTask", enabled=True)
        self.combat = FakeTask("AutoCombatTask")
        self.bridge = FakeBridge(onetime=[self.echo], trigger=[self.combat])

    def test_enabled_but_not_running_is_queued(self):
        """An enabled task has not necessarily finished; it may not have started."""
        state = engine.EngineBridge.run_state(None, FakeTask("T", enabled=True))
        self.assertEqual(state, engine.STATE_QUEUED)

    def test_run_states(self):
        run_state = engine.EngineBridge.run_state
        self.assertEqual(run_state(None, FakeTask("T", running=True, enabled=True)),
                         engine.STATE_RUNNING)
        self.assertEqual(run_state(None, FakeTask("T", running=False, enabled=False)),
                         engine.STATE_FINISHED)
        self.assertEqual(run_state(None, None), engine.STATE_IDLE)

    def test_finds_tasks_by_class_and_name(self):
        self.assertIs(self.bridge.onetime_task("FarmEchoTask"), self.echo)
        self.assertIs(self.bridge.trigger_task("AutoCombatTask"), self.combat)
        self.assertIsNone(self.bridge.find("Nope"))

    def test_trigger_and_onetime_lookup_do_not_bleed(self):
        self.assertIsNone(self.bridge.onetime_task("AutoCombatTask"))
        self.assertIsNone(self.bridge.trigger_task("FarmEchoTask"))

    def test_index_rebuilds_when_the_task_lists_change(self):
        self.bridge.executor.trigger_tasks.append(FakeTask("NewTask"))
        self.assertIsNotNone(self.bridge.find("NewTask"))

    def test_task_counts(self):
        self.assertEqual(self.bridge.task_counts(), (1, 1))

    def test_toggle_trigger_flips_and_reports(self):
        bridge = engine.EngineBridge()
        bridge.executor = FakeExecutor(trigger=[FakeTask("AutoCombatTask")])
        self.assertEqual(bridge.toggle_trigger("AutoCombatTask"), ("AutoCombatTask", True))
        self.assertEqual(bridge.toggle_trigger("AutoCombatTask"), ("AutoCombatTask", False))

    def test_toggle_missing_trigger_returns_none(self):
        bridge = engine.EngineBridge()
        bridge.executor = FakeExecutor()
        self.assertIsNone(bridge.toggle_trigger("Nope"))


class PickyConfig(dict):
    """Mimics ok-script's Config, whose __setitem__ silently drops invalid keys."""

    def __setitem__(self, key, value):
        if key in self:
            super().__setitem__(key, value)


class LiveConfigTests(unittest.TestCase):
    def test_rejected_keys_are_reported(self):
        task = FakeTask("PickyTask", enabled=True)
        task.config = PickyConfig({"Known": "old"})
        bridge = FakeBridge(onetime=[task])
        self.assertEqual(bridge.set_live_config("PickyTask", {"Known": "new", "Bogus": 1}),
                         ["Bogus"])
        self.assertEqual(task.config["Known"], "new")

    def test_no_engine_means_everything_is_rejected(self):
        self.assertEqual(engine.EngineBridge().set_live_config("X", {"a": 1}), ["a"])


class GridTests(unittest.TestCase):
    def render(self, rows, widths, justifies=None):
        columns = len(widths)
        return grid.render_grid(
            "Title", ["A", "B", "C"][:columns], rows, widths,
            [""] * columns, justifies or ["left"] * columns)

    def test_frame_width_is_exact(self):
        block = self.render([[grid.cell("1", "bold magenta"), grid.cell("Auto Combat"),
                              grid.cell("[ON]", "green")]], [4, 14, 8],
                            ["center", "left", "center"])
        lines = [plain(line) for line in block.splitlines()]
        # The title is centred and deliberately not right-padded.
        self.assertEqual({len(line) for line in lines[1:]}, {36})

    def test_borders_are_drawn(self):
        lines = [plain(line) for line in self.render([["1", "x", "y"]], [4, 4, 4]).splitlines()]
        self.assertTrue(lines[1].startswith("\u250c"))
        self.assertTrue(lines[-1].startswith("\u2514"))

    def test_title_is_centred(self):
        lines = [plain(line) for line in self.render([["1", "x", "y"]], [4, 4, 4]).splitlines()]
        # frame = 3 columns * (4 content + 2 padding) + 3 separators + 2 edges
        self.assertEqual(lines[0].index("Title"), (22 - 5) // 2)

    def test_overlong_cells_are_clipped(self):
        block = self.render([[grid.cell("x" * 40, ""), "y", "z"]], [4, 14, 8])
        self.assertTrue(any(ELLIPSIS in plain(line) for line in block.splitlines()))
        self.assertEqual({len(plain(l)) for l in block.splitlines()[1:]}, {36})

    def test_cell_text_survives(self):
        block = self.render([["1", "Auto Combat", "[ON]"]], [4, 14, 8])
        self.assertTrue(any("Auto Combat" in plain(line) for line in block.splitlines()))


class TargetFormattingTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._saved = (config_store.CONFIG_STORE, routines.CONFIG_STORE)
        self.store = TaskConfigStore(self._tmp.name)
        config_store.CONFIG_STORE = self.store
        routines.CONFIG_STORE = self.store

    def tearDown(self):
        config_store.CONFIG_STORE, routines.CONFIG_STORE = self._saved
        self._tmp.cleanup()

    def test_weekly_boss_shows_name_and_level(self):
        self.store.update("FarmEchoTask", {"Target Boss": "Scar (Weekly)",
                                           "Weekly Boss Difficulty": "70"})
        cell = routines.target_cell("FarmEchoTask")
        self.assertEqual(cell.text, "Scar (Lv70)")

    def test_manual_location_boss(self):
        self.store.update("FarmEchoTask", {"Target Boss": "Current Location (No Teleport)"})
        self.assertEqual(routines.target_cell("FarmEchoTask").text, "Current Pos")

    def test_sweep_boss_shows_short_name_and_count(self):
        self.store.update("FarmEchoTask", {"Target Boss": "All Overworld Bosses (Sweep)",
                                           "Sweep Count per Boss": 2})
        cell = routines.target_cell("FarmEchoTask")
        self.assertEqual(cell.text, "All Overworld (x2)")

    def test_guidebook_track_shows_short_name_and_count(self):
        self.store.update("FarmEchoTask", {"Target Boss": "All 3-Cost Echoes (Guidebook Track)",
                                           "Sweep Count per Boss": 1})
        cell = routines.target_cell("FarmEchoTask")
        self.assertEqual(cell.text, "3-Cost Track (x1)")

    def test_numbered_choices_are_shortened(self):
        self.store.update("TacetTask",
                          {"Which Tacet Suppression to Farm": routines.FALLBACK_TACET[2]})
        self.assertEqual(routines.target_cell("TacetTask").text, "Port City Guixu")

    def test_challenge_choices_keep_the_primary_material(self):
        self.store.update("ForgeryTask",
                          {"Which Forgery Challenge to Farm": routines.FALLBACK_FORGERY[1]})
        self.assertEqual(routines.target_cell("ForgeryTask").text, "Port City Guixu (Pistols)")

    def test_unknown_task_renders_a_placeholder(self):
        self.assertEqual(routines.target_cell("Nope").text, "Default")

    def test_missing_config_file_still_renders(self):
        self.assertEqual(routines.target_cell("NightmareNestTask").text, "All Configured Nests")

    def test_limit_clips_the_value(self):
        self.store.update("ForgeryTask",
                          {"Which Forgery Challenge to Farm": routines.FALLBACK_FORGERY[1]})
        self.assertLessEqual(len(routines.target_cell("ForgeryTask", 6).text), 6)

    def test_config_values_cannot_inject_markup(self):
        self.store.update("ChestExplorationTask", {"Region Route": "[bold red]not a tag[/]"})
        cell = routines.target_cell("ChestExplorationTask")
        self.assertTrue(cell.text.startswith("[bold red]not a tag[/]"))
        plain_out = io.StringIO()
        Console(file=plain_out, width=80).print(cell.markup)
        self.assertIn("[bold red]not a tag[/]", plain_out.getvalue())
        colour_out = io.StringIO()
        Console(file=colour_out, width=80, force_terminal=True,
                color_system="truecolor").print(cell.markup)
        self.assertNotIn("31m", colour_out.getvalue())


class CommandRegistryTests(unittest.TestCase):
    def setUp(self):
        self.app = app_module.OKWWAdvancedTUI.__new__(app_module.OKWWAdvancedTUI)
        self.app.running = True
        self.app.active_task = None
        self.app.live = False
        self.app.message = ""
        self.app.message_at = 0.0
        self.app._commands = {}
        app_module.OKWWAdvancedTUI._build_commands(self.app)

    def test_digits_map_to_triggers(self):
        for digit in "123456":
            with self.subTest(key=digit):
                self.assertIn(digit, self.app._commands)

    def test_letters_map_to_routines(self):
        for letter in "edtfmnx":
            with self.subTest(key=letter):
                self.assertIn(letter, self.app._commands)

    def test_aliases_resolve(self):
        self.assertIs(self.app._commands["exit"], self.app._commands["q"])
        self.assertIs(self.app._commands[""], self.app._commands["r"])
        self.assertIs(self.app._commands["diag"], self.app._commands["v"])
        self.assertIs(self.app._commands["annotate"], self.app._commands["a"])
        self.assertIs(self.app._commands["gui"], self.app._commands["a"])
        self.assertIs(self.app._commands["echo"], self.app._commands["e"])
        self.assertIs(self.app._commands["daily"], self.app._commands["d"])
        self.assertIs(self.app._commands["combat"], self.app._commands["1"])
        self.assertIs(self.app._commands["loot"], self.app._commands["2"])
        self.assertIn("sweep", self.app._commands)
        self.assertIn("track", self.app._commands)

    def test_d_maps_to_daily_task_routine(self):
        self.assertIn("d", self.app._commands)
        self.assertIsNot(self.app._commands["d"], self.app._commands["v"])

    def test_unknown_key_is_unmapped(self):
        self.assertNotIn("9", self.app._commands)

    def test_unknown_command_goes_to_the_frame_not_stdout(self):
        self.assertTrue(self.app._dispatch("9"))
        self.assertIn("Unknown command", self.app.message)
        self.assertIn("9", self.app.message)

    def test_unknown_command_suggests_close_matches(self):
        self.assertTrue(self.app._dispatch("exi"))
        self.assertIn("exit", self.app.message)

    def test_dispatch_clears_stale_feedback_on_submit(self):
        self.app.message = "old news"
        self.assertTrue(self.app._dispatch("zzz-unknown"))
        self.assertNotIn("old news", self.app.message)

    def test_handler_errors_become_frame_feedback(self):
        self.app._commands["boom"] = lambda: (_ for _ in ()).throw(RuntimeError("kaput"))
        self.assertTrue(self.app._dispatch("boom"))
        self.assertIn("kaput", self.app.message)

    def test_feedback_expires(self):
        import time

        self.app._feedback("hello")
        self.assertEqual(self.app._take_message(), "hello")
        self.app.message_at = time.monotonic() - app_module.OKWWAdvancedTUI.MESSAGE_TTL - 1
        self.assertEqual(self.app._take_message(), "")
        self.assertEqual(self.app.message, "")

    def test_toggle_pause_reports_in_frame(self):
        from src.tui import engine as engine_module

        bridge = engine_module.EngineBridge()
        bridge.executor = FakeExecutor()
        self.app.bridge = bridge
        self.app._toggle_pause()
        self.assertIn("PAUSED", self.app.message)
        self.assertTrue(bridge.paused)
        self.app._toggle_pause()
        self.assertIn("RESUMED", self.app.message)

    def test_config_menu_exposes_every_screen(self):
        self.assertEqual(sorted(config_menu.HANDLERS_BY_KEY), ["1", "2", "3", "4", "5", "6"])
        for handler in config_menu.HANDLERS_BY_KEY.values():
            self.assertTrue(callable(handler))


class KeyReaderTests(unittest.TestCase):
    def test_non_interactive_stdin_is_reported(self):
        reader = keys.KeyReader()
        try:
            self.assertIsInstance(reader.interactive, bool)
            self.assertIsNone(reader.poll())
            self.assertEqual(reader.wait(0.05), "")
        finally:
            reader.close()


class AppLoopTests(unittest.TestCase):
    """The live loop, driven by raw msvcrt-style bytes end to end.

    Regression test for the Windows input crash: ``msvcrt.getch()`` yields
    ``bytes``, and the loop used to hand them straight to a ``str``-only
    editor. Scripted keys toggle pause and then quit; anything raising (or a
    keypress that never decodes) fails the test.
    """

    def test_live_loop_decodes_bytes_toggles_and_quits(self):
        from src.tui import keys as keys_module

        bridge = FakeBridge()
        bridge.start = lambda: None
        shut = []
        bridge.shutdown = lambda: shut.append(True)

        app = app_module.OKWWAdvancedTUI.__new__(app_module.OKWWAdvancedTUI)
        app.bridge = bridge
        app.running = True
        app.active_task = None
        app.live = False
        app.message = ""
        app.message_at = 0.0
        app._commands = {}
        app_module.OKWWAdvancedTUI._build_commands(app)

        # Bytes exactly as msvcrt.getch() would deliver them; the real
        # KeyReader must decode them, or the loop spins forever.
        class FakeMsvcrt:
            def __init__(self):
                self.chunks = [b"p", b"\r", b"q", b"\r"]

            def kbhit(self):
                return bool(self.chunks)

            def getch(self):
                return self.chunks.pop(0)

        real_msvcrt = keys_module.msvcrt
        real_reader = keys_module.KeyReader
        keys_module.msvcrt = FakeMsvcrt()

        def factory(*args, **kwargs):
            reader = real_reader()
            reader.interactive = True  # stdin is not a tty under test
            return reader

        keys_module.KeyReader = factory
        try:
            app.run()
        finally:
            keys_module.msvcrt = real_msvcrt
            keys_module.KeyReader = real_reader

        self.assertFalse(app.running)
        self.assertTrue(bridge.executor.paused, "the 'p' keypress must have toggled pause")
        self.assertTrue(shut, "shutdown must run on quit")


if __name__ == "__main__":
    unittest.main(verbosity=2)
