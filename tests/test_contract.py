"""The contract: the committed document, the event union, the routes and the error shape."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any, get_args

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sightline_backend.api import WS, problems
from sightline_backend.api.events import EVENTS_PATH
from sightline_backend.app import create_app, openapi_json
from sightline_backend.contract import Problem, ProblemCode, RunEvent
from sightline_backend.errors import BUSY, HANDLERS, INVALID, NOT_BUILT, too_many_active

ROOT = Path(__file__).resolve().parent.parent
CONTRACT = ROOT / "contract" / "openapi.json"
# the frontend's draft, kept in web/ (nested beside backend/ in sightline) until this repo's
# contract replaces it
DRAFT = ROOT.parent / "web" / "contract" / "openapi.draft.yaml"
METHODS = ("get", "put", "post", "patch", "delete")
OUTSIDE_WORKSPACES = ("/healthz", "/api/v1/me")
PROBLEM = {"application/json": {"schema": {"$ref": "#/components/schemas/Problem"}}}

# a valid body for each operation that takes one, so that every stub can be called
BODIES: dict[str, Any] = {
    "createThread": {"question": "Which plant had the best OEE last quarter?"},
    "reviseThread": {"message": "only line 2"},
    "answerCard": {"answers": {"reading": None}},
    "pickChart": {"chart": "line"},
    "giveFeedback": {"rating": None},
    "reviewRegistryEntry": {"action": "approve", "version": 1},
    "sendSignal": {"kind": "thread_opened", "thread_id": "t1"},
}

# Where the contract deliberately departs from the frontend's draft at an operation: the
# parameters v0.2 adds, all optional, so a client written against the draft still works.
# listThreads and listRegistryEntries gain a text search (q) and updated_since or sort (the
# review's COULD items); runEvents gains ?last_event_id=, the fallback for a client that
# cannot send Last-Event-ID. The draft's schemas are not compared: v0.2 changes many of them
# on purpose (contract.py says how).
DRAFT_DEPARTURES = {
    "listThreads": {("q", "query"), ("updated_since", "query")},
    "listRegistryEntries": {("q", "query"), ("sort", "query")},
    "runEvents": {("last_event_id", "query")},
}

# The contract as the frontend's types see it, written out so that a change to a model or a
# route fails here until it is made on purpose: every operation's method and path, and every
# schema's properties (`?` outside required), enum values, union members or map values. A
# change here is a contract change, agreed with the frontend session first.
OPERATIONS = {
    "health": "get /healthz",
    "getMe": "get /api/v1/me",
    "getSchema": "get /api/v1/workspaces/{ws}/schema",
    "listThreads": "get /api/v1/workspaces/{ws}/threads",
    "createThread": "post /api/v1/workspaces/{ws}/threads",
    "getThread": "get /api/v1/workspaces/{ws}/threads/{thread_id}",
    "reviseThread": "post /api/v1/workspaces/{ws}/threads/{thread_id}/revisions",
    "takeBackRevision": "delete /api/v1/workspaces/{ws}/threads/{thread_id}/revisions/{n}",
    "getRun": "get /api/v1/workspaces/{ws}/runs/{run_id}",
    "getRunStep": "get /api/v1/workspaces/{ws}/runs/{run_id}/steps/{step_id}",
    "answerCard": "post /api/v1/workspaces/{ws}/runs/{run_id}/answers",
    "cancelRun": "post /api/v1/workspaces/{ws}/runs/{run_id}/cancel",
    "pickChart": "post /api/v1/workspaces/{ws}/runs/{run_id}/chart",
    "giveFeedback": "post /api/v1/workspaces/{ws}/runs/{run_id}/feedback",
    "runEvents": "get /api/v1/workspaces/{ws}/runs/{run_id}/events",
    "listRegistryEntries": "get /api/v1/workspaces/{ws}/registry/entries",
    "getRegistryEntry": "get /api/v1/workspaces/{ws}/registry/entries/{entry_id}",
    "reviewRegistryEntry": "post /api/v1/workspaces/{ws}/registry/entries/{entry_id}/review",
    "sendSignal": "post /api/v1/workspaces/{ws}/signals",
}
SHAPES = {
    "AnalysisStep": "id label",
    "Answers": "answers text?",
    "AskPolicy": "never|unsure|always",
    "CallInfo": "cost_usd from_cache kind model seconds",
    "CallKind": "s1|s2|vision",
    "Card": "blocking points",
    "CardEvent": "card run_id type",
    "Cell": "string|integer|number|boolean|null",
    "ChartEvent": "chart run_id support_id type",
    "ChartOption": "chart drawn hint label score",
    "ChartPick": "chart",
    "ChartRef": "chart label",
    "ChartView": "chart hint label min_width options png_url score spec subtitle title",
    "Clarify": "gaps missing record warnings warnings_total",
    "ClarifyEvent": "clarify run_id type",
    "Column": "description format label name role type unit",
    "ColumnRole": "dimension|measure|time",
    "CreateThread": "ask? question",
    "DecidedBy": "rules|s1|s2|user|default",
    "DecisionPoint": "by chosen confidence default entry_id id open options question stage step "
    "why",
    "Definition": "definition entry_id label name source status",
    "Demand": "first_asked last_asked runs",
    "EntryChange": "action at by note version",
    "EntryChoice": "count label option",
    "EntryGap": "missing record",
    "EntryRun": "at prompt question rating revision run_id thread_id",
    "EntrySource": "kind text",
    "ErrorEvent": "code detail message retryable run_id stage type",
    "ErrorItem": "ctx? loc msg type",
    "Feedback": "rating",
    "FollowRef": "follow_up_id kind run_id",
    "FollowRequest": "follow_up_id run_id",
    "FollowUp": "id kind question",
    "FollowUpKind": "breakdown|next_level|check|nearest",
    "Gap": "reason requested slot suggestions",
    "GapSuggestion": "id label question",
    "Health": "ok version?",
    "KeyPoint": "id text",
    "KindInfo": "kind label plural",
    "Locale": "en|de",
    "Me": "last_workspace user workspaces",
    "Option": "hint id label",
    "Problem": "code? detail errors?",
    "ProblemCode": "not_latest|not_answerable|stale_run|version_conflict|not_allowed|"
    "too_many_active|not_implemented|no_workspace|no_thread|no_run|no_entry|no_step|no_revision",
    "Rating": "up|down",
    "RegistryCounts": "{string: integer}",
    "RegistryEntry": "choices chosen_option definition demand gap id kind label note "
    "reviewed_at reviewed_by source status term updated_at version words",
    "RegistryEntryDetail": "choices chosen_option definition demand gap history id kind label "
    "note reviewed_at reviewed_by runs runs_total source status term updated_at version words",
    "RegistryKind": "measure|default|gap",
    "RegistryPage": "counts items kinds next_cursor",
    "RegistryStatus": "proposed|approved|rejected",
    "RestatementEvent": "run_id text type",
    "Result": "chart columns concerns findings lead notes row_count rows sql step_id storyline "
    "supports truncated verdict",
    "ResultEvent": "result run_id type",
    "ResultVerdict": "pass|warn|fail",
    "Review": "action changes? note? version",
    "ReviewAction": "approve|reject|reopen|edit",
    "ReviewChanges": "label? words?",
    "Revise": "follows? message via?",
    "RunCreated": "run_id thread_id",
    "RunError": "code detail message retryable stage",
    "RunErrorCode": "timeout|warehouse_unavailable|model_unavailable|budget_exhausted|internal",
    "RunEvent": "RunStatusEvent|StageStartedEvent|StageFinishedEvent|StepStartedEvent|"
    "StepFinishedEvent|RestatementEvent|CardEvent|ClarifyEvent|ChartEvent|ResultEvent|ErrorEvent",
    "RunOrigin": "question|revision|take_back|follow_up|nearest",
    "RunStatus": "queued|running|asking|complete|clarify|failed|cancelled|superseded",
    "RunStatusEvent": "run_id status type",
    "RunSummary": "chart feedback finished_at follows id origin prompt restatement revision "
    "started_at status takes_back top",
    "RunView": "card clarify definitions error feedback finished_at follow_ups follows id "
    "last_event_id locale origin phase prompt restatement result revision stage started_at "
    "status step steps takes_back thread_id timings",
    "SchemaColumn": "description label name role type unit",
    "SchemaInfo": "measures tables",
    "SchemaMeasure": "description label name unit",
    "SchemaTable": "columns description label name",
    "Signal": "kind thread_id",
    "SignalKind": "thread_opened",
    "StageFinishedEvent": "at calls? elapsed_ms phase run_id stage type",
    "StageStartedEvent": "at phase run_id stage type",
    "StageTiming": "elapsed_ms phase stage started_at",
    "StepFinishedEvent": "at cached elapsed_ms role row_count run_id sql stage step type verdict",
    "StepRecord": "cached elapsed_ms id label role row_count sql stage started_at verdict",
    "StepResult": "columns label row_count rows sql step_id truncated",
    "StepRole": "answer|probe|reference|denominator|comparison|decomposition|check|lookup",
    "StepStartedEvent": "at role run_id stage step type",
    "StepVerdict": "as_expected|contradicts|routine|inconclusive|no_effect|failed",
    "Storyline": "key_line top",
    "Support": "chart drawn id layer note point role text",
    "SupportDrawn": "main|small|dropped|none",
    "SupportRole": "answer|comparison|reference|routine_band|whole|rest|denominator|decomposition|"
    "exclusion|exception|context",
    "Thread": "created_at id latest locale question runs updated_at",
    "ThreadPage": "items next_cursor",
    "ThreadSummary": "active_run_id id question restatement revisions status updated_at",
    "User": "email id name",
    "Workspace": "id name pack role starters",
    "WorkspaceRole": "key_user|member",
}
# The 404 codes each operation can answer, as its 404 response names them; an operation
# left out lists no 404.
NOT_FOUND = {
    "getSchema": "no_workspace",
    "listThreads": "no_workspace",
    "createThread": "no_workspace",
    "getThread": "no_workspace no_thread",
    "reviseThread": "no_workspace no_thread no_run",
    "takeBackRevision": "no_workspace no_thread no_revision",
    "getRun": "no_workspace no_run",
    "getRunStep": "no_workspace no_run no_step",
    "answerCard": "no_workspace no_run",
    "cancelRun": "no_workspace no_run",
    "pickChart": "no_workspace no_run",
    "giveFeedback": "no_workspace no_run",
    "runEvents": "no_workspace no_run",
    "listRegistryEntries": "no_workspace",
    "getRegistryEntry": "no_workspace no_entry",
    "reviewRegistryEntry": "no_workspace no_entry",
    "sendSignal": "no_workspace no_thread",
}

DOC = create_app().openapi()


def _operations(doc: dict[str, Any]) -> Iterator[tuple[str, str, dict[str, Any]]]:
    for path, item in doc["paths"].items():
        for method, operation in item.items():
            if method in METHODS:
                yield method, path, operation


def _shape(schema: dict[str, Any]) -> str:
    if "properties" in schema:
        required = set(schema.get("required", []))
        return " ".join(p if p in required else f"{p}?" for p in sorted(schema["properties"]))
    if "enum" in schema:
        return "|".join(schema["enum"])
    if "const" in schema:
        return str(schema["const"])
    if "additionalProperties" in schema:
        return f"{{string: {schema['additionalProperties']['type']}}}"
    branches = schema.get("oneOf") or schema.get("anyOf") or []
    return "|".join(b["$ref"].rsplit("/", 1)[1] if "$ref" in b else b["type"] for b in branches)


def _parameters(doc: dict[str, Any], path: str, op: dict[str, Any]) -> dict[Any, Any]:
    # (name, in) -> (required, schema), the path's own parameters included and $refs
    # resolved; FastAPI's titles and descriptions are left out, they do not change the
    # client's types
    found = {}
    for parameter in [*doc["paths"][path].get("parameters", []), *op.get("parameters", [])]:
        if "$ref" in parameter:
            parameter = doc["components"]["parameters"][parameter["$ref"].rsplit("/", 1)[1]]
        schema = {k: v for k, v in parameter["schema"].items() if k not in ("title", "description")}
        found[parameter["name"], parameter["in"]] = (parameter.get("required", False), schema)
    return found


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


def test_the_committed_contract_is_a_fresh_export() -> None:
    assert CONTRACT.read_bytes() == openapi_json().encode("utf-8"), (
        "contract/openapi.json is stale: run `uv run python scripts/export_openapi.py`"
    )


def test_the_operations_are_the_contracts() -> None:
    ours = {op["operationId"]: f"{method} {path}" for method, path, op in _operations(DOC)}
    assert ours == OPERATIONS


def test_the_schemas_are_the_contracts() -> None:
    assert {n: _shape(s) for n, s in DOC["components"]["schemas"].items()} == SHAPES


def test_the_event_union_maps_every_variant() -> None:
    schemas = DOC["components"]["schemas"]
    union = schemas["RunEvent"]
    variants = {v["$ref"] for v in union["oneOf"]}
    assert union["discriminator"]["propertyName"] == "type"
    mapping = union["discriminator"]["mapping"]
    assert set(mapping.values()) == variants
    for type_, ref in mapping.items():
        variant = schemas[ref.rsplit("/", 1)[1]]
        assert {"type", "run_id"} <= set(variant["required"]), ref
        assert variant["properties"]["type"]["const"] == type_, ref
    models = get_args(RunEvent.model_fields["root"].annotation)
    assert {f"#/components/schemas/{m.__name__}" for m in models} == variants


def test_the_event_stream_is_run_events_after_last_event_id() -> None:
    stream = DOC["paths"][EVENTS_PATH]["get"]
    assert stream["responses"]["200"]["content"] == {
        "text/event-stream": {"schema": {"$ref": "#/components/schemas/RunEvent"}}
    }
    headers = [p for p in stream["parameters"] if p["in"] == "header"]
    assert [(p["name"], p["required"]) for p in headers] == [("Last-Event-ID", False)]
    # the fallback for a client that cannot send the header
    queries = [p for p in stream["parameters"] if p["in"] == "query"]
    assert [(p["name"], p["required"], p["schema"]["type"]) for p in queries] == [
        ("last_event_id", False, "integer")
    ]


def test_no_parameter_is_sent_as_null() -> None:
    # an optional parameter is left out; a null branch would widen the client's type
    for _, _, op in _operations(DOC):
        for parameter in op.get("parameters", []):
            schema = parameter["schema"]
            branches = [schema, *schema.get("anyOf", []), *schema.get("oneOf", [])]
            assert all(b.get("type") != "null" for b in branches), (
                f"{op['operationId']} {parameter['name']}"
            )


@pytest.mark.skipif(not DRAFT.exists(), reason="the frontend's draft is gone")
def test_every_operation_of_the_frontends_draft_is_here() -> None:
    # the same method, path, parameters (but for DRAFT_DEPARTURES) and request body, and at
    # least its responses
    draft = yaml.safe_load(DRAFT.read_text(encoding="utf-8"))
    ours = {op["operationId"]: (method, path, op) for method, path, op in _operations(DOC)}
    for method, path, op in _operations(draft):
        name = op["operationId"]
        assert name in ours, name
        our_method, our_path, our_op = ours[name]
        assert (our_method, our_path) == (method, path), name
        parameters = _parameters(DOC, our_path, our_op)
        added = DRAFT_DEPARTURES.get(name, set())
        assert added <= set(parameters), name
        assert not any(parameters[key][0] for key in added), name
        kept = {key: value for key, value in parameters.items() if key not in added}
        assert kept == _parameters(draft, path, op), name
        body, our_body = op.get("requestBody"), our_op.get("requestBody")
        if body is None:
            assert our_body is None, name
        else:
            assert our_body is not None, name
            assert body.get("required", False) == our_body.get("required", False), name
            assert set(body["content"]) == set(our_body["content"]), name
        assert set(op["responses"]) <= set(our_op["responses"]), name


def test_every_workspace_route_takes_the_workspace() -> None:
    for method, path, op in _operations(DOC):
        if path in OUTSIDE_WORKSPACES:
            continue
        assert path.startswith(f"{WS}/"), path
        required = {(p["name"], p["in"]) for p in op.get("parameters", []) if p["required"]}
        assert ("ws", "path") in required, f"{method} {path}"


def test_every_error_is_a_problem_and_nothing_asks_for_auth() -> None:
    assert "securitySchemes" not in DOC.get("components", {})
    assert "security" not in DOC
    for method, path, op in _operations(DOC):
        assert "security" not in op, f"{method} {path}"
        for status, response in op["responses"].items():
            if not status.startswith("2"):
                assert response.get("content") == PROBLEM, f"{method} {path} {status}"


def test_every_stub_lists_its_501_and_every_429_its_retry_after() -> None:
    for method, path, op in _operations(DOC):
        responses = op["responses"]
        if op["operationId"] != "health":
            assert "501" in responses, f"{method} {path}"
        if "429" in responses:
            headers = responses["429"].get("headers", {})
            assert set(headers) == {"Retry-After"}, f"{method} {path}"
            assert headers["Retry-After"]["schema"] == {"type": "integer"}, f"{method} {path}"
            assert headers["Retry-After"]["required"] is True, f"{method} {path}"


def test_every_404_names_only_the_codes_its_operation_answers() -> None:
    codes = set(get_args(get_args(ProblemCode.__value__)[0]))
    found = {}
    for _, _, op in _operations(DOC):
        if "404" in op["responses"]:
            named = re.findall(r"\bno_[a-z]+", op["responses"]["404"]["description"])
            assert set(named) <= codes, op["operationId"]
            found[op["operationId"]] = " ".join(named)
    assert found == NOT_FOUND


def test_a_route_lists_404_exactly_when_it_names_its_codes() -> None:
    with pytest.raises(ValueError, match="not_found"):
        problems(404, 501)
    with pytest.raises(ValueError, match="not_found"):
        problems(501, not_found=("no_run",))


@pytest.mark.parametrize(
    ("codes", "description"),
    [
        (("no_workspace",), "No such workspace: code no_workspace."),
        (("no_run",), "No such workspace, or nothing by that id in it: code no_run."),
        (
            ("no_workspace", "no_run"),
            "No such workspace, or nothing by that id in it: code no_workspace or no_run.",
        ),
        (
            ("no_workspace", "no_run", "no_step"),
            "No such workspace, or nothing by that id in it: code no_workspace, no_run or no_step.",
        ),
    ],
)
def test_a_404_lists_its_codes(codes: tuple[ProblemCode, ...], description: str) -> None:
    assert problems(404, not_found=codes)[404]["description"] == description


def test_a_429_says_when_to_try_again() -> None:
    # no route answers 429 before P4 builds the queue, so a route of its own raises it
    app = FastAPI(exception_handlers=HANDLERS)

    @app.post("/busy")
    async def busy() -> None:
        raise too_many_active(retry_after=30)

    response = TestClient(app).post("/busy")
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "30"
    assert response.json() == {"detail": BUSY, "code": "too_many_active"}


@pytest.mark.parametrize(
    ("method", "path", "op"),
    [o for o in _operations(DOC) if o[2]["operationId"] != "health"],
    ids=lambda value: value["operationId"] if isinstance(value, dict) else "",
)
def test_every_stub_answers_501_with_a_problem(
    client: TestClient, method: str, path: str, op: dict[str, Any]
) -> None:
    body = BODIES.get(op["operationId"])
    assert ("requestBody" in op) == (body is not None), f"BODIES lacks {op['operationId']}"
    url = path.format(ws="w1", thread_id="t1", run_id="r1", step_id="s1", entry_id="e1", n=1)
    response = client.request(method, url, json=body)
    assert response.status_code == 501
    assert response.json() == {"detail": NOT_BUILT, "code": "not_implemented"}


def test_health_answers(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_a_validation_error_is_a_422_problem(client: TestClient) -> None:
    response = client.post(f"{WS}/threads".format(ws="w1"), json={"question": ""})
    assert response.status_code == 422
    problem = response.json()
    Problem.model_validate(problem)
    assert set(problem) == {"detail", "errors"}
    assert problem["detail"] == INVALID
    for item in problem["errors"]:
        assert {"loc", "msg", "type"} <= set(item) <= {"loc", "msg", "type", "ctx"}
    assert [(e["loc"], e["type"]) for e in problem["errors"]] == [
        (["body", "question"], "string_too_short")
    ]


@pytest.mark.parametrize(
    ("body", "loc", "type_"),
    [
        # card text is no via: the backend marks a revision from answerCard's text itself
        ({"message": "only line 2", "via": "card_text"}, ["body", "via"], "literal_error"),
        (
            {"message": "Why?", "follows": {"run_id": "r1"}},
            ["body", "follows", "follow_up_id"],
            "missing",
        ),
        # a revision sends follows or names its via, never both, whatever the via
        *(
            (
                {"message": "Why?", "via": via, "follows": {"run_id": "r1", "follow_up_id": "f1"}},
                ["body", "via"],
                "via_with_follows",
            )
            for via in ("nearest", "composer")
        ),
    ],
)
def test_a_revision_is_checked_before_the_stub(
    client: TestClient, body: dict[str, Any], loc: list[str | int], type_: str
) -> None:
    response = client.post(WS.format(ws="w1") + "/threads/t1/revisions", json=body)
    assert response.status_code == 422
    assert [(e["loc"], e["type"]) for e in response.json()["errors"]] == [(loc, type_)]


@pytest.mark.parametrize(
    "body",
    [
        {"message": "Why?", "follows": {"run_id": "r1", "follow_up_id": "f1"}},
        {"message": "Which line had the most scrap?", "via": "nearest"},
    ],
)
def test_a_follow_up_or_a_nearest_question_reaches_the_stub(
    client: TestClient, body: dict[str, Any]
) -> None:
    response = client.post(WS.format(ws="w1") + "/threads/t1/revisions", json=body)
    assert response.status_code == 501


@pytest.mark.parametrize(("value", "type_"), [("abc", "int_parsing"), ("-1", "greater_than_equal")])
def test_a_malformed_last_event_id_is_checked_before_the_stub(
    client: TestClient, value: str, type_: str
) -> None:
    url = EVENTS_PATH.format(ws="w1", run_id="r1")
    response = client.get(url, params={"last_event_id": value})
    assert response.status_code == 422
    assert [(e["loc"], e["type"]) for e in response.json()["errors"]] == [
        (["query", "last_event_id"], type_)
    ]
    # a well-formed one reaches the stub
    assert client.get(url, params={"last_event_id": "3"}).status_code == 501


@pytest.mark.parametrize(
    ("path", "body", "loc"),
    [
        ("/threads", {"question": "best\x00plant"}, ["body", "question"]),
        ("/threads/t1/revisions", {"message": "line\x002"}, ["body", "message"]),
        (
            "/threads/t1/revisions",
            {"message": "Why?", "follows": {"run_id": "r\x001", "follow_up_id": "f1"}},
            ["body", "follows", "run_id"],
        ),
        ("/runs/r1/answers", {"answers": {"reading": "oee\x00"}}, ["body", "answers", "reading"]),
        ("/runs/r1/answers", {"answers": {}, "text": "\x00"}, ["body", "text"]),
        ("/runs/r1/chart", {"chart": "line\x00"}, ["body", "chart"]),
        (
            "/registry/entries/e1/review",
            {"action": "approve", "version": 1, "note": "ok\x00"},
            ["body", "note"],
        ),
        (
            "/registry/entries/e1/review",
            {"action": "edit", "version": 1, "changes": {"words": {"de": ["beste\x00Anlage"]}}},
            ["body", "changes", "words", "de", 0],
        ),
        ("/signals", {"kind": "thread_opened", "thread_id": "t\x001"}, ["body", "thread_id"]),
    ],
)
def test_a_nul_character_is_a_422_problem(
    client: TestClient, path: str, body: dict[str, Any], loc: list[str | int]
) -> None:
    # Postgres text and jsonb refuse a NUL, so the request is refused before it gets there
    response = client.post(WS.format(ws="w1") + path, json=body)
    assert response.status_code == 422
    assert [(e["loc"], e["type"]) for e in response.json()["errors"]] == [(loc, "nul_character")]


def test_an_unknown_route_is_a_404_problem(client: TestClient) -> None:
    response = client.get("/api/v1/nowhere")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}
