"""wuwa-auto application launcher.

The branded Qt desktop interface is the default. The terminal dashboard is
kept as an explicit compatibility mode for users who still want it.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


# This identifier is intentionally independent from the release version that
# PyAppify may inject. It lets a support log prove that the recovery launcher,
# rather than an older packaged launcher, actually ran.
SOURCE_BUILD_ID = "recovery-20261003.1"


def _git_identity() -> str:
    """Return an environment/build revision, with a local Git fallback."""
    for variable in ("WUWA_AUTO_BUILD_ID", "GITHUB_SHA", "PYAPPIFY_BUILD_ID"):
        if value := os.environ.get(variable):
            return value[:40]

    try:
        result = subprocess.run(
            ["git", "describe", "--always", "--dirty"],
            cwd=Path(__file__).resolve().parent,
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
        return result.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "not-packaged"


def startup_banner(config: dict, source_version: str, ui_mode: str) -> str:
    """Build the single-line identity banner expected in support logs."""
    return (
        "WUWA-AUTO STARTUP | "
        f"source_version={source_version} | "
        f"runtime_version={config.get('version', source_version)} | "
        f"ui_mode={ui_mode} | "
        f"source_build={SOURCE_BUILD_ID} | "
        f"revision={_git_identity()} | "
        f"cwd={Path.cwd()} | "
        f"entry={Path(__file__).resolve()}"
    )


def _log_startup_banner(config: dict, source_version: str, ui_mode: str) -> str:
    """Emit startup identity after OK has configured file logging when possible."""
    message = startup_banner(config, source_version, ui_mode)
    # stdout is captured by PyAppify/TUI launchers, while the framework logger
    # writes the desktop app's rotating log. Emitting to both makes the banner
    # survive either launch path.
    print(message)
    try:
        from ok import Logger

        Logger.get_logger(__name__).info(message)
    except (ImportError, AttributeError):
        pass
    return message


def main() -> None:
    """Launch the desktop UI, or the legacy TUI when ``--tui`` is requested."""
    from config import config, version

    if "--tui" in sys.argv[1:]:
        # The TUI does not parse command-line arguments. Removing our launcher
        # flag also keeps it away from engine-side argument parsing.
        sys.argv.remove("--tui")
        from src.tui import run_tui

        _log_startup_banner(config, version, "legacy-tui")
        run_tui()
        return

    from ok import OK

    app = OK(config)
    # OK.__init__ configures the rotating log and may inject the packaged
    # runtime version, so emit the banner only after construction.
    _log_startup_banner(config, version, "qt-desktop")
    app.start()


if __name__ == "__main__":
    main()
