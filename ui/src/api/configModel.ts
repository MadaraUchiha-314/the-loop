/**
 * The config form, derived from the schema rather than written out by hand.
 *
 * `GET /api/v1/config/schema` already carries everything a form needs — the nesting, the
 * types, the enums, the ranges, the defaults, and a written description per key — for
 * about a hundred keys. Hand-listing those in TSX would be a second copy of the schema,
 * and the copy is the one that rots. So the Settings tab renders from this projection:
 * one section per top-level property, nested objects as nested groups, and a leaf kind
 * per field.
 *
 * The kinds are deliberately few. Anything that is not a scalar, an enum or a list of
 * strings — an array of objects, a subtree with no declared shape — becomes a
 * `structured` field the operator edits as JSON, so that **no part of the config is
 * unreachable from the UI** (R5.4). A gap would silently send people back to the file.
 */

import type { JsonSchema } from "./types.ts";

export type LeafKind = "string" | "number" | "integer" | "boolean" | "enum" | "stringList" | "structured";

export interface ConfigField {
  /** Key path from the document root, e.g. `["routing", "enabled"]`. */
  path: string[];
  label: string;
  description?: string | undefined;
  kind: LeafKind;
  /** Present for `enum`: exactly the values the schema allows. */
  options?: string[] | undefined;
  /** Shown as a placeholder, never as a value — see `diff`. */
  default?: unknown;
  minimum?: number | undefined;
  maximum?: number | undefined;
}

export interface ConfigGroup {
  path: string[];
  label: string;
  description?: string | undefined;
  fields: ConfigField[];
  groups: ConfigGroup[];
}

/** One section per top-level property, in the schema's own order. */
export function sectionsOf(schema: JsonSchema): ConfigGroup[] {
  const properties = schema.properties ?? {};
  return Object.entries(properties).map(([key, child]) =>
    isGroup(child)
      ? groupOf(key, child, [key])
      : // A top-level leaf (`version`, `collaborators`) still gets its own titled
        // section, so a reader finds it where the file has it.
        { path: [key], label: labelOf(key, child), description: child.description, fields: [fieldOf(key, child, [key])], groups: [] },
  );
}

function groupOf(key: string, schema: JsonSchema, path: string[]): ConfigGroup {
  const fields: ConfigField[] = [];
  const groups: ConfigGroup[] = [];
  for (const [name, child] of Object.entries(schema.properties ?? {})) {
    const childPath = [...path, name];
    if (isGroup(child)) groups.push(groupOf(name, child, childPath));
    else fields.push(fieldOf(name, child, childPath));
  }
  return { path, label: labelOf(key, schema), description: schema.description, fields, groups };
}

function fieldOf(key: string, schema: JsonSchema, path: string[]): ConfigField {
  const field: ConfigField = {
    path,
    label: labelOf(key, schema),
    description: schema.description,
    kind: kindOf(schema),
    default: schema.default,
  };
  if (field.kind === "enum") field.options = (schema.enum ?? []).map(String);
  if (typeof schema.minimum === "number") field.minimum = schema.minimum;
  if (typeof schema.maximum === "number") field.maximum = schema.maximum;
  return field;
}

/** A subtree with declared keys is a group; everything else is a field of some kind. */
function isGroup(schema: JsonSchema): boolean {
  return typeOf(schema) === "object" && Object.keys(schema.properties ?? {}).length > 0;
}

export function kindOf(schema: JsonSchema): LeafKind {
  if (Array.isArray(schema.enum) && schema.enum.length) return "enum";
  const type = typeOf(schema);
  if (type === "boolean") return "boolean";
  if (type === "integer") return "integer";
  if (type === "number") return "number";
  if (type === "string") return "string";
  if (type === "array" && typeOf(schema.items ?? {}) === "string") return "stringList";
  return "structured";
}

function typeOf(schema: JsonSchema): string {
  return Array.isArray(schema.type) ? (schema.type[0] ?? "") : (schema.type ?? "");
}

function labelOf(key: string, schema: JsonSchema): string {
  return typeof schema.title === "string" && schema.title ? schema.title : key;
}

// -- reading and writing a draft ----------------------------------------------------

export function getIn(source: unknown, path: string[]): unknown {
  let node: unknown = source;
  for (const key of path) {
    if (!isRecord(node)) return undefined;
    node = node[key];
  }
  return node;
}

/** `source` with `path` set to `value`, copying only the branch that changed. */
export function setIn(source: Record<string, unknown>, path: string[], value: unknown): Record<string, unknown> {
  const [head, ...rest] = path;
  if (head === undefined) return source;
  const next = { ...source };
  if (rest.length === 0) {
    next[head] = value;
  } else {
    const child = next[head];
    next[head] = setIn(isRecord(child) ? child : {}, rest, value);
  }
  return next;
}

/** `source` with `path` removed, and no empty husk left where it was. */
export function deleteIn(source: Record<string, unknown>, path: string[]): Record<string, unknown> {
  const [head, ...rest] = path;
  if (head === undefined || !(head in source)) return source;
  const next = { ...source };
  if (rest.length === 0) {
    delete next[head];
    return next;
  }
  const child = next[head];
  if (isRecord(child)) next[head] = deleteIn(child, rest);
  return next;
}

/**
 * The sparse patch that turns `original` into `draft`.
 *
 * Only what changed travels, for two reasons: the file keeps every key the form chose
 * not to render, and two operators editing two sections do not overwrite each other. A
 * key the draft dropped becomes an explicit `null`, which is how the service is told to
 * remove it.
 */
export function diff(original: Record<string, unknown>, draft: Record<string, unknown>): Record<string, unknown> {
  const patch: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(draft)) {
    const before = original[key];
    if (isRecord(value) && isRecord(before)) {
      const nested = diff(before, value);
      if (Object.keys(nested).length) patch[key] = nested;
    } else if (!same(before, value)) {
      patch[key] = value;
    }
  }
  for (const key of Object.keys(original)) {
    if (!(key in draft)) patch[key] = null;
  }
  return patch;
}

function same(a: unknown, b: unknown): boolean {
  return JSON.stringify(a ?? null) === JSON.stringify(b ?? null);
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Every field in a group tree, depth-first — the order the form renders them in. */
export function allFields(groups: ConfigGroup[]): ConfigField[] {
  return groups.flatMap((group) => [...group.fields, ...allFields(group.groups)]);
}
