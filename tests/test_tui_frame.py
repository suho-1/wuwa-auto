"""Frame geometry: the dashboard must always be exactly one screen.

The contract is strict, because anything else scrolls:

* every emitted line is exactly ``width`` cells wide, so the frame's closing
  edge never wraps;
* the number of emitted lines is at most the terminal height;
* the visible text of a line always matches the text its padding was computed
  from, so a styled value cannot shift the right-hand border.

These run the real frame builder over a matrix of terminal sizes and buffer
contents.  Several of these checks exist because they caught a real bug during
development: a double-framed panel that was two cells too wide, a prompt whose
cursor glyph was counted but not drawn, and a status row whose markup and
visible text disagreed by one character per trigger.
"""

import io
import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from rich.console import Console
from rich.text import Text

from src.tui import console as tui_console, dashboard, engine, grid, layout, logs

WIDTHS = (40, 48, 56, 64, 72, 80, 100, 120, 160, 200)
HEIGHTS = (8, 10, 12, 14, 16, 20, 24, 30, 40, 60)
BUFFERS = ("", "q", "config")


class FakeTask:
    def __init__(self, name, enabled=False):
        self.name = name
        self._enabled = enabled

    @property
    def enabled(self):
        return self._enabled


class FakeBridge(engine.EngineBridge):
    def __init__(self, triggers=()):
        super().__init__()
        self.executor = type("E", (), {"trigger_tasks": list(triggers),
                                        "onetime_tasks": [], "paused": False})()
        self.ok = None

    def device_status(self):
        return "[bold green]Connected[/bold green] (HWND: 336876 | 1920x1080)"

    def party_status(self):
        return "Slot 1: [bold cyan]Chiya[/bold cyan] | Slot 2: [bold cyan]Zhezhi[/bold cyan]"


def render(markup: str, width: int) -> list:
    """Render a frame the way production does and return its plain lines."""
    sink = io.StringIO()
    # Pin height and disable legacy_windows: Rich's dumb-terminal path (TERM=dumb
    # / FORCE_COLOR) ignores a lone width and forces 80 columns, and Windows
    # legacy mode shrinks every frame by one cell.
    Console(file=sink, width=width, height=60, highlight=False, soft_wrap=False,
            legacy_windows=False).print(markup, end="")
    return [Text.from_markup(line).plain for line in sink.getvalue().split("\n")]

class FrameGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bridge = FakeBridge([FakeTask("AutoCombatTask", True)])
        for level, sender, message in (
            ("INFO", "CombatCheck", "skill rotation started"),
            ("WARN", "TacetTask", "no tacet found, retrying"),
            ("INFO", "ChestExplorationTask", "stop 12 reached"),
            ("ERROR", "FarmEchoTask", "teleport failed"),
            ("INFO", "AutoCombatTask", "combo finisher"),
        ):
            logs.LOG_STORE.append(level, sender, message)
        cls.saved = (tui_console.console, tui_console.detect_size)

    @classmethod
    def tearDownClass(cls):
        tui_console.console, tui_console.detect_size = cls.saved

    def frame(self, width, height, buffer="", message=""):
        tui_console.detect_size = lambda: (width, height)
        markup, plan = dashboard.build(self.bridge, None, buffer, width=width,
                                       height=height, message=message)
        return markup, plan, render(markup, width)

    def test_every_line_is_exactly_the_terminal_width(self):
        for width in WIDTHS:
            for height in HEIGHTS:
                for buffer in BUFFERS:
                    with self.subTest(width=width, height=height, buffer=buffer):
                        _, _, lines = self.frame(width, height, buffer)
                        widths = {len(line) for line in lines}
                        self.assertEqual(widths, {width}, f"line widths {sorted(widths)}")

    def test_frame_never_exceeds_the_terminal_height(self):
        for width in WIDTHS:
            for height in HEIGHTS:
                for buffer in BUFFERS:
                    with self.subTest(width=width, height=height, buffer=buffer):
                        _, _, lines = self.frame(width, height, buffer)
                        self.assertLessEqual(len(lines), height,
                                             f"{len(lines)} lines into {height} rows")

    def test_prompt_line_is_full_width_for_every_buffer(self):
        """The cursor glyph must be drawn, not merely counted in the padding."""
        for buffer in BUFFERS:
            with self.subTest(buffer=buffer):
                _, _, lines = self.frame(80, 24, buffer)
                self.assertEqual(len(lines[-2]), 80)
                self.assertTrue(lines[-2].startswith("║ wuwa-auto> "))

    def test_log_block_shows_at_most_five_entries(self):
        _, plan, _ = self.frame(80, 24)
        self.assertLessEqual(plan.log_rows, layout.MAX_LOG_ROWS)
        _, _, lines = self.frame(80, 24)
        body = [line for line in lines if " INFO " in line or " WARN " in line
                or " ERROR " in line]
        self.assertLessEqual(len(body), layout.MAX_LOG_ROWS)
        self.assertEqual(len(body), plan.log_rows)

    def test_log_block_is_labelled_as_auto_refreshing(self):
        _, _, lines = self.frame(80, 24)
        self.assertTrue(any("auto-refreshing" in line for line in lines))

    def test_frame_is_fully_boxed(self):
        _, _, lines = self.frame(80, 24)
        self.assertTrue(lines[0].startswith("╔") and lines[0].endswith("╗"), lines[0])
        self.assertTrue(lines[-1].startswith("╚") and lines[-1].endswith("╝"), lines[-1])
        for line in lines[1:-1]:
            self.assertTrue(line.startswith("║") and line.endswith("║"), repr(line))

    def test_narrow_terminal_reports_what_it_hid(self):
        _, plan, _ = self.frame(56, 12)
        self.assertTrue(plan.dropped, "a cramped frame must say what it dropped")
        _, _, lines = self.frame(56, 12)
        self.assertTrue(any("hidden:" in line for line in lines))

    def test_message_row_adds_exactly_one_row(self):
        _, _, plain = self.frame(80, 24)
        _, with_plan, with_message = self.frame(80, 24, message="hello")
        self.assertTrue(with_plan.show_message)
        self.assertEqual(len(with_message), len(plain) + 1)
        self.assertTrue(any("hello" in line for line in with_message))

    def test_frame_with_message_still_fits(self):
        for width in (56, 72, 80, 120):
            for height in (12, 16, 24, 40):
                with self.subTest(width=width, height=height):
                    _, plan, lines = self.frame(width, height, message="Executor PAUSED")
                    self.assertLessEqual(len(lines), height)
                    self.assertEqual({len(line) for line in lines}, {width})
                    if plan.show_message:
                        self.assertTrue(any("Executor PAUSED" in line for line in lines))
                    else:
                        self.assertIn("message", plan.dropped)

    def test_roomy_terminal_hides_nothing(self):
        _, plan, _ = self.frame(120, 45)
        self.assertEqual(plan.dropped, ())
        self.assertEqual(plan.log_rows, layout.MAX_LOG_ROWS)
        self.assertTrue(plan.show_routines)
        self.assertTrue(plan.show_hints)


class PanelTests(unittest.TestCase):
    def test_panel_lines_are_uniform(self):
        for width in (20, 40, 56, 80, 120):
            with self.subTest(width=width):
                panel = grid.Panel(width)
                panel.add("hello")
                panel.add_row("Game", "[green]ok[/green]", "ok")
                panel.rule()
                panel.add("")
                lines = [Text.from_markup(line).plain
                         for line in panel.frame("T", "RUNNING")]
                self.assertEqual({len(line) for line in lines}, {width})

    def test_panel_height_is_known_before_rendering(self):
        panel = grid.Panel(60)
        self.assertEqual(panel.height, 2)
        panel.add("a")
        self.assertEqual(panel.height, 3)
        panel.rule()
        self.assertEqual(panel.height, 4)
        self.assertEqual(len(panel.frame()), 4)

    def test_overlong_line_is_clipped(self):
        panel = grid.Panel(30)
        panel.add("x" * 100, plain="x" * 100)
        line = Text.from_markup(panel.frame()[1]).plain
        self.assertEqual(len(line), 30)
        self.assertTrue(line.rstrip("║ ").endswith("…"))

    def test_a_cell_whose_markup_matches_its_text_keeps_the_border(self):
        """The panel pads from the text the caller declares; a mismatch shows."""
        panel = grid.Panel(40)
        cell = grid.Cell("Crownless", "[green]Crownless[/green]")
        panel.add_row("Target", cell.markup, cell.text)
        line = Text.from_markup(panel.frame()[1]).plain
        self.assertEqual(len(line), 40)
        self.assertIn("Crownless", line)

    def test_right_hand_title_may_carry_markup(self):
        panel = grid.Panel(40)
        line = Text.from_markup(panel.top("WUWA-AUTO", "[bold green]RUNNING[/bold green]")).plain
        self.assertEqual(len(line), 40)
        self.assertIn("RUNNING", line)


