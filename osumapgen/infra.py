"""Paths, persisted settings, logging, progress reporting and cancellation."""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass, asdict, field
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Callable, Optional

from . import APP_NAME


# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------

def app_data_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    p = Path(base) / APP_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def default_output_dir() -> Path:
    docs = Path.home() / "Documents"
    if not docs.is_dir():
        docs = Path.home()
    return docs / "OsuMapGen Output"


# --------------------------------------------------------------------------
# Settings (remembered between runs)
# --------------------------------------------------------------------------

STYLES = ["Auto", "Simple and readable", "Stream-focused", "Jump-focused",
          "Technical", "Slider-focused", "Balanced mix (all styles)"]


@dataclass
class Settings:
    last_mp3: str = ""
    last_dir: str = ""
    stars: float = 4.0
    style: str = "Auto"
    output_dir: str = ""
    tolerance: float = 0.5
    offset_ms: float = 0.0        # global audio offset correction (advanced)
    open_in_osu_after: bool = False
    username: str = ""            # osu! username written as the map's Creator (case-sensitive)
    username_asked: bool = False  # the first-run prompt has been shown
    mapset: bool = False          # make a full mapset (Easy up to the target) instead of one difficulty
    length: str = "Full song"     # "Full song" or a length such as "1:30"; the best part of the song is cut

    @classmethod
    def path(cls) -> Path:
        return app_data_dir() / "settings.json"

    @classmethod
    def load(cls) -> "Settings":
        try:
            data = json.loads(cls.path().read_text(encoding="utf-8"))
            known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
            s = cls(**known)
        except (OSError, ValueError, TypeError):
            s = cls()
        if s.style not in STYLES:
            s.style = "Auto"
        if not s.output_dir:
            s.output_dir = str(default_output_dir())
        return s

    def save(self) -> None:
        try:
            self.path().write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        except OSError:
            logging.getLogger(APP_NAME).warning("Could not save settings", exc_info=True)


USERNAME_HINT = ("Case-sensitive: type it exactly as it appears on your osu! profile "
                 "(\"Peppy\" is not the same as \"peppy\"). Only needed if you want to upload the map.")


def check_username(name: str) -> str:
    """Return "" if the name looks like a valid osu! username, else a reason it does not.
    osu! usernames are 3-15 characters of letters, digits, spaces, '-', '_', '[' and ']'."""
    import re
    if not name:
        return ""
    if name != name.strip():
        return "The username starts or ends with a space."
    if not 3 <= len(name) <= 15:
        return "osu! usernames are 3 to 15 characters long."
    if not re.fullmatch(r"[A-Za-z0-9 \-_\[\]]+", name):
        return "osu! usernames may only contain letters, numbers, spaces, -, _, [ and ]."
    if "  " in name:
        return "osu! usernames cannot contain two spaces in a row."
    return ""


# --------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------

_configured = False


def setup_logging(verbose: bool = False) -> Path:
    global _configured
    log_path = app_data_dir() / "osumapgen.log"
    logger = logging.getLogger(APP_NAME)
    if not _configured:
        logger.setLevel(logging.DEBUG)
        fh = RotatingFileHandler(log_path, maxBytes=2_000_000, backupCount=2, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        fh.setLevel(logging.DEBUG)
        logger.addHandler(fh)
        sh = logging.StreamHandler()
        sh.setLevel(logging.DEBUG if verbose else logging.WARNING)
        sh.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        logger.addHandler(sh)
        _configured = True
    return log_path


def get_logger(name: str = "") -> logging.Logger:
    return logging.getLogger(APP_NAME + ("." + name if name else ""))


# --------------------------------------------------------------------------
# Progress and cancellation
# --------------------------------------------------------------------------

class Cancelled(Exception):
    """Raised inside the pipeline when the user cancels."""


class UserFacingError(Exception):
    """An error whose message is safe and useful to show to the user."""


@dataclass
class Progress:
    """Thread-safe progress reporter. Stages are weighted into one 0..1 bar."""
    callback: Optional[Callable[[float, str], None]] = None
    _cancel: threading.Event = field(default_factory=threading.Event)
    _stages: dict = field(default_factory=dict)
    _order: list = field(default_factory=list)
    _current: str = ""

    def plan(self, stages: list) -> None:
        """stages: list of (name, weight)."""
        total = sum(w for _, w in stages)
        acc = 0.0
        for name, w in stages:
            self._stages[name] = (acc / total, w / total)
            self._order.append(name)
            acc += w

    def update(self, stage: str, frac: float, message: str = "") -> None:
        self.check()
        self._current = stage
        start, width = self._stages.get(stage, (0.0, 0.0))
        value = start + width * max(0.0, min(1.0, frac))
        if self.callback:
            self.callback(value, message or stage)

    def cancel(self) -> None:
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def check(self) -> None:
        if self._cancel.is_set():
            raise Cancelled("Generation cancelled")
