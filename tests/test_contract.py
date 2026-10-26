"""The contract: the committed document, the event union, the routes and the error shape."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any, get_args

import pytest
import yaml
from fastapi.testclient import TestClient

from sightline_backend.api import WS
from sightline_backend.api.events import EVENTS_PATH
from sightline_backend.app import create_app, openapi_json
from sightline_backend.contract import Problem, RunEvent

ROOT = Path(__file__).resolve().parent.parent
CONTRACT = ROOT / "contract" / "openapi.json"
# the frontend's draft, kept in sightline-web until this repo's contract replaces it
DRAFT = ROOT.parent / "sightline-web" / "contract" / "openapi.draft.yaml"
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

# The contract as the frontend's types see it, written out so that a change to a model or a
# route fails here until it is made on purpose: every operation's method and path, and every
# schema's properties (`?` outside required), enum values or union members. A change here is
# a contract change, agreed with the frontend session first.
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
    "Answers": "answers text?",
    "AskPolicy": "never|unsure|always",
    "Card": "blocking points",
    "CardEvent": "card run_id type",
    "Cell": "string|integer|number|boolean|null",
    "ChartEvent": "chart run_id type",
    "ChartOption": "chart hint label score",
    "ChartPick": "chart",
    "ChartView": "alternatives chart label png_url spec",
    "Clarify": "gaps missing nearest record warnings",
    "ClarifyEvent": "clarify run_id type",
    "Column": "name type",
    "CreateThread": "ask? question",
    "DecidedBy": "rules|s1|s2|user",
    "DecisionPoint": "by chosen confidence default id open options question stage step why",
    "Definition": "label name source status",
    "Demand": "first_asked last_asked runs",
    "EntryChoice": "count label option",
    "EntryGap": "missing record",
    "EntryRun": "at question rating run_id thread_id",
    "EntrySource": "kind text",
    "ErrorEvent": "message run_id stage type",
    "ErrorItem": "ctx? loc msg type",
    "Feedback": "rating",
    "Gap": "reason requested slot suggestions",
    "Health": "ok version?",
    "Me": "user workspaces",
    "Option": "hint id label",
    "Problem": "code? detail errors?",
    "Rating": "up|down",
    "RegistryCounts": "default gap measure",
    "RegistryEntry": "choices? definition demand gap? id kind label note reviewed_by source "
    "status term updated_at version words",
    "RegistryEntryDetail": "choices? definition demand gap? id kind label note reviewed_by "
    "runs source status term updated_at version words",
    "RegistryKind": "measure|default|gap",
    "RegistryPage": "counts items next_cursor",
    "RegistryStatus": "proposed|approved|rejected",
    "RestatementEvent": "run_id text type",
    "Result": "chart columns findings row_count rows sql truncated",
    "ResultEvent": "result run_id type",
    "Review": "action changes? note? version",
    "ReviewAction": "approve|reject|reopen|edit",
    "ReviewChanges": "label? words?",
    "Revise": "message",
    "RunCreated": "run_id thread_id",
    "RunError": "message stage",
    "RunEvent": "RunStatusEvent|StageStartedEvent|StageFinishedEvent|RestatementEvent|"
    "CardEvent|ClarifyEvent|ChartEvent|ResultEvent|ErrorEvent",
    "RunStatus": "queued|running|asking|complete|clarify|failed|cancelled|superseded",
    "RunStatusEvent": "run_id status type",
    "RunSummary": "feedback finished_at id prompt restatement revision started_at status",
    "RunView": "card clarify definitions error feedback finished_at id last_event_id phase "
    "prompt restatement result revision stage started_at status thread_id timings",
    "Signal": "kind thread_id",
    "SignalKind": "thread_opened",
    "StageFinishedEvent": "at elapsed_ms phase run_id stage type",
    "StageStartedEvent": "at phase run_id stage type",
    "StageTiming": "elapsed_ms phase stage started_at",
    "Thread": "created_at id latest question runs updated_at",
    "ThreadPage": "items next_cursor",
    "ThreadSummary": "active_run_id id question restatement revisions status updated_at",
    "User": "email? id name",
    "Workspace": "id name pack",
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
    branches = schema.get("oneOf") or schema.get("anyOf") or []
    return "|".join(b["$ref"].rsplit("/", 1)[1] if "$ref" in b else b["type"] for b in branches)


def _parameters(doc: dict[str, Any], path: str, op: dict[str, Any]) -> dict[Any, Any]:
    # (name, in) -> (required, schema), the path's own parameters included and $refs
    # resolved; FastAPI's titles are left out, they do not reach the client's types
    found = {}
    for parameter in [*doc["paths"][path].get("parameters", []), *op.get("parameters", [])]:
        if "$ref" in parameter:
            parameter = doc["components"]["parameters"][parameter["$ref"].rsplit("/", 1)[1]]
        schema = {k: v for k, v in parameter["schema"].items() if k != "title"}
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
    # the same method, path, parameters and request body, and at least its responses
    draft = yaml.safe_load(DRAFT.read_text(encoding="utf-8"))
    ours = {op["operationId"]: (method, path, op) for method, path, op in _operations(DOC)}
    for method, path, op in _operations(draft):
        name = op["operationId"]
        assert name in ours, name
        our_method, our_path, our_op = ours[name]
        assert (our_method, our_path) == (method, path), name
        assert _parameters(DOC, our_path, our_op) == _parameters(draft, path, op), name
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
    url = path.format(ws="w1", thread_id="t1", run_id="r1", entry_id="e1", n=1)
    response = client.request(method, url, json=body)
    assert response.status_code == 501
    assert response.json() == {"detail": "not implemented yet", "code": "not_implemented"}


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
    for item in problem["errors"]:
        assert {"loc", "msg", "type"} <= set(item) <= {"loc", "msg", "type", "ctx"}
    assert [(e["loc"], e["type"]) for e in problem["errors"]] == [
        (["body", "question"], "string_too_short")
    ]


@pytest.mark.parametrize(
    ("path", "body", "loc"),
    [
        ("/threads", {"question": "best\x00plant"}, ["body", "question"]),
        ("/threads/t1/revisions", {"message": "line\x002"}, ["body", "message"]),
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
