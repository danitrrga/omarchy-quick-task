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

from .parser import parse_quick_text
from .todoist import TodoistError, load_token, quick_add


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


def _parse_payload(payload: dict[str, object]):
    text = payload.get("text", "")
    ignored = payload.get("ignored", [])
    if not isinstance(text, str) or not isinstance(ignored, list):
        raise ValueError("invalid parse fields")
    if not all(isinstance(value, str) for value in ignored):
        raise ValueError("ignored must contain strings")
    return parse_quick_text(text, now=_parse_now(payload), ignored=ignored)


def main(
    argv: Sequence[str] | None = None,
    *,
    stdin: IO[str] | None = None,
    stdout: IO[str] | None = None,
    environ: Mapping[str, str] | None = None,
    opener: Callable[..., Any] | None = None,
) -> int:
    parser = argparse.ArgumentParser(prog="quick-task")
    parser.add_argument("command", choices=("parse", "add"))
    args = parser.parse_args(argv)
    input_stream = stdin or sys.stdin
    output_stream = stdout or sys.stdout
    environment = os.environ if environ is None else environ

    try:
        payload = _read_request(input_stream)
        parsed = _parse_payload(payload)
        if args.command == "parse":
            _write(output_stream, {"ok": True, "result": parsed.to_dict()})
            return 0

        if not parsed.original.strip():
            raise TodoistError("Type a task before adding it.")
        description = payload.get("description", "")
        if not isinstance(description, str):
            raise ValueError("description must be a string")
        config_value = environment.get("QUICK_TASK_TOD_CONFIG", "")
        config_path = Path(config_value) if config_value else None
        token = load_token(environment, config_path)
        result = quick_add(
            parsed.normalized,
            note=description,
            token=token,
            opener=opener or urlopen,
        )
        _write(
            output_stream,
            {"ok": True, "result": result, "parsed": parsed.to_dict()},
        )
        return 0
    except TodoistError as error:
        _write(output_stream, {"ok": False, "error": str(error)})
        return 1
    except (json.JSONDecodeError, UnicodeError, ValueError, TypeError, OSError):
        _write(output_stream, {"ok": False, "error": "Quick Task received invalid input."})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
