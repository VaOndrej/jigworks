// @jigworks/contracts — frozen after T02. Types and the JSON Schema are generated from
// schema/jigworks.schema.json; see README.md for the rules.
export * from "./generated/types.js";
export { schema } from "./generated/schema.js";
export { validate, assertValid, type DefName, type ValidationOutcome } from "./validate.js";
export { designExampleEvent } from "./examples.js";

/** Header the runner and the extension send instead of the hub session cookie. */
export const HUB_KEY_HEADER = "X-Jigworks-Key";
/** HTTP-only cookie set by POST /api/session after the hub password is entered. */
export const HUB_SESSION_COOKIE = "jigworks_session";
/** The only endpoint that needs no auth. */
export const PUBLIC_ENDPOINTS = ["GET /api/health", "POST /api/session"] as const;
