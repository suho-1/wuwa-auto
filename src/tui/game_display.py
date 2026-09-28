"""Game display profile: windowed resolution, graphics quality and RHI.

Wuthering Waves is an Unreal Engine title, so its display state lives in
``Client/Saved/Config/WindowsNoEditor/GameUserSettings.ini``:

* ``[ScalabilityGroups]`` holds the ``sg.*`` levels the in-game quality slider
  drives, and
* ``[/Script/Engine.GameUserSettings]`` holds the resolution, the window mode
  and the preset level.

The RHI is *not* persisted anywhere in ``Saved/Config`` -- it is chosen per
launch by a command-line flag, which is why this module pairs the settings
write with a launch helper rather than pretending a setting exists.

Two rules make this safe to run unattended:

* the file is edited in place, key by key, so unknown keys, comment lines and
  unrelated sections survive byte-for-byte;
* the game rewrites the whole file when it exits, so a write is refused while
  the game is running, and every write takes a timestamped backup first.
"""

from __future__ import annotations

import glob
import os
import shutil
import time

#: Unreal's ``EWindowMode``.
WINDOW_MODE_FULLSCREEN = 0
WINDOW_MODE_BORDERLESS = 1
WINDOW_MODE_WINDOWED = 2

WINDOW_MODE_NAMES = {
    WINDOW_MODE_FULLSCREEN: "fullscreen",
    WINDOW_MODE_BORDERLESS: "borderless",
    WINDOW_MODE_WINDOWED: "windowed",
}

SCALABILITY_SECTION = "ScalabilityGroups"
SETTINGS_SECTION = "/Script/Engine.GameUserSettings"

#: Keys that must agree for the game to actually come up at the target size.
#: Unreal reads the "Last*"/"Desired*" mirrors on startup, so writing only
#: ``ResolutionSizeX`` leaves the game at its old resolution.
RESOLUTION_KEYS = (
    "ResolutionSizeX", "LastUserConfirmedResolutionSizeX", "DesiredScreenWidth",
    "LastUserConfirmedDesiredScreenWidth",
)
RESOLUTION_HEIGHT_KEYS = (
    "ResolutionSizeY", "LastUserConfirmedResolutionSizeY", "DesiredScreenHeight",
    "LastUserConfirmedDesiredScreenHeight",
)
MODE_KEYS = ("FullscreenMode", "LastConfirmedFullscreenMode", "PreferredFullscreenMode")
QUALITY_KEYS = ("GameQualitySettingLevel", "LastConfirmedQualityLevel")

#: Flags that are unambiguously "lowest cost" for an automation workload.
COST_KEYS = {
    "bUseVSync": "False",
    "bUseDynamicResolution": "False",
    "bUseHDRDisplayOutput": "False",
}

#: The ``DesiredScreenHeight`` key is misspelled in the engine's own template.
DESIRED_HEIGHT_FLAG = "bUseDesiredScreenHeight"

BACKUP_SUFFIX = ".wuwa-backup"
MAX_BACKUPS = 5

#: Unreal RHI selection. The engine reads ``-dx11``/``-dx12``; the ``-d3d*``
#: and ``-force-*`` spellings are the older UE4 aliases and are passed too for
#: the DX11 path because that is what the engine shipped with already uses.
RHI_DEFAULT = "default"
RHI_DX11 = "dx11"
RHI_DX12 = "dx12"
RHI_CHOICES = (RHI_DX11, RHI_DX12, RHI_DEFAULT)

RHI_ARGS = {
    RHI_DX11: ("-dx11", "-d3d11", "-force-d3d11"),
    RHI_DX12: ("-dx12", "-d3d12"),
    RHI_DEFAULT: (),
}

RHI_LABELS = {
    RHI_DX11: "DX11  (cheapest; lowest CPU overhead)",
    RHI_DX12: "DX12  (newer; usually costs more CPU on this title)",
    RHI_DEFAULT: "default  (let the game choose, honouring its own setting)",
}

#: The executable name the settings file sits next to, relative to the install
#: folder, and the process name used to detect a running game.
SHIPPING_EXE = os.path.join("Client", "Binaries", "Win64", "Client-Win64-Shipping.exe")
LAUNCHER_EXE = "Wuthering Waves.exe"
SETTINGS_RELATIVE = os.path.join("Client", "Saved", "Config")

