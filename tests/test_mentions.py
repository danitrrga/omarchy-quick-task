from __future__ import annotations

from io import StringIO
import json
from pathlib import Path
from urllib.error import HTTPError

import pytest

from quick_task.account import save_cache
from quick_task.cli import main
from quick_task.mentions import plan_add, resolve_mentions
from quick_task.parser import parse_quick_text
from quick_task.todoist import TodoistError, quick_add

ACCOUNT = {
    "projects": [
        {"id": "1", "name": "life"},
        {"id": "2", "name": "Mi Casa"},
        {"id": "3", "name": "Work"},
        {"id": "4", "name": "Work Home"},
    ],
    "sections": [
        {"id": "s1", "project_id": "1", "name": "Rutinas 🔁"},
        {"id": "s2", "project_id": "2", "name": "Cocina"},
        {"id": "s3", "project_id": "1", "name": "Cocina"},
    ],
    "labels": [{"name": "FOR JIMMY"}, {"name": "jimmy"}],
}


def test_names_with_spaces_emoji_and_any_case_resolve_to_ids():
    plan = plan_add("Water plants #LIFE /rutinas 🔁 tomorrow", ACCOUNT)

    assert plan.text == "Water plants tomorrow"
    assert (plan.project_id, plan.section_id) == ("1", "s1")


def test_accents_are_ignored_and_the_longest_project_name_wins():
    assert plan_add("x #work home", ACCOUNT).project_id == "4"
    assert plan_add("x #work", ACCOUNT).project_id == "3"
    account = {"projects": [{"id": "9", "name": "Planificación"}]}
    assert plan_add("x #planificacion", account).project_id == "9"


def test_a_section_belongs_to_the_project_written_before_it():
    assert plan_add("x #Mi Casa /Cocina", ACCOUNT).section_id == "s2"
    assert plan_add("x #life /Cocina", ACCOUNT).section_id == "s3"
    assert plan_add("x /Cocina", ACCOUNT) == plan_add("x /Cocina", None)
    assert plan_add("x /Cocina", ACCOUNT).text == "x /Cocina"


def test_labels_resolve_with_either_sigil_and_keep_their_spelling():
    plan = plan_add("x @for jimmy and %jimmy", ACCOUNT)

    assert plan.labels == ("FOR JIMMY", "jimmy")
    assert plan.text == "x and"


def test_unknown_mentions_stay_literal_text_as_in_todoist():
    plan = plan_add("buy #zzz @nolabel", ACCOUNT)

    assert plan.text == "buy #zzz @nolabel"
    assert (plan.project_id, plan.section_id, plan.labels) == ("", "", ())


def test_a_name_must_end_at_a_space_so_a_longer_word_is_not_a_match():
    assert plan_add("x #lifestyle", ACCOUNT).text == "x #lifestyle"
    assert plan_add("x #life", ACCOUNT).project_id == "1"
    assert plan_add("x #Mi Casas", ACCOUNT).project_id == ""


def test_the_same_label_twice_is_applied_once():
    assert plan_add("x @jimmy @jimmy", ACCOUNT).labels == ("jimmy",)


def test_mentions_inside_words_or_protected_as_literal_are_not_resolved():
    assert resolve_mentions("a#life", ACCOUNT) == []
    assert resolve_mentions("x #⁠life", ACCOUNT) == []


def test_an_assignee_keeps_a_plain_project_name_in_the_text_for_todoist_to_read():
    kept = plan_add("x #Work +marta", ACCOUNT)
    assert kept.text == "x #Work +marta" and kept.project_id == ""
    spaced = plan_add("x #Mi Casa +marta", ACCOUNT)
    assert spaced.project_id == "2" and "+marta" in spaced.text


def test_the_parser_extends_a_token_over_a_multi_word_name_and_marks_unknowns():
    result = parse_quick_text("Plan #Mi Casa /Cocina and #zzz", account=ACCOUNT,
                              now=None)
    by_text = {t.text: t for t in result.recognitions}

    assert by_text["#Mi Casa"].known is True
    assert by_text["/Cocina"].known is True
    assert by_text["#zzz"].known is False


def test_without_an_account_tokens_keep_their_old_single_word_span_and_no_known_flag():
    result = parse_quick_text("Plan #Mi Casa", account=None)
    token = result.tokens[0]

    assert token.text == "#Mi" and token.known is None
    assert "known" not in token.to_dict()


def test_a_date_word_inside_a_project_name_is_not_read_as_a_date():
    account = {"projects": [{"id": "1", "name": "Lunes Libre"}]}
    result = parse_quick_text("x #Lunes Libre", account=account)

    assert [t.kind for t in result.tokens] == ["project"]
    assert result.normalized == "x #Lunes Libre"


