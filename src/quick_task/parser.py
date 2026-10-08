"""Deterministic, bilingual normalization for Todoist Quick Add text.

Todoist remains the authority for task metadata. This module handles the small
set of date phrases that must work independent of the account language and
returns enough source-span information for the overlay to explain its reading.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
import calendar
import re
import unicodedata
from typing import Collection


@dataclass(frozen=True, slots=True)
class ParsedToken:
    id: str
    kind: str
    text: str
    value: str
    label: str
    start: int
    end: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ParseResult:
    original: str
    normalized: str
    tokens: tuple[ParsedToken, ...]
    recognitions: tuple[ParsedToken, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "original": self.original,
            "normalized": self.normalized,
            "tokens": [token.to_dict() for token in self.tokens],
            "recognitions": [token.to_dict() for token in self.recognitions],
        }


_WEEKDAY_ALIASES = {
    0: ("monday", "mon", "lunes", "lun"),
    1: ("tuesday", "tues", "tue", "martes", "mar"),
    2: ("wednesday", "weds", "wed", "miercoles", "mier", "mie"),
    3: ("thursday", "thurs", "thur", "thu", "jueves", "jue"),
    4: ("friday", "fri", "viernes", "vie"),
    5: ("saturday", "sat", "sabado", "sab"),
    6: ("sunday", "sun", "domingo", "dom"),
}

_WEEKDAY_BY_ALIAS = {
    alias: weekday
    for weekday, aliases in _WEEKDAY_ALIASES.items()
    for alias in aliases
}
_WEEKDAY_PATTERN = "|".join(
    re.escape(alias) for alias in sorted(_WEEKDAY_BY_ALIAS, key=len, reverse=True)
)

# A date word immediately following Todoist metadata sigils belongs to that
# metadata. Without this guard, `@tomorrow` becomes both a legacy label and a
# due date, and the overlay presents two incompatible readings of one span.
_DATE_START = r"(?<![@%#+/!{])\b"

_RELATIVE_DAYS = {
    "today": 0,
    "tod": 0,
    "hoy": 0,
    "tomorrow": 1,
    "tom": 1,
    "tmrw": 1,
    "manana": 1,
    "pasado manana": 2,
}

_SPANISH_TIME = re.compile(
    r"^\s+a\s+la(?:s)?\s+(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\b",
    re.IGNORECASE,
)
_CLOCK_TIME = re.compile(
    r"^\s+(?:at\s+)?(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<meridiem>am|pm)\b",
    re.IGNORECASE,
)

_WORD_JOINER = "\u2060"

_METADATA_PATTERNS = (
    ("project", "Project", re.compile(r"(?<!\S)#[^\s]+")),
    ("section", "Section", re.compile(r"(?<!\S)/[^\s]+")),
    ("label", "Label", re.compile(r"(?<!\S)[%@][^\s]+")),
    ("assignee", "Assignee", re.compile(r"(?<!\S)\+[^\s]+")),
    ("reminder", "Reminder", re.compile(r"(?<!\S)![^\s]+")),
    ("priority", "Priority", re.compile(r"(?<!\S)p[1-4](?!\S)", re.IGNORECASE)),
    ("deadline", "Deadline", re.compile(r"(?<!\S)\{[^}]+\}")),
)


@dataclass(frozen=True, slots=True)
class _Candidate:
    start: int
    end: int
    due: date


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(char for char in decomposed if not unicodedata.combining(char)).casefold()


def _next_weekday(today: date, weekday: int, *, qualified_next: bool) -> date:
    if qualified_next:
        if weekday > today.weekday():
            days = weekday - today.weekday() + 7
        else:
            days = (weekday - today.weekday()) % 7 or 7
    else:
        days = (weekday - today.weekday()) % 7
    return today + timedelta(days=days)


def _future_day_of_month(today: date, day: int) -> date:
    year, month = today.year, today.month
    for _ in range(24):
        last_day = calendar.monthrange(year, month)[1]
        if day <= last_day:
            candidate = date(year, month, day)
            if candidate >= today:
                return candidate
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
    raise ValueError(f"could not resolve day of month: {day}")


def _overlaps(candidate: _Candidate, selected: list[_Candidate]) -> bool:
    return any(candidate.start < other.end and other.start < candidate.end for other in selected)


def _add_matches(
    selected: list[_Candidate],
    pattern: re.Pattern[str],
    folded: str,
    resolver,
) -> None:
    for match in pattern.finditer(folded):
        candidate = _Candidate(match.start(), match.end(), resolver(match))
        if not _overlaps(candidate, selected):
            selected.append(candidate)


def _with_time(text: str, folded: str, candidate: _Candidate) -> tuple[int, int | None, int | None]:
    suffix = folded[candidate.end :]
    match = _SPANISH_TIME.match(suffix) or _CLOCK_TIME.match(suffix)
    if not match:
        return candidate.end, None, None

    hour = int(match.group("hour"))
    minute = int(match.group("minute") or 0)
    meridiem = match.groupdict().get("meridiem")
    if meridiem:
        if not 1 <= hour <= 12:
            return candidate.end, None, None
        if meridiem.casefold() == "pm" and hour != 12:
            hour += 12
        elif meridiem.casefold() == "am" and hour == 12:
            hour = 0
    if hour > 23 or minute > 59:
        return candidate.end, None, None
    return candidate.end + match.end(), hour, minute


def _token_id(start: int, end: int, raw: str) -> str:
    stable_text = re.sub(r"\s+", "_", _fold(raw).strip())
    return f"date:{start}:{end}:{stable_text}"


def _metadata_tokens(text: str) -> list[ParsedToken]:
    tokens: list[ParsedToken] = []
    for kind, title, pattern in _METADATA_PATTERNS:
        for match in pattern.finditer(text):
            raw = match.group(0)
            stable_text = re.sub(r"\s+", "_", _fold(raw).strip())
            tokens.append(
                ParsedToken(
                    id=f"{kind}:{match.start()}:{match.end()}:{stable_text}",
                    kind=kind,
                    text=raw,
                    value=raw,
                    label=f"{title}  {raw}",
                    start=match.start(),
                    end=match.end(),
                )
            )
    return sorted(tokens, key=lambda token: (token.start, token.end))


def _protect_literal(text: str) -> str:
    """Break Todoist syntax without changing how the task text looks."""

    if not text:
        return text
    return text[0] + _WORD_JOINER + text[1:]


def _label(due: date, hour: int | None, minute: int | None) -> str:
    day = f"{due.day}"
    base = f"{due.strftime('%a')} {day} {due.strftime('%b')}"
    if hour is not None and minute is not None:
        return f"{base}, {hour:02d}:{minute:02d}"
    return base


def parse_quick_text(
    text: str,
    *,
    now: datetime | None = None,
    ignored: Collection[str] = (),
) -> ParseResult:
    """Recognize supported date phrases and return a Todoist-safe sentence."""

    current = now or datetime.now().astimezone()
    today = current.date()
    folded = _fold(text)
    selected: list[_Candidate] = []

    relative_pattern = re.compile(
        _DATE_START + r"(?:" + "|".join(
            re.escape(value) for value in sorted(_RELATIVE_DAYS, key=len, reverse=True)
        ) + r")\b",
        re.IGNORECASE,
    )
    _add_matches(
        selected,
        relative_pattern,
        folded,
        lambda match: today + timedelta(days=_RELATIVE_DAYS[match.group(0).casefold()]),
    )

    qualified_weekday = re.compile(
        rf"{_DATE_START}(?P<qualifier>this|este|esta|next|el\s+proximo|la\s+proxima|proximo|proxima)\s+"
        rf"(?P<weekday>{_WEEKDAY_PATTERN})\b",
        re.IGNORECASE,
    )
    _add_matches(
        selected,
        qualified_weekday,
        folded,
        lambda match: _next_weekday(
            today,
            _WEEKDAY_BY_ALIAS[match.group("weekday").casefold()],
            qualified_next=match.group("qualifier").casefold()
            not in {"this", "este", "esta"},
        ),
    )

    bare_weekday = re.compile(
        rf"{_DATE_START}(?P<weekday>{_WEEKDAY_PATTERN})\b", re.IGNORECASE
    )
    _add_matches(
        selected,
        bare_weekday,
        folded,
        lambda match: _next_weekday(
            today, _WEEKDAY_BY_ALIAS[match.group("weekday").casefold()], qualified_next=False
        ),
    )

    # NFKD folds the Spanish ordinal indicators º/ª to o/a before matching.
    ordinal = re.compile(
        rf"{_DATE_START}(?P<day>[1-9]|[12]\d|3[01])(?:st|nd|rd|th|o|a)\b",
        re.IGNORECASE,
    )
    _add_matches(
        selected,
        ordinal,
        folded,
        lambda match: _future_day_of_month(today, int(match.group("day"))),
    )

    spanish_day = re.compile(
        rf"{_DATE_START}el\s+(?P<day>[1-9]|[12]\d|3[01])\b", re.IGNORECASE
    )
    _add_matches(
        selected,
        spanish_day,
        folded,
        lambda match: _future_day_of_month(today, int(match.group("day"))),
    )

    metadata_tokens = _metadata_tokens(text)
    selected = [
        candidate
        for candidate in selected
        if not any(
            candidate.start < token.end and token.start < candidate.end
            for token in metadata_tokens
        )
    ]

    date_tokens: list[ParsedToken] = []
    date_replacements: dict[str, str] = {}
    for candidate in sorted(selected, key=lambda item: item.start):
        end, hour, minute = _with_time(text, folded, candidate)
        raw = text[candidate.start:end]
        token_id = _token_id(candidate.start, end, raw)

        date_value = candidate.due.isoformat()
        value = (
            f"{date_value}T{hour:02d}:{minute:02d}"
            if hour is not None and minute is not None
            else date_value
        )
        replacement = (
            f"{date_value} at {hour:02d}:{minute:02d}"
            if hour is not None and minute is not None
            else date_value
        )
        date_tokens.append(
            ParsedToken(
                id=token_id,
                kind="date",
                text=raw,
                value=value,
                label=_label(candidate.due, hour, minute),
                start=candidate.start,
                end=end,
            )
        )
        date_replacements[token_id] = replacement

    all_tokens = sorted(date_tokens + metadata_tokens, key=lambda token: (token.start, token.end))
    last_by_kind: dict[str, ParsedToken] = {}
    for token in all_tokens:
        last_by_kind[token.kind] = token

    ignored_ids = set(ignored)
    active_tokens = [
        token
        for token in all_tokens
        if last_by_kind[token.kind].id == token.id and token.id not in ignored_ids
    ]
    active_ids = {token.id for token in active_tokens}

    replacements: list[tuple[int, int, str]] = []
    for token in all_tokens:
        if token.id in active_ids:
            if token.kind == "date":
                replacements.append((token.start, token.end, date_replacements[token.id]))
            continue
        replacements.append((token.start, token.end, _protect_literal(token.text)))

    normalized = text
    for start, end, replacement in reversed(replacements):
        normalized = normalized[:start] + replacement + normalized[end:]

    return ParseResult(
        original=text,
        normalized=normalized,
        tokens=tuple(active_tokens),
        recognitions=tuple(all_tokens),
    )
