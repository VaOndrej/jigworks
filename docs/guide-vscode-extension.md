# Guide: the Jigworks VS Code extension

How to install the extension, run a `feature-development` session against `sample-repo/`,
review it, and see it in the hub. About 10 minutes, plus the run itself.

## What you need

- VS Code with the `code` command on PATH.
- Claude Code installed and logged in. `claude auth status` must print `"loggedIn": true`.
  Real runs use your Claude subscription. A run costs roughly $1–5 API equivalent, and the T06
  live run with two fix loops cost $4.90.
- `uv` and `pnpm`, and this repo on `main`.

```bash
cd ~/Development/jigworks
git switch main && git pull --ff-only
uv sync && pnpm install && pnpm --filter contracts build
```

## 1. Build and install the extension

```bash
pnpm --filter vscode package
code --install-extension clients/vscode/jigworks.vsix --force
```

Then in VS Code, run **Developer: Reload Window**.

## 2. Open the repo and make the PR step local

Open `~/Development/jigworks` as the workspace folder. The extension starts the runner there
(`uv run jigworks`), finds the workflow packages in `workflows/`, and lets the agents change only
`sample-repo/` (setting `jigworks.repoPath`).

The last step of the workflow (`open_pr`) pushes the branch `demo/<runId>` to the PR remote.
The default remote is `origin`, which is the **public** GitHub repo; with a GitHub remote the step
also runs `gh pr create`. For trying it out, push to a local bare repo instead:

```bash
git init --bare ~/jigworks-pr-remote.git
```

Then add this to `.vscode/settings.json` in the workspace (the path must be absolute):

```json
{
  "jigworks.runArgs": ["--pr-remote", "/Users/ondrej/jigworks-pr-remote.git"]
}
```

## 3. Check the Claude Code login

Open the Command Palette and run **Jigworks: Check Claude Code login**. The extension runs this
check before every session as well, and refuses to start one if you are logged out.

## 4. Connect the hub (optional)

Without the hub, the extension runs workflows from the workspace, and runs stay local. With
the hub, runs show up in **Runs & analytics**, and workflows can come from the `stable` channel.

1. Click the gear in the title bar of the Jigworks view (or **Sync** / **Connect** in the
   sidebar, or the command **Jigworks: Connect to hub**).
2. Enter the hub URL `https://jigworks.vercel.app`, then the hub password. Leave the third
   prompt (Vercel protection bypass secret) empty; it is only needed for a protected preview
   URL. The URL goes to the user setting `jigworks.hubUrl`; the password and the bypass secret
   go to VS Code's secret storage, never to settings.
3. The extension syncs right away. The line under **WORKFLOWS** shows the hub and its state
   (`connected`, `sync failed` with the reason, or `Not connected to a hub`).

A new hub seeds itself once with sample data from the contract fixtures: the release
`feature-development 1.3.0` on `stable` and seven runs by `alice/bob/carol@example.com`. The
sample release's steps **do not call an agent**; it exists to fill the hub's screens. To remove
the sample data, call the hub with its URL and password. Only the
seeded releases and runs go; real releases and runs stay, and the hub does not seed itself again:

```bash
set -a; source .env.local; set +a
curl -sS -X POST -H "X-Jigworks-Key: $HUB_PASSWORD" https://jigworks.vercel.app/api/admin/remove-sample-data
# → {"runs":7,"releases":2,"workflows":1,"blobBundles":2}; a second call returns zeros
```
 To run the real workflow from the hub, publish the package in
this repo (`feature-development 1.4.0`) first. Publishing creates an immutable release and moves
`stable` to it:

```bash
cd ~/Development/jigworks
set -a; source .env.local; set +a
uv run python e2e/integration/publish.py https://jigworks.vercel.app workflows/feature-development
```

Then run **Jigworks: Sync workflows from the hub** again.

## 5. Start a session

1. Open the **Jigworks** icon in the Activity Bar. The sidebar lists the workflows (from the
   hub, imported `.zip` files, and the workspace) and your sessions.
2. Click the workflow you want: the hub's `feature-development 1.4.0 · stable` after publishing,
   or the workspace's `feature-development 1.4.0`.
3. Click **+ New session**, describe the change, and click **Start session**. For example:

   > Allow cancelling a partially filled order: cancel keeps the filled quantity, releases the
   > rest, and the position stays the sum of fills. Keep every invariant in INVARIANTS.md.

   The models come from the workflow release, not from VS Code. Each session runs in its own git
   worktree (`.jigworks/` in the repo), so you can start a second session while the first runs.

## 6. Follow and decide

The run view shows the following:

- **% of plan** with the marker where your review comes.
- **The graph** with **NOW** on the running node. Green means done, amber means it needs you.
- **Activity** (node by node) and **Agent output** (the live `claude -p` stream).

The workflow stops twice for you:

1. **approve_plan:** read the plan and click **Approve**, or **Reject** to stop the run.
2. **approve_pr:** this comes after an independent review and a green gate. The gate runs the
   tests, the invariant property tests, the protected-tests check, the secret scan and bandit.
   - Open the change with **Open worktree** and **Audit log**.
   - **Approve** pushes the PR branch.
   - **Request changes** sends your comment to the agent, then runs fix → gate → review again.
   - **Reject** ends the run.

While a session waits for you, the sidebar shows a **Review** badge instead of the %. A
notification appears too.

Rule worth knowing: once `write_tests` has written the tests, they are read-only for `implement`
and `fix`. The same goes for the pytest configuration and `INVARIANTS.md`. If an agent changes
them, the gate fails with **protected tests**. If a test itself is wrong, reject the run and
start again with a better prompt.

## 7. After the run

- **In the hub:** with `jigworks.hubUrl` set, the run appears in **Runs & analytics**. You see
  its audit trail, its cost (raw tokens × price table, API equivalent) and the version comparison.
- **The PR branch** is in the bare remote:

  ```bash
  git --git-dir ~/jigworks-pr-remote.git branch
  ```

- **From the terminal:**

  ```bash
  uv run jigworks ls                     # all runs
  uv run jigworks show <runId>           # summary
  uv run jigworks audit <runId>          # audit record and cost
  ```

## 8. Import a workflow from a file

Run **Jigworks: Import workflow from file** and pick a release `.zip`. If a `<file>.sha256` sits
next to it, the extension checks the digest against it; otherwise it asks for the digest. A
tampered zip is refused and nothing is written.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| "wrong hub password" (401) | Gear in the Jigworks view → **Change hub password…**. |
| "behind Vercel Deployment Protection" | The URL is a protected preview. Use `https://jigworks.vercel.app`, or set the bypass secret (gear → **Set Vercel protection bypass secret…**). |
| "too many wrong hub passwords" (429) | 10 wrong passwords from your IP within 15 min. Wait for the time in the message, then fix the password. |
| Session refused: not logged in | `claude auth login`, then **Jigworks: Check Claude Code login**. |
| Session paused: usage limit | Your subscription's usage window is full. Run **Jigworks: Resume session** after the reset time shown. |
| The run from the hub's 1.3.0 does nothing useful | That is the sample release; publish 1.4.0 (step 4) or pick the workspace workflow. |
| A session is gone after a VS Code restart | Run **Jigworks: Refresh**. Sessions are rebuilt from `.jigworks/` on disk. |
