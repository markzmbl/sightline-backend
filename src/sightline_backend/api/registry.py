"""The registry the key user reviews: proposed measures, learned defaults and data gaps."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from sightline_backend.api import WS, EntryId, Ws, problems
from sightline_backend.contract import (
    RegistryEntryDetail,
    RegistryKind,
    RegistryPage,
    RegistryStatus,
    Review,
)
from sightline_backend.errors import not_implemented

router = APIRouter(prefix=f"{WS}/registry")


@router.get(
    "/entries",
    operation_id="listRegistryEntries",
    description="What sightline proposes for the key user to review, most recently asked "
    "first.",
    response_description="A page of entries, and the proposed counts per kind.",
    responses=problems(404, 422),
)
async def list_registry_entries(
    ws: Ws,
    kind: RegistryKind | None = None,
    status: RegistryStatus | None = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> RegistryPage:
    raise not_implemented()


@router.get(
    "/entries/{entry_id}",
    operation_id="getRegistryEntry",
    response_description="The entry with the runs that used it.",
    responses=problems(404),
)
async def get_registry_entry(ws: Ws, entry_id: EntryId) -> RegistryEntryDetail:
    raise not_implemented()


@router.post(
    "/entries/{entry_id}/review",
    operation_id="reviewRegistryEntry",
    description="Approve, reject, reopen or edit an entry. The request carries the version "
    "the key user saw: 409 with code version_conflict means someone reviewed it first. An "
    "edit changes only the label and the words per locale; 422 with an error of type "
    "word_collision (loc pointing at the word, ctx {word, collides_with}) means a word "
    "belongs to another term. A review applies from the next run on.",
    response_description="The entry at its new version.",
    responses=problems(404, 409, 422),
)
async def review_registry_entry(ws: Ws, entry_id: EntryId, body: Review) -> RegistryEntryDetail:
    raise not_implemented()
