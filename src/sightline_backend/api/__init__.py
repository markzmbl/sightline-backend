"""The routes, one module per resource, with the contract's paths and operationIds.

Everything a workspace owns lives under /api/v1/workspaces/{ws}; only /healthz and
/api/v1/me do not. Each error a route can answer is listed with its status, and every one
of them is a Problem (errors.py); a 404 names the codes that route can answer. A route lists
501 while it is a stub, and drops it when its phase builds it.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Path

from sightline_backend.contract import Problem, ProblemCode

WS = "/api/v1/workspaces/{ws}"

Ws = Annotated[str, Path()]
ThreadId = Annotated[str, Path()]
RunId = Annotated[str, Path()]
StepId = Annotated[str, Path()]
EntryId = Annotated[str, Path()]

_PROBLEMS = {
    409: "The run or entry is not in a state that allows this; code says why.",
    422: "The request is not valid; errors says where.",
    429: "The workspace has too many active runs (code too_many_active); Retry-After says "
    "when to try again.",
    501: "Not built yet: the route is a stub (code not_implemented).",
}
_RETRY_AFTER = {
    "Retry-After": {
        "description": "Seconds to wait before trying again.",
        "required": True,
        "schema": {"type": "integer"},
    }
}


def problems(
    *statuses: int, not_found: tuple[ProblemCode, ...] = ()
) -> dict[int | str, dict[str, Any]]:
    """The `responses` entries for the errors a route answers, each a Problem.

    `not_found` names the 404 codes the route can answer, and only those; a route lists 404
    exactly when it names them.
    """
    if (404 in statuses) != bool(not_found):
        raise ValueError("a route that lists 404 names its codes in not_found, and only then")
    found: dict[int | str, dict[str, Any]] = {}
    for status in statuses:
        description = _missing(not_found) if status == 404 else _PROBLEMS[status]
        found[status] = {"model": Problem, "description": description}
        if status == 429:
            found[status]["headers"] = _RETRY_AFTER
    return found


def _missing(codes: tuple[ProblemCode, ...]) -> str:
    if codes == ("no_workspace",):
        return "No such workspace: code no_workspace."
    listed = codes[0] if len(codes) == 1 else f"{', '.join(codes[:-1])} or {codes[-1]}"
    return f"No such workspace, or nothing by that id in it: code {listed}."
