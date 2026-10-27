"""The service, the caller and a workspace's warehouse: health, getMe, getSchema."""

from __future__ import annotations

from fastapi import APIRouter

from sightline_backend.api import WS, Ws, problems
from sightline_backend.contract import Health, Me, SchemaInfo
from sightline_backend.errors import not_implemented

router = APIRouter()


@router.get(
    "/healthz",
    operation_id="health",
    response_model_exclude_none=True,
    response_description="The service is up.",
)
async def health() -> Health:
    # the core's version joins with the core (P4): runs.core_version, the SHA and dirty flag
    return Health(ok=True)


@router.get(
    "/api/v1/me",
    operation_id="getMe",
    description="The caller and every workspace. v1 has no auth: the caller is the one dev "
    "user, a key user in every workspace.",
    response_description="The caller and the workspaces they may use.",
    responses=problems(501),
)
async def get_me() -> Me:
    raise not_implemented()


@router.get(
    f"{WS}/schema",
    operation_id="getSchema",
    description="The workspace's warehouse as users read it, for browsing what can be asked.",
    response_description="The workspace's tables with their columns, and its measures.",
    responses=problems(404, 501, not_found=("no_workspace",)),
)
async def get_schema(ws: Ws) -> SchemaInfo:
    raise not_implemented()
