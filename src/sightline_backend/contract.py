"""The API contract as pydantic models: the shapes the web client's types are generated from.

They started from sightline-web's contract/openapi.draft.yaml with its schema names, and
carry the changes agreed with the frontend session since (contract v0.2: follow-ups in the
same thread, steps, the storyline and its supports, typed errors; v0.2.1: the answers to the
frontend's check of v0.2) and the plan's additions (the plan's "API contract" section).
They are not the core's artifacts. Those feed System 2's prompts and never change to suit
the API, so the backend projects them into these shapes: the card from AskReport and
DecisionPoint, clarify from ClarificationReport, the chart options from ChartCandidate, the
result from ExecutionArtifact and VisPlan.findings, the steps from the analysis and the
storyline, supports and follow-ups from gather.

Descriptions say what the core guarantees today. The analysis (steps 5 and 6) runs only
under SIGHTLINE_ANALYSIS=route; until then storyline is null, and supports, steps and the
follow-ups of an answered run are empty.

contract/openapi.json is generated from these models and the routes
(scripts/export_openapi.py). A change here is a change to the contract, and it goes
through the frontend session first.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, Field, RootModel, ValidationInfo, field_validator
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
    holding such a field is dumped with exclude_none (Problem, Health, StageFinishedEvent).
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
    """FastAPI's error shape, technical: for the client to act on, not to show users. The
    backend's own types: word_collision (ctx {word, collides_with}); follow_up_mismatch (a
    revision's message is not the question of the follow-up it sends); via_with_follows (loc
    [body, via]: a revision sent via together with follows); stale_run (loc [path, run_id],
    ctx {prompt}: the run's prompt, to ask again with).
    """

    loc: list[str | int]
    msg: str
    type: str
    ctx: dict[str, Any] | None = _optional()


type ProblemCode = Annotated[
    Literal[
        "not_latest", "not_answerable", "stale_run", "version_conflict", "not_allowed",
        "too_many_active", "not_implemented", "no_workspace", "no_thread", "no_run", "no_entry",
        "no_step", "no_revision",
    ],
    Field(
        description="409: not_latest, not_answerable, stale_run, version_conflict, "
        "not_allowed. 429: too_many_active. 501: not_implemented, while a route is a stub. "
        "404: no_workspace, no_thread, no_run, no_entry, no_step, no_revision; each "
        "operation's 404 lists the ones it can answer. stale_run: the run was made by an "
        "earlier version of sightline and can't be changed any more; ask again for a fresh "
        "answer (errors[0].ctx carries {prompt})."
    ),
]


class Problem(BaseModel):
    """Every error, the backend's own and FastAPI's validation errors alike."""

    detail: str = Field(
        description="One sentence fit to show users (English for now); errors holds the "
        "technical part."
    )
    code: ProblemCode | None = _optional(
        "Names the error. Absent on a 422 (a validation error): its types are in errors, "
        "which says where."
    )
    errors: list[ErrorItem] | None = _optional(
        "Technical: what went wrong and where, for the client, not for users."
    )


# ------------------------------------------------------------------ the caller, the service


class Health(BaseModel):
    ok: bool
    version: str | None = _optional()


class User(BaseModel):
    id: str
    name: str
    email: str | None = Field(description="Null when the user has none.")


type WorkspaceRole = Annotated[
    Literal["key_user", "member"],
    Field(
        description="key_user reviews the registry; always key_user in v1, which has no auth."
    ),
]


class Workspace(BaseModel):
    id: str
    name: str
    pack: str = Field(description="The core pack (dataset) behind the workspace.")
    role: WorkspaceRole = Field(description="The caller's role in this workspace.")
    starters: list[str] = Field(
        description="Example questions for the empty page; empty when the pack has none."
    )


class Me(BaseModel):
    user: User
    workspaces: list[Workspace]
    last_workspace: str | None = Field(
        description="The id of the workspace the caller used last; null before the first."
    )


# ----------------------------------------------------------------- the warehouse's schema

type ColumnRole = Literal["dimension", "measure", "time"]


class SchemaColumn(BaseModel):
    name: str
    label: str = Field(description="The name to show.")
    type: str | None = Field(description="The attribute type, e.g. nominal or q_ratio.")
    role: ColumnRole | None
    unit: str | None = Field(description="e.g. EUR, %, kWh; null when it has none.")
    description: str | None


class SchemaTable(BaseModel):
    name: str
    label: str = Field(description="The name to show.")
    description: str | None
    columns: list[SchemaColumn]


class SchemaMeasure(BaseModel):
    name: str
    label: str = Field(description="The name to show.")
    description: str | None = Field(description="The formula or meaning in words.")
    unit: str | None = Field(description="e.g. EUR, %, kWh; null when it has none.")


class SchemaInfo(BaseModel):
    """The workspace's warehouse as users read it: its tables with their columns, and the
    measures its contract defines."""

    tables: list[SchemaTable]
    measures: list[SchemaMeasure]


# -------------------------------------------------------------------------------- runs

type RunStatus = Annotated[
    Literal[
        "queued", "running", "asking", "complete", "clarify", "failed", "cancelled", "superseded",
    ],
    Field(
        description="superseded ends a run that a newer revision replaced; it is terminal. "
        "There is no paused: the service never pauses a run, and a core run that reports "
        "paused is shown as failed with error code internal."
    ),
]
type AskPolicy = Literal["never", "unsure", "always"]
type DecidedBy = Annotated[
    Literal["rules", "s1", "s2", "user", "default"],
    Field(
        description="Who settled the point. default: a default the key user approved; chosen "
        "is its approved option, open is false, confidence is null, and the card does not "
        "block, so it sits beside the chart and the user can change it. Not the same as "
        "DecisionPoint.default, which is what the rules alone choose."
    ),
]
type Rating = Literal["up", "down"]
type Cell = str | int | float | bool | None
type Locale = Annotated[
    Literal["en", "de"],
    Field(description="The asker's language."),
]
type RunOrigin = Annotated[
    Literal["question", "revision", "take_back", "follow_up", "nearest"],
    Field(
        description="question: the thread's question (revision 0); revision: typed in the "
        "composer or as the card's free text; take_back: a take-back (takes_back names the "
        "revision it removed); follow_up: a follow-up sent from the transcript (follows names "
        "it); nearest: one of a clarify run's nearest questions."
    ),
]


STAGE_NAMES = (
    "A stage name only; the words for it belong to the client, and a name the client does "
    "not know gets a generic label. Within one pass the phases are contiguous and the stages "
    "run in this order: situate, recall, define, ground, abstract, plan, bind (phase "
    "understand); enrich, derive, query, analyse, gather (phase analyse); idiom, render, "
    "perceive, validate (phase present). Only reconsider, repair and the hole loop (gather back to "
    "analyse) go back. Side states: clarify, reconsider and repair (understand), restore "
    "(present), ask and propose (the phase of the stage they follow). Propose runs before an "
    "ask waits, so the card is not delayed; it is fast and makes no model call. Plan, analyse "
    "and gather run only under SIGHTLINE_ANALYSIS=route."
)

STEP_LABEL = (
    "A noun phrase of at most 40 characters with no trailing punctuation, in the run's locale "
    'when known, e.g. "the prior period".'
)


class StageTiming(BaseModel):
    phase: str
    stage: str = Field(description=STAGE_NAMES)
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
    chosen: str | None = Field(
        description="The option in force: the user's answer, an approved default, System 1's "
        "lean, else the rules' default."
    )
    default: str | None = Field(
        description="What the rules alone choose; not the same as by = default."
    )
    by: DecidedBy
    confidence: float | None = Field(
        description="The System 1 model's confidence, when it answered; null for by = default."
    )
    why: str = Field(
        description="Why it is open, or what settled it; empty when nothing to say. For by = "
        "default it says what the default says (\"'best plant' means the highest OEE\"), not "
        "where it came from; the client tags it as the key user's default."
    )
    open: bool = Field(
        description="Nobody was sure. Under ask=always a point can be asked with open = false."
    )
    stage: str = Field(description="The pipeline stage that applies the answer.")
    entry_id: str | None = Field(
        description="The registry entry whose approved default settled it (by = default); "
        "null otherwise."
    )


class Card(BaseModel):
    """The points a run asks, from the core's decisions (to_ask and beside).

    A card asks the first step that has points to ask: the points nobody was sure of (open)
    and, under ask=always, also the judgement points no rule settled. A card that does not
    block, after the drawing, applies the same rule to the form, point and detail steps, and
    adds the points an approved default settled (by = default). Every point in points is
    asked; open keeps its meaning (nobody was sure), so under ask=always a point can be
    asked with open = false. A null answer ("decide for me") keeps the chosen option (an
    approved default, else System 1's lean, else the rules' default), and by stays default,
    s1 or rules.
    """

    blocking: bool = Field(
        description="True when the run waits for an answer; otherwise the card sits beside "
        "the chart."
    )
    points: list[DecisionPoint]


class GapSuggestion(BaseModel):
    id: str
    label: str = Field(description="What it suggests, in a few words.")
    question: str = Field(
        description="A full revised question that stands on its own, worded like the nearest "
        "questions."
    )


class Gap(BaseModel):
    slot: str
    requested: str
    reason: str = Field(description="Why nothing matched, written for users.")
    suggestions: list[GapSuggestion]


class Clarify(BaseModel):
    """Why a run ended in clarify, from the core's ClarificationReport. gaps are terms that
    matched nothing in the data. missing and record are the data-gap ending: the KPI is not
    possible yet, here is what the warehouse lacks and what would have to be recorded. The
    nearest questions the warehouse can answer instead are the run's follow_ups (kind
    nearest). sightline never answers with a silent proxy.
    """

    gaps: list[Gap]
    missing: list[str]
    record: list[str]
    warnings: list[str] = Field(description="Deduplicated, at most five.")
    warnings_total: int = Field(
        description="How many distinct warnings there were, before the cap."
    )


class Column(BaseModel):
    name: str = Field(description="The column's name in the rows, as the SQL has it.")
    label: str = Field(description="The name to show.")
    type: str | None = Field(description="The attribute type, e.g. nominal or q_ratio.")
    role: ColumnRole | None
    unit: str | None = Field(description="e.g. EUR, %, kWh; null when it has none.")
    format: str | None = Field(
        description='A d3-format specifier for its values, e.g. ",.0f" or ".1%".'
    )
    description: str | None


class ChartOption(BaseModel):
    chart: str
    label: str = Field(description="The form's name, or the humanised chart class.")
    hint: str | None = Field(
        description="What it lets you read (the core's candidates[].reads)."
    )
    score: float = Field(
        description="The idiom stage's ranking score (candidates[].score), comparable only "
        "within one run."
    )
    drawn: bool = Field(description="True for the chart drawn now.")


CHART_SPEC = (
    "Vega-Lite v5, already carrying the Pattern Perspectives theme config. spec.description "
    "is plain language for screen readers; rule ids live in spec.usermeta. The main chart is "
    'one view whose comparisons are layers (width "container" keeps working), each with the '
    "Vega-Lite name that Support.layer gives; a chart switch keeps those layers. Its "
    "title.text equals storyline.top verbatim (after render's rewording) when there is a "
    "storyline, and on every run its subtitle holds only bases (filters, window, "
    "aggregation): exclusions, partial periods and every other caveat live in Result.notes. "
    "A small chart is a single view (no concat, facet or repeat) with no top-level width, an "
    "explicit small height, and no title or subtitle: Support.text is its caption. Key-line "
    "points and notes never go into a spec."
)


class ChartView(BaseModel):
    """A drawn chart: the run's main chart (Result.chart) or a support's small chart
    (Support.chart)."""

    chart: str = Field(description="The chart class, e.g. horizontal_bar.")
    label: str = Field(description="The form's name, or the humanised chart class.")
    title: str | None = Field(
        description="The drawn chart's title text, as in the spec; null on a small chart."
    )
    subtitle: list[str] = Field(
        description="The drawn chart's subtitle lines, as in the spec: bases only (filters, "
        "window, aggregation) on every run, never a caveat. Empty on a small chart."
    )
    hint: str | None = Field(description="What the drawn chart lets you read.")
    score: float | None = Field(
        description="The idiom stage's ranking score for the drawn chart, comparable only "
        "within one run; null on a small chart."
    )
    spec: dict[str, Any] = Field(description=CHART_SPEC)
    png_url: str | None = Field(description="Set only when perception rendered a PNG.")
    min_width: float | None = Field(
        description="On a small chart, the width in pixels below which it needs a row of its "
        "own; null on the main chart."
    )
    options: list[ChartOption] = Field(
        description="Every admissible chart, the drawn one included, for the switcher: by "
        "score descending, then chart id. A switch does not reorder it. Empty on a small "
        "chart."
    )


class ChartRef(BaseModel):
    chart: str = Field(description="The chart class, e.g. horizontal_bar.")
    label: str = Field(description="The form's name, or the humanised chart class.")


type SupportRole = Literal[
    "answer", "comparison", "reference", "routine_band", "whole", "rest", "denominator",
    "decomposition", "exclusion", "exception", "context",
]
type SupportDrawn = Annotated[
    Literal["main", "small", "dropped", "none"],
    Field(
        description="main: on the main chart, as the layer Support.layer names; small: its "
        "own small chart, in Support.chart; dropped: its chart was left out, Support.note "
        "says why; none: it has no chart."
    ),
]
type FollowUpKind = Annotated[
    Literal["breakdown", "next_level", "check", "nearest"],
    Field(
        description="breakdown: the step a stop left (e.g. a routine change broken down); "
        "next_level: one level down from the lead; check: a breaking check the budget left "
        "unrun; nearest: the nearest other question, when every explanation was ruled out (on "
        "an answered run, sent with follows like any follow-up) or when a run ended in clarify "
        "(sent with via nearest and no follows)."
    ),
]


class KeyPoint(BaseModel):
    id: str
    text: str = Field(description="One supporting statement; it goes into no spec.")


class Storyline(BaseModel):
    """The answer's argument, from the analysis (gather): the governing thought on top and its
    supporting statements. What tempers it lives in Result.notes."""

    top: str = Field(
        description="The governing thought, stated as the effect. The main chart's title.text "
        "equals it verbatim (after render's rewording)."
    )
    key_line: list[KeyPoint] = Field(
        description="At most five supporting statements, in order. A breaking check that "
        "changed or limited the claim is a note (Result.notes), never a key-line point."
    )


class Support(BaseModel):
    id: str
    role: SupportRole
    point: str | None = Field(
        description="The id of the KeyPoint it illustrates; null when it illustrates none."
    )
    text: str = Field(
        description="What this support says, in words; for a small chart, its caption."
    )
    drawn: SupportDrawn
    chart: ChartView | None = Field(
        description="Its small chart, set only when drawn = small (no title or subtitle, no "
        "options, no PNG)."
    )
    layer: str | None = Field(
        description="The Vega-Lite name of its layer on the main chart, set only when drawn = "
        "main."
    )
    note: str | None = Field(description="Why it was dropped, set only when drawn = dropped.")


class FollowUp(BaseModel):
    id: str = Field(
        description="Unique within its run. It survives a chart pick, and may vanish after a "
        "side-card answer."
    )
    question: str = Field(
        description="A full question that stands on its own; the client sends it unchanged "
        "as the revision's message."
    )
    kind: FollowUpKind


class FollowRef(BaseModel):
    """The follow-up a run answers."""

    run_id: str = Field(description="The run that offered it.")
    follow_up_id: str
    kind: FollowUpKind


type ResultVerdict = Annotated[
    Literal["pass", "warn", "fail"],
    Field(description="validate's verdict on the answer."),
]


class Result(BaseModel):
    """The answer. One home per text: the storyline's top is the main chart's title, the key
    line lives only in the storyline, every caveat only in notes, findings only without a
    storyline, and a small chart's caption only in Support.text.
    """

    sql: str | None = Field(description="The SQL of the step step_id names.")
    step_id: str | None = Field(
        description="The step whose SQL and rows sql and rows are: the lead's step, or the "
        "primary when there is no analysis. getRunStep serves any step's rows."
    )
    columns: list[Column]
    rows: list[list[Cell]] = Field(description="At most the first 200 rows.")
    row_count: int
    truncated: bool = Field(
        description="The core truncated, or row_count exceeds the rows sent."
    )
    chart: ChartView | None = Field(
        description="The main chart, the lead's when there is a storyline. A run that failed "
        "after gather may have a storyline while chart is null."
    )
    findings: list[str] = Field(
        description="The analysis' findings in words (the core's plan.findings[].text); empty "
        "when storyline is set."
    )
    notes: list[str] = Field(
        description="Every caveat of the answer, on every run, and their only home (never in a "
        "spec's subtitle, the key line or the restatement): the rows left out and the periods "
        "left out as incomplete; with the analysis also the breaking checks that changed or "
        "limited the claim, the pruned branches, the data edges and what was not checked."
    )
    verdict: ResultVerdict
    concerns: list[str] = Field(
        description="validate's warnings and failures in words; empty on pass."
    )
    storyline: Storyline | None = Field(
        description="null until the analysis runs (SIGHTLINE_ANALYSIS=route), and for a run "
        "that ended before gather."
    )
    lead: str | None = Field(
        description="The id of the support that Result.chart draws (drawn = main). It is set "
        "whenever storyline is set, also when chart is null because the run failed after "
        "gather; null without a storyline."
    )
    supports: list[Support] = Field(
        description="At most five: those with a point in key_line order, then those whose "
        "point is null, in gather's order. Empty until the analysis runs."
    )


type RunErrorCode = Annotated[
    Literal["timeout", "warehouse_unavailable", "model_unavailable", "budget_exhausted",
            "internal"],
    Field(description="internal also stands for a core run that reported paused."),
]


class RunError(BaseModel):
    code: RunErrorCode
    message: str = Field(description="One sentence fit to show users.")
    detail: str | None = Field(description="Technical, not for users; null when there is none.")
    stage: str | None = Field(description="The stage it failed in, when known.")
    retryable: bool = Field(description="Asking again may succeed.")


type StepVerdict = Annotated[
    Literal["as_expected", "contradicts", "routine", "inconclusive", "no_effect", "failed"],
    Field(
        description="routine: inside its routine band (the analysis stops); no_effect: no "
        "difference found after the breakdown; failed: the step's query failed, its issue "
        "stays unchecked."
    ),
]
type StepRole = Annotated[
    Literal[
        "answer", "probe", "reference", "denominator", "comparison", "decomposition", "check",
        "lookup",
    ],
    Field(
        description="Probes and silent checks are told as steps too (probe, check); the client "
        "folds them, so a check that survived stays silent."
    ),
]


class AnalysisStep(BaseModel):
    """A step of the analysis; steps are told only under SIGHTLINE_ANALYSIS=route."""

    id: str = Field(description="Unique per execution: a step run again gets a new id.")
    label: str = Field(description=STEP_LABEL)


class StepRecord(BaseModel):
    """A step of the analysis, as it ran or runs."""

    id: str = Field(description="Unique per execution: a step run again gets a new id.")
    stage: str = Field(description="The stage it ran in.")
    label: str = Field(description=STEP_LABEL)
    role: StepRole
    started_at: datetime
    elapsed_ms: float | None = Field(description="Null while the step runs.")
    verdict: StepVerdict | None = Field(
        description="Null while the step runs or when it reached no verdict."
    )
    cached: bool = Field(
        description="Its rows came from the cache; no query ran. False while the step runs."
    )
    sql: str | None = Field(description="Null while the step runs or when the step ran no SQL.")
    row_count: int | None = Field(
        description="Null while the step runs or when it has no query; 0 when its query "
        "returned no rows."
    )


class StepResult(BaseModel):
    """One step's SQL and rows."""

    step_id: str
    label: str = Field(description=STEP_LABEL)
    sql: str | None = Field(description="Null when the step ran no SQL.")
    columns: list[Column]
    rows: list[list[Cell]] = Field(description="At most the first 200 rows.")
    row_count: int
    truncated: bool = Field(
        description="The core truncated, or row_count exceeds the rows sent."
    )