#: The three folders between the install root and the shipping executable.
_SHIPPING_SUBDIRS = ("client", "binaries", "win64")


class DisplayProfile:
    """A target display configuration.

    ``resolution_quality`` is kept separate from ``scale_levels`` on purpose.
    ``sg.ResolutionQuality`` is the game's *internal* render scale, not the
    window size: dropping it saves GPU work but softens the captured image, and
    this whole app recognises targets by template matching against that image.
    The window is already 1280x720, which is where the saving matters, so the
    default keeps internal rendering at full scale and only drops the effect
    groups.
    """

    def __init__(self, width=1280, height=720, window_mode=WINDOW_MODE_WINDOWED,
                 quality=0, scale_levels=0, resolution_quality=100,
                 label="1280x720 windowed, lowest"):
        self.width = int(width)
        self.height = int(height)
        self.window_mode = int(window_mode)
        self.quality = int(quality)
        self.scale_levels = int(scale_levels)
        self.resolution_quality = int(resolution_quality)
        self.label = label

    def __repr__(self):
        return (f"DisplayProfile({self.width}x{self.height} "
                f"{WINDOW_MODE_NAMES.get(self.window_mode, self.window_mode)} q{self.quality})")

    def describe(self) -> str:
        mode = WINDOW_MODE_NAMES.get(self.window_mode, "windowed")
        return f"{self.width}x{self.height} {mode}, quality level {self.quality}"


#: The profile the dashboard command applies.
DEFAULT_PROFILE = DisplayProfile()


# --------------------------------------------------------------- ini file ---
class IniDocument:
    """A line-preserving INI editor.

    Unreal ini files are small and flat, so rewriting them through a general
    parser would risk reordering keys, dropping sections, or normalising the
    line endings the engine wrote. Lines are therefore kept *with* their
    terminators and edited in place, which makes :meth:`render` an exact round
    trip of any input it did not touch.
    """

    def __init__(self, text=""):
        self.chunks = text.splitlines(keepends=True)
        if text and not self.chunks:
            self.chunks = [text]
        self.newline = "\r\n" if "\r\n" in text else "\n"

    @classmethod
    def load(cls, path):
        # Read bytes so the file's own line endings survive; the engine writes
        # CRLF and rewriting it as LF is a gratuitous change.
        with open(path, "rb") as stream:
            return cls(stream.read().decode("utf-8-sig", errors="replace"))

    def render(self) -> str:
        return "".join(self.chunks)

    @property
    def lines(self):
        return self.chunks

    def _split(self, chunk):
        """Return ``(body, ending)`` for one chunk."""
        stripped = chunk.rstrip("\r\n")
        return stripped, chunk[len(stripped):]

    def _section_bounds(self, section):
        """Index range of a section's body lines, or ``None``."""
        start = None
        for index, chunk in enumerate(self.chunks):
            body, _ = self._split(chunk)
            body = body.strip()
            if body.startswith("[") and body.endswith("]"):
                if body[1:-1] == section:
                    start = index + 1
                elif start is not None:
                    return start, index
        if start is not None:
            return start, len(self.chunks)
        return None

    def keys(self, section) -> list:
        bounds = self._section_bounds(section)
        if bounds is None:
            return []
        start, end = bounds
        found = []
        for index in range(start, end):
            body, _ = self._split(self.chunks[index])
            body = body.strip()
            if not body or body.startswith((";", "#", "[")):
                continue
            name, separator, _ = body.partition("=")
            if separator:
                found.append(name.strip())
        return found

    def get(self, section, key, default=None):
        bounds = self._section_bounds(section)
        if bounds is None:
            return default
        start, end = bounds
        for index in range(start, end):
            body, _ = self._split(self.chunks[index])
            body = body.strip()
            if body.startswith((";", "#", "[")):
                continue
            name, separator, value = body.partition("=")
            if separator and name.strip() == key:
                return value.strip()
        return default

    def set(self, section, key, value) -> bool:
        """Update ``key`` in place, inserting it (and the section) if absent.

        Returns ``True`` when the document changed.
        """
        bounds = self._section_bounds(section)
        if bounds is not None:
            start, end = bounds
            for index in range(start, end):
                body, ending = self._split(self.chunks[index])
                stripped = body.strip()
                if stripped.startswith((";", "#", "[")):
                    continue
                name, separator, _ = stripped.partition("=")
                if separator and name.strip() == key:
                    chunk = f"{key}={value}{ending or self.newline}"
                    if self.chunks[index] == chunk:
                        return False
                    self.chunks[index] = chunk
                    return True
            insert_at = end
            while insert_at > start and not self._split(self.chunks[insert_at - 1])[0].strip():
                insert_at -= 1
            self.chunks.insert(insert_at, f"{key}={value}{self.newline}")
            return True

        while self.chunks and not self._split(self.chunks[-1])[0].strip():
            self.chunks.pop()
        if self.chunks and not self._split(self.chunks[-1])[1]:
            self.chunks[-1] += self.newline
        if self.chunks:
            self.chunks.append(self.newline)
        self.chunks.append(f"[{section}]{self.newline}")
        self.chunks.append(f"{key}={value}{self.newline}")
        return True


