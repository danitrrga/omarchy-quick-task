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


@pytest.mark.parametrize(
    ("phrase", "expected"),
    [
        ("mon", "2026-09-21"),
        ("tue", "2026-09-22"),
        ("wed", "2026-09-16"),
        ("thu", "2026-09-17"),
        ("fri", "2026-09-18"),
        ("sat", "2026-09-19"),
        ("sun", "2026-09-20"),
        ("lun", "2026-09-21"),
        ("mar", "2026-09-22"),
        ("mie", "2026-09-16"),
        ("jue", "2026-09-17"),
        ("vie", "2026-09-18"),
        ("sab", "2026-09-19"),
        ("dom", "2026-09-20"),
    ],
)
def test_short_weekday_forms_cover_the_full_week_in_both_languages(phrase, expected):
    result = parse_quick_text(f"Plan {phrase}", now=NOW)

    assert result.normalized == f"Plan {expected}"


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
    word_joiner = "\u2060"
    first = parse_quick_text("Create monthly report mon", now=NOW)
    ignored_id = first.tokens[0].id

    second = parse_quick_text(
        "Create monthly report mon", now=NOW, ignored=(ignored_id,)
    )

    assert second.normalized == f"Create monthly report m{word_joiner}on"
    assert second.tokens == ()


def test_plain_numbers_are_not_mistaken_for_dates():
    result = parse_quick_text("Buy 21 screws", now=NOW)

    assert result.normalized == "Buy 21 screws"
    assert result.tokens == ()


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("Call Jimmy @tomorrow", "label"),
        ("Prepare slides %mon", "label"),
        ("Review #viernes", "project"),
        ("Ask +monday", "assignee"),
        ("File /mon", "section"),
        ("Nudge !tomorrow", "reminder"),
        ("Ship {mon}", "deadline"),
        ("Ship {due friday}", "deadline"),
    ],
)
def test_date_words_inside_todoist_metadata_are_not_recognized_twice(text, kind):
    result = parse_quick_text(text, now=NOW)

    assert result.normalized == text
    assert [token.kind for token in result.tokens] == [kind]


def test_todoist_metadata_is_previewed_once_in_sentence_order():
    result = parse_quick_text(
        "Review el 21 #Personal /Admin %paper +Jimmy !30min p1 {Sep 30}",
        now=NOW,
    )

    assert [(token.kind, token.text) for token in result.tokens] == [
        ("date", "el 21"),
        ("project", "#Personal"),
        ("section", "/Admin"),
        ("label", "%paper"),
        ("assignee", "+Jimmy"),
        ("reminder", "!30min"),
        ("priority", "p1"),
        ("deadline", "{Sep 30}"),
    ]


def test_only_the_last_value_of_each_kind_controls_submission():
    word_joiner = "\u2060"
    result = parse_quick_text("Review tomorrow and ship fri", now=NOW)

    assert result.normalized == f"Review t{word_joiner}omorrow and ship 2026-09-18"
    assert [(token.text, token.value) for token in result.tokens] == [("fri", "2026-09-18")]
    assert [(token.kind, token.text) for token in result.recognitions] == [
        ("date", "tomorrow"),
        ("date", "fri"),
    ]


def test_last_value_wins_for_every_todoist_metadata_kind():
    word_joiner = "\u2060"
    result = parse_quick_text(
        "Review #Old #New /First /Last %one @two +Ana +Bob "
        "!09:00 !10:00 p3 p1 {Sep 20} {Sep 30}",
        now=NOW,
    )

    assert result.normalized == (
        f"Review #{word_joiner}Old #New /{word_joiner}First /Last "
        f"%{word_joiner}one @two +{word_joiner}Ana +Bob "
        f"!{word_joiner}09:00 !10:00 p{word_joiner}3 p1 "
        f"{{{word_joiner}Sep 20}} {{Sep 30}}"
    )
    assert [(token.kind, token.text) for token in result.tokens] == [
        ("project", "#New"),
        ("section", "/Last"),
        ("label", "@two"),
        ("assignee", "+Bob"),
        ("reminder", "!10:00"),
        ("priority", "p1"),
        ("deadline", "{Sep 30}"),
    ]


