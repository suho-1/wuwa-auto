"""Single-key input for views that must react without waiting for Enter."""

from __future__ import annotations

import sys
import time

try:  # pragma: no cover - platform dependent
    import msvcrt
except ImportError:
    msvcrt = None

try:  # pragma: no cover - platform dependent
    import select
except ImportError:
    select = None

try:  # pragma: no cover - platform dependent
    import termios
    import tty
except ImportError:
    termios = None
    tty = None


class KeyReader:
    """Poll for a single keypress.

    Windows uses ``msvcrt``.  POSIX switches the terminal into cbreak mode so
    keystrokes arrive unbuffered and polls with ``select``.  When stdin is not
    a terminal (piped or redirected) no key can ever be read, so
    :attr:`interactive` is ``False`` and callers can surface that instead of
    silently blocking on an unreachable branch.
    """

    def __init__(self):
        self.interactive = False
        self._pending = ""
        self._saved = None
        try:
            isatty = sys.stdin is not None and sys.stdin.isatty()
        except Exception:
            isatty = False

        if msvcrt is not None:
            self.interactive = isatty
        elif select is not None and termios is not None and isatty:
            try:
                self._saved = termios.tcgetattr(sys.stdin.fileno())
                tty.setcbreak(sys.stdin.fileno())
                self.interactive = True
            except Exception:
                self._saved = None

    def poll(self):
        """Return the pending key as ``str``, or ``None`` if nothing is waiting.

        ``msvcrt.getch()`` returns ``bytes`` and yields a two-byte sequence for
        extended keys (arrows, function keys). Both are normalised here so
        callers only ever see printable text or ``None``.
        """
        if self._pending:
            key, self._pending = self._pending[0], self._pending[1:]
            return key
        if not self.interactive:
            return None
        if msvcrt is not None:
            if not msvcrt.kbhit():
                return None
            key = msvcrt.getch()
            if key in (b"\x00", b"\xe0"):
                # Extended key: consume the second byte and report nothing
                # printable. It is already in the buffer alongside the first.
                if msvcrt.kbhit():
                    msvcrt.getch()
                return None
            try:
                return key.decode("utf-8", errors="replace")
            except Exception:
                return None
        try:
            ready, _, _ = select.select([sys.stdin], [], [], 0)
        except Exception:
            return None
        if not ready:
            return None
        return sys.stdin.read(1) or None

    def wait(self, timeout: float) -> str:
        """Block for at most ``timeout`` seconds waiting for a key."""
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            key = self.poll()
            if key is not None:
                return key
            if time.monotonic() >= deadline:
                return ""
            time.sleep(0.02)

    def close(self) -> None:
        """Restore the terminal to the state it was found in."""
        self._pending = ""
        if self._saved is not None:
            try:
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self._saved)
            except Exception:
                pass
            self._saved = None


ENTER = ("\r", "\n")
BACKSPACE = ("\x08", "\x7f")
CTRL_C = "\x03"
CTRL_D = "\x04"
ESCAPE = "\x1b"
MAX_LINE = 64


class LineEditor:
    """A single-line editor driven by :class:`KeyReader`.

    Typing goes through a polled key reader rather than ``input()`` so the
    dashboard can keep repainting itself while the operator is halfway through
    typing a command.
    """

    def __init__(self, reader: KeyReader, limit: int = MAX_LINE):
        self.reader = reader
        self.limit = limit
        self._text = ""

    @property
    def text(self) -> str:
        return self._text

    def clear(self) -> None:
        self._text = ""

    def _swallow_escape_tail(self) -> None:
        """Drop the rest of a CSI/SS3 sequence after a bare ESC."""
        while True:
            following = self.reader.wait(0.01)
            if not following:
                return
            if following.isalpha() or following == "~":
                return

    def feed(self, key: str):
        """Consume one key. Returns the submitted line, or ``None``."""
        if not isinstance(key, str) or not key:
            return None
        if key in ENTER:
            line, self._text = self._text, ""
            return line
        if key in BACKSPACE:
            self._text = self._text[:-1]
            return None
        if key == ESCAPE:
            self._swallow_escape_tail()
            self._text = ""
            return None
        if key == CTRL_D:
            self._text = ""
            return ""
        if key and key.isprintable() and len(self._text) < self.limit:
            self._text += key
        return None
