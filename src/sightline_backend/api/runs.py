"""Runs: read one or one of its steps, answer its card, cancel it, switch its chart, rate it."""

from __future__ import annotations

from fastapi import APIRouter

from sightline_backend.api import WS, RunId, StepId, Ws, problems
from sightline_backend.contract import (
    Answers,
    ChartPick,
    Feedback,
    RunCreated,
    RunView,
    StepResult,
)
from sightline_backend.errors import not_implemented

router = APIRouter(prefix=WS)


@router.get(
    "/runs/{run_id}",
    operation_id="getRun",
    description="Any run of the workspace, older and superseded runs included.",
    response_description="The run as it stands.",
    responses=problems(404, 501, not_found=("no_workspace", "no_run")),
)
async def get_run(ws: Ws, run_id: RunId) -> RunView:
    raise not_implemented()


@router.get(
    "/runs/{run_id}/steps/{step_id}",
    operation_id="getRunStep",
    description="One step's SQL and rows, at most the first 200: a step of RunView.steps, or "
    "the step Result.step_id names. 404 with code no_step when the run has no such step.",
    response_description="The step's SQL and rows.",
    responses=problems(404, 501, not_found=("no_workspace", "no_run", "no_step")),
)
async def get_run_step(ws: Ws, run_id: RunId, step_id: StepId) -> StepResult:
    raise not_implemented()


@router.post(
    "/runs/{run_id}/answers",
    operation_id="answerCard",
    status_code=202,
    description="Answer the choice card. A null answer (\"decide for me\") keeps the chosen "
    "option (an approved default, else System 1's lean, else the rules' default), and by stays "
    "default, s1 or rules. Free text becomes a revision of the thread (marked card text), "
    "which starts a new run. Answers are taken on the thread's latest run while it is asking, "
    "or when it is complete with a card that does not block; the run then goes back to queued "
    "under the same run_id and keeps its rating, though a follow-up may vanish when it "
    "presents again. 409: not_latest, not_answerable, or "
    "stale_run (the run was made by an earlier version of sightline and can't be changed any "
    "more; ask again for a fresh answer; errors[0].ctx carries {prompt}).",
    response_description="The run resumes (same run_id) or a revision starts (new run_id).",
    responses=problems(404, 409, 422, 429, 501, not_found=("no_workspace", "no_run")),
)
async def answer_card(ws: Ws, run_id: RunId, body: Answers) -> RunCreated:
    raise not_implemented()


@router.post(
    "/runs/{run_id}/cancel",
    operation_id="cancelRun",
    status_code=202,
    description="Stop a run that is queued, running or asking; it ends with status "
    "cancelled. Idempotent: on a run that has already ended the answer is the same 202; "
    "nothing changes and no event follows.",
    response_description="Cancelling; the event stream reports when it has stopped.",
    responses=problems(404, 501, not_found=("no_workspace", "no_run")),
)
async def cancel_run(ws: Ws, run_id: RunId) -> RunCreated:
    raise not_implemented()


@router.post(
    "/runs/{run_id}/chart",
    operation_id="pickChart",
    status_code=202,
    description="Draw the run with another of its charts. Taken on the thread's latest run "
    "when it is complete and the chart is one of its options; the run goes back to queued "
    "under the same run_id. The form point is set to chosen = the chart, by = user, and a "
    "card event follows. The options keep their order, the comparison layers stay, and the "
    "run keeps its rating and its follow-up ids. 409: not_latest, not_answerable or "
    "stale_run.",
    response_description="The run presents again with the chosen chart.",
    responses=problems(404, 409, 422, 429, 501, not_found=("no_workspace", "no_run")),
)
async def pick_chart(ws: Ws, run_id: RunId, body: ChartPick) -> RunCreated:
    raise not_implemented()


@router.post(
    "/runs/{run_id}/feedback",
    operation_id="giveFeedback",
    status_code=204,
    description="Rate the run, up or down; a null rating clears it. A chart switch or a "
    "side-card answer keeps the run's rating.",
    response_description="Recorded.",
    responses=problems(404, 422, 501, not_found=("no_workspace", "no_run")),
)
async def give_feedback(ws: Ws, run_id: RunId, body: Feedback) -> None:
    raise not_implemented()
