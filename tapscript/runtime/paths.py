"""Filesystem locations.

Every path the system writes to is derived here. Nothing else in the codebase
may hardcode a home directory, a project directory, or an output directory.

Resolution order for each location:

1. An explicit environment variable (``TAPSCRIPT_CONFIG_DIR`` and friends).
2. A project-local ``.tapscript/`` directory, if the current working directory
   is inside a project (detected by walking up for a marker file).
3. The platform convention -- XDG on Linux/BSD, ``~/Library`` on macOS,
   ``%APPDATA%`` on Windows.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_MARKERS = (".tapscript", "tapscript.toml", "pyproject.toml", ".git")

APP_NAME = "tapscript"


def _env_path(name: str) -> Path | None:
    raw = os.environ.get(name)
    return Path(raw).expanduser() if raw else None


def _platform_dirs() -> tuple[Path, Path, Path, Path]:
    """Return (config, data, state, cache) roots for this platform."""
    home = Path.home()
    if sys.platform == "darwin":
        base = home / "Library"
        return (
            base / "Application Support" / APP_NAME,
            base / "Application Support" / APP_NAME,
            base / "Application Support" / APP_NAME / "state",
            base / "Caches" / APP_NAME,
        )
    if os.name == "nt":
        appdata = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
        local = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        return (
            appdata / APP_NAME,
            appdata / APP_NAME,
            local / APP_NAME / "state",
            local / APP_NAME / "cache",
        )
    xdg_config = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))
    xdg_data = Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share"))
    xdg_state = Path(os.environ.get("XDG_STATE_HOME", home / ".local" / "state"))
    xdg_cache = Path(os.environ.get("XDG_CACHE_HOME", home / ".cache"))
    return (
        xdg_config / APP_NAME,
        xdg_data / APP_NAME,
        xdg_state / APP_NAME,
        xdg_cache / APP_NAME,
    )


def find_project_root(start: Path | None = None) -> Path | None:
    """Walk up from *start* looking for a project marker. None if not in one."""
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        for marker in PROJECT_MARKERS:
            if (candidate / marker).exists():
                return candidate
    return None


class Paths:
    """Resolved locations for one run of the application."""

    def __init__(self, project_root: Path | None = None) -> None:
        config, data, state, cache = _platform_dirs()
        self.project_root = project_root or find_project_root()
        self.config_dir = _env_path("TAPSCRIPT_CONFIG_DIR") or config
        self.data_dir = _env_path("TAPSCRIPT_DATA_DIR") or data
        self.state_dir = _env_path("TAPSCRIPT_STATE_DIR") or state
        self.cache_dir = _env_path("TAPSCRIPT_CACHE_DIR") or cache

    # -- files ---------------------------------------------------------------

    @property
    def config_file(self) -> Path:
        override = _env_path("TAPSCRIPT_CONFIG")
        if override:
            return override
        return self.config_dir / "config.toml"

    @property
    def project_config_file(self) -> Path | None:
        """``.tapscript/config.toml`` beside the project, if there is a project."""
        if not self.project_root:
            return None
        return self.project_root / ".tapscript" / "config.toml"

    @property
    def workspace(self) -> Path:
        """Where generated artefacts land.

        Project-local when run inside a project so output travels with the work,
        otherwise the per-user data directory.
        """
        override = _env_path("TAPSCRIPT_WORKSPACE")
        if override:
            return override
        if self.project_root:
            return self.project_root / ".tapscript" / "workspace"
        return self.data_dir / "workspace"

    @property
    def output_dir(self) -> Path:
        return self.workspace / "output"

    @property
    def sessions_dir(self) -> Path:
        return self.workspace / "sessions"

    @property
    def bridge_dir(self) -> Path:
        """Handshake directory for host-agent delegation."""
        override = _env_path("TAPSCRIPT_BRIDGE_DIR")
        if override:
            return override
        return self.workspace / "bridge"

    @property
    def plugins_dir(self) -> Path:
        return self.data_dir / "plugins"

    @property
    def secrets_file(self) -> Path:
        return self.config_dir / "credentials.toml"

    # -- helpers -------------------------------------------------------------

    def ensure(self, *dirs: Path) -> None:
        for directory in dirs:
            directory.mkdir(parents=True, exist_ok=True)

    def ensure_runtime(self) -> None:
        self.ensure(self.config_dir, self.output_dir, self.sessions_dir)

    def describe(self) -> dict[str, str]:
        return {
            "project_root": str(self.project_root) if self.project_root else "(none)",
            "config_file": str(self.config_file),
            "workspace": str(self.workspace),
            "output_dir": str(self.output_dir),
            "data_dir": str(self.data_dir),
            "cache_dir": str(self.cache_dir),
        }


def default_paths() -> Paths:
    return Paths()
