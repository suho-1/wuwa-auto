"""Task configuration persistence for the TUI.

The dashboard renders a target summary for every one-time routine on each
redraw.  The previous implementation called ``open()`` + ``json.load()`` once
per routine per frame -- seven synchronous disk round-trips for data that only
changes when a human edits it.

This store keys a parsed copy of each file on ``(mtime_ns, size)``, so a
repeated read is a single ``stat()`` plus a shallow dict copy, and it falls
back to a full parse the moment the file actually changes (including changes
made by the Qt GUI in another window).
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from typing import Dict, Optional

CONFIG_FOLDER = "configs"


class TaskConfigStore:
    def __init__(self, folder: str = CONFIG_FOLDER):
        self.folder = folder
        self._cache: Dict[str, tuple] = {}
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def path(self, name: str) -> str:
        return os.path.join(self.folder, f"{name}.json")

    def load(self, name: str) -> dict:
        """Return a mutable copy of the task config (empty dict when absent)."""
        path = self.path(name)
        try:
            stat = os.stat(path)
        except OSError:
            with self._lock:
                self._cache.pop(name, None)
            return {}

        stamp = (stat.st_mtime_ns, stat.st_size)
        with self._lock:
            cached = self._cache.get(name)
        if cached is not None and cached[0] == stamp:
            with self._lock:
                self.hits += 1
            return dict(cached[1])

        try:
            with open(path, "r", encoding="utf-8") as stream:
                data = json.load(stream)
            if not isinstance(data, dict):
                data = {}
        except (OSError, ValueError):
            data = {}

        with self._lock:
            self._cache[name] = (stamp, data)
            self.misses += 1
        return dict(data)

    def get(self, name: str, key: str, default=None):
        return self.load(name).get(key, default)

    def save(self, name: str, config: dict) -> bool:
        """Atomically write the config; a crash can never truncate the file."""
        os.makedirs(self.folder, exist_ok=True)
        path = self.path(name)
        payload = json.dumps(config, indent=4, ensure_ascii=False)
        handle, temporary = tempfile.mkstemp(prefix=f".{name}.", suffix=".tmp", dir=self.folder)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        self._remember(name, path, config)
        return True

    def update(self, name: str, values: dict) -> dict:
        """Merge ``values`` into the stored config and persist the result."""
        config = self.load(name)
        config.update(values)
        self.save(name, config)
        return config

    def _remember(self, name: str, path: str, config: dict) -> None:
        try:
            stat = os.stat(path)
            stamp = (stat.st_mtime_ns, stat.st_size)
        except OSError:
            stamp = None
        with self._lock:
            self._cache[name] = (stamp, dict(config))

    def invalidate(self, name: Optional[str] = None) -> None:
        with self._lock:
            if name is None:
                self._cache.clear()
            else:
                self._cache.pop(name, None)

    def stats(self) -> str:
        with self._lock:
            total = self.hits + self.misses
            ratio = (100.0 * self.hits / total) if total else 0.0
            return f"{self.hits} cached / {self.misses} parsed ({ratio:.0f}% hit rate)"


#: Process-wide store shared by the views and the configuration screens.
CONFIG_STORE = TaskConfigStore()
