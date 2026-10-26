"""A run's event stream (server-sent events), one stream per run.

FastAPI streams an EventSourceResponse route from its generator, so an error the stream
answers (404, and 501 until P5 builds it) is raised by a dependency, before the response
starts. The OpenAPI document shows the stream as RunEvent frames and the Last-Event-ID
header; app.py writes that part, since FastAPI documents an SSE route as generic frames.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Header
from fastapi.sse import EventSourceResponse, ServerSentEvent

from sightline_backend.api import WS, RunId, Ws, problems
from sightline_backend.contract import RunEvent
from sightline_backend.errors import not_implemented

router = APIRouter(prefix=WS)

EVENTS_PATH = f"{WS}/runs/{{run_id}}/events"


async def _stream_not_built() -> None:
    raise not_implemented()


@router.get(
    "/runs/{run_id}/events",
    operation_id="runEvents",
    response_class=EventSourceResponse,
    dependencies=[Depends(_stream_not_built)],
    description="Server-sent events. Each frame is `id: <n>`, `event: <type>` and "
    "`data: <RunEvent as JSON>`; ids increase per run. Reconnect with `Last-Event-ID` to get "
    "only the frames after it (ids are per-run integers from 1, the same counter as "
    "RunView.last_event_id). A comment line `: ping` comes every 15 s. The stream ends after "
    "a terminal run.status (complete, clarify, failed, cancelled, superseded) or after asking.",
    response_description="The event stream.",
    responses={200: {"model": RunEvent}, **problems(404)},
)
async def run_events(
    ws: Ws,
    run_id: RunId,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> AsyncIterator[ServerSentEvent]:
    # an empty stream, never opened: the dependency answers first
    return
    yield