# --- the add command -------------------------------------------------------


class Response:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False

    def read(self, _limit=-1):
        return self._body


def run_add(text: str, tmp_path: Path, *, fail_on: str = "", labels_from_quick_add=()):
    cache_home = tmp_path / "cache"
    save_cache(ACCOUNT, cache_home / "quick-task" / "account.json")
    calls: list[tuple[str, str, dict]] = []

    def opener(request, *, timeout):
        body = json.loads(request.data) if request.data else {}
        calls.append((request.get_method(), request.full_url.rsplit("/api/v1", 1)[1], body))
        if fail_on and fail_on in request.full_url:
            raise HTTPError(request.full_url, 400, "bad", {}, None)
        if request.full_url.endswith("/tasks/quick"):
            return Response({"id": "t1", "labels": list(labels_from_quick_add)})
        return Response({"id": "t1"})

    stdout = StringIO()
    code = main(["add"], stdin=StringIO(json.dumps({"text": text, "now": "2026-09-16T14:00:00+02:00"}) + "\n"),
                stdout=stdout, environ={"TODOIST_API_TOKEN": "tok-secret", "XDG_CACHE_HOME": str(cache_home)},
                opener=opener)
    return code, json.loads(stdout.getvalue()), calls


def test_add_sends_the_stripped_text_then_moves_and_labels_by_id(tmp_path):
    code, output, calls = run_add("Water plants #life /Rutinas 🔁 @for jimmy p2", tmp_path)

    assert code == 0 and output["warnings"] == []
    assert calls[0] == ("POST", "/tasks/quick", {"text": "Water plants p2", "meta": True})
    assert ("POST", "/tasks/t1/move", {"project_id": "1", "section_id": "s1"}) in calls
    assert ("POST", "/tasks/t1", {"labels": ["FOR JIMMY"]}) in calls


def test_labels_quick_add_already_applied_are_kept(tmp_path):
    _, _, calls = run_add("x @for jimmy", tmp_path, labels_from_quick_add=["urgent"])

    assert ("POST", "/tasks/t1", {"labels": ["urgent", "FOR JIMMY"]}) in calls


def test_a_task_without_resolved_mentions_makes_exactly_one_call(tmp_path):
    _, _, calls = run_add("Buy milk tomorrow", tmp_path)

    assert len(calls) == 1


def test_a_failed_move_is_a_warning_because_the_task_already_exists(tmp_path):
    code, output, calls = run_add("x #life", tmp_path, fail_on="/move")

    assert code == 0 and output["ok"] is True
    assert output["warnings"] and "Inbox" in output["warnings"][0]
    assert "tok-secret" not in json.dumps(output)


def test_a_mention_only_task_is_rejected_before_any_call(tmp_path):
    code, output, calls = run_add("#life", tmp_path)

    assert code == 1 and "Type a task" in output["error"]
    assert calls == []


def test_without_a_cached_account_the_text_goes_to_quick_add_unchanged(tmp_path):
    calls = []

    def opener(request, *, timeout):
        calls.append(json.loads(request.data))
        return Response({"id": "t1"})

    stdout = StringIO()
    main(["add"], stdin=StringIO(json.dumps({"text": "x #life"}) + "\n"), stdout=stdout,
         environ={"TODOIST_API_TOKEN": "t", "XDG_CACHE_HOME": str(tmp_path / "empty")}, opener=opener)

    assert calls == [{"text": "x #life", "meta": True}]


# --- the API's own reason --------------------------------------------------


def test_a_premium_only_refusal_shows_the_apis_reason_without_the_token():
    class Body:
        def read(self, _n=-1):
            return b'{"error":"Deadlines are a premium only feature tok-secret","error_tag":"PREMIUM_ONLY"}'

        def close(self):
            pass

    def opener(request, *, timeout):
        raise HTTPError(request.full_url, 403, "no", {}, Body())

    with pytest.raises(TodoistError) as error:
        quick_add("x {oct 30}", token="tok-secret", opener=opener)

    assert "Deadlines are a premium only feature" in str(error.value)
    assert "tok-secret" not in str(error.value)


def test_a_refusal_without_a_readable_body_keeps_the_generic_message():
    def opener(request, *, timeout):
        raise HTTPError(request.full_url, 403, "no", {}, None)

    with pytest.raises(TodoistError, match="^Todoist refused this task.$"):
        quick_add("x", token="t", opener=opener)
