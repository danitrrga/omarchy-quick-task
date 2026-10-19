from __future__ import annotations

import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).parents[1]
LOGIC = ROOT / "QuickTaskLogic.js"


def run_logic() -> dict[str, object]:
    script = r"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync(process.argv[1], "utf8")
  .replace(/^\.pragma library\s*/, "");
const context = {};
vm.createContext(context);
vm.runInContext(source, context);
const tokens = [
  { id: "date:5:8:fri", kind: "date", start: 5, end: 8 },
  { id: "priority:9:11:p1", kind: "priority", start: 9, end: 11 }
];
const recognitions = [
  { id: "date:5:8:fri", kind: "date", start: 5, end: 8 },
  { id: "date:14:17:tue", kind: "date", start: 14, end: 17 },
  { id: "priority:18:20:p1", kind: "priority", start: 18, end: 20 }
];
process.stdout.write(JSON.stringify({
  after: context.tokenEndingAt(tokens, 11, 11, 11),
  elsewhere: context.tokenEndingAt(tokens, 10, 10, 10),
  selection: context.tokenEndingAt(tokens, 11, 9, 11),
  remaining: context.withoutToken(tokens, "priority:9:11:p1"),
  literalized: context.literalizeKind("Plan fri then tue p1", recognitions, "date"),
  cursor: context.cursorAfterLiteralizingKind(17, recognitions, "date")
}));
"""
    result = subprocess.run(
        ["node", "-e", script, str(LOGIC)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_backspace_immediately_after_a_token_returns_that_token():
    assert run_logic()["after"]["id"] == "priority:9:11:p1"


def test_backspace_elsewhere_or_with_a_selection_keeps_normal_editing_behavior():
    result = run_logic()

    assert result["elsewhere"] is None
    assert result["selection"] is None


def test_ignored_token_disappears_immediately_from_visible_state():
    assert run_logic()["remaining"] == [
        {"id": "date:5:8:fri", "kind": "date", "start": 5, "end": 8}
    ]


def test_literalizing_keeps_the_visible_word_and_moves_the_cursor_past_the_invisible_guard():
    result = run_logic()

    assert result["literalized"] == "Plan f\u2060ri then t\u2060ue p1"
    assert result["cursor"] == 19
