"""Small, private client for Todoist's current Quick Add endpoint."""

from __future__ import annotations

from collections.abc import Mapping
import json
import os
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


API_URL = "https://api.todoist.com/api/v1"
QUICK_ADD_URL = f"{API_URL}/tasks/quick"
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


def _reason(body: bytes, token: str) -> str:
    """The API's own explanation (e.g. "Deadlines are a premium only feature"), or "" if unusable."""
    try:
        message = json.loads(body.decode("utf-8")).get("error")
    except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
        return ""
    if not isinstance(message, str) or not message.strip():
        return ""
    return message.replace(token, "").strip()[:160] if token else message.strip()[:160]


def _safe_http_error(code: int, body: bytes = b"", token: str = "") -> TodoistError:
    reason = _reason(body, token)
    if code == 401:
        return TodoistError("Todoist rejected the API token.")
    if code == 403:
        return TodoistError(f"Todoist refused this task: {reason}." if reason else "Todoist refused this task.")
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
    return _request("POST", QUICK_ADD_URL, token=token, payload=payload, opener=opener)


def post_json(
    url: str,
    payload: dict[str, object],
    *,
    token: str,
    opener: Callable[..., Any] = urlopen,
) -> dict[str, object]:
    return _request("POST", url, token=token, payload=payload, opener=opener)


def move_task(
    task_id: str,
    *,
    project_id: str,
    section_id: str = "",
    token: str,
    opener: Callable[..., Any] = urlopen,
) -> dict[str, object]:
    payload: dict[str, object] = {"project_id": project_id}
    if section_id:
        payload["section_id"] = section_id
    return post_json(f"{API_URL}/tasks/{task_id}/move", payload, token=token, opener=opener)


def set_labels(
    task_id: str,
    labels: list[str],
    *,
    token: str,
    opener: Callable[..., Any] = urlopen,
) -> dict[str, object]:
    return post_json(f"{API_URL}/tasks/{task_id}", {"labels": labels}, token=token, opener=opener)


def get_json(
    url: str,
    *,
    token: str,
    opener: Callable[..., Any] = urlopen,
) -> dict[str, object]:
    return _request("GET", url, token=token, payload=None, opener=opener)


def _request(
    method: str,
    url: str,
    *,
    token: str,
    payload: dict[str, object] | None,
    opener: Callable[..., Any],
) -> dict[str, object]:
    body = (
        None
        if payload is None
        else json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = Request(url, data=body, method=method, headers=headers)

    try:
        with opener(request, timeout=DEFAULT_TIMEOUT) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as error:
        try:
            detail = error.read(4096)
        except (OSError, AttributeError, ValueError):
            detail = b""
        raise _safe_http_error(error.code, detail, token) from None
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
