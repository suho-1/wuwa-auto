"""Thread-safe capture of engine logs for the terminal interface.

The engine logs from worker threads through ok-script's ``communicate.log``
signal bus.  Messages are pushed into a bounded ring buffer that the views read
back.

The buffer is addressed by a *monotonic sequence number* rather than its
length.  A ``deque(maxlen=N)`` reports a constant length once it saturates, so
a consumer that diffs on ``len()`` silently stops receiving anything -- which
is exactly what the live log stream used to do after 100 messages.
"""

from __future__ import annotations

import itertools
import logging
import threading
import time
from collections import deque
from typing import List, NamedTuple

#: High-frequency engine chatter that carries no signal for an operator.
NOISE_TERMS = (
    "RefreshAdb",
    "hwnd_window:do_update",
    "update_pc_device",
    "heartbeat",
    "is_moving",
    "active_trigger_task_count",
)

_LEVEL_NAMES = {
    logging.DEBUG: "DEBUG",
    logging.INFO: "INFO",
    logging.WARNING: "WARNING",
    logging.ERROR: "ERROR",
    logging.CRITICAL: "CRITICAL",
}

SENDER_MAX = 18


class LogEntry(NamedTuple):
    seq: int
    timestamp: str
    level: str
    sender: str
    message: str

    @property
    def is_error(self) -> bool:
        return self.level in ("ERROR", "CRITICAL", "FATAL")

    @property
    def is_warning(self) -> bool:
        return self.level in ("WARNING", "WARN")

    def style(self) -> str:
        if self.is_error:
            return "red"
        if self.is_warning:
            return "yellow"
        if self.level == "DEBUG":
            return "dim"
        return "green"


_stamp_lock = threading.Lock()
_stamp_second = -1
_stamp_text = ""


def timestamp() -> str:
    """``strftime`` once per second instead of once per log line."""
    global _stamp_second, _stamp_text
    second = int(time.time())
    if second != _stamp_second:
        with _stamp_lock:
            if second != _stamp_second:
                _stamp_second = second
                _stamp_text = time.strftime("%H:%M:%S", time.localtime(second))
    return _stamp_text


def split_sender(message: str):
    """ok-script formats logs as ``<ts> <LEVEL> <sender>: <message>``."""
    parts = message.split(" ", 3)
    if len(parts) < 4:
        return "Engine", message
    remainder = parts[3]
    if ":" in remainder:
        sender, _, body = remainder.partition(":")
        tokens = sender.split()
        return (tokens[-1] if tokens else "Engine"), body.strip()
    return "Engine", remainder.strip()


def is_noise(message: str) -> bool:
    for term in NOISE_TERMS:
        if term in message:
            return True
    return False


class LogStore:
    """Bounded ring buffer with cursor-based reads."""

    def __init__(self, capacity: int = 100):
        self._entries: deque = deque(maxlen=capacity)
        self._lock = threading.Lock()
        self._seq = 0

    @property
    def capacity(self) -> int:
        return self._entries.maxlen

    @property
    def cursor(self) -> int:
        """Highest sequence number issued so far."""
        with self._lock:
            return self._seq

    def append(self, level: str, sender: str, message: str) -> LogEntry:
        with self._lock:
            self._seq += 1
            entry = LogEntry(self._seq, timestamp(), str(level), str(sender), str(message))
            self._entries.append(entry)
            return entry

    def tail(self, count: int) -> List[LogEntry]:
        """The most recent ``count`` entries."""
        with self._lock:
            start = max(0, len(self._entries) - count)
            return list(itertools.islice(self._entries, start, None))

    def since(self, cursor: int) -> List[LogEntry]:
        """Entries appended after ``cursor``.

        When the buffer wrapped, the entries that scrolled out are reported as
        a single synthetic ``WARN`` line instead of the stream going quiet.
        """
        with self._lock:
            pending = self._seq - cursor
            if pending <= 0:
                return []
            start = max(0, len(self._entries) - pending)
            items: List[LogEntry] = list(itertools.islice(self._entries, start, None))
            dropped = pending - len(items)
        if dropped > 0:
            items.insert(0, LogEntry(cursor, timestamp(), "WARN", "TUI",
                                      f"... {dropped} earlier message(s) scrolled out ..."))
        return items

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


#: Process-wide store shared by the engine bridge and every view.
LOG_STORE = LogStore()


def record(level: str, sender: str, message: str) -> LogEntry:
    """Write a TUI-authored line into the same stream as engine logs."""
    return LOG_STORE.append(level, sender, message)


def info(message: str, sender: str = "TUI") -> LogEntry:
    return record("INFO", sender, message)


def warn(message: str, sender: str = "TUI") -> LogEntry:
    return record("WARN", sender, message)


def error(message: str, sender: str = "TUI") -> LogEntry:
    return record("ERROR", sender, message)


def _make_listener():
    def on_log(levelno, message) -> None:
        try:
            text = message if isinstance(message, str) else str(message)
            if is_noise(text):
                return
            sender, body = split_sender(text)
            level = _LEVEL_NAMES.get(levelno)
            if level is None:
                level = logging.getLevelName(levelno) or "INFO"
            LOG_STORE.append(level, sender, body)
        except Exception:
            # A logging callback must never raise into the engine's threads.
            pass

    return on_log


_LISTENER = None
_SUBSCRIBED = False
_INSTALL_LOCK = threading.Lock()


def subscribe() -> None:
    """Attach to ``communicate.log`` exactly once."""
    global _LISTENER, _SUBSCRIBED
    with _INSTALL_LOCK:
        if _SUBSCRIBED:
            return
        try:
            from ok.core.events import communicate

            _LISTENER = _make_listener()
            communicate.log.connect(_LISTENER)
        except Exception:
            _LISTENER = None
        _SUBSCRIBED = True


def strip_console_handlers() -> None:
    """Detach stdout/stderr log handlers so they cannot corrupt the TUI.

    ``OK()`` rebuilds the logging handlers during construction, so this is
    cheap and idempotent but must be re-runnable.
    """
    try:
        from ok.util.logger import _ok_logger

        loggers = [_ok_logger, logging.getLogger()]
    except Exception:
        return

    for logger in loggers:
        for handler in list(logger.handlers):
            if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
                logger.removeHandler(handler)


def install() -> None:
    subscribe()
    strip_console_handlers()


def format_line(entry: LogEntry, sender_limit: int = 8, message_limit: int = 0) -> str:
    """Render one entry as rich markup, truncating to keep lines readable."""
    sender = entry.sender
    if sender_limit and len(sender) > sender_limit + 1:
        sender = sender[:sender_limit] + "…"
    message = entry.message.replace("\n", " ")
    if message_limit and len(message) > message_limit:
        message = message[: max(0, message_limit - 1)] + "…"
    return (f"[dim]{entry.timestamp}[/dim] "
            f"[{entry.style()}]{entry.level:<5}[/{entry.style()}] "
            f"[bold]{sender}[/bold]: {message}")
