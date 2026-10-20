from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from quick_task.credentials import (
    clear_saved,
    config_path,
    resolve_token,
    save_token,
)
from quick_task.todoist import TodoistError


def test_config_path_follows_xdg_then_home_and_is_none_without_either(tmp_path: Path):
    assert config_path({"XDG_CONFIG_HOME": str(tmp_path)}) == tmp_path / "quick-task" / "config.json"
    assert config_path({"HOME": str(tmp_path)}) == tmp_path / ".config" / "quick-task" / "config.json"
    assert config_path({}) is None


def test_saved_token_round_trips_in_a_private_file(tmp_path: Path):
    path = tmp_path / "quick-task" / "config.json"

    save_token(path, "abc123")

    assert json.loads(path.read_text()) == {"token": "abc123"}
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert [p.name for p in path.parent.iterdir()] == ["config.json"]


def test_overwriting_keeps_the_file_private(tmp_path: Path):
    path = tmp_path / "quick-task" / "config.json"
    save_token(path, "first")
    os.chmod(path, 0o644)

    save_token(path, "second")

    assert json.loads(path.read_text())["token"] == "second"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.parametrize("bad", ["", "   ", "two words", "line\nbreak", "tab\there", "x" * 300])
def test_a_token_that_cannot_be_one_is_refused_and_nothing_is_written(tmp_path: Path, bad: str):
    path = tmp_path / "quick-task" / "config.json"

    with pytest.raises(TodoistError, match="does not look like a Todoist token") as error:
        save_token(path, bad)

    assert not path.exists()
    assert bad.strip() == "" or bad not in str(error.value)


def test_precedence_is_environment_then_saved_then_tod_cfg(tmp_path: Path):
    saved = tmp_path / "quick-task" / "config.json"
    save_token(saved, "from-saved")
    tod = tmp_path / "tod.cfg"
    tod.write_text(json.dumps({"token": "from-tod"}))
    environ = {"XDG_CONFIG_HOME": str(tmp_path)}

    assert resolve_token({**environ, "TODOIST_API_TOKEN": "from-env"}, tod) == ("from-env", "environment")
    assert resolve_token(environ, tod) == ("from-saved", "saved")
    clear_saved(saved)
    assert resolve_token(environ, tod) == ("from-tod", "tod.cfg")
    tod.unlink()
    assert resolve_token(environ, tod) == ("", "")


def test_an_unreadable_saved_file_falls_through_instead_of_crashing(tmp_path: Path):
    saved = tmp_path / "quick-task" / "config.json"
    saved.parent.mkdir()
    saved.write_text("{not json")
    tod = tmp_path / "tod.cfg"
    tod.write_text(json.dumps({"token": "from-tod"}))

    assert resolve_token({"XDG_CONFIG_HOME": str(tmp_path)}, tod) == ("from-tod", "tod.cfg")


def test_clearing_a_missing_file_is_fine(tmp_path: Path):
    assert clear_saved(tmp_path / "nope" / "config.json") is False
