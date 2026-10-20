from __future__ import annotations

import io
import json
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest

from quick_task.todoist import TodoistError, load_token, quick_add, set_description


class Response:
    def __init__(self, payload: dict[str, object]):
        self._body = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit: int = -1) -> bytes:
        return self._body


def test_environment_token_wins_without_reading_the_legacy_file(tmp_path: Path):
    missing = tmp_path / "does-not-exist"

    assert load_token({"TODOIST_API_TOKEN": "from-environment"}, missing) == "from-environment"


def test_token_is_loaded_from_the_existing_tod_json(tmp_path: Path):
    config = tmp_path / "tod.cfg"
    config.write_text(json.dumps({"timezone": "Europe/Madrid", "token": "from-file"}))

    assert load_token({}, config) == "from-file"


def test_missing_token_has_an_actionable_error_without_echoing_config(tmp_path: Path):
    config = tmp_path / "tod.cfg"
    config.write_text(json.dumps({"token": ""}))

    with pytest.raises(TodoistError, match="Todoist token not found") as error:
        load_token({}, config)

    assert str(config) not in str(error.value)


def test_quick_add_sends_the_current_json_contract_and_returns_the_real_response():
    captured: dict[str, object] = {}
    response_payload = {
        "id": "task-123",
        "content": "Buy milk",
        "meta": {"project": {"name": "Inbox"}, "priority": 4},
    }

    def opener(request, *, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return Response(response_payload)

    result = quick_add(
        "Buy milk 2026-09-18 #Inbox p1",
        token="secret-token",
        opener=opener,
    )

    request = captured["request"]
    assert request.full_url == "https://api.todoist.com/api/v1/tasks/quick"
    assert request.get_method() == "POST"
    assert request.get_header("Authorization") == "Bearer secret-token"
    assert request.get_header("Content-type") == "application/json"
    assert captured["timeout"] == 10
    assert json.loads(request.data) == {
        "text": "Buy milk 2026-09-18 #Inbox p1",
        "meta": True,
    }
    assert result == response_payload


def test_description_is_set_on_the_task_not_sent_as_a_quick_add_note():
    """Todoist's quick-add `note` creates a comment; the task's own description is a field of the task."""
    captured = {}

    def opener(request, *, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["payload"] = json.loads(request.data)
        return Response({"id": "task-123"})

    set_description("task-123", "  Check oat milk too  ", token="secret", opener=opener)

    assert captured["url"] == "https://api.todoist.com/api/v1/tasks/task-123"
    assert captured["method"] == "POST"
    assert captured["payload"] == {"description": "Check oat milk too"}


@pytest.mark.parametrize(
    ("code", "message"),
    [
        (401, "Todoist rejected the API token."),
        (403, "Todoist refused this task."),
        (429, "Todoist is rate-limiting requests. Try again shortly."),
        (500, "Todoist returned HTTP 500."),
    ],
)
def test_http_errors_are_specific_but_never_include_server_bodies_or_tokens(code, message):
    def opener(request, *, timeout):
        raise HTTPError(
            request.full_url,
            code,
            "failure secret-token",
            hdrs=None,
            fp=io.BytesIO(b"server echoed secret-token"),
        )

    with pytest.raises(TodoistError) as error:
        quick_add("Buy milk", token="secret-token", opener=opener)

    assert str(error.value) == message
    assert "secret-token" not in str(error.value)


def test_network_error_is_redacted():
    def opener(_request, *, timeout):
        raise URLError("connection failed while using secret-token")

    with pytest.raises(TodoistError) as error:
        quick_add("Buy milk", token="secret-token", opener=opener)

    assert str(error.value) == "Could not reach Todoist."


def test_unreadable_success_response_is_a_safe_error():
    class BrokenResponse(Response):
        def read(self, _limit=-1):
            return b"not json"

    def opener(_request, *, timeout):
        return BrokenResponse({})

    with pytest.raises(TodoistError, match="unreadable response"):
        quick_add("Buy milk", token="secret", opener=opener)
