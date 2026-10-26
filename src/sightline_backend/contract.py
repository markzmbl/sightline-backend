"""The API contract as pydantic models: the shapes the web client's types are generated from.

They mirror sightline-web's contract/openapi.draft.yaml with its schema names, plus the
changes agreed with the frontend session and the plan's additions (the plan's "API
contract" section). They are not the core's artifacts. Those feed System 2's prompts and
never change to suit the API, so the backend projects them into these shapes: the card from
AskReport and DecisionPoint, clarify from ClarificationReport, the chart options from
ChartCandidate, the result from ExecutionArtifact and VisPlan.findings.

contract/openapi.json is generated from these models and the routes
(scripts/export_openapi.py). A change here is a change to the contract, and it goes
through the frontend session first.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, Field, RootModel
from pydantic_core import PydanticCustomError


def _no_default(schema: dict[str, Any]) -> None:
    # openapi-typescript (defaultNonNullable) types a property with a default as always
    # present, so an optional field must not show its default
    schema.pop("default", None)


def _no_default_no_null(schema: dict[str, Any]) -> None:
    schema.pop("default", None)
    branches = [b for b in schema.pop("anyOf", []) if b != {"type": "null"}]
    if len(branches) == 1:
        schema.update(branches[0])
    elif branches:
        schema["anyOf"] = branches


def _optional(description: str | None = None, *, default: Any = None, null: bool = False) -> Any:
    """A field outside `required`, shown without its default, so the client may leave it out.

    With `null` it may also be null. Without, the schema has no null branch, so a response
    holding such a field is dumped with exclude_none (Problem, Health).
    """
    return Field(
        default=default,
        description=description,
        json_schema_extra=_no_default if null else _no_default_no_null,
    )


def _no_nul(text: str) -> str:
    if "\x00" in text:
        raise PydanticCustomError("nul_character", "Text must not contain a NUL character")
    return text


# every string a request carries into Postgres: text and jsonb refuse a NUL character, so
# it is a 422 here rather than a 500 there
Text = Annotated[str, AfterValidator(_no_nul)]
Prompt = Annotated[str, Field(min_length=1), AfterValidator(_no_nul)]


# ----------------------------------------------------------------------------- errors


class ErrorItem(BaseModel):
    """FastAPI's error shape; a word collision is type word_collision with ctx
    {word, collides_with}.
    """

    loc: list[str | int]
    msg: str
    type: str
    ctx: dict[str, Any] | None = _optional()


class Problem(BaseModel):
    """Every error, the backend's own and FastAPI's validation errors alike."""

    detail: str
    code: str | None = _optional(
        "For 409s, one of not_latest, not_answerable, not_active, stale_run, "
        "version_conflict; "
        "too_many_active for 429s."
    )
    errors: list[ErrorItem] | None = _optional()


# ------------------------------------------------------------------ the caller, the service


class Health(BaseModel):
    ok: bool
    version: str | None = _optional()


class User(BaseModel):
    id: str
    name: str
    email: str | None = _optional(null=True)


class Workspace(BaseModel):
    id: str
    name: str
    pack: str = Field(description="The core pack (dataset) behind the workspace.")


class Me(BaseModel):
    user: User
    workspaces: list[Workspace]


# -------------------------------------------------------------------------------- runs

type RunStatus = Annotated[
    Literal[
        "queued", "running", "asking", "complete", "clarify", "failed", "cancelled", "superseded",
    ],
    Field(description="superseded ends a run that a newer revision replaced; it is terminal."),
]
type AskPolicy = Literal["never", "unsure", "always"]
type DecidedBy = Literal["rules", "s1", "s2", "user"]
type Rating = Literal["up", "down"]
type Cell = str | int | float | bool | None


class StageTiming(BaseModel):
    phase: str
    stage: str
    started_at: datetime
    elapsed_ms: float | None = Field(description="Null while the stage runs.")


class Option(BaseModel):
    id: str
    label: str
    hint: str = Field(description="Empty when there is none.")


class DecisionPoint(BaseModel):
    id: str
    step: str = Field(
        description="meaning, terms, form, point or detail; meaning and terms block a run."
    )
    question: str
    options: list[Option]
    chosen: str | None
    default: str | None = Field(description="What the rules alone choose.")
    by: DecidedBy
    confidence: float | None = Field(
        description="The System 1 model's confidence, when it answered."
    )
    why: str = Field(description="Why it is open, or what settled it; empty when nothing to say.")
    open: bool = Field(description="Nobody was sure; these are the points the user is asked.")
    stage: str = Field(description="The pipeline stage that applies the answer.")


class Card(BaseModel):
    blocking: bool = Field(
        description="True when the run waits for an answer; otherwise the card sits beside "
        "the chart."
    )
    points: list[DecisionPoint]


class Gap(BaseModel):
    slot: str
    requested: str
    reason: str
    suggestions: list[str]


class Clarify(BaseModel):
    """Why a run ended in clarify, from the core's ClarificationReport. gaps are terms that
    matched nothing in the data. missing, record and nearest are the data-gap ending: the KPI
    is not possible yet, here is what the warehouse lacks, what would have to be recorded, and
    the nearest questions it can answer instead. sightline never answers with a silent proxy.
    """

    gaps: list[Gap]
    missing: list[str]
    record: list[str]
    nearest: list[str] = Field(description="Answerable questions, offered as revisions.")
    warnings: list[str]


class Column(BaseModel):
    name: str
    type: str | None = Field(description="The attribute type, e.g. nominal or q_ratio.")


class ChartOption(BaseModel):
    chart: str
    label: str = Field(description="The form's name, or the humanised chart class.")
    hint: str | None = Field(
        description="What it lets you read (the core's candidates[].reads)."
    )
    score: float = Field(description="The idiom stage's score for it (candidates[].score).")


class ChartView(BaseModel):
    chart: str = Field(description="The chart class, e.g. horizontal_bar.")
    label: str = Field(description="The form's name, or the humanised chart class.")
    spec: dict[str, Any] = Field(
        description="Vega-Lite v5, already carrying the Pattern Perspectives theme config."
    )
    png_url: str | None = Field(description="Set only when perception rendered a PNG.")
    alternatives: list[ChartOption] = Field(
        description="The other admissible charts, for the switcher."
    )


class Result(BaseModel):
    sql: str | None
    columns: list[Column]
    rows: list[list[Cell]] = Field(description="At most the first 200 rows.")
    row_count: int
    truncated: bool = Field(
        description="The core truncated, or row_count exceeds the rows sent."
    )
    chart: ChartView | None
    findings: list[str] = Field(
        description="The analysis' findings in words (the core's plan.findings[].text)."
    )


class RunError(BaseModel):
    message: str
    stage: str | None


type RegistryKind = Annotated[
    Literal["measure", "default", "gap"],
    Field(
        description='measure, a proposed measure; default, a learned default (e.g. "best plant" '
        "means OEE); gap, data the warehouse lacks."
    ),
]
type RegistryStatus = Literal["proposed", "approved", "rejected"]


class EntrySource(BaseModel):
    kind: Literal["library", "drafted", "learned"]
    text: str = Field(
        description="In words, e.g. \"from sightline's KPI library (ISO 22400-2)\" or "
        '"drafted by sightline".'
    )


class Definition(BaseModel):
    """A definition the run used: a registry entry, approved or proposed, or one this run
    proposed. A proposed one answers at once, marked with its source, and a key user reviews
    it later.
    """

    name: str = Field(description="The term it defines, as RegistryEntry.term names it.")
    label: str
    source: EntrySource
    status: Literal["proposed", "approved"] = Field(
        description="A rejected entry never answers, so it is never listed here."
    )


class RunView(BaseModel):
    id: str
    thread_id: str
    revision: int = Field(description="0 for the question, n for the nth revision.")
    prompt: str = Field(description="What the user typed for this run.")
    status: RunStatus
    phase: str | None
    stage: str | None
    started_at: datetime | None
    finished_at: datetime | None
    restatement: str | None
    definitions: list[Definition] = Field(
        description="The proposed and registry definitions the run used, with their source."
    )
    card: Card | None
    clarify: Clarify | None
    result: Result | None
    timings: list[StageTiming] = Field(
        description="One entry per stage.started, in event id order, side states included; a "
        "stage that runs again (a reconsider loop) has an entry each time."
    )
    error: RunError | None
    feedback: Rating | None
    last_event_id: int = Field(
        description="The id of the last event folded into this view; open the stream after it."
    )


class RunSummary(BaseModel):
    """One run of a thread in brief; getRun has it in full."""

    id: str
    revision: int = Field(description="0 for the question, n for the nth revision.")
    prompt: str = Field(description="What the user typed for this run.")
    status: RunStatus
    restatement: str | None
    started_at: datetime | None
    finished_at: datetime | None
    feedback: Rating | None


# ----------------------------------------------------------------------------- threads


class ThreadSummary(BaseModel):
    id: str
    question: str
    restatement: str | None
    status: RunStatus
    active_run_id: str | None = Field(
        description="The run still queued, running or asking, if any."
    )
    revisions: int = Field(description="How many revisions follow the question.")
    updated_at: datetime


class ThreadPage(BaseModel):
    items: list[ThreadSummary]
    next_cursor: str | None


class Thread(BaseModel):
    id: str
    question: str
    created_at: datetime
    updated_at: datetime
    latest: RunView = Field(description="The latest run in full; getRun fetches an older one.")
    runs: list[RunSummary] = Field(
        description="One run per revision, oldest first (the question is revision 0), the "
        "latest included."
    )


# ---------------------------------------------------------------------------- requests


class CreateThread(BaseModel):
    question: Prompt
    ask: AskPolicy = _optional(
        "When the run asks the user; unsure when left out.", default="unsure"
    )


class RunCreated(BaseModel):
    thread_id: str
    run_id: str


class Revise(BaseModel):
    message: Prompt


class Answers(BaseModel):
    answers: dict[Text, Text | None] = Field(
        description="An option id per point id; null means decide for me."
    )
    text: Text | None = _optional(
        "Free text, which becomes a revision of the thread.", null=True
    )


class ChartPick(BaseModel):
    chart: Text


class Feedback(BaseModel):
    rating: Rating | None = Field(description="null clears the rating.")


# ---------------------------------------------------------------------------- registry


class Demand(BaseModel):
    runs: int
    first_asked: datetime | None
    last_asked: datetime | None


class EntryGap(BaseModel):
    """For kind gap, in the same words as Clarify.missing and Clarify.record."""

    missing: list[str]
    record: list[str]


class EntryChoice(BaseModel):
    """For kind default, what users picked on the card for this criterion."""

    option: str
    label: str
    count: int


class RegistryEntry(BaseModel):
    id: str
    kind: RegistryKind
    term: str
    label: str
    source: EntrySource
    status: RegistryStatus
    demand: Demand
    words: dict[str, list[str]] = Field(
        description="The words that name the term, per locale, e.g. {en:[...], de:[...]}."
    )
    definition: str | None = Field(
        description="The formula or meaning in words; for a default, the label of the chosen "
        "measure."
    )
    note: str | None
    version: int
    updated_at: datetime
    reviewed_by: str | None
    gap: EntryGap | None = _optional(null=True)
    choices: list[EntryChoice] | None = _optional(null=True)


class EntryRun(BaseModel):
    run_id: str
    thread_id: str
    question: str
    rating: Rating | None
    at: datetime


class RegistryEntryDetail(RegistryEntry):
    runs: list[EntryRun]


class RegistryCounts(BaseModel):
    """Proposed entries per kind, regardless of the page's filters (drives the badge)."""

    measure: int
    default: int
    gap: int


