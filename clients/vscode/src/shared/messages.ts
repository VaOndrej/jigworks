// Messages between the extension host and its webviews.
import type { GraphJSON, RunEvent } from "@jigworks/contracts";

export interface WorkflowInfo {
  /** Stable key: `<name>@<version>` plus the source. */
  key: string;
  name: string;
  version: string;
  release: string;
  digest: string;
  path: string;
  source: "workspace" | "imported" | "hub";
  channel?: string;
  /** Workspace package whose name is also published (hub/imported) with a different digest. */
  changed?: boolean;
  description?: string;
  plannedPath: string[];
  interruptNodes: string[];
  models: { default: string; nodes?: Record<string, string> };
  allowedTools: string[];
  network?: boolean;
  graph?: GraphJSON;
}

export interface Preflight {
  ok: boolean;
  authMethod?: string;
  subscriptionType?: string;
  message?: string;
}

export interface HubStatus {
  /** Hub URL from settings; empty when no hub is configured. */
  url: string;
  hasPassword: boolean;
  state: "not_configured" | "unknown" | "connected" | "error";
  message?: string;
}

export interface HostState {
  workflows: WorkflowInfo[];
  selectedWorkflow?: string;
  sessions: Record<string, RunEvent[]>;
  running: string[];
  preflight?: Preflight;
  activeRun?: string;
  repoLabel?: string;
  hub?: HubStatus;
}

export type ToHost =
  | { type: "ready"; view: ViewKind; runId?: string }
  | { type: "selectWorkflow"; key: string }
  | { type: "newSession" }
  | { type: "openSession"; runId: string }
  | { type: "start"; prompt: string; workflowKey: string; attachments?: string[] }
  | { type: "attach" }
  | { type: "openAudit"; runId: string }
  | { type: "decide"; runId: string; decision: "approve" | "request_changes" | "reject"; comment?: string }
  | { type: "resume"; runId: string }
  | { type: "stop"; runId: string }
  | { type: "openDiff"; runId: string }
  | { type: "importWorkflow" }
  | { type: "sync" }
  | { type: "hubSettings" };

export type ToWebview =
  | { type: "state"; state: HostState }
  | { type: "event"; runId: string; event: RunEvent }
  | { type: "attached"; paths: string[] }
  | { type: "error"; message: string };

export type ViewKind = "sidebar" | "new" | "session";
