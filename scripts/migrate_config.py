#!/usr/bin/env python3
"""Perform the two exact, backup-first user-config migrations."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import tempfile


LEGACY_BINDING = (
    'o.bind("SUPER + SHIFT + SEMICOLON", "Quick task (Todoist)", '
    '"uwsm-app -- " .. os.getenv("HOME") .. "/.local/bin/tod-quickadd-launch")'
)
NEW_BINDING = (
    'o.bind("SUPER + SHIFT + SEMICOLON", "Quick task (Todoist)", '
    '"omarchy-shell shell summon danitrrga.quick-task \'{}\'")'
)
MANAGED_BINDING = (
    "\n-- >>> quick-task (managed) — do not edit inside markers >>>\n"
    + NEW_BINDING
    + "\n-- <<< quick-task (managed) <<<\n"
)
LEGACY_WINDOW_RULE = (
    "-- Todoist quick-capture popup (tod-quickadd, SUPER + SHIFT + ;)\n"
    'o.window("^(TodQuickAdd)$", { float = true, center = true, size = { 660, 195 } })\n'
)


def backup_once(path: Path) -> Path:
    backup = Path(str(path) + ".quick-task.bak")
    if not backup.exists():
        shutil.copy2(path, backup)
    return backup


def atomic_write(path: Path, text: str) -> None:
    mode = path.stat().st_mode
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=path.name + ".",
        delete=False,
    ) as handle:
        handle.write(text)
        temporary = Path(handle.name)
    os.chmod(temporary, mode)
    os.replace(temporary, path)


def migrate_bindings(path: Path) -> bool:
    original = path.read_text(encoding="utf-8")
    updated = original
    if LEGACY_BINDING in updated:
        updated = updated.replace(LEGACY_BINDING, NEW_BINDING)
    elif NEW_BINDING not in updated:
        updated = updated.rstrip() + "\n" + MANAGED_BINDING
    if updated == original:
        return False
    backup_once(path)
    atomic_write(path, updated)
    return True


def migrate_hyprland(path: Path) -> bool:
    original = path.read_text(encoding="utf-8")
    updated = original.replace(LEGACY_WINDOW_RULE, "")
    if updated == original:
        return False
    backup_once(path)
    atomic_write(path, updated)
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bindings", type=Path, required=True)
    parser.add_argument("--hyprland", type=Path, required=True)
    args = parser.parse_args()

    if not args.bindings.is_file():
        parser.error(f"bindings file not found: {args.bindings}")
    if not args.hyprland.is_file():
        parser.error(f"hyprland file not found: {args.hyprland}")

    print("bindings updated" if migrate_bindings(args.bindings) else "bindings already current")
    print("legacy window rule removed" if migrate_hyprland(args.hyprland) else "window rules already current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