# ------------------------------------------------------------- discovery ---
def find_settings_file(root=None) -> str:
    """Locate ``GameUserSettings.ini`` under a Wuthering Waves install.

    The platform folder is build-dependent (``WindowsNoEditor`` on this
    install), so every ``Config/*/GameUserSettings.ini`` is considered and the
    most recently written one wins.
    """
    roots = []
    if root:
        roots.append(root)
    else:
        roots.extend(_candidate_roots())
    for base in roots:
        if not base or not os.path.isdir(base):
            continue
        pattern = os.path.join(base, SETTINGS_RELATIVE, "*", "GameUserSettings.ini")
        matches = [path for path in glob.glob(pattern) if os.path.isfile(path)]
        if matches:
            return max(matches, key=os.path.getmtime)
    return ""


def _candidate_roots() -> list:
    roots = []

    def add(path):
        if path and path not in roots:
            roots.append(path)

    # A running game tells us exactly where it lives.
    for process in running_game_processes():
        exe = process.get("exe") or ""
        if exe:
            root = install_root_from_exe(exe)
            if root:
                add(root)

    # The engine's own resolution of the configured launcher path.
    try:
        from config import calculate_pc_exe_path

        launcher = calculate_pc_exe_path(None)
        if launcher:
            add(os.path.dirname(os.path.abspath(launcher)))
    except Exception:
        pass

    # Anything the app already knows about.
    try:
        from ok import og

        manager = getattr(og, "device_manager", None)
        device = manager.get_preferred_device() if manager else None
        if device:
            add(install_root_from_exe(device.get("full_path") or ""))
    except Exception:
        pass
    return [root for root in roots if root]


def install_root_from_exe(exe_path: str) -> str:
    """``.../Client/Binaries/Win64/Client-Win64-Shipping.exe`` -> ``.../``.

    The shipping executable always lives three folders below the install root,
    so the settings search can be anchored on the executable's own location
    rather than a guessed absolute path.
    """
    if not exe_path:
        return ""
    directory = os.path.dirname(os.path.abspath(exe_path))
    parts = directory.split(os.sep)
    if [part.lower() for part in parts[-3:]] == list(_SHIPPING_SUBDIRS):
        directory = os.sep.join(parts[:-3]) or os.sep
    return directory


def running_game_processes() -> list:
    """Processes belonging to the game, or ``[]`` when psutil is unavailable."""
    try:
        import psutil
    except ImportError:
        return []
    wanted = {os.path.basename(SHIPPING_EXE).lower(), "wuthering waves.exe"}
    found = []
    for process in psutil.process_iter(["name", "exe"]):
        try:
            name = (process.info.get("name") or "").lower()
            if name in wanted:
                found.append({"pid": process.info.get("pid"), "name": name,
                              "exe": process.info.get("exe") or ""})
        except Exception:
            continue
    return found


def is_game_running() -> bool:
    return bool(running_game_processes())


