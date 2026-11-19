/**
 * The UI's copy (issue-540): every user-visible string the dashboard renders is
 * a `ui.*` entry of the-loop's one string catalog, `cli/the_loop/strings/en.json`.
 * Vite bundles the JSON at build time, so there is no runtime fetch and the page
 * and the CLI can never ship different text.
 *
 * `t(key, vars)` looks one entry up and fills its `{name}` fields in a single
 * pass: a substituted value is inserted literally and never re-expanded, and
 * `{{` / `}}` stand for a literal brace — the semantics of Python's
 * `str.format`, which the CLI side uses. A missing key, or a field the text
 * uses that `vars` lacks, throws: no blank copy reaches the screen.
 *
 * Spec: docs/specs/issue-540/design.md § "The UI".
 */

import en from "../../cli/the_loop/strings/en.json";

const CATALOG: Readonly<Record<string, string>> = en;

const FIELD = /\{\{|\}\}|\{([A-Za-z_][A-Za-z0-9_]*)\}/g;

/** The catalog's text for `key` with its `{name}` fields filled from `vars`. */
export function t(key: string, vars?: Record<string, string | number>): string {
  const text = CATALOG[key];
  if (text === undefined) throw new Error(`no catalog entry for key: ${key}`);
  return format(text, vars, key);
}

/** One pass over `text`: `{name}` → `vars[name]`, `{{` / `}}` → a literal brace. */
export function format(text: string, vars?: Record<string, string | number>, key = "text"): string {
  return text.replace(FIELD, (match, name: string | undefined) => {
    if (match === "{{") return "{";
    if (match === "}}") return "}";
    const value = name === undefined ? undefined : vars?.[name];
    if (value === undefined) throw new Error(`${key} needs a value for {${name ?? ""}}`);
    return String(value);
  });
}

/** Every key in the catalog (tests). */
export function catalogKeys(): string[] {
  return Object.keys(CATALOG);
}
