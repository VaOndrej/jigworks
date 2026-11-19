"""Regenerate the Python side of the contracts from schema/jigworks.schema.json.

    uv run python packages/contracts/scripts/generate.py           # write files
    uv run python packages/contracts/scripts/generate.py --check   # fail if out of date

Writes jigworks_contracts/models.py (datamodel-codegen) and openapi.json (from a
FastAPI stub that declares every hub endpoint with the generated models). After T02,
HUB regenerates openapi.json from the real FastAPI app; it must stay compatible.
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
    if not check:
        MODELS.write_text(new_models)
    new_openapi = generate_openapi()  # imports the (possibly just written) models
    if check:
        stale = [p.name for p, new in ((MODELS, new_models), (OPENAPI, new_openapi))
                 if not p.exists() or p.read_text() != new]
        if stale:
            print(f"out of date: {', '.join(stale)}; run scripts/generate.py", file=sys.stderr)
            return 1
        print("generated files are up to date")
        return 0
    OPENAPI.write_text(new_openapi)
    print(f"wrote {MODELS.relative_to(ROOT)} and {OPENAPI.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