def test_ignoring_the_last_value_makes_the_whole_kind_literal_without_promoting_an_older_value():
    word_joiner = "\u2060"
    first = parse_quick_text("Review tomorrow then fri p3 p1", now=NOW)
    ignored = tuple(token.id for token in first.tokens)

    second = parse_quick_text(
        "Review tomorrow then fri p3 p1",
        now=NOW,
        ignored=ignored,
    )

    assert second.tokens == ()
    assert second.normalized == (
        f"Review t{word_joiner}omorrow then f{word_joiner}ri "
        f"p{word_joiner}3 p{word_joiner}1"
    )


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
        "recognitions": [
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


import pytest

from quick_task.parser import parse_quick_text as _parse
from datetime import datetime as _datetime

_NOW = _datetime.fromisoformat("2026-10-19T09:00:00+02:00")


@pytest.mark.parametrize(
    "word", ["tmr", "tmw", "tmrw", "tmrrw", "tomm", "tomorow", "2moro", "2morrow", "2mrw", "mñn", "MNN", "Tmr"]
)
def test_the_ways_tomorrow_is_typed_in_a_hurry_all_resolve(word):
    result = _parse(f"call {word}", now=_NOW)

    assert result.normalized == "call 2026-10-20"
    assert result.tokens[0].text == word


@pytest.mark.parametrize("word", ["tdy", "tday", "2day", "TDY"])
def test_the_ways_today_is_typed_in_a_hurry_all_resolve(word):
    assert _parse(f"call {word}", now=_NOW).normalized == "call 2026-10-19"


@pytest.mark.parametrize("word", ["tmrx", "tomo", "tmrwx", "tdys", "mnnx"])
def test_near_misses_are_not_dates(word):
    assert _parse(f"call {word}", now=_NOW).tokens == ()


def test_token_offsets_are_utf16_units_so_they_index_the_string_the_way_qml_does():
    text = "Rutina 🔁 y 😀 tmr p1"
    result = _parse(text, now=_NOW).to_dict()
    utf16 = text.encode("utf-16-le")

    for token in result["tokens"]:
        start, end = token["start"] * 2, token["end"] * 2
        assert utf16[start:end].decode("utf-16-le") == token["text"]
    assert [t["text"] for t in result["tokens"]] == ["tmr", "p1"]


def test_ascii_text_is_unaffected_by_the_offset_conversion():
    result = _parse("call tmr", now=_NOW).to_dict()

    assert (result["tokens"][0]["start"], result["tokens"][0]["end"]) == (5, 8)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("pay rent 31 oct", "pay rent 2026-10-31"),
        ("pay rent oct 31", "pay rent 2026-10-31"),
        ("pay rent 31 october", "pay rent 2026-10-31"),
        ("pay rent October 31st", "pay rent 2026-10-31"),
        ("dentist 31st of october", "dentist 2026-10-31"),
        ("pagar alquiler 31 de octubre", "pagar alquiler 2026-10-31"),
        ("pagar alquiler 31 oct", "pagar alquiler 2026-10-31"),
        ("pagar 1 de diciembre", "pagar 2026-12-01"),
        ("send 31 oct 2027", "send 2027-10-31"),
        ("send oct 31, 2027", "send 2027-10-31"),
        ("send 31/10", "send 2026-10-31"),
        ("send 10/31", "send 2026-10-31"),
        ("send 5/10/26", "send 2026-10-05"),
        ("send 05/10/2027", "send 2027-10-05"),
    ],
)
def test_dates_with_a_month_resolve_in_english_and_spanish(text, expected):
    assert _parse(text, now=_NOW).normalized == expected


def test_a_month_date_that_has_passed_means_the_next_one_but_today_is_still_today():
    assert _parse("x 19 oct", now=_NOW).normalized == "x 2026-10-19"
    assert _parse("x 5 oct", now=_NOW).normalized == "x 2027-10-05"
    assert _parse("x oct 18", now=_NOW).normalized == "x 2027-10-18"
    assert _parse("x 29 feb", now=_NOW).normalized == "x 2028-02-29"


def test_a_time_after_a_month_date_stays_attached():
    assert _parse("x 31 oct at 5pm", now=_NOW).normalized == "x 2026-10-31 at 17:00"
    assert _parse("x 31 de octubre a las 9", now=_NOW).normalized == "x 2026-10-31 at 09:00"


@pytest.mark.parametrize("text", ["x 31 apr", "x 30 feb", "x 30 feb 2027", "x 31/4/2027", "x oct 2026", "x 1/2 cup", "x 3/4", "x 12/12", "x v1/2/3", "x 32 oct"])
def test_things_that_are_not_dates_stay_plain_text(text):
    assert _parse(text, now=_NOW).tokens == ()
    assert _parse(text, now=_NOW).normalized == text


def test_mar_is_march_next_to_a_day_and_tuesday_alone():
    assert _parse("x 31 mar", now=_NOW).normalized == "x 2027-03-31"
    assert _parse("x mar 5", now=_NOW).normalized == "x 2027-03-05"
    assert _parse("x mar", now=_NOW).normalized == "x 2026-10-20"


def test_a_month_date_is_one_token_with_its_own_span_and_a_readable_label():
    result = _parse("pay 31 de octubre a las 9 now", now=_NOW)
    token = result.tokens[0]

    assert token.kind == "date" and token.text == "31 de octubre a las 9"
    assert token.label == "Sat 31 Oct, 09:00"
