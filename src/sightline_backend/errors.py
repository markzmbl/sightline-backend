"""Every non-2xx answer is a Problem: {detail, code?, errors?}.

The handlers below normalize what FastAPI and Starlette raise (HTTPException, request
validation errors, anything unhandled) and the backend's own ProblemError into that shape,
so the client reads one error type everywhere.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine, Mapping
from typing import Any

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from sightline_backend.contract import ErrorItem, Problem


class ProblemError(Exception):
    """An error the API answers with a Problem body; `code` names it for the client."""

    def __init__(
        self,
        status: int,
        detail: str,
        code: str | None = None,
        errors: list[ErrorItem] | None = None,
    ) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail
        self.code = code
        self.errors = errors


def not_implemented() -> ProblemError:
    """What a route answers until its phase builds it."""
    return ProblemError(501, "not implemented yet", code="not_implemented")


def problem_response(
    status: int, problem: Problem, headers: Mapping[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(
        problem.model_dump(mode="json", exclude_none=True), status_code=status, headers=headers
    )


def _item(error: dict[str, Any]) -> ErrorItem:
    # pydantic's errors also carry the input (left out: it echoes the request) and a ctx
    # whose values can be exceptions, which are sent as text
    ctx = error.get("ctx")
    return ErrorItem(
        loc=list(error.get("loc", ())),
        msg=str(error.get("msg", "")),
        type=str(error.get("type", "")),
        ctx=None if ctx is None else {
            k: v if v is None or isinstance(v, str | int | float | bool) else str(v)
            for k, v in ctx.items()
        },
    )


async def _problem_error(request: Request, exc: ProblemError) -> Response:
    return problem_response(
        exc.status, Problem(detail=exc.detail, code=exc.code, errors=exc.errors)
    )


async def _http_error(request: Request, exc: StarletteHTTPException) -> Response:
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return problem_response(exc.status_code, Problem(detail=detail), headers=exc.headers)


async def _validation_error(request: Request, exc: RequestValidationError) -> Response:
    errors = [_item(e) for e in exc.errors()]
    return problem_response(422, Problem(detail="invalid request", errors=errors))


async def _crash(request: Request, exc: Exception) -> Response:
    # Starlette re-raises the exception after this answer, so the server still logs it
    return problem_response(500, Problem(detail="internal error"))


# FastAPI(exception_handlers=...). Both HTTPException classes are named: FastAPI registers
# its own handler for its subclass, which would otherwise answer before Starlette's.
HANDLERS: dict[int | type[Exception], Callable[[Request, Any], Coroutine[Any, Any, Response]]] = {
    ProblemError: _problem_error,
    HTTPException: _http_error,
    StarletteHTTPException: _http_error,
    RequestValidationError: _validation_error,
    Exception: _crash,
}
