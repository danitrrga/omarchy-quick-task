from __future__ import annotations

from io import StringIO
import json
import os
from pathlib import Path
import stat
from urllib.parse import parse_qs, urlparse

import pytest

from quick_task.account import fetch_account, load_cache, save_cache
from quick_task.cli import main
from quick_task.todoist import TodoistError


class Response:
    def __init__(self, payload: dict[str, object]):
        self._body = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit: int = -1) -> bytes:
        return self._body


def fake_todoist(calls: list[tuple[str, dict[str, list[str]]]] | None = None):
    """Two project pages, one shared project, labels and sections on one page."""
    pages = {
        ("/api/v1/user", ""): {"id": "u0", "is_premium": False},
        ("/api/v1/projects", ""): {
            "results": [
                {"id": "p1", "name": "Inbox", "is_shared": False, "inbox_project": True},
                {"id": "p2", "name": "Work", "is_shared": True},
            ],
            "next_cursor": "c2",
        },
        ("/api/v1/projects", "c2"): {
            "results": [{"id": "p3", "name": "Casa", "is_shared": False}],
            "next_cursor": None,
        },
        ("/api/v1/labels", ""): {"results": [{"id": "l1", "name": "email"}], "next_cursor": None},
        ("/api/v1/sections", ""): {
            "results": [{"id": "s1", "project_id": "p2", "name": "Admin"}],
            "next_cursor": None,
        },
        ("/api/v1/projects/p2/collaborators", ""): {
            "results": [{"id": "u1", "name": "Marta", "email": "m@example.com"}],
            "next_cursor": None,
        },
    }

    def opener(request, *, timeout):
        url = urlparse(request.full_url)
        query = parse_qs(url.query)
        if calls is not None:
            calls.append((url.path, query))
        assert request.get_method() == "GET"
        assert request.get_header("Authorization") == "Bearer tok-secret"
        return Response(pages[(url.path, query.get("cursor", [""])[0])])

    return opener


def test_fetch_follows_pagination_and_asks_collaborators_only_for_shared_projects():
    calls: list[tuple[str, dict[str, list[str]]]] = []

    account = fetch_account("tok-secret", opener=fake_todoist(calls))

    assert account["premium"] is False
    assert [p["name"] for p in account["projects"]] == ["Inbox", "Work", "Casa"]
    assert account["projects"][0]["inbox"] is True
    assert account["labels"] == [{"name": "email"}]
    assert account["sections"] == [{"id": "s1", "project_id": "p2", "name": "Admin"}]
    assert account["collaborators"] == {
        "p2": [{"id": "u1", "name": "Marta", "email": "m@example.com"}]
    }
    asked = [path for path, _ in calls]
    assert asked.count("/api/v1/projects/p2/collaborators") == 1
    assert "/api/v1/projects/p1/collaborators" not in asked
    assert "/api/v1/projects/p3/collaborators" not in asked


def test_cache_is_private_and_atomic_and_reports_staleness(tmp_path: Path):
    path = tmp_path / "quick-task" / "account.json"
    account = fetch_account("tok-secret", opener=fake_todoist())

    save_cache(account, path, now=1000.0)

    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert not [p for p in path.parent.iterdir() if p.name != "account.json"]
    assert "tok-secret" not in path.read_text()
    assert load_cache(path, now=1100.0)["stale"] is False
    assert load_cache(path, now=1000.0 + 301)["stale"] is True
    assert load_cache(path, now=1100.0)["projects"][1]["name"] == "Work"


def test_a_missing_or_corrupt_cache_loads_as_empty_and_stale(tmp_path: Path):
    path = tmp_path / "account.json"
    assert load_cache(path)["projects"] == []
    assert load_cache(path)["stale"] is True
    path.write_text("not json")
    assert load_cache(path)["stale"] is True


def test_a_rejected_token_during_sync_fails_without_echoing_it():
    from urllib.error import HTTPError

    def opener(request, *, timeout):
        raise HTTPError(request.full_url, 401, "no", {}, None)

    with pytest.raises(TodoistError, match="rejected the API token") as error:
        fetch_account("tok-secret", opener=opener)
    assert "tok-secret" not in str(error.value)


def run_cli(command: str, *, environ: dict[str, str], opener=None):
    stdout = StringIO()
    code = main([command], stdin=StringIO(""), stdout=stdout, environ=environ, opener=opener)
    return code, json.loads(stdout.getvalue())


def test_sync_then_account_round_trip_through_the_cli(tmp_path: Path):
    environ = {"TODOIST_API_TOKEN": "tok-secret", "XDG_CACHE_HOME": str(tmp_path)}

    code, synced = run_cli("sync", environ=environ, opener=fake_todoist())
    assert code == 0 and synced["ok"] is True
    assert synced["account"]["stale"] is False

    code, cached = run_cli("account", environ=environ)
    assert code == 0
    assert [p["name"] for p in cached["account"]["projects"]] == ["Inbox", "Work", "Casa"]


def test_sync_without_a_token_reports_it_and_leaves_the_cache_alone(tmp_path: Path):
    environ = {"XDG_CACHE_HOME": str(tmp_path), "QUICK_TASK_TOD_CONFIG": str(tmp_path / "none")}

    code, output = run_cli("sync", environ=environ)

    assert code == 1
    assert "token not found" in output["error"]
    assert not (tmp_path / "quick-task").exists()


def test_the_cache_reports_when_it_was_fetched_so_the_overlay_can_say_synced(tmp_path: Path):
    path = tmp_path / "account.json"
    save_cache(fetch_account("tok-secret", opener=fake_todoist()), path, now=1_700_000_000.0)

    assert load_cache(path, now=1_700_000_100.0)["fetched_at"] == 1_700_000_000.0
    assert load_cache(tmp_path / "missing.json")["fetched_at"] is None
