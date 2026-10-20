from __future__ import annotations

from io import StringIO
import json
from urllib.error import HTTPError

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
        captured.setdefault("requests", []).append((request.full_url, json.loads(request.data)))
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
    assert captured["requests"] == [
        ("https://api.todoist.com/api/v1/tasks/quick", {"text": "Call Marta 2026-09-21", "meta": True}),
        ("https://api.todoist.com/api/v1/tasks/task-42", {"description": "Ask about the lease"}),
    ]
    assert output == {
        "ok": True,
        "result": {"id": "task-42", "content": "Call Marta"},
        "parsed": {
            "original": "Call Marta el 21",
            "normalized": "Call Marta 2026-09-21",
            "tokens": output["parsed"]["tokens"],
            "recognitions": output["parsed"]["recognitions"],
        },
        "warnings": [],
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


class _Response:
    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit=-1):
        return self._body


def run_argv(argv, *, environ=None, opener=None, stdin_text=""):
    stdout, stderr = StringIO(), StringIO()
    code = main(
        argv,
        stdin=StringIO(stdin_text),
        stdout=stdout,
        stderr=stderr,
        environ=environ if environ is not None else {},
        opener=opener,
    )
    return code, stdout.getvalue(), stderr.getvalue()


def test_add_from_argv_joins_words_forwards_the_note_and_prints_one_plain_line():
    captured = {}

    def opener(request, *, timeout):
        captured.setdefault("requests", []).append((request.full_url, json.loads(request.data)))
        return _Response(b'{"id":"task-7","content":"Call Marta"}')

    code, out, err = run_argv(
        ["add", "Call", "Marta", "2026-09-21", "--note", "Ask about the lease"],
        environ={"TODOIST_API_TOKEN": "secret"},
        opener=opener,
    )

    assert code == 0
    assert captured["requests"] == [
        ("https://api.todoist.com/api/v1/tasks/quick", {"text": "Call Marta 2026-09-21", "meta": True}),
        ("https://api.todoist.com/api/v1/tasks/task-7", {"description": "Ask about the lease"}),
    ]
    assert out.splitlines()[0] == "Added: Call Marta (task-7)"
    assert err == ""
    assert "secret" not in out


def test_add_from_argv_with_json_prints_the_overlay_payload():
    def opener(request, *, timeout):
        return _Response(b'{"id":"task-7","content":"Call Marta"}')

    code, out, _err = run_argv(
        ["add", "Call Marta", "--json"],
        environ={"TODOIST_API_TOKEN": "secret"},
        opener=opener,
    )

    payload = json.loads(out)
    assert code == 0
    assert payload["ok"] is True
    assert payload["result"]["id"] == "task-7"


def test_add_from_argv_reports_an_error_on_stderr_with_exit_one():
    def opener(_request, *, timeout):
        raise AssertionError("an empty task must not reach Todoist")

    code, out, err = run_argv(["add", "   "], environ={"TODOIST_API_TOKEN": "secret"}, opener=opener)

    assert code == 1
    assert out == ""
    assert err == "error: Type a task before adding it.\n"


def test_argv_text_wins_over_stdin_so_an_agent_with_a_pipe_still_works():
    seen = {}

    def opener(request, *, timeout):
        seen["payload"] = json.loads(request.data)
        return _Response(b'{"id":"t","content":"x"}')

    run_argv(
        ["add", "from argv"],
        environ={"TODOIST_API_TOKEN": "secret"},
        opener=opener,
        stdin_text='{"text":"from stdin"}\n',
    )

    assert seen["payload"]["text"] == "from argv"


def test_parse_from_argv_shows_the_normalized_sentence_and_what_was_read():
    code, out, err = run_argv(["parse", "Entregar", "propuesta", "lun"])

    assert code == 0
    assert err == ""
    lines = out.splitlines()
    assert lines[0].startswith("Entregar propuesta 20")
    assert any("lun" in line and "date" in line for line in lines[1:])


def test_overlay_stdin_protocol_is_unchanged_when_no_text_is_given():
    code, output = run_cli("parse", {"text": "hoy"})

    assert code == 0 and output["ok"] is True


def test_running_the_wrapper_with_plain_python_leaves_no_bytecode_in_the_plugin_folder(tmp_path):
    """The shell watches the plugin folder: a __pycache__ appearing there reloads it and closes the overlay."""
    import os
    import shutil
    import subprocess
    import sys
    from pathlib import Path

    helper = tmp_path / "helper"
    shutil.copytree(Path(__file__).resolve().parents[1] / "helper", helper, ignore=shutil.ignore_patterns("__pycache__"))
    env = {k: v for k, v in os.environ.items() if k != "PYTHONDONTWRITEBYTECODE"}

    done = subprocess.run(
        [sys.executable, str(helper / "quick-task"), "parse", "hoy"],
        capture_output=True, text=True, env=env, check=False,
    )

    assert done.returncode == 0, done.stderr
    assert not list(helper.rglob("__pycache__"))


def test_a_failed_description_is_a_warning_because_the_task_already_exists():
    calls = []

    def opener(request, *, timeout):
        calls.append(request.full_url)
        if request.full_url.endswith("/tasks/task-9"):
            raise HTTPError(request.full_url, 500, "boom", {}, None)
        return _Response(b'{"id":"task-9","content":"Call Marta"}')

    code, out, err = run_argv(
        ["add", "Call Marta", "--note", "details"],
        environ={"TODOIST_API_TOKEN": "secret"},
        opener=opener,
    )

    assert code == 0
    assert out.splitlines()[0] == "Added: Call Marta (task-9)"
    assert err.startswith("warning: Added, but could not save the description")


