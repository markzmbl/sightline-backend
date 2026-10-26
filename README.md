# sightline-backend

The HTTP service around the sightline core: users ask a workspace's warehouse a question,
revise it by prompt, follow each run live over server-sent events, answer choice cards,
switch charts, rate answers, and key users review what sightline proposes. The only v1
client is the React app in `sightline-web`.

The plan, with its decisions, is
`C:\Users\MarkusZimmball\.claude\plans\sightlines-core-is-currently-squishy-karp.md`.

## Where it stands (P0)

This repo holds the contract only:

- `src/sightline_backend/contract.py`: the API's pydantic models, mirroring the frontend's
  `web/contract/openapi.draft.yaml` with its schema and operation names.
- `src/sightline_backend/api/`: every route with its path, method, operationId, status
  codes and models. Each one answers 501 with a Problem (`code: not_implemented`) until
  its phase builds it; `/healthz` answers. That 501 is scaffolding, not contract: no
  operation declares it, and `Problem.code` does not list it.
- `contract/openapi.json`: the OpenAPI document generated from the two, committed.

There is no database, worker or core dependency yet. The core (`sightline`) joins in P3/P4.

## Run

```
uv sync
uv run pytest
uv run ruff check .
uv run mypy src
uv run uvicorn --factory sightline_backend.app:create_app --reload
```

The docs are at `http://127.0.0.1:8000/api/v1/docs`, the document at `/api/v1/openapi.json`.

## The contract comes first

`contract/openapi.json` is what `sightline-web` generates its types from
(`npm run gen:api` reads `../backend/contract/openapi.json`; both sit in sightline as submodules). After a change to
`contract.py` or a route, export it again and commit the file with the change:

```
uv run python scripts/export_openapi.py
```

`tests/test_contract.py` fails while the committed file differs from a fresh export. It
also holds the contract written out (`OPERATIONS`, `SHAPES`: every operation's method and
path, every schema's properties and required fields), so a model change fails there until
the snapshot is changed with it, on purpose. While the frontend's draft exists, it also
checks that every draft operation is here with the same parameters, body and responses.

A contract change goes through the frontend session first, by message: propose it, agree
on it, then change the models here. Never change the contract on the backend's side alone.
