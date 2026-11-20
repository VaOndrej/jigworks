"""Regenerate the Python side of the contracts from schema/jigworks.schema.json.

    uv run python packages/contracts/scripts/generate.py                  # write models.py
    uv run python packages/contracts/scripts/generate.py --openapi-stub   # also write openapi.json from the stub
    uv run python packages/contracts/scripts/generate.py --check          # fail if models.py is stale

models.py comes from datamodel-codegen. openapi.json was first written from a FastAPI stub
(scripts/openapi_stub.py). After T02, HUB owns its regeneration from the real FastAPI app,
so this script only rewrites it with --openapi-stub; the tests check that it stays
compatible with the stub (same paths and methods, same component schemas, same auth).
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "schema" / "jigworks.schema.json"
MODELS = ROOT / "jigworks_contracts" / "models.py"
OPENAPI = ROOT / "openapi.json"


def generate_models(out: Path) -> None:
    subprocess.run(
        [
            "datamodel-codegen",
            "--input", str(SCHEMA),
            "--input-file-type", "jsonschema",
            "--output", str(out),
            "--output-model-type", "pydantic_v2.BaseModel",
            "--target-python-version", "3.12",
            "--use-standard-collections",
            "--use-union-operator",
            "--use-annotated",
            "--field-constraints",
            "--use-schema-description",
            "--use-field-description",
            "--disable-timestamp",
            "--enum-field-as-literal", "all",
            "--collapse-root-models",
            "--use-double-quotes",
            "--formatters", "builtin",
            "--custom-file-header",
            "# GENERATED from schema/jigworks.schema.json by scripts/generate.py. Do not edit.",
        ],
        check=True,
    )


def generate_openapi() -> str:
    sys.path.insert(0, str(ROOT / "scripts"))
    from openapi_stub import build_app  # noqa: PLC0415

    return json.dumps(build_app().openapi(), indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    check = "--check" in sys.argv
    with tempfile.TemporaryDirectory() as tmp:
        new_models_path = Path(tmp) / "models.py"
        generate_models(new_models_path)
        new_models = new_models_path.read_text()
    if check:
        if not MODELS.exists() or MODELS.read_text() != new_models:
            print("out of date: models.py; run scripts/generate.py", file=sys.stderr)
            return 1
        print("models.py is up to date")
        return 0
    MODELS.write_text(new_models)
    print(f"wrote {MODELS.relative_to(ROOT)}")
    if "--openapi-stub" in sys.argv:
        OPENAPI.write_text(generate_openapi())
        print(f"wrote {OPENAPI.relative_to(ROOT)} from scripts/openapi_stub.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
