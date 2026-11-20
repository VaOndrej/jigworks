"""Publish a workflow package from this repo to the hub: draft → validate → release (→ channel).

The hub's editor changes the draft file by file; this uploads a whole package from the repo
(the same files as the release bundle, without tests/ and evals/) as the new draft, validates it
in the hub's sandbox and publishes the version from its workflow.toml.

    uv run python scripts/publish-workflow.py workflows/feature-development              # dry run
    uv run python scripts/publish-workflow.py workflows/feature-development --channel stable --yes

Environment (never printed): JIGWORKS_HUB_URL, HUB_PASSWORD, optional
VERCEL_AUTOMATION_BYPASS_SECRET for a protected deployment.

The draft upload is a full replacement: edits made in the hub's editor and not in the repo are
lost. The dry run lists what would change in the draft, so look at it first.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

from jigworks_runner.package import bundle_files


def request(method: str, url: str, body: dict | None = None) -> dict:
    headers = {"Content-Type": "application/json", "X-Jigworks-Key": os.environ["HUB_PASSWORD"]}
    if os.environ.get("VERCEL_AUTOMATION_BYPASS_SECRET"):
        headers["x-vercel-protection-bypass"] = os.environ["VERCEL_AUTOMATION_BYPASS_SECRET"]
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:500]
        sys.exit(f"{method} {url.split('/api/', 1)[-1]}: HTTP {exc.code}: {detail}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("package", help="workflow package directory, e.g. workflows/feature-development")
    p.add_argument("--channel", choices=["stable", "beta"], help="point this channel to the new release")
    p.add_argument("--notes", default=None)
    p.add_argument("--yes", action="store_true", help="really replace the draft and publish (default: dry run)")
    args = p.parse_args()

    for var in ("JIGWORKS_HUB_URL", "HUB_PASSWORD"):
        if not os.environ.get(var):
            sys.exit(f"{var} is not set")
    hub = os.environ["JIGWORKS_HUB_URL"].rstrip("/")
    root = Path(args.package)
    manifest = tomllib.loads((root / "workflow.toml").read_text())
    wf, version = manifest["name"], manifest["version"]
    files = {path: data.decode() for path, data in sorted(bundle_files(root).items())}

    current = {f["path"]: f["content"] for f in request("GET", f"{hub}/api/workflows/{wf}/draft").get("files", [])}
    changed = sorted(p for p in files if current.get(p) != files[p])
    removed = sorted(set(current) - set(files))
    print(f"{wf}@{version} → {hub}  ({len(files)} files; draft: {len(changed)} changed/new, {len(removed)} removed)")
    for path in changed:
        print(f"  {'~' if path in current else '+'} {path}")
    for path in removed:
        print(f"  - {path}")
    existing = [r["version"] for r in request("GET", f"{hub}/api/workflows/{wf}/releases").get("releases", [])]
    if version in existing:
        sys.exit(f"{wf}@{version} is already published (releases are immutable); bump the version in workflow.toml")
    if not args.yes:
        print("dry run: nothing changed on the hub. Re-run with --yes to replace the draft and publish.")
        return 0

    request("PUT", f"{hub}/api/workflows/{wf}/draft", {"files": [{"path": k, "content": v} for k, v in files.items()]})
    result = request("POST", f"{hub}/api/workflows/{wf}/validate")
    for check in result.get("checks", []):
        print(f"  {'✓' if check.get('ok') else '✗'} {check['name']} {check.get('message', '')}")
    if not result.get("ok"):
        sys.exit("validation failed: the draft is uploaded but nothing was published")
    body = {"version": version, **({"channel": args.channel} if args.channel else {}),
            **({"notes": args.notes} if args.notes else {})}
    release = request("POST", f"{hub}/api/workflows/{wf}/publish", body)
    print(f"published {wf}@{release.get('version')} {release.get('digest', '')}"
          + (f", channel {args.channel}" if args.channel else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
