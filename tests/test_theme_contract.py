from __future__ import annotations

import re
from pathlib import Path


QML = (
    Path(__file__).parents[1]
    / "packaging"
    / "omarchy"
    / "plugins"
    / "danitrrga.quick-task"
    / "QuickTask.qml"
)


def qml_source() -> str:
    return QML.read_text(encoding="utf-8")


def without_comments(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    return re.sub(r"^\s*//.*$", "", source, flags=re.M)


def test_every_visible_color_comes_from_live_omarchy_roles():
    source = without_comments(qml_source())

    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", source)
    for role in (
        "Color.menu.background",
        "Color.menu.text",
        "Color.menu.border",
        "Color.menu.scrim",
        "Color.menu.selectedBackground",
        "Color.menu.selectedText",
        "Color.accent",
        "Color.urgent",
    ):
        assert role in source


def test_font_and_spacing_follow_the_live_shell_scale():
    source = without_comments(qml_source())

    assert "Style.font.menuFamily" in source
    assert "Style.font.heading" in source
    assert "Style.font.body" in source
    assert "Style.spacing.panelPadding" in source
    assert "Style.spacing.controlPaddingX" in source
    assert source.count("Style.space(") >= 4
    assert source.count("Style.spacing.") >= 12
    assert not re.search(r'font\.family:\s*["\']', source)


def test_every_drawn_corner_uses_the_single_live_theme_radius():
    source = without_comments(qml_source())
    radius_assignments = re.findall(r"\bradius\s*:\s*([^\n}]+)", source)

    assert "readonly property int cornerRadius: Style.cornerRadius" in source
    # The quiet capture surface deliberately draws very few shapes; every
    # corner that remains must still follow the live theme.
    assert len(radius_assignments) >= 2
    assert all("root.cornerRadius" in assignment for assignment in radius_assignments)
    assert not re.search(r"\bradius\s*:\s*\d", source)


def test_overlay_contains_no_machine_specific_paths_or_decorative_effects():
    source = without_comments(qml_source())

    assert "/home/" not in source
    assert "Caskaydia" not in source
    assert "DropShadow" not in source
    assert "Gradient" not in source
    assert 'Quickshell.env("HOME") + "/.local/bin/quick-task"' in source


def test_square_theme_control_would_fail_if_a_fixed_radius_were_added():
    poisoned = qml_source() + "\nRectangle { radius: 8 }\n"

    assert re.search(r"\bradius\s*:\s*\d", without_comments(poisoned))
