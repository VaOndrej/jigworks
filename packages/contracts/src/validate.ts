import * as ajv2020Module from "ajv/dist/2020.js";
import * as ajvFormatsModule from "ajv-formats";
import type { ErrorObject, ValidateFunction } from "ajv";
import { schema } from "./generated/schema.js";

// ajv ships CommonJS; depending on ESM/CJS interop the export sits on .default (once or twice).
interface AjvLike {
  addSchema(schema: object): unknown;
  getSchema(ref: string): ValidateFunction | undefined;
}
type AjvCtor = new (opts: { allErrors: boolean; strict: boolean }) => AjvLike;
type AddFormats = (ajv: AjvLike) => unknown;
function unwrap<T>(mod: unknown): T {
  let m = mod as { default?: unknown };
  while (typeof m !== "function" && m && m.default) m = m.default as { default?: unknown };
  return m as T;
}
const Ajv2020 = unwrap<AjvCtor>(ajv2020Module);
const addFormats = unwrap<AddFormats>(ajvFormatsModule);

export type DefName = keyof typeof schema.$defs;
export interface ValidationOutcome {
  ok: boolean;
  errors: string[];
}

let ajv: AjvLike | undefined;
const cache = new Map<DefName, ValidateFunction>();

function validatorFor(def: DefName): ValidateFunction {
  if (!ajv) {
    ajv = new Ajv2020({ allErrors: true, strict: false });
    addFormats(ajv);
    ajv.addSchema(schema as object);
  }
  let fn = cache.get(def);
  if (!fn) {
    fn = ajv.getSchema(`${schema.$id}#/$defs/${def}`);
    if (!fn) throw new Error(`unknown contract definition: ${String(def)}`);
    cache.set(def, fn);
  }
  return fn;
}

function format(errors: ErrorObject[] | null | undefined): string[] {
  return (errors ?? []).map((e) => `${e.instancePath || "/"} ${e.message ?? "is invalid"}`);
}

/** Validate a value against one $defs entry, including the RunEvent kind → payload rules. */
export function validate(def: DefName, value: unknown): ValidationOutcome {
  const fn = validatorFor(def);
  const ok = fn(value) as boolean;
  return { ok, errors: ok ? [] : format(fn.errors) };
}

export function assertValid(def: DefName, value: unknown): void {
  const { ok, errors } = validate(def, value);
  if (!ok) throw new Error(`invalid ${String(def)}: ${errors.join("; ")}`);
}
