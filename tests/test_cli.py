from __future__ import annotations

from io import StringIO
import json

from quick_task.cli import main


def run_cli(command: str, payload: object, *, environ=None, opener=None):
    stdin = StringIO(json.dumps(payload) + "\n")
    stdout = StringIO()
    exit_code = main(
        [command],
        stdin=stdin,
        stdout=stdout,
        environ=environ or {},
        opener=opener,
    )
    return exit_code, json.loads(stdout.getvalue())


def test_parse_command_returns_the_normalized_sentence_and_visible_token():
    code, output = run_cli(
        "parse",
        {"text": "Entregar propuesta lun", "now": "2026-09-16T14:00:00+02:00"},
    )

    assert code == 0
    assert output["ok"] is True
    assert output["result"]["normalized"] == "Entregar propuesta 2026-09-21"
    assert output["result"]["tokens"][0]["text"] == "lun"


def test_parse_command_accepts_an_empty_draft_for_the_overlay_empty_state():
    code, output = run_cli("parse", {"text": ""})

    assert code == 0
    assert output == {
        "ok": True,
        "result": {
            "original": "",
            "normalized": "",
            "tokens": [],
            "recognitions": [],
        },
    }


def test_add_command_normalizes_dates_and_forwards_description():
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit=-1):
            return b'{"id":"task-42","content":"Call Marta"}'

    def opener(request, *, timeout):
        captured["payload"] = json.loads(request.data)
        return Response()

    code, output = run_cli(
        "add",
        {
            "text": "Call Marta el 21",
            "description": "Ask about the lease",
            "now": "2026-09-16T14:00:00+02:00",
        },
        environ={"TODOIST_API_TOKEN": "secret"},
        opener=opener,
    )

    assert code == 0
    assert captured["payload"] == {
        "text": "Call Marta 2026-09-21",
        "note": "Ask about the lease",
        "meta": True,
    }
    assert output == {
        "ok": True,
        "result": {"id": "task-42", "content": "Call Marta"},
        "parsed": {
            "original": "Call Marta el 21",
            "normalized": "Call Marta 2026-09-21",
            "tokens": output["parsed"]["tokens"],
            "recognitions": output["parsed"]["recognitions"],
        },
    }


def test_add_command_rejects_an_empty_task_without_contacting_todoist():
    contacted = False

    def opener(_request, *, timeout):
        nonlocal contacted
        contacted = True

    code, output = run_cli(
        "add",
        {"text": "   "},
        environ={"TODOIST_API_TOKEN": "secret"},
        opener=opener,
    )

    assert code == 1
    assert output == {"ok": False, "error": "Type a task before adding it."}
    assert contacted is False


def test_malformed_input_is_machine_readable_and_does_not_traceback():
    stdin = StringIO("not json\n")
    stdout = StringIO()

    code = main(["parse"], stdin=stdin, stdout=stdout, environ={})

    assert code == 1
    assert json.loads(stdout.getvalue()) == {
        "ok": False,
        "error": "Quick Task received invalid input.",
    }


def test_todoist_errors_remain_safe_at_the_cli_boundary():
    def opener(_request, *, timeout):
        raise OSError("secret must never cross stdout")

    code, output = run_cli(
        "add",
        {"text": "Buy milk"},
        environ={"TODOIST_API_TOKEN": "secret"},
        opener=opener,
    )

    assert code == 1
    assert output == {"ok": False, "error": "Could not reach Todoist."}
    assert "secret" not in json.dumps(output)
