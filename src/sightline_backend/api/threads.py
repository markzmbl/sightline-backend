"""Threads: a question plus its revisions, each revision one run."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query

from sightline_backend.api import WS, ThreadId, Ws, problems
from sightline_backend.contract import CreateThread, Revise, RunCreated, Thread, ThreadPage
from sightline_backend.errors import not_implemented

router = APIRouter(prefix=WS)


@router.get(
    "/threads",
    operation_id="listThreads",
    response_description="Threads, most recently updated first.",
    responses=problems(404, 422),
)
async def list_threads(
    ws: Ws,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ThreadPage:
    raise not_implemented()


@router.post(
    "/threads",
    operation_id="createThread",
    status_code=202,
    description="Ask a question. 429 (too_many_active) while the workspace has as many runs "
    "queued, running or asking as it allows.",
    response_description="The thread exists and its first run is queued.",
    responses=problems(404, 422, 429),
)
async def create_thread(ws: Ws, body: CreateThread) -> RunCreated:
    raise not_implemented()


@router.get(
    "/threads/{thread_id}",
    operation_id="getThread",
    response_description="The thread with its latest run in full and every run in brief, "
    "oldest first.",
    responses=problems(404),
)
async def get_thread(ws: Ws, thread_id: ThreadId) -> Thread:
    raise not_implemented()


@router.post(
    "/threads/{thread_id}/revisions",
    operation_id="reviseThread",
    status_code=202,
    description="Revise the question by prompt. Post it directly, never /cancel first: a run "
    "of this thread still active is superseded (it ends with status superseded). Cancel is "
    "cooperative at stage boundaries, so the old run may emit events for up to a minute; "
    "clients drop events of runs that are not the thread's active run.",
    response_description="The revision's run is queued.",
    responses=problems(404, 422, 429),
)
async def revise_thread(ws: Ws, thread_id: ThreadId, body: Revise) -> RunCreated:
    raise not_implemented()


@router.delete(
    "/threads/{thread_id}/revisions/{n}",
    operation_id="takeBackRevision",
    status_code=202,
    description="Take back revision n (n >= 1 is the thread's nth revision). Like "
    "reviseThread, it supersedes a run of this thread still active and starts a new run, "
    "whose prompt is the text taken back.",
    response_description="The revision is taken back and the thread runs again without it.",
    responses=problems(404, 422, 429),
)
async def take_back_revision(
    ws: Ws, thread_id: ThreadId, n: Annotated[int, Path(ge=1)]
) -> RunCreated:
    raise not_implemented()
