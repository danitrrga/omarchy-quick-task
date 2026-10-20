"""The token Quick Task keeps for itself: one private file, never in argv, a log or the IPC state."""

from __future__ import annotations

from collections.abc import Mapping
import json
import os
from pathlib import Path
import re

from .todoist import TodoistError


_SHAPE = re.compile(r"[\x21-\x7e]{1,200}")


def config_path(environ: Mapping[str, str]) -> Path | None:
    """Where the saved token lives, or None when the environment names no home (tests, odd sandboxes)."""
    base = environ.get("XDG_CONFIG_HOME")
    if not base:
        home = environ.get("HOME")
        if not home:
            return None
        base = str(Path(home) / ".config")
    return Path(base) / "quick-task" / "config.json"


def _read_token(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return ""
    return str(payload.get("token", "")).strip() if isinstance(payload, dict) else ""


def resolve_token(environ: Mapping[str, str], tod_path: Path | None = None) -> tuple[str, str]:
    """The token to use and where it came from: environment, then saved, then the `tod` client's file."""
    token = str(environ.get("TODOIST_API_TOKEN", "")).strip()
    if token:
        return token, "environment"
    token = _read_token(config_path(environ))
    if token:
        return token, "saved"
    token = _read_token(tod_path or Path.home() / ".config" / "tod.cfg")
    return (token, "tod.cfg") if token else ("", "")


def save_token(path: Path, token: str) -> None:
    token = token.strip()
    if not _SHAPE.fullmatch(token):
        raise TodoistError("That does not look like a Todoist token.")
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    temp = path.with_name(f".{path.name}.tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"token": token}, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def clear_saved(path: Path | None) -> bool:
    if path is None or not path.exists():
        return False
    path.unlink()
    return True
