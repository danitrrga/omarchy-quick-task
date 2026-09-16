"""Small, private client for Todoist's current Quick Add endpoint."""

from __future__ import annotations

from collections.abc import Mapping
import json
import os
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


QUICK_ADD_URL = "https://api.todoist.com/api/v1/tasks/quick"
DEFAULT_TIMEOUT = 10
MAX_RESPONSE_BYTES = 1_048_576


class TodoistError(RuntimeError):
    """An error safe to display in the overlay."""


def load_token(
    environ: Mapping[str, str] | None = None,
    config_path: Path | None = None,
) -> str:
    source = os.environ if environ is None else environ
    token = str(source.get("TODOIST_API_TOKEN", "")).strip()
    if token:
        return token

    path = config_path or Path.home() / ".config" / "tod.cfg"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        payload = {}
    token = str(payload.get("token", "")).strip() if isinstance(payload, dict) else ""
    if not token:
        raise TodoistError(
            "Todoist token not found. Set TODOIST_API_TOKEN or configure the existing tod client."
        )
    return token


def _safe_http_error(code: int) -> TodoistError:
    if code == 401:
        return TodoistError("Todoist rejected the API token.")
    if code == 403:
        return TodoistError("Todoist refused this task.")
    if code == 429:
        return TodoistError("Todoist is rate-limiting requests. Try again shortly.")
    return TodoistError(f"Todoist returned HTTP {code}.")


def quick_add(
    text: str,
    *,
    note: str = "",
    token: str,
    opener: Callable[..., Any] = urlopen,
) -> dict[str, object]:
    payload: dict[str, object] = {"text": text, "meta": True}
    if note.strip():
        payload["note"] = note.strip()
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    request = Request(
        QUICK_ADD_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )

    try:
        with opener(request, timeout=DEFAULT_TIMEOUT) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as error:
        raise _safe_http_error(error.code) from None
    except (URLError, OSError, TimeoutError):
        raise TodoistError("Could not reach Todoist.") from None

    if len(raw) > MAX_RESPONSE_BYTES:
        raise TodoistError("Todoist returned an unreadable response.")
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise TodoistError("Todoist returned an unreadable response.") from None
    if not isinstance(decoded, dict):
        raise TodoistError("Todoist returned an unreadable response.")
    return decoded
