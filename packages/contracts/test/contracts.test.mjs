// Contract tests for the TS side. Run: pnpm --filter contracts build (builds, then runs these).
import { test } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import * as esm from "../dist/esm/index.js";

const cjs = createRequire(import.meta.url)("../dist/cjs/index.js");
const fix = new URL("../fixtures/", import.meta.url);
const index = JSON.parse(readFileSync(new URL("index.json", fix), "utf8"));

function load(rel) {
  const meta = index.fixtures[rel];
  const text = readFileSync(new URL(rel, fix), "utf8");
  if (meta.jsonl) return text.split("\n").filter(Boolean).map((l) => JSON.parse(l));
  const data = JSON.parse(text);
  return meta.list ? data : [data];
}

for (const [name, lib] of [["esm", esm], ["cjs", cjs]]) {
  test(`${name}: design.md §8 example validates as-is`, () => {
    assert.deepEqual(lib.validate("RunEvent", lib.designExampleEvent), { ok: true, errors: [] });
  });

  test(`${name}: kind requires its payload`, () => {
    const r = lib.validate("RunEvent", { runId: "r", kind: "interrupt", node: "approve_pr", at: "2026-11-19T15:00:00Z" });
    assert.equal(r.ok, false);
    assert.ok(r.errors.some((e) => e.includes("interrupt")), r.errors.join("; "));
  });
}

for (const rel of Object.keys(index.fixtures).sort()) {
  test(`fixture ${rel} validates as ${index.fixtures[rel].def}`, () => {
    for (const item of load(rel)) {
      const r = esm.validate(index.fixtures[rel].def, item);
      assert.ok(r.ok, `${rel}: ${r.errors.join("; ")}`);
    }
  });
}

test("bundle digests match the bytes; the tampered bundle does not", () => {
  const sha = (rel) => "sha256:" + createHash("sha256").update(readFileSync(new URL(rel, fix))).digest("hex");
  for (const [rel, expected] of Object.entries(index.bundles)) assert.equal(sha(rel), expected);
  for (const [rel, claimed] of Object.entries(index.tampered)) assert.notEqual(sha(rel), claimed);
});

test("auth constants match the OpenAPI security schemes", () => {
  const spec = JSON.parse(readFileSync(new URL("../openapi.json", import.meta.url), "utf8"));
  assert.equal(spec.components.securitySchemes.hubKey.name, esm.HUB_KEY_HEADER);
  assert.equal(spec.components.securitySchemes.hubSession.name, esm.HUB_SESSION_COOKIE);
});