type RegistryKind = Annotated[
    Literal["measure", "default", "gap"],
    Field(
        description='measure, a proposed measure; default, a learned default (e.g. "best plant" '
        "means OEE); gap, data the warehouse lacks. Later kinds come in a later contract; a "
        "client renders a kind it does not know with the generic fields."
    ),
]
type RegistryStatus = Literal["proposed", "approved", "rejected"]


class EntrySource(BaseModel):
    kind: Literal["library", "drafted", "learned", "question"]
    text: str = Field(
        description="In words, e.g. \"from sightline's KPI library (ISO 22400-2)\", "
        '"drafted by sightline", or "as the question states it" (a definition the question '
        "itself gives). Neutral for every kind of entry; the transcript words it per kind."
    )


class Definition(BaseModel):
    """A definition the run used: a registry entry, approved or proposed, or one this run
    proposed. A proposed one answers at once, marked with its source, and a key user reviews
    it later. The restatement never carries a "Defined as ..." clause; a definition's wording
    and its approval live only in definitions[].
    """

    name: str = Field(description="The term it defines, as RegistryEntry.term names it.")
    label: str
    definition: str | None = Field(description="The formula or meaning in words.")
    entry_id: str | None = Field(description="The registry entry, when it is one.")
    source: EntrySource
    status: Literal["proposed", "approved"] = Field(
        description="A rejected entry never answers, so it is never listed here."
    )


