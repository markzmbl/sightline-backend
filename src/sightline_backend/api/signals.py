"""Client beacons, stored as raw signals; the server records the rest of them itself."""

from __future__ import annotations

from fastapi import APIRouter

from sightline_backend.api import WS, Ws, problems
from sightline_backend.contract import Signal
from sightline_backend.errors import not_implemented

router = APIRouter(prefix=WS)


@router.post(
    "/signals",
    operation_id="sendSignal",
    status_code=204,
    description="A beacon from the client, stored as a raw event that nothing interprets in "
    "v1: thread_opened when the user opens a thread.",
    response_description="Recorded.",
    responses=problems(404, 422),
)
async def send_signal(ws: Ws, body: Signal) -> None:
    raise not_implemented()
