// Editor tab title and icon state for a session panel. Pure, so it is unit-tested; the host only
// maps the icon state to an SVG under media/.
import { recentActions, stepGerund } from "./activity";
import type { SessionView } from "./session";

export type TabIcon = "running" | "waiting" | "failed" | "done" | "stopped";

export interface TabChrome {
  title: string;
  icon: TabIcon;
}

const MAX_TITLE = 24;
const MAX_ACTION = 14;

/** Cut on a word boundary to about `max` characters and add "…"; never cut inside a word
 *  (unless the first word alone is longer than `max`). Unicode-safe: counts code points. */
export function shortTitle(title: string, max = MAX_TITLE): string {
  const clean = title.replace(/\s+/g, " ").trim();
  const chars = [...clean];
  if (chars.length <= max) return clean;
  const head = chars.slice(0, max + 1).join("");
  const space = head.lastIndexOf(" ");
  const cutAt = space > 0 ? space : [...head].slice(0, max).join("").length;
  return `${clean.slice(0, cutAt).replace(/[\s,.;:–-]+$/u, "")}…`;
}

const GATE: Record<string, string> = {
  approve_plan: "plan",
  approve_pr: "review",
  approve_brainstorm: "brainstorm",
};

export function tabIcon(s: SessionView): TabIcon {
  switch (s.status) {
    case "running":
      return "running";
    case "waiting_human":
      return "waiting";
    case "failed":
      return "failed";
    case "succeeded":
      return "done";
    default:
      return "stopped"; // rejected, cancelled, paused on the usage limit
  }
}

export function tabChrome(s: SessionView): TabChrome {
  const name = shortTitle(s.title || s.runId);
  let suffix: string;
  switch (s.status) {
    case "waiting_human":
      suffix = GATE[s.interrupt?.node ?? s.currentNode ?? ""] ?? "your turn";
      break;
    case "running": {
      const action = recentActions(s, 1)[0]?.short;
      const what = action && action.length <= MAX_ACTION ? action : s.currentNode ? stepGerund(s.currentNode) : "starting";
      suffix = s.progress >= 5 ? `${what} · ${Math.round(s.progress)} %` : what;
      break;
    }
    case "succeeded":
      suffix = "done";
      break;
    case "failed":
      suffix = "failed";
      break;
    case "paused_usage_limit":
      suffix = "paused";
      break;
    default:
      suffix = s.status; // rejected, cancelled
  }
  return { title: `${name} · ${suffix}`, icon: tabIcon(s) };
}
