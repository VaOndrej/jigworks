// Login preflight (docs/spikes/claude-stream-json.md §5): `claude auth status --json`, which
// starts no task and costs nothing. Logged in = exit 0 and `loggedIn: true`. Only authMethod and
// subscriptionType are kept; email and org never leave this function.
import { spawn } from "node:child_process";
import type { Preflight } from "../shared/messages";

export function checkClaude(claudeBin = "claude", timeoutMs = 15000): Promise<Preflight> {
  return new Promise((resolve) => {
    let out = "";
    let settled = false;
    const done = (p: Preflight) => {
      if (!settled) {
        settled = true;
        resolve(p);
      }
    };
    let proc;
    try {
      proc = spawn(claudeBin, ["auth", "status", "--json"], { stdio: ["ignore", "pipe", "ignore"] });
    } catch {
      return done({ ok: false, message: notInstalled(claudeBin) });
    }
    const timer = setTimeout(() => {
      proc.kill();
      done({ ok: false, message: "`claude auth status` did not answer in time." });
    }, timeoutMs);
    proc.stdout.setEncoding("utf8").on("data", (c: string) => (out += c));
    proc.on("error", () => {
      clearTimeout(timer);
      done({ ok: false, message: notInstalled(claudeBin) });
    });
    proc.on("close", (code) => {
      clearTimeout(timer);
      let data: Record<string, unknown> = {};
      try {
        data = JSON.parse(out || "{}");
      } catch {
        /* fall through */
      }
      const ok = code === 0 && data.loggedIn === true;
      done({
        ok,
        authMethod: typeof data.authMethod === "string" ? data.authMethod : undefined,
        subscriptionType: typeof data.subscriptionType === "string" ? data.subscriptionType : undefined,
        message: ok ? undefined : "Claude Code is not logged in. Run `claude` in a terminal and use /login, then try again.",
      });
    });
  });
}

function notInstalled(bin: string): string {
  return `Claude Code (\`${bin}\`) is not installed or not on PATH. Install it (https://code.claude.com) and run \`claude\` once to log in.`;
}