# --------------------------------------------------------------- applying ---
def read_state(path=None) -> dict:
    """Current display settings, for the status line and the verify step."""
    path = path or find_settings_file()
    if not path or not os.path.isfile(path):
        return {}
    try:
        document = IniDocument.load(path)
    except OSError:
        return {}
    state = {
        "path": path,
        "width": _as_int(document.get(SETTINGS_SECTION, "ResolutionSizeX")),
        "height": _as_int(document.get(SETTINGS_SECTION, "ResolutionSizeY")),
        "window_mode": _as_int(document.get(SETTINGS_SECTION, "FullscreenMode")),
        "quality": _as_int(document.get(SETTINGS_SECTION, "GameQualitySettingLevel")),
    }
    levels = {}
    for key in document.keys(SCALABILITY_SECTION):
        if key.startswith("sg."):
            levels[key] = _as_int(document.get(SCALABILITY_SECTION, key))
    state["scalability"] = levels
    return state


def _as_int(value, default=None):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def summarise_state(state: dict) -> str:
    if not state:
        return "settings file not found"
    mode = WINDOW_MODE_NAMES.get(state.get("window_mode"), "unknown")
    levels = state.get("scalability") or {}
    quality = f"preset {state.get('quality')}" if state.get("quality") is not None else "preset ?"
    # ``sg.ResolutionQuality`` is a percentage, not a 0-3 level, so it is
    # reported on its own rather than counted among the raised groups.
    effect_levels = {k: v for k, v in levels.items() if k != "sg.ResolutionQuality"}
    above = sorted(key for key, value in effect_levels.items() if (value or 0) > 0)
    parts = []
    if above:
        parts.append(f"{len(above)}/{len(effect_levels)} sg groups above 0")
    scale = levels.get("sg.ResolutionQuality")
    if scale is not None and float(scale) < 100.0:
        parts.append(f"render scale {float(scale):g}%")
    detail = f", {', '.join(parts)}" if parts else ""
    return f"{state.get('width')}x{state.get('height')} {mode}, {quality}{detail}"


def profile_settings(document: "IniDocument", profile: "DisplayProfile") -> list:
    """Return the ``(section, key, value)`` writes a profile implies.

    Scalability keys are only written for groups the file already declares, so
    the engine is never handed a setting it does not know about.
    """
    writes = []
    for key in RESOLUTION_KEYS:
        writes.append((SETTINGS_SECTION, key, str(profile.width)))
    for key in RESOLUTION_HEIGHT_KEYS:
        writes.append((SETTINGS_SECTION, key, str(profile.height)))
    writes.append((SETTINGS_SECTION, DESIRED_HEIGHT_FLAG, "False"))
    for key in MODE_KEYS:
        writes.append((SETTINGS_SECTION, key, str(profile.window_mode)))
    for key in QUALITY_KEYS:
        if document.get(SETTINGS_SECTION, key) is not None or key == QUALITY_KEYS[0]:
            writes.append((SETTINGS_SECTION, key, str(profile.quality)))
    for key, value in COST_KEYS.items():
        if document.get(SETTINGS_SECTION, key) is not None:
            writes.append((SETTINGS_SECTION, key, value))
    for key in document.keys(SCALABILITY_SECTION):
        if key == "sg.ResolutionQuality":
            # Internal render scale, handled separately from the effect groups.
            writes.append((SCALABILITY_SECTION, key,
                           f"{float(profile.resolution_quality):.6f}"))
        elif key.startswith("sg."):
            writes.append((SCALABILITY_SECTION, key, str(profile.scale_levels)))
    return writes


