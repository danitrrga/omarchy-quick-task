"""The account's projects, sections, labels and collaborators, cached for autocomplete."""

from __future__ import annotations

from collections.abc import Callable, Mapping
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

from .todoist import API_URL, TodoistError, get_json

PAGE_SIZE = 200
MAX_PAGES = 20
STALE_AFTER_SECONDS = 300


def cache_path(environ: Mapping[str, str] | None = None) -> Path:
    source = os.environ if environ is None else environ
    home = source.get("HOME") or str(Path.home())
    base = source.get("XDG_CACHE_HOME") or str(Path(home) / ".cache")
    return Path(base) / "quick-task" / "account.json"


def _pages(
    path: str,
    *,
    token: str,
    opener: Callable[..., Any],
    extra: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    cursor = ""
    for _ in range(MAX_PAGES):
        query = {"limit": str(PAGE_SIZE), **(extra or {})}
        if cursor:
            query["cursor"] = cursor
        page = get_json(f"{API_URL}/{path}?{urlencode(query)}", token=token, opener=opener)
        results = page.get("results", [])
        if not isinstance(results, list):
            raise TodoistError("Todoist returned an unreadable response.")
        items.extend(item for item in results if isinstance(item, dict))
        cursor = str(page.get("next_cursor") or "")
        if not cursor:
            break
    return items


def fetch_account(token: str, *, opener: Callable[..., Any] = urlopen) -> dict[str, Any]:
    premium = get_json(f"{API_URL}/user", token=token, opener=opener).get("is_premium") is True
    projects = _pages("projects", token=token, opener=opener)
    labels = _pages("labels", token=token, opener=opener)
    sections = _pages("sections", token=token, opener=opener)
    collaborators: dict[str, list[dict[str, str]]] = {}
    for project in projects:
        if project.get("is_shared") is not True:
            continue
        people = _pages(f"projects/{project['id']}/collaborators", token=token, opener=opener)
        collaborators[str(project["id"])] = [
            {"id": str(p.get("id", "")), "name": str(p.get("name", "")), "email": str(p.get("email", ""))}
            for p in people
            if p.get("name")
        ]
    return {
        "premium": premium,
        "projects": [
            {
                "id": str(p["id"]),
                "name": str(p.get("name", "")),
                "shared": p.get("is_shared") is True,
                "inbox": p.get("inbox_project") is True,
            }
            for p in projects
            if p.get("name")
        ],
        "sections": [
            {"id": str(s["id"]), "project_id": str(s.get("project_id", "")), "name": str(s.get("name", ""))}
            for s in sections
            if s.get("name")
        ],
        "labels": [{"name": str(label["name"])} for label in labels if label.get("name")],
        "collaborators": collaborators,
    }


def save_cache(account: Mapping[str, Any], path: Path, *, now: float | None = None) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    payload = {"fetched_at": time.time() if now is None else now, **account}
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=".account.")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def load_cache(path: Path, *, now: float | None = None) -> dict[str, Any]:
    empty = {"premium": False, "projects": [], "sections": [], "labels": [], "collaborators": {}, "stale": True}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty
    if not isinstance(payload, dict):
        return empty
    fetched_at = payload.get("fetched_at")
    age = (time.time() if now is None else now) - fetched_at if isinstance(fetched_at, (int, float)) else None
    return {
        "premium": payload.get("premium") is True,
        "projects": payload.get("projects", []),
        "sections": payload.get("sections", []),
        "labels": payload.get("labels", []),
        "collaborators": payload.get("collaborators", {}),
        "stale": age is None or age > STALE_AFTER_SECONDS,
    }