RESTATEMENT = (
    "What sightline understood, and only that. Every run that got past bind has one, "
    "clarify and asking runs included; the core tells it right after bind. Null before bind. "
    "The restatement never carries a \"Defined as ...\" clause; a definition's wording and "
    "its approval live only in definitions[]."
)
RESTATEMENT_TOLD = (
    "What sightline understood, and only that; told right after bind, and again when the "
    "text changes."
)
REVISION = "0 for the question, n for the nth run after it (follow-ups and take-backs included)."
UPDATED_AT = "Moves when a run is created or changes status; feedback and signals do not move it."


class RunView(BaseModel):
    """A run in full. A run cancelled, failed or superseded before gather has storyline null
    and supports and follow_ups empty, and keeps its steps (see steps). A run that fails after
    gather may have a storyline while its chart is null.
    """

    id: str
    thread_id: str
    revision: int = Field(description=REVISION)
    prompt: str = Field(
        description="What the user sent for this run: typed text, a follow-up or nearest "
        "question, or for a take-back the text taken back."
    )
    origin: RunOrigin
    takes_back: int | None = Field(
        description="For a take-back, the revision number it removed; null otherwise."
    )
    follows: FollowRef | None = Field(
        description="The follow-up this run answers; null for the question, typed revisions, "
        "take-backs and a clarify run's nearest questions (sent with via nearest)."
    )
    status: RunStatus
    locale: Locale | None = Field(
        description="Null until the core detects the asker's language (understanding's step "
        "for German, not built yet)."
    )
    phase: str | None
    stage: str | None
    started_at: datetime | None
    finished_at: datetime | None
    restatement: str | None = Field(description=RESTATEMENT)
    definitions: list[Definition] = Field(
        description="The proposed and registry definitions the run used, with their source."
    )
    card: Card | None
    clarify: Clarify | None
    result: Result | None
    follow_ups: list[FollowUp] = Field(
        description="At most three, in rule order. On an answered run, questions to send with "
        "follows (empty until the analysis runs); on a clarify run, clarify's nearest "
        "questions (kind nearest), sent with via nearest and no follows."
    )
    step: AnalysisStep | None = Field(
        description="The step under way; null when none is, always until the analysis runs, "
        "and whenever the run's status is terminal or asking."
    )
    steps: list[StepRecord] = Field(
        description="The steps in the order they started, the one under way included; empty "
        "until the analysis runs. A step under way when the run ends (cancelled, failed or "
        "superseded) stays here with elapsed_ms set to the time until the end, verdict, sql "
        "and row_count null, and cached false. The stream tells no step.finished for it, so "
        "only getRun has that elapsed_ms."
    )
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
    revision: int = Field(description=REVISION)
    prompt: str = Field(description="What the user sent for this run.")
    origin: RunOrigin
    takes_back: int | None = Field(
        description="For a take-back, the revision number it removed; null otherwise."
    )
    follows: FollowRef | None = Field(
        description="The follow-up this run answers; null for the question, typed revisions, "
        "take-backs and a clarify run's nearest questions (sent with via nearest)."
    )
    status: RunStatus
    restatement: str | None
    top: str | None = Field(description="The storyline's top; null without a storyline.")
    chart: ChartRef | None = Field(description="The main chart; null when none was drawn.")
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
    revisions: int = Field(
        description="Runs after the question, follow-ups and take-backs included."
    )
    updated_at: datetime = Field(description=UPDATED_AT)


