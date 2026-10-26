"""Runs: read one, answer its card, cancel it, switch its chart, rate it."""

from __future__ import annotations

from fastapi import APIRouter

from sightline_backend.api import WS, RunId, Ws, problems
from sightline_backend.contract import Answers, ChartPick, Feedback, RunCreated, RunView
from sightline_backend.errors import not_implemented

router = APIRouter(prefix=WS)


@router.get(
    "/runs/{run_id}",
    operation_id="getRun",
    response_description="The run as it stands.",
    responses=problems(404),
)
async def get_run(ws: Ws, run_id: RunId) -> RunView:
    raise not_implemented()


@router.post(
    "/runs/{run_id}/answers",
    operation_id="answerCard",
    status_code=202,
    description="Answer the choice card. A null answer means \"decide for me\". Free text "
    "becomes a revision of the thread, which starts a new run. Answers are taken on the "
    "thread's latest run while it is asking, or when it is complete with a card that does "
    "not block; the run then goes back to queued under the same run_id. 409: not_latest, "
    "not_answerable, or stale_run (the run was made by another core version).",
    response_description="The run resumes (same run_id) or a revision starts (new run_id).",
    responses=problems(404, 409, 422, 429),
)
async def answer_card(ws: Ws, run_id: RunId, body: Answers) -> RunCreated:
    raise not_implemented()


@router.post(
    "/runs/{run_id}/cancel",
    operation_id="cancelRun",
    status_code=202,
    description="Stop a run that is queued, running or asking; it ends with status "
    "cancelled. 409 (not_active) when the run has already ended.",
    response_description="Cancelling; the event stream reports when it has stopped.",
    responses=problems(404, 409),
)
async def cancel_run(ws: Ws, run_id: RunId) -> RunCreated:
    raise not_implemented()


@router.post(
    "/runs/{run_id}/chart",
    operation_id="pickChart",
    status_code=202,
    description="Draw the run with another of its charts. Taken on the thread's latest run "
    "when it is complete and the chart is one of its alternatives; the run goes back to "
    "queued under the same run_id. 409: not_latest or not_answerable.",
    response_description="The run presents again with the chosen chart.",
    responses=problems(404, 409, 422, 429),
)
async def pick_chart(ws: Ws, run_id: RunId, body: ChartPick) -> RunCreated:
    raise not_implemented()


@router.post(
    "/runs/{run_id}/feedback",
    operation_id="giveFeedback",
    status_code=204,
    description="Rate the run, up or down; a null rating clears it.",
    response_description="Recorded.",
    responses=problems(404, 422),
)
async def give_feedback(ws: Ws, run_id: RunId, body: Feedback) -> None:
    raise not_implemented()
