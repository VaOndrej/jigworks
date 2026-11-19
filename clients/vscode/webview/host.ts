// Connection to the extension host. In VS Code this is `acquireVsCodeApi()`; the standalone UI
// (screenshots, development) installs a mock that replays recorded runs instead.
import { useEffect, useMemo, useState } from "react";
import type { RunEvent } from "@jigworks/contracts";
import type { HostState, ToHost, ToWebview, ViewKind } from "../src/shared/messages";
import { foldEvents, type SessionView } from "../src/shared/session";

export interface HostApi {
  postMessage(msg: ToHost): void;
}

declare global {
  interface Window {
    __JIGWORKS_BOOT__?: { view: ViewKind; runId: string | null };
    __JIGWORKS_HOST__?: HostApi;
    acquireVsCodeApi?: () => HostApi;
  }
}

let api: HostApi | undefined;

export function host(): HostApi {
  if (!api) api = window.__JIGWORKS_HOST__ ?? window.acquireVsCodeApi?.() ?? { postMessage: () => undefined };
  return api;
}

export const EMPTY: HostState = { workflows: [], sessions: {}, running: [] };

export function useHostState(view: ViewKind, runId?: string | null): HostState {
  const [state, setState] = useState<HostState>(EMPTY);
  useEffect(() => {
    const onMessage = (ev: MessageEvent<ToWebview>) => {
      const msg = ev.data;
      if (msg.type === "state") setState(msg.state);
      else if (msg.type === "event") {
        setState((prev) => {
          const list: RunEvent[] = prev.sessions[msg.runId] ?? [];
          const last = list.length ? (list[list.length - 1].seq ?? -1) : -1;
          if ((msg.event.seq ?? last + 1) <= last) return prev;
          return { ...prev, sessions: { ...prev.sessions, [msg.runId]: [...list, msg.event] } };
        });
      }
    };
    window.addEventListener("message", onMessage);
    host().postMessage({ type: "ready", view, runId: runId ?? undefined });
    return () => window.removeEventListener("message", onMessage);
  }, [view, runId]);
  return state;
}

export function useSessions(state: HostState): SessionView[] {
  return useMemo(
    () =>
      Object.entries(state.sessions)
        .map(([id, events]) => foldEvents(id, events))
        .sort((a, b) => (b.startedAt ?? "").localeCompare(a.startedAt ?? "")),
    [state.sessions],
  );
}
