# Jigworks for VS Code

Run published Jigworks workflows from VS Code: pick a workflow, write the prompt, watch the run
step through its graph, and approve, request changes or reject at the human steps. Every session
runs in its own git worktree through the local Jigworks runner, which calls `claude -p`.

- **Sidebar:** workflows (workspace, imported `.zip`, synced from the hub) and sessions with their
  current node and % of plan; a **Review** badge replaces the % while a session waits for you.
- **New session:** the prompt in the middle of the editor; models come from the workflow release.
- **Run view:** % of plan, the graph with the NOW marker, agent output, Approve / Request changes /
  Reject.

Requirements: Claude Code installed and logged in (`claude auth status`), `uv`, and the Jigworks
runner (`uv run jigworks`, setting `jigworks.runnerCommand`).

Development:

```bash
pnpm --filter vscode test       # @vscode/test-electron, fake adapter
pnpm --filter vscode test:ui    # standalone webview + Playwright screenshots (1440 px)
pnpm --filter vscode package    # jigworks.vsix
```
