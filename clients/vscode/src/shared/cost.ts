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