class LayoutTests(unittest.TestCase):
    def test_plan_matches_its_own_budget(self):
        for width in WIDTHS:
            for height in HEIGHTS:
                for message_rows in (0, 1):
                    with self.subTest(width=width, height=height, message_rows=message_rows):
                        hint_rows = len(dashboard._hints(max(16, width - 4)))
                        plan = layout.fit(width, height, 7, hint_rows,
                                          message_rows=message_rows)
                        columns = layout.routine_columns(max(16, width - 4))
                        routine_rows = -(-7 // columns)
                        expected = 2 + 1 + len(plan.status_lines)
                        if plan.show_routines:
                            expected += 2 + routine_rows
                        expected += 2 + max(1, plan.log_rows)
                        if plan.show_hints:
                            expected += hint_rows
                        if plan.show_message:
                            expected += message_rows
                        expected += 1
                        self.assertLessEqual(expected, height,
                                             f"plan says {expected} rows into {height}")

    def test_message_is_shed_after_hints(self):
        # Shed order is hints, then the message row, then log rows: feedback
        # survives longer than static reference, but the log outranks it.
        hint_rows = len(dashboard._hints(76))
        roomy = layout.fit(80, 24, 7, hint_rows, message_rows=1)
        self.assertTrue(roomy.show_message)
        self.assertEqual(roomy.dropped, ())
        hints_gone = layout.fit(80, 22, 7, hint_rows, message_rows=1)
        self.assertIn("hints", hints_gone.dropped)
        self.assertTrue(hints_gone.show_message)
        self.assertNotIn("message", hints_gone.dropped)
        message_gone = layout.fit(80, 21, 7, hint_rows, message_rows=1)
        self.assertIn("message", message_gone.dropped)
        self.assertEqual(message_gone.log_rows, layout.MAX_LOG_ROWS)

    def test_log_rows_never_leave_the_configured_range(self):
        for width in WIDTHS:
            for height in HEIGHTS:
                plan = layout.fit(width, height, 7, 3)
                with self.subTest(width=width, height=height):
                    self.assertGreaterEqual(plan.log_rows, layout.MIN_LOG_ROWS)
                    self.assertLessEqual(plan.log_rows, layout.MAX_LOG_ROWS)

    def test_routine_columns_shrink_with_width(self):
        wide = layout.routine_columns(116)
        narrow = layout.routine_columns(36)
        self.assertGreaterEqual(wide, narrow)
        self.assertGreaterEqual(narrow, 1)

    def test_hints_never_overflow(self):
        for width in WIDTHS:
            for line in dashboard._hints(max(16, width - 4)):
                with self.subTest(width=width):
                    self.assertLessEqual(len(Text.from_markup(line).plain), max(16, width - 4))

    def test_hints_contain_every_command(self):
        joined = " ".join(Text.from_markup(line).plain for line in dashboard._hints(120))
        for key in ("1-6", "e d t f m n x", "c", "a", "l", "k", "p", "d", "?", "q"):
            with self.subTest(key=key):
                self.assertIn(key, joined)

    def test_hints_stay_terse(self):
        """The hint block competes with the log for rows, so it must be short."""
        self.assertLessEqual(len(dashboard._hints(76)), 2)


class LineEditorTests(unittest.TestCase):
    def editor(self):
        from src.tui import keys

        return keys, keys.LineEditor(keys.KeyReader())

    def test_typing_and_submit(self):
        keys, editor = self.editor()
        for char in "cfg":
            self.assertIsNone(editor.feed(char))
        self.assertEqual(editor.text, "cfg")
        self.assertEqual(editor.feed("\r"), "cfg")
        self.assertEqual(editor.text, "")

    def test_backspace(self):
        _, editor = self.editor()
        for char in "quit":
            editor.feed(char)
        editor.feed("\x7f")
        self.assertEqual(editor.text, "qui")

    def test_escape_clears(self):
        keys, editor = self.editor()
        editor.feed("a")
        editor.feed(keys.ESCAPE)
        self.assertEqual(editor.text, "")

    def test_line_is_bounded(self):
        from src.tui import keys

        editor = keys.LineEditor(keys.KeyReader(), limit=8)
        for _ in range(50):
            editor.feed("x")
        self.assertEqual(len(editor.text), 8)

    def test_non_string_input_is_ignored(self):
        """A bytes key must never crash the editor (see KeyReader)."""
        _, editor = self.editor()
        self.assertIsNone(editor.feed(b"q"))
        self.assertIsNone(editor.feed(None))
        self.assertEqual(editor.text, "")


class KeyDecodingTests(unittest.TestCase):
    """``msvcrt.getch()`` returns bytes; the reader must only ever yield str."""

    def reader_with(self, chunks):
        from src.tui import keys

        class FakeMsvcrt:
            def __init__(self):
                self.chunks = list(chunks)

            def kbhit(self):
                return bool(self.chunks)

            def getch(self):
                return self.chunks.pop(0)

        saved = keys.msvcrt
        keys.msvcrt = FakeMsvcrt()
        self.addCleanup(setattr, keys, "msvcrt", saved)
        reader = keys.KeyReader()
        reader.interactive = True
        return reader

    def test_printable_bytes_decode_to_text(self):
        reader = self.reader_with([b"q"])
        self.assertEqual(reader.poll(), "q")

    def test_enter_decodes(self):
        reader = self.reader_with([b"\r"])
        self.assertEqual(reader.poll(), "\r")

    def test_extended_keys_are_swallowed_whole(self):
        """Arrows arrive as a prefix plus a second byte; neither may leak."""
        reader = self.reader_with([b"\xe0", b"H", b"\x00", b"K", b"a"])
        self.assertIsNone(reader.poll())
        self.assertIsNone(reader.poll())
        self.assertEqual(reader.poll(), "a")
        self.assertIsNone(reader.poll())

    def test_ctrl_c_decodes(self):
        reader = self.reader_with([b"\x03"])
        self.assertEqual(reader.poll(), "\x03")

    def test_poll_never_returns_bytes(self):
        reader = self.reader_with([b"q", b"\r", b"\x00", b"H", b"\xe0", b"M", b"\x03"])
        for _ in range(7):
            key = reader.poll()
            self.assertTrue(key is None or isinstance(key, str), repr(key))


class DrawFrameTests(unittest.TestCase):
    """The in-place repaint must emit styled output, not raw markup."""

    def terminal(self, width=40, height=20):
        sink = io.StringIO()
        terminal = Console(file=sink, width=width, height=height,
                           force_terminal=True, color_system="truecolor")
        saved = tui_console.console
        tui_console.console = terminal
        self.addCleanup(setattr, tui_console, "console", saved)
        return sink

    def test_markup_is_rendered_not_printed_literally(self):
        from src.tui import console as console_module

        sink = self.terminal()
        console_module.draw_frame("[cyan]hello[/cyan]")
        out = sink.getvalue()
        self.assertNotIn("[cyan]", out)
        self.assertIn("hello", out)

    def test_frame_is_wrapped_in_home_and_erase(self):
        from src.tui import console as console_module

        sink = self.terminal()
        console_module.draw_frame("hi")
        out = sink.getvalue()
        self.assertTrue(out.startswith("\x1b[H"), repr(out[:10]))
        self.assertTrue(out.endswith("\x1b[J"), repr(out[-10:]))

    def test_malformed_markup_falls_back_without_raising(self):
        from src.tui import console as console_module

        sink = self.terminal()
        console_module.draw_frame("[unclosed oops")
        self.assertIn("oops", sink.getvalue())

    def test_redirected_output_is_plain_print(self):
        from src.tui import console as console_module

        sink = io.StringIO()
        plain = Console(file=sink, width=40, highlight=False, soft_wrap=False)
        saved = tui_console.console
        tui_console.console = plain
        try:
            console_module.draw_frame("hi")
        finally:
            tui_console.console = saved
        self.assertNotIn("\x1b[H", sink.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
