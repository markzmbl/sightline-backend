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

DOC = create_app().openapi()


def _operations(doc: dict[str, Any]) -> Iterator[tuple[str, str, dict[str, Any]]]:
    for path, item in doc["paths"].items():
        for method, operation in item.items():
            if method in METHODS:
                yield method, path, operation


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


def test_the_committed_contract_is_a_fresh_export() -> None:
    assert CONTRACT.read_bytes() == openapi_json().encode("utf-8"), (
        "contract/openapi.json is stale: run `uv run python scripts/export_openapi.py`"
    )


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


@pytest.mark.skipif(not DRAFT.exists(), reason="the frontend's draft is gone")
def test_every_operation_of_the_frontends_draft_is_here() -> None:
    draft = yaml.safe_load(DRAFT.read_text(encoding="utf-8"))
    ours = {op["operationId"]: (method, path) for method, path, op in _operations(DOC)}
    for method, path, op in _operations(draft):
        assert ours.get(op["operationId"]) == (method, path), op["operationId"]


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


def test_a_nul_character_is_a_422_problem(client: TestClient) -> None:
    response = client.post(f"{WS}/threads".format(ws="w1"), json={"question": "best\x00plant"})
    assert response.status_code == 422
    assert [(e["loc"], e["type"]) for e in response.json()["errors"]] == [
        (["body", "question"], "nul_character")
    ]


def test_an_unknown_route_is_a_404_problem(client: TestClient) -> None:
    response = client.get("/api/v1/nowhere")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}
