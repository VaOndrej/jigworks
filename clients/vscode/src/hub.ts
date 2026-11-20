// Hub client for the extension (T15): resolve `stable`, download the bundle, check the digest from
// the channel resolution (not only the response header), install it. The password lives in VS Code
// SecretStorage and is sent as X-Jigworks-Key; it never goes into settings.json.
import type { ChannelResolution, WorkflowList } from "@jigworks/contracts";

export const HUB_KEY_HEADER = "X-Jigworks-Key";

export class HubError extends Error {
  constructor(message: string, readonly status?: number) {
    super(message);
  }
}

export class HubClient {
  constructor(private readonly url: string, private readonly key: string, private readonly bypass?: string) {}

  private headers(): Record<string, string> {
    const h: Record<string, string> = { [HUB_KEY_HEADER]: this.key, accept: "application/json" };
    if (this.bypass) h["x-vercel-protection-bypass"] = this.bypass;
    return h;
  }

  private async fetch(path: string, init: RequestInit = {}): Promise<Response> {
    let res: Response;
    try {
      res = await fetch(this.url.replace(/\/$/, "") + path, {
        ...init,
        headers: { ...this.headers(), ...(init.headers as Record<string, string> | undefined) },
        signal: AbortSignal.timeout(20000),
        // A hub never redirects its API; a redirect is Vercel Deployment Protection (SSO login page).
        redirect: "manual",
      });
    } catch (err) {
      throw new HubError(`The hub at ${this.url} is unreachable (${(err as Error).message}).`);
    }
    if (res.status >= 300 && res.status < 400) {
      const to = res.headers.get("location") ?? "";
      throw new HubError(
        /vercel\.com\/sso|vercel\.com\/login/.test(to)
          ? `The hub at ${this.url} is behind Vercel Deployment Protection. Set the protection bypass secret (gear in the Jigworks view → “Set Vercel protection bypass secret”) or use the production hub URL.`
          : `The hub at ${this.url} redirected to ${to || "another page"}; check the hub URL.`,
        res.status,
      );
    }
    if (res.status === 401) {
      throw new HubError("The hub refused the password. Run “Jigworks: Set hub password” with the hub password.", 401);
    }
    if (!res.ok) {
      let msg = `${res.status}`;
      try {
        msg = ((await res.json()) as { error?: { message?: string } }).error?.message ?? msg;
      } catch {
        /* keep the status */
      }
      throw new HubError(`${init.method ?? "GET"} ${path} failed: ${msg}`, res.status);
    }
    return res;
  }

  async json<T>(path: string, init?: RequestInit): Promise<T> {
    return (await (await this.fetch(path, init)).json()) as T;
  }

  async bytes(path: string): Promise<{ data: Buffer; headerDigest: string | null }> {
    const res = await this.fetch(path, { headers: { accept: "application/zip" } });
    return { data: Buffer.from(await res.arrayBuffer()), headerDigest: res.headers.get("x-jigworks-digest") };
  }

  workflows(): Promise<WorkflowList> {
    return this.json<WorkflowList>("/api/workflows");
  }

  channel(workflowId: string, channel = "stable"): Promise<ChannelResolution> {
    return this.json<ChannelResolution>(`/api/workflows/${encodeURIComponent(workflowId)}/channels/${channel}`);
  }
}
