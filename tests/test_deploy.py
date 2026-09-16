from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess


ROOT = Path(__file__).parents[1]
DEPLOY = ROOT / "deploy.sh"

LEGACY_BINDING = (
    'o.bind("SUPER + SHIFT + SEMICOLON", "Quick task (Todoist)", '
    '"uwsm-app -- " .. os.getenv("HOME") .. "/.local/bin/tod-quickadd-launch")'
)
NEW_BINDING = (
    'o.bind("SUPER + SHIFT + SEMICOLON", "Quick task (Todoist)", '
    '"omarchy-shell shell summon danitrrga.quick-task \'{}\'")'
)
LEGACY_WINDOW_RULE = (
    '-- Todoist quick-capture popup (tod-quickadd, SUPER + SHIFT + ;)\n'
    'o.window("^(TodQuickAdd)$", { float = true, center = true, size = { 660, 195 } })\n'
)


def installation(tmp_path: Path):
    home = tmp_path / "home"
    bindings = home / ".config" / "hypr" / "bindings.lua"
    hyprland = home / ".config" / "hypr" / "hyprland.lua"
    config = home / ".config" / "tod.cfg"
    bin_dir = home / ".local" / "bin"
    share_dir = home / ".local" / "share" / "quick-task"
    plugin_dir = home / ".config" / "omarchy" / "plugins" / "danitrrga.quick-task"

    bindings.parent.mkdir(parents=True)
    bindings.write_text(
        "-- personal bindings stay intact\n" + LEGACY_BINDING + "\n-- tail comment\n",
        encoding="utf-8",
    )
    hyprland.write_text(
        "-- personal windows stay intact\n" + LEGACY_WINDOW_RULE + "-- chrome rule stays\n",
        encoding="utf-8",
    )
    config.write_text(json.dumps({"token": "fixture-token"}), encoding="utf-8")
    config.chmod(0o644)

    environment = os.environ.copy()
    environment.update(
        {
            "HOME": str(home),
            "QT_USER_HOME": str(home),
            "QT_BIN_DIR": str(bin_dir),
            "QT_SHARE_DIR": str(share_dir),
            "QT_PLUGIN_DIR": str(plugin_dir),
            "QT_BINDINGS_FILE": str(bindings),
            "QT_HYPRLAND_FILE": str(hyprland),
            "QT_TOD_CONFIG": str(config),
            "QT_SKIP_RELOAD": "1",
        }
    )
    return {
        "home": home,
        "bindings": bindings,
        "hyprland": hyprland,
        "config": config,
        "bin_dir": bin_dir,
        "share_dir": share_dir,
        "plugin_dir": plugin_dir,
        "environment": environment,
    }


def run_deploy(targets: dict[str, object]):
    return subprocess.run(
        [str(DEPLOY)],
        cwd=ROOT,
        env=targets["environment"],
        text=True,
        capture_output=True,
        check=True,
    )


def test_deploy_installs_a_working_helper_and_native_plugin(tmp_path: Path):
    targets = installation(tmp_path)

    run_deploy(targets)

    helper = targets["bin_dir"] / "quick-task"
    assert helper.is_file()
    assert helper.stat().st_mode & stat.S_IXUSR
    assert (targets["share_dir"] / "quick_task" / "parser.py").is_file()
    assert (targets["share_dir"] / "quick_task" / "todoist.py").is_file()
    assert (targets["plugin_dir"] / "manifest.json").is_file()
    assert (targets["plugin_dir"] / "QuickTask.qml").is_file()

    result = subprocess.run(
        [str(helper), "parse"],
        input='{"text":"Entregar lun","now":"2026-09-16T14:00:00+02:00"}\n',
        env=targets["environment"],
        text=True,
        capture_output=True,
        check=True,
    )
    assert json.loads(result.stdout)["result"]["normalized"] == "Entregar 2026-09-21"


def test_deploy_migrates_config_once_preserves_user_text_and_makes_backups(tmp_path: Path):
    targets = installation(tmp_path)

    run_deploy(targets)
    first_bindings = targets["bindings"].read_text(encoding="utf-8")
    first_hyprland = targets["hyprland"].read_text(encoding="utf-8")
    run_deploy(targets)

    bindings = targets["bindings"].read_text(encoding="utf-8")
    hyprland = targets["hyprland"].read_text(encoding="utf-8")
    assert bindings == first_bindings
    assert hyprland == first_hyprland
    assert bindings.count(NEW_BINDING) == 1
    assert LEGACY_BINDING not in bindings
    assert "-- personal bindings stay intact" in bindings
    assert "-- tail comment" in bindings
    assert LEGACY_WINDOW_RULE not in hyprland
    assert "-- personal windows stay intact" in hyprland
    assert "-- chrome rule stays" in hyprland

    bindings_backup = Path(str(targets["bindings"]) + ".quick-task.bak")
    hyprland_backup = Path(str(targets["hyprland"]) + ".quick-task.bak")
    assert bindings_backup.read_text(encoding="utf-8").count(LEGACY_BINDING) == 1
    assert LEGACY_WINDOW_RULE in hyprland_backup.read_text(encoding="utf-8")
    assert list(bindings_backup.parent.glob("bindings.lua.quick-task.bak*")) == [bindings_backup]
    assert list(hyprland_backup.parent.glob("hyprland.lua.quick-task.bak*")) == [hyprland_backup]


def test_deploy_hardens_the_existing_token_file_without_changing_it(tmp_path: Path):
    targets = installation(tmp_path)
    before = targets["config"].read_bytes()

    run_deploy(targets)

    assert targets["config"].read_bytes() == before
    assert stat.S_IMODE(targets["config"].stat().st_mode) == 0o600


def test_fresh_binding_file_gets_one_managed_binding_and_remains_idempotent(tmp_path: Path):
    targets = installation(tmp_path)
    targets["bindings"].write_text("-- no old quick task binding\n", encoding="utf-8")

    run_deploy(targets)
    run_deploy(targets)

    bindings = targets["bindings"].read_text(encoding="utf-8")
    assert bindings.count(NEW_BINDING) == 1
    assert bindings.count(">>> quick-task (managed)") == 1
    assert bindings.count("<<< quick-task (managed)") == 1
