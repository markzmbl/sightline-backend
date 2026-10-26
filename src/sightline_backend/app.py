"""The FastAPI application, and the OpenAPI document the contract file is exported from.

create_app() wires routes and error handlers only: no database, no I/O, so the contract
can be exported and tested without a running service.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI

from sightline_backend import __version__
from sightline_backend.api import events, meta, registry, runs, signals, threads
from sightline_backend.errors import HANDLERS

DESCRIPTION = """\
Ask a question of a workspace's warehouse, revise it by prompt, and follow the run live. \
A thread is one question plus its revisions; each revision is one run. Runs are \
asynchronous: creating one answers 202 with its id, and progress arrives on the run's \
event stream. Stages are not monotonic: a reconsider loop can start abstract again after \
validate, with the phase back at understand, and side states (clarify, ask, reconsider, \
restore) can appear as a stage. A run can go from complete back to queued under the same \
id (an answer to a beside-the-chart card, a chart switch); a run.status queued after \
running means a worker restarted it. Every error is a Problem. There is no auth in v1: \
calls are same-origin and carry no header.
"""

_PROBLEM = {"$ref": "#/components/schemas/Problem"}
_LAST_EVENT_ID = {
    "name": "Last-Event-ID",
    "in": "header",
    "required": False,
    "description": "The id of the last frame seen; the stream resumes after it.",
    "schema": {"type": "string"},
}


class ContractAPI(FastAPI):
    """FastAPI whose OpenAPI document is the contract (see _contract)."""

    def openapi(self) -> dict[str, Any]:
        if self.openapi_schema is None:
            self.openapi_schema = _contract(super().openapi())
        return self.openapi_schema


def _contract(doc: dict[str, Any]) -> dict[str, Any]:
    """FastAPI's document, changed where it does not say what the API does.

    - FastAPI adds a 422 HTTPValidationError to any route with parameters; the routes list
      the 422s they can answer, and every error is a Problem.
    - No security: v1 has no auth.
    - The event stream is RunEvent frames, with the Last-Event-ID header; FastAPI shows an
      SSE route as generic frames and its errors as text/event-stream too.
    """
    for path in doc["paths"].values():
        for operation in path.values():
            operation.pop("security", None)
            responses = operation.get("responses", {})
            invalid = responses.get("422", {}).get("content", {}).get("application/json", {})
            if invalid.get("schema", {}).get("$ref", "").endswith("/HTTPValidationError"):
                del responses["422"]
    schemas = doc.get("components", {}).get("schemas", {})
    for name in ("HTTPValidationError", "ValidationError"):
        schemas.pop(name, None)
    doc.get("components", {}).pop("securitySchemes", None)
    doc.pop("security", None)

    stream = doc["paths"][events.EVENTS_PATH]["get"]
    for status, response in stream["responses"].items():
        media = "text/event-stream" if status == "200" else "application/json"
        schema = {"$ref": "#/components/schemas/RunEvent"} if status == "200" else _PROBLEM
        response["content"] = {media: {"schema": schema}}
    params = [p for p in stream.get("parameters", []) if p.get("name") != "Last-Event-ID"]
    stream["parameters"] = [*params, _LAST_EVENT_ID]
    return doc


def create_app() -> FastAPI:
    app = ContractAPI(
        title="sightline API",
        version=__version__,
        description=DESCRIPTION,
        servers=[{"url": "/"}],
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
        redoc_url=None,
        exception_handlers=HANDLERS,
    )
    for module in (meta, threads, runs, events, registry, signals):
        app.include_router(module.router)
    return app


def openapi_json() -> str:
    """The contract as contract/openapi.json holds it: sorted keys, LF, a final newline."""
    return json.dumps(create_app().openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
