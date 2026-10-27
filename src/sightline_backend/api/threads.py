"""Threads: a question plus the runs after it (revisions, follow-ups, take-backs)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Path, Query

from sightline_backend.api import WS, ThreadId, Ws, problems
from sightline_backend.contract import CreateThread, Revise, RunCreated, Thread, ThreadPage
from sightline_backend.errors import not_implemented

router = APIRouter(prefix=WS)


@router.get(
    "/threads",
    operation_id="listThreads",
    description="The workspace's threads, most recently updated first. A thread's updated_at "
    "moves when a run is created or changes status; feedback and signals do not move it.",
    response_description="Threads, most recently updated first.",
    responses=problems(404, 422, 501, not_found=("no_workspace",)),
)
async def list_threads(
    ws: Ws,
    q: Annotated[
        str | None, Query(description="A text search over the questions and prompts.")
    ] = None,
    updated_since: Annotated[
        datetime | None, Query(description="Only threads updated at or after this time.")
    ] = None,
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
    responses=problems(404, 422, 429, 501, not_found=("no_workspace",)),
)
async def create_thread(ws: Ws, body: CreateThread) -> RunCreated:
    raise not_implemented()


@router.get(
    "/threads/{thread_id}",
    operation_id="getThread",
    response_description="The thread with its latest run in full and every run in brief, "
    "oldest first.",
    responses=problems(404, 501, not_found=("no_workspace", "no_thread")),
)
async def get_thread(ws: Ws, thread_id: ThreadId) -> Thread:
    raise not_implemented()


@router.post(
    "/threads/{thread_id}/revisions",
    operation_id="reviseThread",
    status_code=202,
    description="Revise the question by prompt, or send a follow-up or a nearest question "
    "from the transcript. Post it directly, never /cancel first: a run of this thread still "
    "active is superseded (it ends with status superseded). Cancel is cooperative at stage "
    "boundaries, so the old run may emit events for up to a minute; clients drop events of "
    "runs that are not the thread's active run.\n\n"
    "Each run answers an anchor, which is the question or the latest follow-up or nearest "
    "question in its chain, plus the revisions typed after that anchor. A typed revision "
    "after a follow-up revises the follow-up. Any standalone question sent from the "
    "transcript (a follow-up, a nearest question) becomes the new anchor; composer and "
    "card-text revisions never do. A take-back re-runs revision n-1 and copies its anchor; "
    "taking back a follow-up re-runs the parent's reading.\n\n"
    "How a follow-up is sent depends on the status of the run that offered it, not on the "
    "follow-up's kind. A clarify run has no answer, so its follow-ups (its nearest questions) "
    "go with via nearest and no follows; a complete run's follow-ups, kind nearest included, "
    "go with follows. via is never sent with follows: 422 with errors[0] {loc: [body, via], "
    "type: via_with_follows}.\n\n"
    "With follows: follows.run_id must name a run of this thread, else 404 no_run, and be "
    "the thread's latest run, else 409 not_latest. That run must be complete and "
    "follow_up_id one of its follow_ups, else 409 not_answerable. Follow-up ids are unique "
    "per run and survive a chart pick, but may vanish after a side-card answer re-presents "
    "the run, and a vanished id is not_answerable too. message must equal that follow-up's "
    "question, else 422 with errors[0] {loc: [body, message], type: follow_up_mismatch}. A "
    "follow-up offered by a run an earlier version of sightline made is allowed, never "
    "stale_run: its question stands on its own, so the new run answers it with today's "
    "core.\n\n"
    "With via nearest: the thread's latest run must be a clarify run and message the "
    "question of one of its follow_ups (kind nearest), else 409 not_answerable.",
    response_description="The revision's run is queued.",
    responses=problems(404, 409, 422, 429, 501, not_found=("no_workspace", "no_thread", "no_run")),
)
async def revise_thread(ws: Ws, thread_id: ThreadId, body: Revise) -> RunCreated:
    raise not_implemented()


@router.delete(
    "/threads/{thread_id}/revisions/{n}",
    operation_id="takeBackRevision",
    status_code=202,
    description="Take back revision n (n >= 1 is the thread's nth run after the question). "
    "Like reviseThread, it supersedes a run of this thread still active and starts a new run "
    "(origin take_back, takes_back n), whose prompt is the text taken back. It re-runs "
    "revision n-1 with that revision's anchor; taking back a follow-up re-runs the parent's "
    "reading. 404 with code no_revision when n names no revision: beyond the latest, or one "
    "already taken back.",
    response_description="The revision is taken back and the thread runs again without it.",
    responses=problems(404, 422, 429, 501, not_found=("no_workspace", "no_thread", "no_revision")),
)
async def take_back_revision(
    ws: Ws, thread_id: ThreadId, n: Annotated[int, Path(ge=1)]
) -> RunCreated:
    raise not_implemented()
