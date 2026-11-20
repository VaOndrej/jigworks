// Generates src/generated/types.ts and src/generated/schema.ts from schema/jigworks.schema.json.
// Run via `pnpm --filter contracts build` (or `generate`). Do not edit the generated files.
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { compile } from "json-schema-to-typescript";

const here = new URL("..", import.meta.url);
const schemaPath = new URL("schema/jigworks.schema.json", here);
const outDir = new URL("src/generated/", here);
const schema = JSON.parse(await readFile(schemaPath, "utf8"));

// json-schema-to-typescript turns `{ $ref, description }` or `{ $ref, default }` into a new
// duplicate type (ToolCall1, inlined enums). For the TS output only, keep the bare $ref.
function stripRefSiblings(node) {
  if (Array.isArray(node)) return node.map(stripRefSiblings);
  if (node && typeof node === "object") {
    if (typeof node.$ref === "string") return { $ref: node.$ref };
    return Object.fromEntries(Object.entries(node).map(([k, v]) => [k, stripRefSiblings(v)]));
  }
  return node;
}

const banner = "/* eslint-disable */\n// GENERATED from schema/jigworks.schema.json by scripts/gen-ts.mjs. Do not edit.\n";
const ts = await compile(stripRefSiblings(schema), "JigworksContracts", {
  bannerComment: banner,
  unreachableDefinitions: true,
  additionalProperties: false,
  strictIndexSignatures: false,
  format: true,
});

await mkdir(outDir, { recursive: true });
await writeFile(new URL("types.ts", outDir), ts);
await writeFile(
  new URL("schema.ts", outDir),
  `${banner}export const schema = ${JSON.stringify(schema, null, 2)} as const;\n`,
);
console.log("generated src/generated/types.ts and src/generated/schema.ts");
