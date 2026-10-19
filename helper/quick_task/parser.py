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
from collections.abc import Mapping
from typing import Any, Collection

from .mentions import resolve_mentions


@dataclass(frozen=True, slots=True)
class ParsedToken:
    id: str
    kind: str
    text: str
    value: str
    label: str
    start: int
    end: int
    known: bool | None = None  # project, section and label: found in the account (None: account not loaded)

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        if data["known"] is None:
            del data["known"]
        return data


def _utf16_offset(text: str, index: int) -> int:
    return len(text[:index].encode("utf-16-le", "surrogatepass")) // 2


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
            "tokens": [self._for_qml(token) for token in self.tokens],
            "recognitions": [self._for_qml(token) for token in self.recognitions],
        }

    def _for_qml(self, token: ParsedToken) -> dict[str, object]:
        """Offsets in UTF-16 units, which is how QML and JavaScript index a string: a character such as
        an emoji is one code point here and two there, and every offset after it would be off by one."""
        data = token.to_dict()
        data["start"] = _utf16_offset(self.original, token.start)
        data["end"] = _utf16_offset(self.original, token.end)
        return data


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

_MONTH_ALIASES = {
    1: ("january", "jan", "enero", "ene"),
    2: ("february", "feb", "febrero"),
    3: ("march", "mar", "marzo"),
    4: ("april", "apr", "abril", "abr"),
    5: ("may", "mayo"),
    6: ("june", "jun", "junio"),
    7: ("july", "jul", "julio"),
    8: ("august", "aug", "agosto", "ago"),
    9: ("september", "sept", "sep", "septiembre", "setiembre", "set"),
    10: ("october", "oct", "octubre"),
    11: ("november", "nov", "noviembre"),
    12: ("december", "dec", "diciembre", "dic"),
}
_MONTH_BY_ALIAS = {alias: month for month, aliases in _MONTH_ALIASES.items() for alias in aliases}
_MONTH_PATTERN = "|".join(re.escape(alias) for alias in sorted(_MONTH_BY_ALIAS, key=len, reverse=True))
_DAY_PATTERN = r"(?:3[01]|[12]\d|0?[1-9])"

_RELATIVE_DAYS = {
    "today": 0,
    "tod": 0,
    "tdy": 0,
    "tday": 0,
    "2day": 0,
    "hoy": 0,
    "tomorrow": 1,
    "tom": 1,
    "tmr": 1,
    "tmw": 1,
    "tmrw": 1,
    "tmrrw": 1,
    "tomm": 1,
    "tomorow": 1,
    "2moro": 1,
    "2morrow": 1,
    "2mrw": 1,
    "manana": 1,
    "mnn": 1,  # "mñn", the way Spanish is typed in a hurry (ñ folds to n)
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


def _month_day(today: date, month: int, day: int, year: int | None = None) -> date | None:
    """A day in a named month. Without a year, the next one that is not already past."""
    if year is not None:
        try:
            return date(year, month, day)
        except ValueError:
            return None
    for candidate_year in range(today.year, today.year + 9):
        try:
            candidate = date(candidate_year, month, day)
        except ValueError:
            continue
        if candidate >= today:
            return candidate
    return None


def _numeric_day_month(today: date, first: int, second: int, year: int | None) -> date | None:
    """31/10 and 10/31 are unambiguous, 5/10/26 is day first. A bare 1/2 or 3/4 stays text: fractions
    are far commoner in a task than a date written without a year."""
    if first > 12 and second <= 12:
        day, month = first, second
    elif second > 12 and first <= 12:
        day, month = second, first
    elif year is not None:
        day, month = first, second
    else:
        return None
    return _month_day(today, month, day, year)


def _overlaps(candidate: _Candidate, selected: list[_Candidate]) -> bool:
    return any(candidate.start < other.end and other.start < candidate.end for other in selected)


def _add_matches(
    selected: list[_Candidate],
    pattern: re.Pattern[str],
    folded: str,
    resolver,
) -> None:
    for match in pattern.finditer(folded):
        due = resolver(match)
        if due is None:
            continue
        candidate = _Candidate(match.start(), match.end(), due)
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


def _metadata_tokens(text: str, account: Mapping[str, Any] | None = None) -> list[ParsedToken]:
    tokens: list[ParsedToken] = []
    mentions = {(m.kind, m.start): m for m in resolve_mentions(text, account)}
    loaded = bool(account and account.get("projects"))
    for kind, title, pattern in _METADATA_PATTERNS:
        for match in pattern.finditer(text):
            raw = match.group(0)
            end = match.end()
            known: bool | None = None
            if kind in ("project", "section", "label") and loaded:
                mention = mentions.get((kind, match.start()))
                known = mention is not None
                if mention is not None:
                    end = mention.end
                    raw = text[match.start():end]
            stable_text = re.sub(r"\s+", "_", _fold(raw).strip())
            tokens.append(
                ParsedToken(
                    id=f"{kind}:{match.start()}:{end}:{stable_text}",
                    kind=kind,
                    text=raw,
                    value=raw,
                    label=f"{title}  {raw}",
                    start=match.start(),
                    end=end,
                    known=known,
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
    account: Mapping[str, Any] | None = None,
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

    # Named months go before the weekday patterns: "31 mar" is March, not a Tuesday.
    def _year(match):
        text = match.group("year")
        return int(text) if text else None

    day_then_month = re.compile(
        rf"{_DATE_START}(?P<day>{_DAY_PATTERN})(?:st|nd|rd|th|o|a)?\s+(?:de\s+|of\s+)?"
        rf"(?P<month>{_MONTH_PATTERN})\b(?:\.?,?\s+(?:de\s+)?(?P<year>20\d\d)\b)?",
        re.IGNORECASE,
    )
    _add_matches(
        selected,
        day_then_month,
        folded,
        lambda match: _month_day(
            today, _MONTH_BY_ALIAS[match.group("month").casefold()], int(match.group("day")), _year(match)
        ),
    )

    month_then_day = re.compile(
        rf"{_DATE_START}(?P<month>{_MONTH_PATTERN})\b\.?\s+(?P<day>{_DAY_PATTERN})(?:st|nd|rd|th)?\b"
        rf"(?:,?\s+(?P<year>20\d\d)\b)?",
        re.IGNORECASE,
    )
    _add_matches(
        selected,
        month_then_day,
        folded,
        lambda match: _month_day(
            today, _MONTH_BY_ALIAS[match.group("month").casefold()], int(match.group("day")), _year(match)
        ),
    )

    numeric = re.compile(
        rf"(?<![\d/@%#+!{{]){_DATE_START}(?P<first>\d{{1,2}})/(?P<second>\d{{1,2}})"
        rf"(?:/(?P<year>\d{{4}}|\d{{2}}))?(?![\d/])",
        re.IGNORECASE,
    )
    _add_matches(
        selected,
        numeric,
        folded,
        lambda match: _numeric_day_month(
            today,
            int(match.group("first")),
            int(match.group("second")),
            None if not match.group("year") else (int(match.group("year")) + (2000 if len(match.group("year")) == 2 else 0)),
        ),
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

    metadata_tokens = _metadata_tokens(text, account)
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
