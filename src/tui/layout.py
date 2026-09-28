"""Frame budget for the dashboard.

The dashboard must always occupy exactly one screen: never taller than the
terminal, never scrollable.  This module turns the terminal size into a
:class:`Plan` describing which sections to include and how many log lines fit.

The budget is computed from the *actual* line counts each section will emit,
so a plan can never under-count and overflow.  When the terminal is too short
the plan sheds content in priority order -- hints, then the transient message
row, then log rows down to a floor, then routine rows, then optional status
lines -- and records what it dropped so the dashboard can say so rather than
silently lying about the layout.
"""

from __future__ import annotations

from typing import NamedTuple

#: The activity log never shrinks past this; the frame is useless without it.
MIN_LOG_ROWS = 1
MAX_LOG_ROWS = 5

#: Rows consumed by the panel's own top and bottom borders.
FRAME_OVERHEAD = 2

#: Status lines in priority order; the first is the most important.
STATUS_LINES = ("game", "party", "privilege", "triggers")


class Plan(NamedTuple):
    width: int
    height: int
    log_rows: int
    status_lines: tuple
    show_routines: bool
    show_hints: bool
    show_message: bool
    dropped: tuple


def _routine_rows(columns: int, count: int) -> int:
    return -(-count // columns) if columns else count


def routine_columns(inner_width: int) -> int:
    """How many routine cells fit across the frame."""
    per_column = max(18, inner_width // 2)
    return max(1, min(3, inner_width // per_column))


def fit(width: int, height: int, routine_count: int, hint_rows: int,
        status_rows: int = len(STATUS_LINES), message_rows: int = 0) -> Plan:
    """Choose a layout whose exact height is ``<= height``.

    ``routine_columns`` is derived from the frame width, so a narrow terminal
    costs rows only once the columns run out. ``message_rows`` is 1 when the
    dashboard has transient feedback (a toggle confirmation, an error) to show
    inside the frame instead of printing it underneath and scrolling.
    """
    width = max(40, width)
    height = max(8, height)
    inner = width - 4
    columns = routine_columns(inner)
    routine_rows = _routine_rows(columns, routine_count)
    prompt_rows = 1

    def cost(log_rows, status_n, routines, hints, message):
        total = FRAME_OVERHEAD + prompt_rows
        total += status_n
        if routines:
            total += 2 + routine_rows          # rule + header + rows
        total += 2 + max(1, log_rows)          # rule + header + at least one line
        if hints:
            total += hint_rows
        if message:
            total += message_rows
        total += 1                             # the "hidden: ..." note
        return total

    log_rows = MAX_LOG_ROWS
    status = STATUS_LINES[:status_rows]
    routines = True
    hints = True
    message = message_rows > 0
    dropped = []

    def shed():
        nonlocal log_rows, status, routines, hints, message, dropped
        if cost(log_rows, len(status), routines, hints, message) <= height:
            return False
        if hints:
            hints = False
            dropped.append("hints")
            return True
        if message:
            message = False
            dropped.append("message")
            return True
        if log_rows > MIN_LOG_ROWS:
            log_rows -= 1
            dropped.append("log rows")
            return True
        if routines:
            routines = False
            dropped.append("routines")
            return True
        if status:
            status = status[:-1]
            dropped.append("status")
            return True
        return False

    while shed():
        pass

    # The frame itself, one log line and the prompt are non-negotiable. If even
    # that does not fit, shed the rest rather than overflow the terminal.
    while cost(MIN_LOG_ROWS, 0, False, False, False) > height and status:
        status = status[:-1]
        dropped.append("status")

    return Plan(width=width, height=height, log_rows=log_rows, status_lines=status,
                show_routines=routines, show_hints=hints, show_message=message,
                dropped=tuple(dropped))
