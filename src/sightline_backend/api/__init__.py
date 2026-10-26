"""The routes, one module per resource, with the contract's paths and operationIds.

Everything a workspace owns lives under /api/v1/workspaces/{ws}; only /healthz and
/api/v1/me do not. Each error a route can answer is listed with its status, and every one
of them is a Problem (errors.py).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Path

from sightline_backend.contract import Problem

WS = "/api/v1/workspaces/{ws}"

Ws = Annotated[str, Path()]
ThreadId = Annotated[str, Path()]
RunId = Annotated[str, Path()]
EntryId = Annotated[str, Path()]

_PROBLEMS = {
    404: "No such workspace, or nothing by that id in it.",
    409: "The run or entry is not in a state that allows this; code says why.",
    422: "The request is not valid; errors says where.",
    429: "The workspace has too many active runs (code too_many_active).",
}


def problems(*statuses: int) -> dict[int | str, dict[str, Any]]:
    """The `responses` entries for the errors a route answers, each a Problem."""
    return {s: {"model": Problem, "description": _PROBLEMS[s]} for s in statuses}
