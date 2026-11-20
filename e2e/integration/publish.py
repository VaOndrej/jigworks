"""Publish a workflow package to a hub through its real API: PUT the draft, POST publish.

    uv run python e2e/integration/publish.py <hub url> <package dir> [--channel stable]

The key comes from $HUB_PASSWORD. Prints the Release JSON (no secrets).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tomllib
from pathlib import Path

from jigworks_runner.hub import HubClient, HubConfig, HubError
from jigworks_runner.package import bundle_files


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("url")
    p.add_argument("package")
    p.add_argument("--channel", default="stable")
    args = p.parse_args()
    client = HubClient(HubConfig(args.url.rstrip("/"), os.environ["HUB_PASSWORD"]))
    root = Path(args.package)
    manifest = tomllib.loads((root / "workflow.toml").read_text())
    files = [{"path": path, "content": data.decode()} for path, data in sorted(bundle_files(root).items())]
    wid = manifest["name"]
    try:
        client.request("PUT", f"/api/workflows/{wid}/draft", {"files": files})
        release = client.request("POST", f"/api/workflows/{wid}/publish",
                                 {"version": manifest["version"], "channel": args.channel, "notes": "verify:e2e"})
    except HubError as exc:
        print(f"publish failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(release))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
