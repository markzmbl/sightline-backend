"""Export the API contract to contract/openapi.json.

The committed file is what sightline-web generates its types from; tests/test_contract.py
fails while it differs from a fresh export.

Usage: uv run python scripts/export_openapi.py
"""

from __future__ import annotations

from pathlib import Path

from sightline_backend.app import openapi_json

OUT = Path(__file__).resolve().parent.parent / "contract" / "openapi.json"


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(openapi_json(), encoding="utf-8", newline="\n")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
