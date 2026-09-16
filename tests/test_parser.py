from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from quick_task.parser import parse_quick_text


NOW = datetime(2026, 9, 16, 14, 0, tzinfo=ZoneInfo("Europe/Amsterdam"))


@pytest.mark.parametrize(
    ("phrase", "expected"),
    [
        ("mon", "2026-09-21"),
        ("monday", "2026-09-21"),
        ("lun", "2026-09-21"),
        ("lunes", "2026-09-21"),
        ("this Friday", "2026-09-18"),
        ("este viernes", "2026-09-18"),
        ("next Tuesday", "2026-09-22"),
        ("el próximo martes", "2026-09-22"),
        ("today", "2026-09-16"),
        ("tod", "2026-09-16"),
        ("hoy", "2026-09-16"),
        ("tomorrow", "2026-09-17"),
        ("tom", "2026-09-17"),
        ("tmrw", "2026-09-17"),
        ("mañana", "2026-09-17"),
        ("manana", "2026-09-17"),
        ("pasado mañana", "2026-09-18"),
    ],
)
def test_bilingual_relative_and_weekday_phrases_become_absolute_dates(phrase, expected):
    result = parse_quick_text(f"Plan demo {phrase}", now=NOW)

    assert result.normalized == f"Plan demo {expected}"
    assert [token.kind for token in result.tokens] == ["date"]
    assert result.tokens[0].text == phrase
    assert result.tokens[0].value == expected


@pytest.mark.parametrize("phrase", ["21st", "21º", "el 21"])
def test_day_of_month_forms_resolve_in_the_current_month_when_still_ahead(phrase):
    result = parse_quick_text(f"Renew passport {phrase}", now=NOW)

    assert result.normalized == "Renew passport 2026-09-21"
    assert result.tokens[0].label == "Mon 21 Sep"


def test_past_day_of_month_rolls_forward_instead_of_creating_an_overdue_task():
    result = parse_quick_text("Send invoice el 10", now=NOW)

    assert result.normalized == "Send invoice 2026-10-10"


def test_spanish_accents_are_optional_but_original_text_is_preserved_in_token():
    result = parse_quick_text("Revisión miercoles", now=NOW)

    assert result.normalized == "Revisión 2026-09-16"
    assert result.tokens[0].text == "miercoles"


def test_spanish_time_next_to_a_date_is_normalized_without_eating_task_metadata():
    result = parse_quick_text(
        "Preparar demo este viernes a las 9 #Trabajo p1", now=NOW
    )

    assert result.normalized == "Preparar demo 2026-09-18 at 09:00 #Trabajo p1"
    assert result.tokens[0].value == "2026-09-18T09:00"


def test_an_ignored_recognition_stays_literal_for_the_current_draft():
    first = parse_quick_text("Create monthly report mon", now=NOW)
    ignored_id = first.tokens[0].id

    second = parse_quick_text(
        "Create monthly report mon", now=NOW, ignored=(ignored_id,)
    )

    assert second.normalized == "Create monthly report mon"
    assert second.tokens == ()


def test_plain_numbers_are_not_mistaken_for_dates():
    result = parse_quick_text("Buy 21 screws", now=NOW)

    assert result.normalized == "Buy 21 screws"
    assert result.tokens == ()


def test_multiple_date_phrases_do_not_overlap_or_duplicate_tokens():
    result = parse_quick_text("Review tomorrow and ship fri", now=NOW)

    assert result.normalized == "Review 2026-09-17 and ship 2026-09-18"
    assert [(token.text, token.value) for token in result.tokens] == [
        ("tomorrow", "2026-09-17"),
        ("fri", "2026-09-18"),
    ]


def test_result_serializes_to_the_cli_contract():
    result = parse_quick_text("Call Marta el 21", now=NOW)

    assert result.to_dict() == {
        "original": "Call Marta el 21",
        "normalized": "Call Marta 2026-09-21",
        "tokens": [
            {
                "id": result.tokens[0].id,
                "kind": "date",
                "text": "el 21",
                "value": "2026-09-21",
                "label": "Mon 21 Sep",
                "start": 11,
                "end": 16,
            }
        ],
    }
