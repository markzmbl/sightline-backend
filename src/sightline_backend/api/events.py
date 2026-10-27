"""A run's event stream (server-sent events), one stream per run.

FastAPI streams an EventSourceResponse route from its generator, so an error the stream
answers (404, and 501 until P5 builds it) is raised by a dependency, before the response
starts. That dependency takes ?last_event_id=: FastAPI calls a dependency only when its
parameters are valid, so a malformed one is a 422 before the 501, as on every other stub.
The OpenAPI document shows the stream as RunEvent frames and the Last-Event-ID header;
app.py writes that part, since FastAPI documents an SSE route as generic frames.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query
from fastapi.sse import EventSourceResponse, ServerSentEvent

from sightline_backend.api import WS, RunId, Ws, problems
from sightline_backend.contract import RunEvent
from sightline_backend.errors import not_implemented

router = APIRouter(prefix=WS)

EVENTS_PATH = f"{WS}/runs/{{run_id}}/events"


async def _stream_not_built(
    last_event_id: Annotated[
        int | None,
        Query(ge=0, description="The id of the last frame seen, when Last-Event-ID is absent."),
    ] = None,
) -> None:
    raise not_implemented()


@router.get(
    "/runs/{run_id}/events",
    operation_id="runEvents",
    response_class=EventSourceResponse,
    dependencies=[Depends(_stream_not_built)],
    description="Server-sent events. Each frame is `id: <n>`, `event: <type>` and "
    "`data: <RunEvent as JSON>`; ids increase per run. The stream opens with a `retry: 3000` "
    "line, so a client reconnects after 3 s. Reconnect with `Last-Event-ID` to get only the "
    "frames after it (ids are per-run integers from 1, the same counter as "
    "RunView.last_event_id); `?last_event_id=` is the fallback when the header is absent, "
    "e.g. on the first connect after getRun, and a malformed one is a 422. A comment line "
    "`: ping` comes every 15 s. The stream ends after a terminal run.status (complete, "
    "clarify, failed, cancelled, superseded) or after asking.\n\n"
    "A complete run tells, in this order: run.status queued, then running; stage.started "
    "and stage.finished per stage, with step.started and step.finished inside the analyse "
    "stage (not the whole analyse phase); restatement right after bind, and again when the "
    "text changes; chart after render, the main chart first, then each small chart with its "
    "support_id; card when it applies, result; the terminal run.status. The storyline and "
    "supports ride only on the result event and RunView.result, the follow-ups only on "
    "RunView: getRun has them after the terminal run.status.\n\n"
    "The other endings: a failed run tells the error event just before run.status failed; "
    "a clarify run tells a clarify event, then run.status clarify, and no result event; an "
    "asking run tells the card event, then run.status asking; a cancelled or superseded run "
    "tells only its run.status.",
    response_description="The event stream.",
    responses={
        200: {"model": RunEvent},
        **problems(404, 422, 501, not_found=("no_workspace", "no_run")),
    },
)
async def run_events(
    ws: Ws,
    run_id: RunId,
    last_event_id_header: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> AsyncIterator[ServerSentEvent]:
    # an empty stream, never opened: the dependency answers first
    return
    yield
