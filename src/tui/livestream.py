"""Live log streaming and one-time routine monitoring.

Replaces the old "poll a saturated deque" loop.  The monitor is an explicit
state machine over the engine's task flags, so a routine that is still waiting
in the executor queue is never mistaken for one that has finished.
"""

from __future__ import annotations

import time

from . import console, engine, keys, logs

POLL_INTERVAL = 0.12
QUEUE_WARN_AFTER = 12.0
FINAL_BANNER_LINGER = 0.6

_STATE_STYLE = {
    engine.STATE_QUEUED: "[bold yellow]QUEUED[/bold yellow]",
    engine.STATE_RUNNING: "[bold green]RUNNING[/bold green]",
    engine.STATE_FINISHED: "[bold cyan]FINISHED[/bold cyan]",
    engine.STATE_IDLE: "[dim]IDLE[/dim]",
}


def _describe(state: str) -> str:
    return _STATE_STYLE.get(state, state)


def _flush(cursor: int, sender_limit: int = 0, message_limit: int = 0):
    """Print everything appended since ``cursor``; return the new cursor."""
    for entry in logs.LOG_STORE.since(cursor):
        console.print(logs.format_line(entry, sender_limit, message_limit))
    return logs.LOG_STORE.cursor


def show(bridge: engine.EngineBridge, active_task=None) -> None:
    """Tail the log buffer until a key is pressed.

    ``Esc`` additionally stops a running routine, any other key detaches and
    leaves the routine running in the background.
    """
    title = "LIVE COMBAT & SYSTEM LOG STREAM"
    if active_task is not None:
        title += f" - [{bridge.task_name(active_task)}]"
    console.banner(title, "(any key to return, Esc to stop the run)")

    cursor = logs.LOG_STORE.cursor
    reader = keys.KeyReader()
    if not reader.interactive:
        console.print("[yellow]No interactive keyboard available - the stream ends when the routine "
                       "finishes, or on Ctrl-C.[/yellow]")
    try:
        while True:
            key = reader.poll()
            if key == "\x1b" and active_task is not None:
                if console.confirm(f"Stop {bridge.task_name(active_task)}?", default=False):
                    try:
                        active_task.disable()
                        logs.warn(f"Stopped by operator: {bridge.task_name(active_task)}")
                    except Exception as exc:
                        console.report_exception("Could not stop the routine", exc)
                return
            if key is not None:
                return

            cursor = _flush(cursor)
            if active_task is not None and bridge.run_state(active_task) == engine.STATE_FINISHED:
                cursor = _flush(cursor)
                console.print(f"\n{_describe(engine.STATE_FINISHED)}: "
                               f"{bridge.task_name(active_task)}")
                time.sleep(FINAL_BANNER_LINGER)
                return
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        console.print("\n[yellow]Log stream detached.[/yellow]")
    finally:
        reader.close()


def monitor(bridge: engine.EngineBridge, task) -> None:
    """Watch a dispatched routine until it finishes or the operator detaches."""
    name = bridge.task_name(task)
    console.banner(f"RUNNING: {name}", "(any key to detach, Esc to stop the routine)")

    cursor = logs.LOG_STORE.cursor
    reader = keys.KeyReader()
    if not reader.interactive:
        console.print("[yellow]No interactive keyboard available - this view closes when the routine "
                       "finishes, or on Ctrl-C.[/yellow]")

    queued_since = time.monotonic()
    started_at = None
    warned = False
    last_status = None

    try:
        while True:
            key = reader.poll()
            if key is not None:
                if key == "\x1b":
                    if console.confirm(f"Stop {name}?", default=False):
                        try:
                            task.disable()
                            logs.warn(f"Stopped by operator: {name}")
                        except Exception as exc:
                            console.report_exception("Could not stop the routine", exc)
                else:
                    console.print(f"[dim]Detached. {name} keeps running - press l to watch the log.[/dim]")
                return

            cursor = _flush(cursor)
            state = bridge.run_state(task)

            if state == engine.STATE_RUNNING and started_at is None:
                started_at = time.monotonic()

            if state == engine.STATE_FINISHED:
                cursor = _flush(cursor)
                runtime = time.monotonic() - (started_at or queued_since)
                console.print(f"\n[bold green]>>> {name} completed[/bold green] "
                               f"[dim]({runtime:.0f}s)[/dim]")
                time.sleep(FINAL_BANNER_LINGER)
                return

            if state == engine.STATE_QUEUED and not warned and time.monotonic() - queued_since > QUEUE_WARN_AFTER:
                warned = True
                if bridge.paused:
                    console.print("[bold yellow]Still queued: the executor is paused - press p to resume."
                                   "[/bold yellow]")
                else:
                    console.print("[bold yellow]Still queued: the game window is probably not being captured."
                                   "[/bold yellow]")

            if state != last_status:
                last_status = state
                console.print(f"[dim]Status: {_describe(state)}[/dim]")

            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        console.print(f"\n[dim]Detached. {name} keeps running.[/dim]")
    finally:
        reader.close()
