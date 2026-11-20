"""Print LangGraph's raw get_graph().to_json() for a workflow package directory.

    uv run --no-project --with langgraph python scripts/dump_graph.py <package-dir> [entrypoint]

Runs outside the workspace venv on purpose: workflow code executes in its own
environment (design.md §5), never in the hub API process.
"""

import importlib
import json
import sys

pkg = sys.argv[1]
entry = sys.argv[2] if len(sys.argv) > 2 else "graph:build_graph"
sys.path.insert(0, pkg)
module_name, func = entry.split(":")
graph = getattr(importlib.import_module(module_name), func)().compile()
print(json.dumps(graph.get_graph().to_json(), indent=2, default=str))
