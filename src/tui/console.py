"""Shared terminal plumbing for the wuwa-auto TUI.

Every view goes through this module so that screen clearing, framing, width
handling and user prompts behave identically everywhere.
"""

from __future__ import annotations

import functools
import shutil
import sys
import time

from rich.console import Console
from rich.markup import escape

__all__ = [
    "console", "print", "draw_frame", "clear", "banner", "ask", "confirm", "ask_number",
    "pause", "notice", "success", "invalid", "warn", "error", "report_exception",
    "countdown", "is_admin", "width", "height", "refresh_size", "detect_size",
    "rule", "thin_rule", "center", "escape",
]

MIN_WIDTH = 56
DEFAULT_WIDTH = 80
DEFAULT_HEIGHT = 24
MIN_HEIGHT = 10

_CLEAR = "\x1b[H\x1b[2J\x1b[3J"
_HOME = "\x1b[H"
_ERASE_DOWN = "\x1b[J"


def detect_size() -> tuple:
    try:
        size = shutil.get_terminal_size((DEFAULT_WIDTH, DEFAULT_HEIGHT))
        return size.columns, size.lines
    except Exception:
        return DEFAULT_WIDTH, DEFAULT_HEIGHT


def detect_width() -> int:
    columns, _ = detect_size()
    return max(MIN_WIDTH, columns)


def detect_height() -> int:
    _, lines = detect_size()
    return max(MIN_HEIGHT, lines)


