"""Newline-delimited JSON bridge used by the QML overlay."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import datetime
import json
import os
from pathlib import Path
import sys
from typing import IO, Any, Callable
from urllib.request import urlopen

from .account import cache_path, fetch_account, load_cache, save_cache
from .credentials import clear_saved, config_path as saved_config_path, resolve_token, save_token
from .mentions import plan_add
from .parser import parse_quick_text
from .todoist import API_URL, TodoistError, get_json, load_token, move_task, quick_add, set_description, set_labels


DESCRIPTION = """Send a task to Todoist from a terminal or an agent.

  quick-task add "Call Marta tomorrow 9am #Work @waiting p2" --note "ask about the lease"
  quick-task parse "pasado mañana a las 9"     (dry run: shows how a sentence is read, adds nothing)

  printf %s "$TOKEN" | quick-task token set   (or: token status, token clear; the token is never an argument)

Dates, #project, /section, @label and p1-p4 are read out of the sentence, in English and Spanish.
It is add-only: it never reads or changes existing tasks."""

EPILOG = """The token comes from $TODOIST_API_TOKEN, then the one saved by `token set`, then the "token" field of ~/.config/tod.cfg.
Exit status 0 on success; on failure 1 and "error: ..." on stderr (with --json, {"ok":false,"error":...} on stdout).
With no text, add and parse read one JSON request from stdin: that is the overlay's private protocol."""


def _write(stdout: IO[str], payload: dict[str, object]) -> None:
    stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    stdout.flush()


def _read_request(stdin: IO[str]) -> dict[str, object]:
    raw = stdin.readline()
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("request must be an object")
    return payload


def _parse_now(payload: dict[str, object]) -> datetime | None:
    value = payload.get("now")
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ValueError("now must be a string")
    return datetime.fromisoformat(value)


def _parse_payload(payload: dict[str, object], account: Mapping[str, Any] | None = None):
    text = payload.get("text", "")
    ignored = payload.get("ignored", [])
    if not isinstance(text, str) or not isinstance(ignored, list):
        raise ValueError("invalid parse fields")
    if not all(isinstance(value, str) for value in ignored):
        raise ValueError("ignored must contain strings")
    return parse_quick_text(text, now=_parse_now(payload), ignored=ignored, account=account)


def _describe_parse(parsed, *, header: bool = True) -> str:
    """One line per recognised part, for a person or an agent reading a terminal."""
    lines = [parsed.normalized] if header else []
    for item in parsed.to_dict()["tokens"]:
        reading = f" -> {item['label']}" if item["kind"] == "date" else ""
        lines.append(f"  {item['kind']}: {item['text']}{reading}")
    return "".join(line + "\n" for line in lines)


SOURCE_LABELS = {"environment": "environment (TODOIST_API_TOKEN)", "tod.cfg": "tod.cfg"}


def _token_command(args, environment, tod_path, stdin, stdout, stderr, opener) -> int:
    """token set|status|clear. The token only ever travels on stdin, and never comes back out."""
    action = args.text[0] if len(args.text) == 1 else ""
    saved = saved_config_path(environment)

    def respond(payload: dict[str, object], plain: str, code: int = 0) -> int:
        if args.json:
            _write(stdout, payload)
        else:
            (stdout if code == 0 else stderr).write(plain + "\n")
        return code

    if action == "status":
        token, source = resolve_token(environment, tod_path)
        if not token:
            return respond(
                {"ok": False, "source": None, "error": "No Todoist token."},
                "error: No Todoist token. Run: printf %s \"$TOKEN\" | quick-task token set",
                1,
            )
        label = SOURCE_LABELS.get(source, f"saved ({saved})")
        try:
            premium = get_json(f"{API_URL}/user", token=token, opener=opener).get("is_premium") is True
        except TodoistError as error:
            return respond({"ok": False, "source": source, "error": str(error)}, f"error: Token: {label}. {error}", 1)
        return respond(
            {"ok": True, "source": source, "premium": premium},
            f"Token: {label}, accepted by Todoist" + (" (Pro)" if premium else ""),
        )

    if action == "set":
        if saved is None:
            raise TodoistError("Could not find a home folder to save the token in.")
        if stdin.isatty():
            raise TodoistError('Pipe the token in: printf %s "$TOKEN" | quick-task token set')
        token = stdin.readline(1024).strip()  # one line: the overlay never closes its end of the pipe
        get_json(f"{API_URL}/user", token=token, opener=opener)  # Todoist must accept it before it is kept
        save_token(saved, token)
        _token, source = resolve_token(environment, tod_path)
        note = " TODOIST_API_TOKEN is set and still takes priority." if source == "environment" else ""
        return respond({"ok": True, "saved": True, "source": source}, f"Saved to {saved}.{note}")

    if action == "clear":
        removed = clear_saved(saved)
        _token, source = resolve_token(environment, tod_path)
        left = f" Still using {SOURCE_LABELS.get(source, source)}." if source else " No token is left."
        return respond(
            {"ok": True, "source": source or None},
            ("Saved token removed." if removed else "No saved token.") + left,
        )

    if len(args.text) > 1 and args.text[0] == "set":
        raise TodoistError("Do not pass the token as an argument (every user can read arguments): pipe it in.")
    raise TodoistError("Use: quick-task token set | status | clear")


