"""Bridge between the terminal UI and the OK-WW engine.

Everything that touches the live engine lives here: headless start-up, the
class-name -> task index, trigger toggles, live config propagation and the
status probes the dashboard reads.  The views never touch ``self.ok`` directly.
"""

from __future__ import annotations

import contextlib
import os
import threading

from . import console, logs

#: Task states reported by the run monitor, ordered from least to most progress.
STATE_IDLE = "idle"
STATE_QUEUED = "queued"
STATE_RUNNING = "running"
STATE_FINISHED = "finished"


class EngineBridge:
    """Owns the engine handle and the cached task index."""

    def __init__(self):
        self.ok = None
        self.executor = None
        self.startup_error = None
        self._tasks = {}
        self._signature = None
        self._lock = threading.Lock()

    # -- lifecycle --------------------------------------------------------
    def start(self) -> None:
        """Construct the engine in headless mode with console logs captured."""
        from config import config
        from ok import OK

        config["tui"] = True
        config["disable_console_log"] = True
        config["gui"] = None
        config["check_mutex"] = False

        logs.install()
        console.notice("[bold cyan]>>> Initializing OK-WW Engine (Headless TUI Mode)...[/bold cyan]")

        devnull = open(os.devnull, "w", encoding="utf-8")
        try:
            with contextlib.redirect_stdout(devnull), contextlib.redirect_stderr(devnull):
                self.ok = OK(config)
        finally:
            devnull.close()

        self.executor = getattr(self.ok, "task_executor", None)

        # OK() rebuilds the logging handlers during construction.
        logs.install()
        self.invalidate()

        if hasattr(self.ok, "start_runtime"):
            self.ok.start_runtime()
        if self.executor is not None and hasattr(self.executor, "start"):
            self.executor.start()

        console.success("OK-WW Core Engine online. Game capture ready.")
        logs.info("Engine started in headless TUI mode")

    @property
    def ready(self) -> bool:
        return self.executor is not None

    def shutdown(self) -> None:
        if self.executor is not None:
            try:
                self.executor.exit()
            except Exception as exc:
                console.report_exception("Executor shutdown failed", exc)
        if self.ok is not None:
            try:
                self.ok.quit()
            except Exception as exc:
                console.report_exception("Engine shutdown failed", exc)
        self.executor = None
        self.ok = None
        self.invalidate()

    # -- task index -------------------------------------------------------
    def invalidate(self) -> None:
        with self._lock:
            self._tasks = {}
            self._signature = None

    def _signature_now(self):
        if self.executor is None:
            return None
        onetime = self.executor.onetime_tasks
        trigger = self.executor.trigger_tasks
        return (id(onetime), len(onetime), id(trigger), len(trigger))

    def _ensure_index(self) -> dict:
        """Rebuild the class-name -> task map when the task lists change.

        The previous implementation walked ``executor.trigger_tasks`` linearly
        for every row of the dashboard, seven times per frame.  Task lists are
        fixed once ``OK()`` returns, so an identity/length signature is a
        sufficient and O(1) cache key.
        """
        signature = self._signature_now()
        with self._lock:
            if signature is not None and signature == self._signature:
                return self._tasks
        index = {}
        for task in self._onetime_tasks() + self._trigger_tasks():
            index.setdefault(type(task).__name__, task)
            name = getattr(task, "name", None)
            if name:
                index.setdefault(str(name), task)
        with self._lock:
            self._tasks = index
            self._signature = signature
        return index

    def _onetime_tasks(self):
        return list(self.executor.onetime_tasks) if self.executor else []

    def _trigger_tasks(self):
        return list(self.executor.trigger_tasks) if self.executor else []

    def task_counts(self) -> tuple:
        return (len(self._trigger_tasks()), len(self._onetime_tasks()))

    def find(self, class_name: str):
        """Look a task up by class name, then by configured name."""
        if self.executor is None:
            return None
        return self._ensure_index().get(class_name)

    def trigger_task(self, class_name: str):
        if self.executor is None:
            return None
        getter = getattr(self.executor, "get_task_by_class_name", None)
        if callable(getter):
            try:
                return getter(class_name)
            except Exception:
                pass
        task = self.find(class_name)
        if task is not None and task in self._trigger_tasks():
            return task
        return None

    def onetime_task(self, class_name: str):
        if self.executor is None:
            return None
        task = self.find(class_name)
        if task is not None and task in self._onetime_tasks():
            return task
        return None

    @staticmethod
    def task_name(task) -> str:
        return str(getattr(task, "name", "") or type(task).__name__)

    # -- triggers ---------------------------------------------------------
    def is_trigger_enabled(self, class_name: str) -> bool:
        task = self.trigger_task(class_name)
        return bool(task is not None and getattr(task, "enabled", False))

    def toggle_trigger(self, class_name: str):
        """Flip a trigger. Returns ``(task_name, new_state)`` or ``None``."""
        task = self.trigger_task(class_name)
        if task is None:
            return None
        name = self.task_name(task)
        if getattr(task, "enabled", False):
            task.disable()
            logs.info(f"Disabled: {name}")
            return name, False
        task.enable()
        logs.info(f"Enabled: {name}")
        return name, True

    # -- executor ---------------------------------------------------------
    @property
    def paused(self) -> bool:
        return bool(self.executor is not None and getattr(self.executor, "paused", False))

    def toggle_paused(self) -> bool:
        if self.executor is None:
            return True
        self.executor.paused = not self.executor.paused
        logs.info("Executor PAUSED" if self.executor.paused else "Executor RESUMED")
        return bool(self.executor.paused)

    # -- one-time routines ------------------------------------------------
    def run_state(self, task) -> str:
        """Classify a one-time task without racing the executor thread.

        ``Task.start()`` sets ``_enabled`` synchronously, so a task that is
        enabled but not yet running is *queued*, not finished.  The old check
        (``not running and not _enabled``) could therefore report success for a
        task that had not even been picked up yet.
        """
        if task is None:
            return STATE_IDLE
        if getattr(task, "running", False):
            return STATE_RUNNING
        if getattr(task, "_enabled", False):
            return STATE_QUEUED
        return STATE_FINISHED

    def dispatch(self, class_name: str):
        """Start a one-time routine. Returns the task, or ``None`` on failure."""
        task = self.onetime_task(class_name)
        if task is None:
            logs.warn(f"Routine not found: {class_name}")
            return None
        if getattr(task, "running", False):
            return task
        logs.info(f"Dispatched: {self.task_name(task)}")
        logs.install()  # cheap, idempotent: guards against handler rebuilds
        task.start()
        return task

    def set_live_config(self, class_name: str, values: dict) -> list:
        """Push config into the live task object; returns rejected keys.

        ``Config.__setitem__`` validates and silently drops invalid values, so
        the result is re-read to find out what actually landed.
        """
        task = self.onetime_task(class_name)
        if task is None:
            return list(values)
        rejected = []
        for key, value in values.items():
            task.config[key] = value
            if key not in task.config:
                rejected.append(key)
        return rejected

    # -- status probes ----------------------------------------------------
    def device_status(self) -> str:
        manager = getattr(self.ok, "device_manager", None)
        if manager is None:
            return "[yellow]Connecting...[/yellow]"
        try:
            preferred = manager.get_preferred_device()
        except Exception:
            return "[dim]Standby[/dim]"
        if preferred and preferred.get("connected"):
            width = preferred.get("width", 0)
            height = preferred.get("height", 0)
            hwnd = preferred.get("real_hwnd", "N/A")
            return f"[bold green]Connected[/bold green] (HWND: {hwnd} | {width}x{height})"
        return "[yellow]Searching game window...[/yellow]"

    def party_status(self) -> str:
        task = self.trigger_task("AutoCombatTask")
        if task is None:
            return "[dim]Standby (detects in combat)[/dim]"
        try:
            characters = [c for c in getattr(task, "chars", None) or [] if c]
        except Exception:
            characters = []
        if not characters:
            return "[dim]Standby (detects in combat)[/dim]"
        slots = []
        for index, character in enumerate(characters, 1):
            name = getattr(character, "display_name", None) or getattr(character, "name", "Unknown")
            slots.append(f"Slot {index}: [bold cyan]{name}[/bold cyan]")
        return " | ".join(slots)

    def capture_frame(self):
        """Grab a live frame, or ``None`` when capture is unavailable."""
        manager = getattr(self.ok, "device_manager", None)
        if manager is None:
            return None
        capture = getattr(manager, "capture_method", None)
        if not capture:
            return None
        try:
            return capture.get_frame()
        except Exception:
            return None

    def clear_feature_cache(self) -> None:
        """Drop cached template matches so newly exported templates take effect."""
        feature_set = getattr(self.ok, "feature_set", None)
        if not feature_set:
            return
        try:
            with feature_set.lock:
                feature_set.feature_dict.clear()
                feature_set.box_dict.clear()
                feature_set._processed_images.clear()
        except Exception as exc:
            console.report_exception("Could not clear the feature cache", exc)