class RegistryPage(BaseModel):
    items: list[RegistryEntry]
    next_cursor: str | None
    counts: RegistryCounts


type ReviewAction = Literal["approve", "reject", "reopen", "edit"]


class ReviewChanges(BaseModel):
    label: Text | None = _optional()
    words: dict[Text, list[Text]] | None = _optional()


class Review(BaseModel):
    action: ReviewAction
    version: int = Field(description="The version the key user saw.")
    note: Text | None = _optional()
    changes: ReviewChanges | None = _optional()


# ----------------------------------------------------------------------------- signals

type SignalKind = Literal["thread_opened"]


class Signal(BaseModel):
    """A client beacon, stored as a raw event; nothing interprets it in v1."""

    kind: SignalKind
    thread_id: Text


# ------------------------------------------------------------------------------ events
# One SSE frame per event: `id:` the run's event counter, `event:` the type, `data:` the
# event as JSON. Every variant carries type and run_id.


class RunStatusEvent(BaseModel):
    type: Literal["run.status"]
    run_id: str
    status: RunStatus


class StageStartedEvent(BaseModel):
    type: Literal["stage.started"]
    run_id: str
    phase: str
    stage: str
    at: datetime


class StageFinishedEvent(BaseModel):
    type: Literal["stage.finished"]
    run_id: str
    phase: str
    stage: str
    at: datetime
    elapsed_ms: float


class RestatementEvent(BaseModel):
    type: Literal["restatement"]
    run_id: str
    text: str


class CardEvent(BaseModel):
    type: Literal["card"]
    run_id: str
    card: Card


class ClarifyEvent(BaseModel):
    type: Literal["clarify"]
    run_id: str
    clarify: Clarify


class ChartEvent(BaseModel):
    type: Literal["chart"]
    run_id: str
    chart: ChartView


class ResultEvent(BaseModel):
    type: Literal["result"]
    run_id: str
    result: Result


class ErrorEvent(BaseModel):
    type: Literal["error"]
    run_id: str
    message: str
    stage: str | None


class RunEvent(
    RootModel[
        Annotated[
            RunStatusEvent
            | StageStartedEvent
            | StageFinishedEvent
            | RestatementEvent
            | CardEvent
            | ClarifyEvent
            | ChartEvent
            | ResultEvent
            | ErrorEvent,
            Field(discriminator="type"),
        ]
    ]
):
    pass