def _fail(message: str, stdout: IO[str], stderr: IO[str], *, plain: bool) -> int:
    if plain:
        stderr.write(f"error: {message}\n")
    else:
        _write(stdout, {"ok": False, "error": message})
    return 1


def _apply_plan(result: dict[str, object], plan, description: str, token: str, opener: Callable[..., Any]) -> list[str]:
    """Apply by id what Quick Add cannot read. The task already exists, so a failure here is a warning."""
    warnings: list[str] = []
    task_id = str(result.get("id", ""))
    if description.strip():
        try:
            set_description(task_id, description, token=token, opener=opener)
        except TodoistError as error:
            warnings.append(f"Added, but could not save the description: {error}")
    if plan.labels:
        known = [str(label) for label in result.get("labels") or []]
        labels = known + [label for label in plan.labels if label not in known]
        try:
            set_labels(task_id, labels, token=token, opener=opener)
        except TodoistError as error:
            warnings.append(f"Could not set the label: {error}")
    if plan.project_id:
        try:
            move_task(task_id, project_id=plan.project_id, section_id=plan.section_id, token=token, opener=opener)
        except TodoistError as error:
            warnings.append(f"Added to Inbox, but could not move it: {error}")
    return warnings


def main(
    argv: Sequence[str] | None = None,
    *,
    stdin: IO[str] | None = None,
    stdout: IO[str] | None = None,
    stderr: IO[str] | None = None,
    environ: Mapping[str, str] | None = None,
    opener: Callable[..., Any] | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        prog="quick-task",
        description=DESCRIPTION,
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("command", choices=("parse", "add", "account", "sync", "token"))
    parser.add_argument("text", nargs="*", help="the task sentence (add, parse), or set|status|clear (token); omit to read the overlay's JSON from stdin")
    parser.add_argument("--note", default="", help="description to attach to the task (add)")
    parser.add_argument("--json", action="store_true", help="print the overlay's JSON instead of a plain line")
    args = parser.parse_args(argv)
    input_stream = stdin or sys.stdin
    output_stream = stdout or sys.stdout
    error_stream = stderr or sys.stderr
    from_argv = bool(args.text)
    environment = os.environ if environ is None else environ

    config_value = environment.get("QUICK_TASK_TOD_CONFIG", "")
    config_path = Path(config_value) if config_value else None

    try:
        if args.command == "token":
            return _token_command(args, environment, config_path, input_stream, output_stream, error_stream, opener or urlopen)
        if args.command == "account":
            _write(output_stream, {"ok": True, "account": load_cache(cache_path(environment))})
            return 0
        if args.command == "sync":
            token = load_token(environment, config_path)
            account = fetch_account(token, opener=opener or urlopen)
            save_cache(account, cache_path(environment))
            _write(output_stream, {"ok": True, "account": load_cache(cache_path(environment))})
            return 0

        if from_argv:
            payload = {"text": " ".join(args.text), "description": args.note}
        elif input_stream.isatty():
            raise TodoistError("Give the task as arguments: quick-task add \"buy milk tomorrow p1\".")
        else:
            payload = _read_request(input_stream)
        account = load_cache(cache_path(environment))
        parsed = _parse_payload(payload, account)
        if args.command == "parse":
            if from_argv and not args.json:
                output_stream.write(_describe_parse(parsed))
            else:
                _write(output_stream, {"ok": True, "result": parsed.to_dict()})
            return 0

        plan = plan_add(parsed.normalized, account)
        if not plan.text.strip():
            raise TodoistError("Type a task before adding it.")
        description = payload.get("description", "")
        if not isinstance(description, str):
            raise ValueError("description must be a string")
        token = load_token(environment, config_path)
        transport = opener or urlopen
        result = quick_add(plan.text, token=token, opener=transport)
        warnings = _apply_plan(result, plan, description, token, transport)
        if from_argv and not args.json:
            content = result.get("content") or plan.text
            output_stream.write(f"Added: {content} ({result.get('id', '')})\n")
            output_stream.write(_describe_parse(parsed, header=False))
            for warning in warnings:
                error_stream.write(f"warning: {warning}\n")
        else:
            _write(
                output_stream,
                {"ok": True, "result": result, "parsed": parsed.to_dict(), "warnings": warnings},
            )
        return 0
    except TodoistError as error:
        return _fail(str(error), output_stream, error_stream, plain=from_argv and not args.json)
    except (json.JSONDecodeError, UnicodeError, ValueError, TypeError, OSError):
        return _fail("Quick Task received invalid input.", output_stream, error_stream, plain=from_argv and not args.json)


if __name__ == "__main__":
    raise SystemExit(main())