#: Cached once; the device topology cannot change under a running process.
_DEVICES = None
_BACKEND = None


def _devices():
    global _DEVICES
    if _DEVICES is None:
        try:
            import openvino

            core = openvino.Core()
            _DEVICES = {}
            for name in core.available_devices:
                try:
                    _DEVICES[name] = core.get_property(name, "FULL_DEVICE_NAME")
                except Exception:
                    _DEVICES[name] = name
        except Exception as exc:
            _DEVICES = {"error": str(exc)}
    return _DEVICES


def yolo_backend_summary() -> str:
    """Which device the YOLO model actually compiled onto, and what else exists.

    ``src/OpenVinoYolo8Detect.py`` prefers NPU, then CPU, and never requests
    GPU. On this machine that is measured to be correct: 36.0 ms per infer on
    the CPU against 79.8 ms on the RTX 5050. The unused devices are reported so
    the choice is visible rather than mysterious.

    The live model is owned by the application object (``og.my_app``); a fresh
    ``Globals()`` would always report nothing, so it is never consulted.
    """
    global _BACKEND
    if _BACKEND is not None:
        return _BACKEND
    model = None
    try:
        from ok import og

        holder = getattr(og, "my_app", None)
        model = getattr(holder, "_yolo_model", None)
    except Exception:
        model = None
    if model is None:
        return "not loaded yet (compiles on first detect)"
    _BACKEND = f"{type(model).__name__} on {getattr(model, 'device_used', 'unknown')}"
    devices = _devices()
    if devices and "error" not in devices:
        unused = ", ".join(k for k in devices if k != "CPU") or "CPU only"
        _BACKEND = f"{_BACKEND} (also present: {unused})"
    return _BACKEND


def directml_summary() -> str:
    """Whether the ``Use DirectML`` setting can currently do anything.

    The option is declared in ``ok/util/GlobalConfig.py:64`` and labelled "Use
    GPU to Improve Performance", but its only consumer is
    ``src/OnnxYolo8Detect.py:44`` and that path needs onnxruntime, which is not
    a declared dependency. Report the truth instead of implying the knob works.
    """
    try:
        import onnxruntime  # noqa: F401

        try:
            import onnxruntime as ort

            providers = ort.get_available_providers()
        except Exception:
            providers = []
        dml = "DmlExecutionProvider" in providers
        return "available" + ("" if dml else " (no DmlExecutionProvider)")
    except ImportError:
        return "unavailable - onnxruntime is not installed (setting has no effect)"