def apply_profile(profile: "DisplayProfile" = None, path=None, force=False):
    """Write the profile into the game's settings file.

    Returns ``(ok, message)``. Refuses while the game is running, because the
    engine rewrites the whole file on exit and would discard the change.
    """
    profile = profile or DEFAULT_PROFILE
    path = path or find_settings_file()
    if not path or not os.path.isfile(path):
        return False, f"Settings file not found. Looked for {SETTINGS_RELATIVE}/*/GameUserSettings.ini"

    if is_game_running() and not force:
        return False, ("The game is running and will overwrite GameUserSettings.ini when it "
                       "exits. Close it first, or use 'resize now' to change the live window.")

    try:
        document = IniDocument.load(path)
    except OSError as exc:
        return False, f"Could not read {path}: {exc}"

    writes = profile_settings(document, profile)
    changed = [w for w in writes if document.set(*w)]
    if not changed:
        return True, f"Already at {profile.describe()} - {path}"

    backup = backup_path(path)
    try:
        shutil.copy2(path, backup)
        _prune_backups(path)
    except OSError as exc:
        return False, f"Could not write the backup {backup}: {exc}"

    temporary = path + ".tmp"
    try:
        payload = document.render().encode("utf-8")
        with open(temporary, "wb") as stream:
            stream.write(payload)
        os.replace(temporary, path)
    except OSError as exc:
        if os.path.exists(temporary):
            try:
                os.unlink(temporary)
            except OSError:
                pass
        return False, f"Could not write {path}: {exc}"

    return True, (f"Applied {profile.describe()} - {len(changed)} key(s) in {os.path.basename(path)}. "
                  f"Backup: {os.path.basename(backup)}")


def backup_path(path) -> str:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return f"{path}{BACKUP_SUFFIX}-{stamp}"


def list_backups(path=None) -> list:
    path = path or find_settings_file()
    if not path:
        return []
    return sorted(glob.glob(f"{path}{BACKUP_SUFFIX}-*"), reverse=True)


def _prune_backups(path) -> None:
    for stale in list_backups(path)[MAX_BACKUPS:]:
        try:
            os.unlink(stale)
        except OSError:
            pass


def restore_backup(path=None) -> str:
    """Copy the newest backup over the settings file. Returns its name."""
    path = path or find_settings_file()
    backups = list_backups(path)
    if not backups:
        return ""
    newest = backups[0]
    shutil.copy2(newest, path)
    return os.path.basename(newest)


# ---------------------------------------------------------------- launch ---
def rhi_args(rhi: str) -> list:
    return list(RHI_ARGS.get(rhi, ()))


def launcher_path() -> str:
    try:
        from config import calculate_pc_exe_path

        return calculate_pc_exe_path(None) or ""
    except Exception:
        return ""


def launch(rhi: str = RHI_DEFAULT, wait=False):
    """Start the game with the chosen RHI. Returns ``(ok, message)``."""
    if rhi not in RHI_CHOICES:
        return False, f"Unknown RHI '{rhi}'. Choose one of: {', '.join(RHI_CHOICES)}"
    if is_game_running():
        return False, "The game is already running."

    path = launcher_path()
    if not path or not os.path.isfile(path):
        return False, f"Game launcher not found ({path or 'path unresolved'}). Start the game manually."

    args = rhi_args(rhi)
    try:
        from ok.util.process import execute, WINDOWS_START_METHOD_START

        started = execute(path, arguments=args or None, start_method=WINDOWS_START_METHOD_START)
    except Exception as exc:
        return False, f"Could not start the game: {exc.__class__.__name__}: {exc}"

    if not started:
        return False, "The game did not start. Try launching it from its own launcher."
    described = " ".join(args) if args else "no RHI flag (game default)"
    return True, f"Started {os.path.basename(path)} with {described}"


# ------------------------------------------------------ live window size ---
def resize_running_window(bridge, profile: "DisplayProfile" = None):
    """Force the live game window to the profile's client size.

    Works even when the settings file could not be written, and is the right
    tool when the game is already running. Returns ``(ok, message)``.
    """
    profile = profile or DEFAULT_PROFILE
    capture = getattr(getattr(bridge, "ok", None), "device_manager", None)
    capture = getattr(capture, "capture_method", None)
    hwnd_window = getattr(capture, "hwnd_window", None)
    if hwnd_window is None:
        return False, "No game window is being captured yet."
    try:
        ok = hwnd_window.try_resize_to([(profile.width, profile.height)])
        hwnd_window.do_update_window_size()
        size = f"{hwnd_window.width}x{hwnd_window.height}"
    except Exception as exc:
        return False, f"Resize failed: {exc.__class__.__name__}: {exc}"
    if ok:
        return True, f"Window resized to a {profile.width}x{profile.height} client area (now {size})"
    return False, (f"Could not resize to {profile.width}x{profile.height}; "
                   f"the client area is {size}. The window may be borderless or full-screen.")