TOKEN = "fake-api-token-for-tests"


def token_env(tmp_path, **extra):
    return {"XDG_CONFIG_HOME": str(tmp_path), "QUICK_TASK_TOD_CONFIG": str(tmp_path / "no-tod.cfg"), **extra}


def user_opener(seen):
    def opener(request, *, timeout):
        seen.append((request.full_url, request.get_header("Authorization")))
        return _Response(b'{"id":"1","is_premium":true}')

    return opener


def test_token_set_reads_stdin_verifies_with_todoist_and_saves_it_privately(tmp_path):
    seen = []

    code, out, err = run_argv(
        ["token", "set", "--json"],
        environ=token_env(tmp_path),
        opener=user_opener(seen),
        stdin_text=TOKEN + "\n",
    )

    saved = tmp_path / "quick-task" / "config.json"
    assert code == 0
    assert json.loads(out) == {"ok": True, "saved": True, "source": "saved"}
    assert seen == [("https://api.todoist.com/api/v1/user", f"Bearer {TOKEN}")]
    assert json.loads(saved.read_text()) == {"token": TOKEN}
    assert TOKEN not in out + err


def test_token_set_refuses_a_token_todoist_rejects_and_saves_nothing(tmp_path):
    def opener(request, *, timeout):
        raise HTTPError(request.full_url, 401, "no", {}, None)

    code, out, err = run_argv(["token", "set"], environ=token_env(tmp_path), opener=opener, stdin_text=TOKEN)

    assert code == 1
    assert err == "error: Todoist rejected the API token.\n"
    assert not (tmp_path / "quick-task").exists()
    assert TOKEN not in out + err


def test_token_set_refuses_a_token_given_as_an_argument_because_argv_is_public(tmp_path):
    code, out, err = run_argv(["token", "set", TOKEN], environ=token_env(tmp_path), opener=user_opener([]))

    assert code == 1
    assert "pipe it in" in err
    assert TOKEN not in out + err
    assert not (tmp_path / "quick-task").exists()


def test_token_set_says_when_the_environment_will_keep_winning(tmp_path):
    code, out, _err = run_argv(
        ["token", "set", "--json"],
        environ=token_env(tmp_path, TODOIST_API_TOKEN="from-env"),
        opener=user_opener([]),
        stdin_text=TOKEN,
    )

    assert code == 0
    assert json.loads(out) == {"ok": True, "saved": True, "source": "environment"}


def test_token_status_names_the_source_and_never_prints_the_token(tmp_path):
    run_argv(["token", "set"], environ=token_env(tmp_path), opener=user_opener([]), stdin_text=TOKEN)

    code, out, err = run_argv(["token", "status"], environ=token_env(tmp_path), opener=user_opener([]))

    assert code == 0
    assert out.startswith("Token: saved")
    assert "accepted by Todoist" in out
    assert TOKEN not in out + err

    code, out, _err = run_argv(["token", "status", "--json"], environ=token_env(tmp_path), opener=user_opener([]))
    assert json.loads(out) == {"ok": True, "source": "saved", "premium": True}


def test_token_status_without_a_token_exits_one_and_says_how_to_add_one(tmp_path):
    code, out, err = run_argv(["token", "status"], environ=token_env(tmp_path), opener=user_opener([]))

    assert code == 1
    assert out == ""
    assert "No Todoist token" in err and "quick-task token set" in err


def test_token_status_reports_a_rejected_token_with_its_source(tmp_path):
    def opener(request, *, timeout):
        raise HTTPError(request.full_url, 401, "no", {}, None)

    code, out, _err = run_argv(
        ["token", "status", "--json"],
        environ=token_env(tmp_path, TODOIST_API_TOKEN="stale"),
        opener=opener,
    )

    assert code == 1
    assert json.loads(out) == {"ok": False, "source": "environment", "error": "Todoist rejected the API token."}


def test_token_clear_removes_only_the_saved_token(tmp_path):
    run_argv(["token", "set"], environ=token_env(tmp_path), opener=user_opener([]), stdin_text=TOKEN)

    code, out, _err = run_argv(["token", "clear", "--json"], environ=token_env(tmp_path))

    assert code == 0
    assert json.loads(out) == {"ok": True, "source": None}
    assert not (tmp_path / "quick-task" / "config.json").exists()


def test_a_missing_token_error_points_at_both_ways_to_add_one(tmp_path):
    code, _out, err = run_argv(["add", "x"], environ=token_env(tmp_path), opener=user_opener([]))

    assert code == 1
    assert "Ctrl+," in err and "quick-task token set" in err


def test_token_set_reads_one_line_because_the_overlay_never_closes_the_pipe(tmp_path):
    class OpenPipe:
        """A stdin that, like the overlay's Process, has a line but no end of file."""

        def isatty(self):
            return False

        def readline(self, _limit=-1):
            return TOKEN + "\n"

        def read(self, _limit=-1):
            raise AssertionError("waiting for end of input would hang the overlay")

    stdout = StringIO()
    code = main(
        ["token", "set", "--json"],
        stdin=OpenPipe(),
        stdout=stdout,
        stderr=StringIO(),
        environ=token_env(tmp_path),
        opener=user_opener([]),
    )

    assert code == 0
    assert json.loads(stdout.getvalue())["saved"] is True
