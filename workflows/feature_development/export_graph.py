"""Print the `get_graph()` JSON of the feature-development package.

    uv run python -m workflows.feature_development.export_graph          # normalized GraphJSON
    uv run python -m workflows.feature_development.export_graph --raw    # raw LangGraph to_json()

The package directory is `workflows/feature-development/` (a hyphen, like its workflow id), which
Python cannot import by name; this module is the importable entry point for it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jigworks_runner.package import load_package

PACKAGE_DIR = Path(__file__).resolve().parent.parent / "feature-development"


def main(argv: list[str]) -> int:
    package = load_package(PACKAGE_DIR)
    if "--raw" in argv:
        out = package.build_graph().compile().get_graph().to_json()
    else:
        out = package.graph_json()
    json.dump(out, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
