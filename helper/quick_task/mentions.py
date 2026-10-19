"""Resolve #project, /section and %label mentions against the account.

Todoist's Quick Add endpoint only reads single-word names; the apps resolve a mention to an id in the
client and send that. This does the same from the cached account, so names with spaces and emoji work.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import re
import unicodedata
from typing import Any


@dataclass(frozen=True, slots=True)
class Mention:
    kind: str  # "project" | "section" | "label"
    start: int
    end: int
    name: str
    id: str = ""
    project_id: str = ""


def _fold_char(char: str) -> str:
    stripped = "".join(c for c in unicodedata.normalize("NFD", char) if not unicodedata.combining(c))
    lowered = stripped.lower()
    return lowered if len(lowered) == len(char) else char


def fold(text: str) -> str:
    """Lowercase and strip accents without changing the length, so offsets stay valid."""
    return "".join(_fold_char(char) for char in text)


def _longest(text_folded: str, start: int, entries: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    best: Mapping[str, Any] | None = None
    best_length = 0
    for entry in entries:
        name = fold(str(entry.get("name", "")))
        if not name or not text_folded.startswith(name, start):
            continue
        end = start + len(name)
        if end < len(text_folded) and not text_folded[end].isspace():
            continue
        if len(name) > best_length:
            best, best_length = entry, len(name)
    return best


def resolve_mentions(text: str, account: Mapping[str, Any] | None) -> list[Mention]:
    if not account:
        return []
    projects = account.get("projects") or []
    sections = account.get("sections") or []
    labels = account.get("labels") or []
    folded = fold(text)
    found: list[Mention] = []
    current_project = ""
    for index, char in enumerate(text):
        if char not in "#/%@" or (index > 0 and not text[index - 1].isspace()):
            continue
        start = index + 1
        if char == "#":
            entry = _longest(folded, start, projects)
            if entry:
                current_project = str(entry["id"])
                found.append(Mention("project", index, start + len(str(entry["name"])), str(entry["name"]), str(entry["id"])))
        elif char == "/" and current_project:
            scoped = [s for s in sections if str(s.get("project_id")) == current_project]
            entry = _longest(folded, start, scoped)
            if entry:
                found.append(Mention("section", index, start + len(str(entry["name"])), str(entry["name"]), str(entry["id"]), current_project))
        elif char in "%@":
            entry = _longest(folded, start, labels)
            if entry:
                found.append(Mention("label", index, start + len(str(entry["name"])), str(entry["name"])))
    return found


@dataclass(frozen=True, slots=True)
class AddPlan:
    text: str
    project_id: str = ""
    section_id: str = ""
    labels: tuple[str, ...] = ()


_ASSIGNEE = re.compile(r"(?<!\S)\+\S")
_PLAIN_NAME = re.compile(r"^[\w-]+$")


def plan_add(text: str, account: Mapping[str, Any] | None) -> AddPlan:
    """What to send to Quick Add and what to apply afterwards by id."""
    mentions = resolve_mentions(text, account)
    if not mentions:
        return AddPlan(text)
    projects = [m for m in mentions if m.kind == "project"]
    sections = [m for m in mentions if m.kind == "section"]
    project = projects[-1] if projects else None
    # An assignee is only understood next to its #project; keep that one in the text when its name is plain.
    keep_project = project is not None and bool(_ASSIGNEE.search(text)) and bool(_PLAIN_NAME.match(project.name))
    section = next((s for s in reversed(sections) if project and s.project_id == project.id), None)

    removed = [m for m in mentions if not (keep_project and m is project)]
    remaining = text
    for mention in sorted(removed, key=lambda m: m.start, reverse=True):
        remaining = remaining[: mention.start] + remaining[mention.end :]
    remaining = re.sub(r"[ \t]{2,}", " ", remaining).strip()
    labels: list[str] = []
    for mention in mentions:
        if mention.kind == "label" and mention.name not in labels:
            labels.append(mention.name)
    return AddPlan(
        text=remaining,
        project_id="" if keep_project or project is None else project.id,
        section_id="" if section is None else section.id,
        labels=tuple(labels),
    )
