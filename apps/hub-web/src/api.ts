// Typed client for the hub API (same origin; the session cookie rides along).
import type {
  ChannelName,
  ChannelResolution,
  Draft,
  DraftFile,
  OutcomeReport,
  PublishRequest,
  Release,
  ReleaseComparison,
  ReleaseList,
  RunDetail,
  RunList,
  UsageReport,
  ValidationResult,
  WorkflowList,
} from "@jigworks/contracts";

/** Hub-only (not in the frozen contract): GET /api/analytics/overview. */
export interface GroupStats {
  runs: number;
  costUsd: number;
  costPerRunUsd?: number | null;
  gateRuns: number;
  gatePassFirstTry?: number | null;
  medianTimeToPrSec?: number | null;
  medianHumanWaitSec?: number | null;
}
export interface Overview extends GroupStats {
  from: string;
  to: string;
  costLabel: string;
  previousRuns: number;
  running: number;
  waitingHuman: number;
  pausedUsageLimit: number;
  oldestWaitingSince?: string | null;
  costByDay: { day: string; input: number; output: number; cache_write: number; cache_read: number }[];
  workflows: (GroupStats & { workflowId: string; running: number })[];
  releases: (GroupStats & { release: string })[];
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

let onUnauthorized: () => void = () => {};
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    credentials: "same-origin",
    headers: body === undefined ? {} : { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  const data = text ? JSON.parse(text) : undefined;
  if (!res.ok) {
    const err = data?.error ?? { code: "error", message: res.statusText };
    if (res.status === 401 && path !== "/api/session") onUnauthorized();
    throw new ApiError(res.status, err.code, err.message);
  }
  return data as T;
}

const q = (params: Record<string, string | number | undefined | null>) => {
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") s.set(k, String(v));
  const str = s.toString();
  return str ? `?${str}` : "";
};

export const api = {
  login: (password: string) => call<void>("POST", "/api/session", { password }),
  logout: () => call<void>("DELETE", "/api/session"),
  workflows: () => call<WorkflowList>("GET", "/api/workflows"),
  draft: (id: string) => call<Draft>("GET", `/api/workflows/${id}/draft`),
  saveDraft: (id: string, files: DraftFile[]) => call<Draft>("PUT", `/api/workflows/${id}/draft`, { files }),
  validate: (id: string) => call<ValidationResult>("POST", `/api/workflows/${id}/validate`),
  publish: (id: string, body: PublishRequest) => call<Release>("POST", `/api/workflows/${id}/publish`, body),
  releases: (id: string) => call<ReleaseList>("GET", `/api/workflows/${id}/releases`),
  pointChannel: (id: string, channel: ChannelName, releaseId: string) =>
    call<ChannelResolution>("PUT", `/api/workflows/${id}/channels/${channel}`, { releaseId }),
  runs: (params: { workflowId?: string; status?: string; limit?: number } = {}) =>
    call<RunList>("GET", `/api/runs${q({ limit: 200, ...params })}`),
  run: (runId: string) => call<RunDetail>("GET", `/api/runs/${runId}`),
  usage: (params: { groupBy: "release" | "model" | "node" | "day"; workflowId?: string; from?: string; to?: string }) =>
    call<UsageReport>("GET", `/api/analytics/usage${q(params)}`),
  releaseComparison: (workflowId: string) =>
    call<ReleaseComparison>("GET", `/api/analytics/releases${q({ workflowId })}`),
  outcomes: (workflowId?: string) => call<OutcomeReport>("GET", `/api/analytics/outcomes${q({ workflowId })}`),
  overview: (params: { workflowId?: string; from?: string; to?: string } = {}) =>
    call<Overview>("GET", `/api/analytics/overview${q(params)}`),
};
