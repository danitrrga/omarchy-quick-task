from __future__ import annotations

import json
from pathlib import Path
import subprocess


LOGIC = Path(__file__).parents[1] / "QuickTaskLogic.js"

ACCOUNT = {
    "projects": [
        {"id": "1", "name": "Inbox", "inbox": True},
        {"id": "2", "name": "Work", "shared": True},
        {"id": "3", "name": "Mi Casa"},
        {"id": "4", "name": "Planificación"},
        {"id": "5", "name": "Workshop"},
    ],
    "sections": [
        {"id": "s1", "project_id": "2", "name": "Admin"},
        {"id": "s2", "project_id": "3", "name": "Cocina"},
    ],
    "labels": [{"name": "email"}, {"name": "Emergencia"}, {"name": "reply-email"}],
    "collaborators": {"2": [{"name": "Marta", "email": "m@example.com"}]},
}


def js(expression: str, account: object = ACCOUNT):
    script = r"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync(process.argv[1], "utf8").replace(/^\.pragma library\s*/, "");
const context = {};
vm.createContext(context);
vm.runInContext(source, context);
const account = JSON.parse(process.argv[2]);
const completionAt = context.completionAt, applyCompletion = context.applyCompletion;
process.stdout.write(JSON.stringify(eval(process.argv[3])));
"""
    done = subprocess.run(
        ["node", "-e", script, str(LOGIC), json.dumps(account), expression],
        check=True, capture_output=True, text=True,
    )
    return json.loads(done.stdout)


def labels(text: str, cursor: int | None = None, account: object = ACCOUNT):
    cursor = len(text) if cursor is None else cursor
    result = js(f"completionAt({json.dumps(text)}, {cursor}, account)", account)
    return None if result is None else [item["label"] for item in result["items"]]


def test_sigil_alone_lists_every_project_in_account_order_up_to_the_cap():
    assert labels("buy #") == ["Inbox", "Work", "Mi Casa", "Planificación", "Workshop"]
    many = {"projects": [{"id": str(n), "name": f"P{n}"} for n in range(20)]}
    assert len(labels("#", account=many)) == 8


def test_typing_narrows_by_prefix_ignoring_case_and_accents():
    assert labels("buy #wo") == ["Work", "Workshop"]
    assert labels("buy #PLANIFICACION") == ["Planificación"]
    assert labels("buy #planificación") == ["Planificación"]


def test_prefix_matches_rank_before_word_start_before_substring_whatever_the_account_order():
    account = {"labels": [{"name": "zzmail"}, {"name": "reply-mail"}, {"name": "mail"}]}
    assert labels("x %mai", account=account) == ["mail", "reply-mail", "zzmail"]
    assert labels("x %em") == ["email", "Emergencia", "reply-email"]


def test_project_names_with_spaces_match_across_the_space():
    assert labels("x #mi c") == ["Mi Casa"]


def test_the_picker_closes_when_nothing_matches_or_the_sentence_moves_on():
    assert labels("x #zzz") is None
    assert labels("x #Work and then buy") is None
    assert labels("pay rent") is None


def test_sigils_inside_words_dates_and_addresses_are_not_triggers():
    # Each of these would open a picker if the sigil were not required to start a word.
    assert labels("x #Work a/ad") is None
    assert labels("x #Work a+ma") is None
    assert labels("write me@em") is None
    assert labels("write a#wo") is None
    assert labels("hurry!3") is None
    assert labels("x #Work /ad") == ["Admin"]


def test_a_section_needs_the_project_before_it_and_only_offers_that_projects_sections():
    assert labels("x #Work /") == ["Admin"]
    assert labels("x #Mi Casa /co") == ["Cocina"]
    assert labels("x /") is None
    assert labels("x #Inbox /") is None


def test_an_assignee_needs_a_shared_project_before_it():
    assert labels("x #Work +ma") == ["Marta"]
    assert labels("x +ma") is None
    assert labels("x #Mi Casa +ma") is None


def test_the_longest_project_name_wins_when_one_name_starts_another():
    account = {
        "projects": [{"id": "a", "name": "Work", "shared": True}, {"id": "b", "name": "Work Home"}],
        "sections": [{"id": "s", "project_id": "b", "name": "Garden"}],
    }
    assert labels("x #Work Home /", account=account) == ["Garden"]


def test_reminder_choices_filter_by_what_follows_the_bang():
    pro = {**ACCOUNT, "premium": True}
    assert labels("x !3", account=pro) == ["30 min before"]
    assert labels("x !", account=pro) == ["5 min before", "10 min before", "30 min before", "1 hour before", "1 day before"]


def test_the_priority_picker_is_soft_and_only_opens_on_a_lone_p_word():
    for text in ("x p", "p", "x P"):
        result = js(f"completionAt({json.dumps(text)}, {len(text)}, account)")
        assert result["soft"] is True
        assert [i["label"] for i in result["items"]] == ["p1", "p2", "p3", "p4"]
    for text in ("pay", "ap", "x p1", "x pp"):
        assert labels(text) is None
    sigil = js('completionAt("x #", 3, account)')
    assert sigil["soft"] is False


def test_the_cursor_decides_not_the_end_of_the_text():
    assert labels("buy #wo milk", 7) == ["Work", "Workshop"]
    assert labels("buy #wo milk", 12) is None


def test_applying_replaces_only_the_trigger_and_places_the_cursor_after_it():
    applied = js('applyCompletion("buy #wo", completionAt("buy #wo", 7, account), completionAt("buy #wo", 7, account).items[0])')
    assert applied == {"text": "buy #Work ", "cursor": 10}


def test_applying_mid_sentence_does_not_double_the_space():
    applied = js('applyCompletion("buy #wo milk", completionAt("buy #wo milk", 7, account), completionAt("buy #wo milk", 7, account).items[0])')
    assert applied == {"text": "buy #Work milk", "cursor": 10}


def test_applying_a_section_keeps_the_project_before_it():
    expression = 'applyCompletion("x #Work /ad", completionAt("x #Work /ad", 11, account), completionAt("x #Work /ad", 11, account).items[0])'
    assert js(expression) == {"text": "x #Work /Admin ", "cursor": 15}


def test_an_over_long_query_is_not_a_picker():
    long_name = "n" * 45
    account = {"projects": [{"id": "1", "name": long_name}]}
    assert labels("x #" + "n" * 40, account=account) == [long_name]
    assert labels("x #" + "n" * 41, account=account) is None


def test_a_project_name_must_end_at_a_space_before_a_section_can_follow():
    account = {"projects": [{"id": "1", "name": "Work"}],
               "sections": [{"id": "s", "project_id": "1", "name": "Admin"}]}
    assert labels("x #Workshop /", account=account) is None
    assert labels("x #Work /", account=account) == ["Admin"]


def note(token: dict, account: object = ACCOUNT) -> str:
    return js(f"context.chipNote({json.dumps(token)}, account)", account)


def test_reminders_are_only_offered_on_a_pro_account():
    assert labels("x !") is None
    pro = {**ACCOUNT, "premium": True}
    assert labels("x !3", account=pro) == ["30 min before"]


def test_chips_warn_about_unknown_mentions_and_pro_only_syntax_once_the_account_is_loaded():
    assert note({"kind": "project", "known": False}) == "not found"
    assert note({"kind": "project", "known": True}) == ""
    assert note({"kind": "project"}) == ""
    assert note({"kind": "deadline"}) == "needs Todoist Pro"
    assert note({"kind": "reminder"}) == "needs Todoist Pro"
    assert note({"kind": "deadline"}, {**ACCOUNT, "premium": True}) == ""
    assert note({"kind": "priority"}) == ""


def test_chips_say_nothing_before_the_account_has_loaded():
    empty = {"projects": [], "premium": False}
    assert note({"kind": "project", "known": False}, empty) == ""
    assert note({"kind": "deadline"}, empty) == ""


def styled(text: str, tokens: list[dict]) -> str:
    return js(
        f"context.styledDraft({json.dumps(text)}, {json.dumps(tokens)}, "
        "function(t) { return t.kind === 'date' ? '#00ff00' : '#0000ff' }, '#ffffff')"
    )


def test_each_recognised_word_is_wrapped_in_its_kind_colour_and_the_rest_in_the_base_colour():
    html = styled("call tom now", [{"kind": "date", "start": 5, "end": 8}])

    assert html == (
        '<font color="#ffffff">call&nbsp;</font>'
        '<font color="#00ff00">tom</font>'
        '<font color="#ffffff">&nbsp;now</font>'
    )


def test_markup_in_the_draft_is_escaped_and_every_space_survives():
    html = styled("a <b> &  c", [])

    assert html == '<font color="#ffffff">a&nbsp;&lt;b&gt;&nbsp;&amp;&nbsp;&nbsp;c</font>'


def test_overlapping_or_out_of_range_tokens_are_skipped_not_garbled():
    tokens = [
        {"kind": "date", "start": 0, "end": 4},
        {"kind": "project", "start": 2, "end": 6},
        {"kind": "label", "start": 90, "end": 99},
        {"kind": "label", "start": 7, "end": 7},
    ]
    html = styled("abcdef gh", tokens)

    assert html.count("#00ff00") == 1 and html.count("#0000ff") == 0
    assert "abcd" in html and html.replace("&nbsp;", " ").count("ef gh") == 1


def test_the_plain_text_is_unchanged_by_styling():
    import re
    text = "x  #Work p1 <&>"
    tokens = [{"kind": "project", "start": 3, "end": 8}, {"kind": "priority", "start": 9, "end": 11}]
    html = styled(text, tokens)
    plain = re.sub(r"<[^>]+>", "", html).replace("&nbsp;", " ").replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")

    assert plain == text


def parts(tokens: list[dict], account: object = ACCOUNT) -> list[dict]:
    result = js(f"context.metaParts({json.dumps(tokens)}, account)", account)
    return [{k: p[k] for k in ("kind", "text", "note", "separator")} for p in result]


def test_the_detail_line_reads_in_words_in_typed_order_with_the_right_separators():
    tokens = [
        {"kind": "date", "text": "tmr 9am", "label": "Tue 20 Oct, 09:00"},
        {"kind": "project", "text": "#life", "known": True},
        {"kind": "section", "text": "/Rutinas 🔁", "known": True},
        {"kind": "label", "text": "@jimmy", "known": True},
        {"kind": "priority", "text": "p2"},
    ]

    assert parts(tokens) == [
        {"kind": "date", "text": "Tue 20 Oct, 09:00", "note": "", "separator": ""},
        {"kind": "project", "text": "life", "note": "", "separator": "·"},
        {"kind": "section", "text": "Rutinas 🔁", "note": "", "separator": "/"},
        {"kind": "label", "text": "jimmy", "note": "", "separator": "·"},
        {"kind": "priority", "text": "priority 2", "note": "", "separator": "·"},
    ]


def test_a_section_only_follows_a_project_with_a_slash_when_it_comes_right_after_it():
    tokens = [
        {"kind": "section", "text": "/a"}, {"kind": "label", "text": "%b"}, {"kind": "section", "text": "/c"},
    ]
    assert [p["separator"] for p in parts(tokens)] == ["", "·", "·"]


def test_unknown_and_pro_only_details_carry_their_note():
    tokens = [{"kind": "project", "text": "#zzz", "known": False}, {"kind": "deadline", "text": "{oct 30}"},
              {"kind": "reminder", "text": "!30"}]
    result = parts(tokens)

    assert result[0]["text"] == "zzz" and result[0]["note"] == "not found"
    assert result[1]["text"] == "deadline oct 30" and result[1]["note"] == "needs Todoist Pro"
    assert result[2]["text"] == "reminder 30"


def details(text: str, account: object = ACCOUNT) -> list[str]:
    result = js(f"completionAt({json.dumps(text)}, {len(text)}, account)", account)
    return [item["detail"] for item in result["items"]]


def test_a_project_row_says_how_many_sections_it_has_and_whether_it_is_inbox_or_shared():
    account = {
        "projects": [
            {"id": "1", "name": "Inbox", "inbox": True},
            {"id": "2", "name": "Work", "shared": True},
            {"id": "3", "name": "Mi Casa"},
            {"id": "4", "name": "Casa Dos"},
        ],
        "sections": [
            {"id": "a", "project_id": "2", "name": "Admin"},
            {"id": "b", "project_id": "2", "name": "Ops"},
            {"id": "c", "project_id": "3", "name": "Cocina"},
        ],
    }

    assert details("x #", account) == ["Inbox", "Shared · 2 sections", "1 section", ""]