def _enable_utf8() -> None:
    """Force UTF-8 on the console streams so CJK/emoji never raise."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _enable_windows_vt() -> bool:
    """Turn on ANSI escape processing for the Windows console host.

    Rich with ``legacy_windows=False`` emits VT sequences for colour and cursor
    control.  ``cmd.exe`` (how ``wuwa-auto.bat`` launches us) leaves that bit
    off by default, so the escapes otherwise print as literal ``←[36m`` junk.
    Returns whether virtual-terminal processing is active afterwards.
    """
    if sys.platform != "win32":
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        enable = 0x0001 | 0x0004  # PROCESSED_OUTPUT | VIRTUAL_TERMINAL_PROCESSING
        ok = False
        for std_handle in (-11, -12):  # STD_OUTPUT_HANDLE, STD_ERROR_HANDLE
            handle = kernel32.GetStdHandle(std_handle)
            mode = ctypes.c_uint32()
            if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                continue
            if kernel32.SetConsoleMode(handle, mode.value | enable):
                ok = True
        # UTF-8 code page so box-drawing and CJK survive ConHost.
        try:
            kernel32.SetConsoleOutputCP(65001)
            kernel32.SetConsoleCP(65001)
        except Exception:
            pass
        return ok
    except Exception:
        return False


def _file_is_tty() -> bool:
    """True when the console can accept in-place ANSI redraws.

    Rich's ``is_terminal`` can report True under ``FORCE_COLOR`` even for a
    ``StringIO``, which would dump home/erase codes into redirected output.
    Honour an explicit ``force_terminal`` (used by the tests), otherwise trust
    the file's own ``isatty``.
    """
    force = getattr(console, "_force_terminal", None)
    if force is not None:
        return bool(force)
    isatty = getattr(console.file, "isatty", None)
    try:
        return bool(isatty and isatty())
    except Exception:
        return False


_enable_utf8()
_enable_windows_vt()

# Both dimensions must be set: Rich's dumb-terminal path ignores a lone width
# and forces 80x25.  legacy_windows must stay off or every frame is one cell
# short of the terminal width on Windows.  VT mode is enabled above so the
# ANSI that follows is interpreted rather than printed literally.
console = Console(
    highlight=False,
    width=detect_width(),
    height=detect_height(),
    soft_wrap=False,
    legacy_windows=False,
)


def refresh_size() -> tuple:
    """Pick up terminal resizes; returns the current ``(width, height)``."""
    width = detect_width()
    height = detect_height()
    if console.width != width:
        console.width = width
    if console.height != height:
        console.height = height
    return console.width, height


def width() -> int:
    """Current drawable width, without forcing a resize."""
    return console.width or detect_width()


def height() -> int:
    """Current drawable height, without forcing a resize."""
    return console.height or detect_height()


@functools.lru_cache(maxsize=16)
def _fill(char: str, width: int) -> str:
    return char * width


def rule() -> str:
    return _fill("=", console.width)


def thin_rule() -> str:
    return _fill("-", console.width)


def center(text: str) -> str:
    """Centre ``text`` in the console width. ``text`` must be plain (no markup)."""
    width = console.width
    if len(text) >= width:
        return text[:width]
    return " " * ((width - len(text)) // 2) + text


def clear() -> None:
    """Erase the screen without spawning a shell.

    The previous implementation ran ``os.system('cls')`` *and* issued an ANSI
    erase on every single frame, paying for a ``cmd.exe`` spawn to achieve
    nothing. On a non-tty (redirected output) we emit a blank separator
    instead of spamming control codes into the log.
    """
    if _file_is_tty():
        console.file.write(_CLEAR)
        console.file.flush()
    else:
        console.print()


def draw_frame(markup: str) -> None:
    """Overwrite the previous frame in place.

    The cursor is homed, the markup is rendered through rich (so ``[cyan]``
    becomes colour, not literal text), and the region below the new frame is
    erased, so nothing is appended and the scrollback stays empty. The frame
    carries no trailing newline, which is what keeps a full-height frame from
    scrolling the terminal by one row.
    """
    if not _file_is_tty():
        print(markup)
        return
    console.file.write(_HOME)
    try:
        console.print(markup, end="")
    except Exception:
        # A malformed tag must never leave a half-drawn screen behind;
        # fall back to the unstyled text.
        from rich.text import Text

        try:
            console.print(Text.from_markup(markup), end="")
        except Exception:
            console.file.write(markup)
    console.file.write(_ERASE_DOWN)
    console.file.flush()


def print(*args, **kwargs) -> None:
    """The single output entry point, so a redirected console is respected."""
    kwargs.setdefault("highlight", False)
    console.print(*args, **kwargs)


def banner(title: str, subtitle: str = "") -> None:
    """Clear the screen and draw the standard framed header."""
    clear()
    print(rule(), style="cyan")
    print(center(title), style="bold cyan")
    if subtitle:
        print(center(subtitle), style="dim")
    print(rule(), style="cyan")


def ask(prompt: str) -> str:
    """Read a line of input, stripped. Raises ``EOFError`` on closed stdin."""
    return console.input(prompt).strip()


def confirm(question: str, default: bool = False) -> bool:
    hint = "[Y/n]" if default else "[y/N]"
    answer = ask(f"{question} {hint} ").lower()
    if not answer:
        return default
    return answer in ("y", "yes")


def ask_number(question: str, minimum: int, maximum: int, default: int = None) -> int:
    """Prompt until the user types an integer inside ``[minimum, maximum]``."""
    suffix = f" (Enter for {default})" if default is not None else ""
    while True:
        answer = ask(f"{question}{suffix}: ")
        if not answer and default is not None:
            return default
        if answer.isdigit() and minimum <= int(answer) <= maximum:
            return int(answer)
        invalid(f"Enter a number between {minimum} and {maximum}.")


def pause(message: str = "Press Enter to return to the dashboard...") -> None:
    try:
        console.input(f"[dim]{message}[/dim]")
    except EOFError:
        pass


def notice(message: str) -> None:
    print(message)


def success(message: str) -> None:
    print(f"[bold green][OK][/bold green] {message}")


def invalid(message: str) -> None:
    print(f"[bold red][!][/bold red] {message}")


def warn(message: str) -> None:
    print(f"[bold yellow][*][/bold yellow] {message}")


def error(message: str) -> None:
    print(f"[bold red][x] {message}[/bold red]")


def report_exception(context: str, exc: BaseException) -> None:
    """Surface a failure instead of swallowing it, without dumping a traceback."""
    error(f"{context}: {exc.__class__.__name__}: {exc}")


def countdown(seconds: float) -> None:
    """Sleep, but stay interruptible with Ctrl-C."""
    try:
        time.sleep(seconds)
    except KeyboardInterrupt:
        pass


@functools.lru_cache(maxsize=1)
def is_admin() -> bool:
    """Cached once: privilege level cannot change while the process runs."""
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False