class ThreadPage(BaseModel):
    items: list[ThreadSummary]
    next_cursor: str | None


class Thread(BaseModel):
    id: str
    question: str
    locale: Locale | None = Field(
        description="Null until the core detects the asker's language (understanding's step "
        "for German, not built yet)."
    )
    created_at: datetime
    updated_at: datetime = Field(description=UPDATED_AT)
    latest: RunView = Field(description="The latest run in full; getRun fetches an older one.")
    runs: list[RunSummary] = Field(
        description="Every run, oldest first (the question is revision 0), the latest "
        "included."
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


class FollowRequest(BaseModel):
    run_id: Text = Field(description="The thread's latest run, which offered the follow-up.")
    follow_up_id: Text


class Revise(BaseModel):
    # follows comes before via, so that via's check sees it
    message: Prompt = Field(
        description="The revision's text; with follows, the follow-up's question verbatim."
    )
    follows: FollowRequest | None = _optional(
        "The follow-up this revision sends: one of the follow_ups of the thread's latest run, "
        "when that run is complete."
    )
    via: Literal["composer", "nearest"] = _optional(
        "Where a revision without follows came from (an implicit signal): typed in the "
        "composer, or one of a clarify run's nearest questions; composer when left out. Never "
        "sent with follows (422 via_with_follows). Free text sent with answerCard is a "
        "revision too, and the backend marks it card text itself.",
        default="composer",
    )

    @field_validator("via")
    @classmethod
    def _not_with_follows(cls, via: str, info: ValidationInfo) -> str:
        # runs only when via is sent: a default is not validated
        if info.data.get("follows") is not None:
            raise PydanticCustomError(
                "via_with_follows", "via must not be sent together with follows"
            )
        return via


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
    version: int = Field(
        description="Only a review (approve, reject, reopen, edit) moves it. Demand updates "
        "and repeated proposals do not, so a run asking for the entry never causes a "
        "version_conflict."
    )
    updated_at: datetime
    reviewed_by: str | None
    reviewed_at: datetime | None
    gap: EntryGap | None = Field(description="Set for kind gap; null for the other kinds.")
    choices: list[EntryChoice] | None = Field(
        description="Set for kind default; null for the other kinds."
    )
    chosen_option: str | None = Field(
        description="For kind default, the id of the option it chooses; null for the other kinds."
    )


class EntryRun(BaseModel):
    run_id: str
    thread_id: str
    revision: int = Field(description=REVISION)
    question: str = Field(description="The thread's question.")
    prompt: str = Field(description="What the user sent for this run.")
    rating: Rating | None
    at: datetime


type ReviewAction = Literal["approve", "reject", "reopen", "edit"]


class EntryChange(BaseModel):
    """One change of an entry. Only a review (approve, reject, reopen, edit) changes the
    entry's version; demand updates and repeated proposals do not, so a run asking for the
    entry never causes a version_conflict."""

    version: int = Field(
        description="The entry's version after the change: moved by a review, kept by "
        "sightline's own changes."
    )
    action: ReviewAction | Literal["proposed", "demand"] = Field(
        description="A key user's review, or sightline's own change: proposed (it proposed "
        "the entry) or demand (runs asked for it)."
    )
    by: str | None = Field(description="Who reviewed it; null for sightline's own changes.")
    at: datetime
    note: str | None


class RegistryEntryDetail(RegistryEntry):
    runs: list[EntryRun] = Field(description="The 20 newest runs that used it, newest first.")
    runs_total: int = Field(description="How many runs used it.")
    history: list[EntryChange] = Field(description="Its changes, oldest first.")


class RegistryCounts(RootModel[dict[str, int]]):
    """Proposed entries per kind, regardless of the page's filters (drives the badge): a map
    from RegistryKind to its count, every kind present."""


class KindInfo(BaseModel):
    kind: RegistryKind
    label: str = Field(description='The display word, e.g. "measure".')
    plural: str = Field(description='e.g. "measures".')


class RegistryPage(BaseModel):
    items: list[RegistryEntry]
    next_cursor: str | None
    counts: RegistryCounts
    kinds: list[KindInfo] = Field(description="The display words of every kind.")


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
    stage: str = Field(description=STAGE_NAMES)
    at: datetime


# the core records System 2's calls as llm; the backend reports them as s2
type CallKind = Annotated[
    Literal["s1", "s2", "vision"],
    Field(
        description="s1: the System 1 model; s2: System 2, titles included; vision: a vision "
        "model reading the chart's image."
    ),
]


class CallInfo(BaseModel):
    """A model call a stage made."""

    kind: CallKind
    model: str
    seconds: float
    cost_usd: float | None = Field(description="Null when the provider reports no cost.")
    from_cache: bool = Field(description="Answered by sightline's call cache: no call was made.")


class StageFinishedEvent(BaseModel):
    type: Literal["stage.finished"]
    run_id: str
    phase: str
    stage: str = Field(description=STAGE_NAMES)
    at: datetime
    elapsed_ms: float
    calls: list[CallInfo] | None = _optional(
        "The model calls the stage made, when the core reports them."
    )


class StepStartedEvent(BaseModel):
    """A step started. With its step.finished it carries every field of StepRecord, so a
    RunView folded from the stream equals getRun, except for a step cut off by the run's end
    (RunView.steps): no step.finished comes for it, so its elapsed_ms is only in getRun,
    which a client refetches after a terminal run.status."""

    type: Literal["step.started"]
    run_id: str
    stage: str = Field(description="The stage the step runs in.")
    step: AnalysisStep
    role: StepRole
    at: datetime


class StepFinishedEvent(BaseModel):
    """A step ended. With its step.started it carries every field of StepRecord, so a
    RunView folded from the stream equals getRun, except for a step cut off by the run's end
    (RunView.steps): no step.finished comes for it, so its elapsed_ms is only in getRun,
    which a client refetches after a terminal run.status."""

    type: Literal["step.finished"]
    run_id: str
    stage: str = Field(description="The stage the step ran in.")
    step: AnalysisStep
    role: StepRole
    cached: bool = Field(description="Its rows came from the cache; no query ran.")
    at: datetime
    elapsed_ms: float
    verdict: StepVerdict | None = Field(description="null when the step reached no verdict.")
    sql: str | None = Field(description="Null when the step ran no SQL.")
    row_count: int | None = Field(
        description="Null when the step has no query; 0 when its query returned no rows."
    )


class RestatementEvent(BaseModel):
    type: Literal["restatement"]
    run_id: str
    text: str = Field(description=RESTATEMENT_TOLD)


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
    support_id: str | None = Field(
        description="The support whose small chart this is; null for the main chart. Small "
        "charts come only with the analysis (SIGHTLINE_ANALYSIS=route)."
    )
    chart: ChartView


class ResultEvent(BaseModel):
    type: Literal["result"]
    run_id: str
    result: Result


class ErrorEvent(BaseModel):
    type: Literal["error"]
    run_id: str
    code: RunErrorCode
    message: str = Field(description="One sentence fit to show users.")
    detail: str | None = Field(description="Technical, not for users; null when there is none.")
    stage: str | None = Field(description="The stage it failed in, when known.")
    retryable: bool = Field(description="Asking again may succeed.")


class RunEvent(
    RootModel[
        Annotated[
            RunStatusEvent
            | StageStartedEvent
            | StageFinishedEvent
            | StepStartedEvent
            | StepFinishedEvent
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
