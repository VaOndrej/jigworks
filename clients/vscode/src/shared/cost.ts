// API-equivalent cost from a price table with validity (design.md §8): tokens × the price valid
// at the call time, cache tokens priced separately. The CLI's own cost is only a cross-check.
import type { PriceEntry, UsageRecord } from "@jigworks/contracts";

const TOKEN_TYPES = ["input", "output", "cache_write", "cache_read"] as const;

export function priceAt(prices: PriceEntry[], model: string, tokenType: string, at: string): number | undefined {
  let best: PriceEntry | undefined;
  for (const p of prices) {
    if (p.model !== model || p.tokenType !== tokenType || p.validFrom > at) continue;
    if (!best || p.validFrom > best.validFrom) best = p;
  }
  return best?.pricePerMtok;
}

/** Sum of the priced records; records with an unknown model are skipped and counted. */
export function apiCost(prices: PriceEntry[], usages: UsageRecord[]): { usd: number; unpriced: number } {
  let usd = 0;
  let unpriced = 0;
  for (const u of usages) {
    const at = u.at ?? "9999-12-31T00:00:00Z";
    let ok = true;
    let call = 0;
    for (const t of TOKEN_TYPES) {
      const p = priceAt(prices, u.model, t, at);
      if (p === undefined) ok = false;
      else call += (u[t] * p) / 1_000_000;
    }
    if (ok) usd += call;
    else unpriced += 1;
  }
  return { usd, unpriced };
}

export function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${Math.round(n / 1_000)}k`;
  return String(n);
}

// --- per-call usage of resumed sessions (mirrors packages/contracts/jigworks_contracts/usage.py) ---
// Claude CLI 2.1.329 reports a `--resume` call's modelUsage as the session's running total, and
// runners before T25 recorded it per call: summing those records counts every earlier call again
// ($168 shown for a ~$23 run). The leading records of a session and model where no field shrinks
// and the output grows are running totals (each adds its difference); after the first record that
// breaks this, records are already per call (runners from T25 on).

const USAGE_FIELDS = ["input", "output", "cache_write", "cache_read", "cliCostUsd"] as const;

/** Per (session, model): the last running total while still in the leading run, or "per-call". */
export type UsageSeries = Record<string, UsageRecord | "per-call">;

const v = (r: UsageRecord, f: (typeof USAGE_FIELDS)[number]): number => (r[f] as number | null | undefined) ?? 0;

function covers(later: UsageRecord, earlier: UsageRecord): boolean {
  return USAGE_FIELDS.every((f) => v(later, f) >= v(earlier, f)) && v(later, "output") > v(earlier, "output");
}

/** The usage of this record's own call; `series` is updated in place (keep it per run). */
export function perCall(series: UsageSeries, r: UsageRecord): UsageRecord {
  if (!r.sessionId) return r;
  const key = `${r.sessionId}\u0000${r.model}`;
  const last = series[key];
  if (last === undefined) {
    series[key] = r;
    return r;
  }
  if (last === "per-call") return r;
  if (!covers(r, last)) {
    series[key] = "per-call";
    return r;
  }
  series[key] = r;
  const out: UsageRecord = { ...r };
  for (const f of USAGE_FIELDS) {
    if (r[f] === undefined || r[f] === null) continue;
    const d = (r[f] as number) - v(last, f);
    (out as unknown as Record<string, unknown>)[f] = f === "cliCostUsd" ? Math.round(d * 1e10) / 1e10 : Math.round(d);
  }
  return out;
}
