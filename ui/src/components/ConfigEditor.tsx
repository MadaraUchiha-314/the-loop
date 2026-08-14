/**
 * The CLI config, editable (issue-222).
 *
 * Every control on this screen is derived from `GET /api/v1/config/schema` — sections,
 * labels, prose, types, enums and defaults all come from there, so the form cannot drift
 * from what the service will accept. What the operator edits is a **draft** copy; Save
 * sends the diff, which is why a field nobody touched contributes nothing and the file
 * keeps its comments and its untouched keys.
 *
 * Two behaviours are worth knowing before reading the code:
 *
 * - **A default is a placeholder, not a value.** An unset field shows the schema's
 *   default greyed out; typing is what turns it into a value. Pre-filling would freeze
 *   today's defaults into the operator's file the first time they saved anything.
 * - **A subtree with no renderable shape is still editable**, as JSON, so no key is
 *   unreachable from this screen.
 */

import { useMemo, useState } from "react";

import { ApiError } from "../api/client.ts";
import { diff, getIn, isRecord, sectionsOf, setIn, type ConfigField, type ConfigGroup } from "../api/configModel.ts";
import type { ConfigDocument, ConfigSaveResult, JsonSchema, RestartSchedule } from "../api/types.ts";
import { Blueprint } from "./Blueprint.tsx";

type Saved =
  | { state: "idle" }
  | { state: "saving" }
  | { state: "done"; result: ConfigSaveResult }
  | { state: "failed"; message: string };

interface ConfigEditorProps {
  document: ConfigDocument;
  schema: JsonSchema;
  onSave: (patch: Record<string, unknown>) => Promise<ConfigSaveResult>;
  /** Called after a successful save so the page can re-read what the service now holds. */
  onSaved?: (result: ConfigSaveResult) => void;
  /**
   * Schedule the restart that makes boot-time keys take effect (issue-228:
   * `POST /api/v1/restart`). When provided, a save whose result carries
   * `restartRequired` keys offers a "Restart now" button beside the report.
   */
  onRestart?: () => Promise<RestartSchedule>;
}

export function ConfigEditor({ document, schema, onSave, onSaved, onRestart }: ConfigEditorProps) {
  // `baseline` is what the service last told us the file holds; the draft is measured
  // against it, not against the prop, so a save settles the form instead of leaving it
  // reporting a change that has already landed.
  const [baseline, setBaseline] = useState<Record<string, unknown>>(() => structuredClone(document.config));
  const [draft, setDraft] = useState<Record<string, unknown>>(() => structuredClone(document.config));
  const [invalid, setInvalid] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState<Saved>({ state: "idle" });
  // Bumped on save and discard to remount the field tree. The structured (JSON) controls
  // hold their own text — that is what lets somebody type a half-finished object without
  // it being reformatted under the cursor — so settling the form has to reset them too.
  const [revision, setRevision] = useState(0);

  const sections = useMemo(() => sectionsOf(schema), [schema]);
  const patch = useMemo(() => diff(baseline, draft), [baseline, draft]);
  const changedCount = Object.keys(patch).length;
  const blocked = Object.keys(invalid).length > 0;

  function update(path: string[], value: unknown): void {
    setSaved({ state: "idle" });
    setDraft((current) => setIn(current, path, value));
  }

  function markInvalid(key: string, message: string | null): void {
    setInvalid((current) => {
      const next = { ...current };
      if (message) next[key] = message;
      else delete next[key];
      return next;
    });
  }

  async function save(): Promise<void> {
    setSaved({ state: "saving" });
    try {
      const result = await onSave(patch);
      setSaved({ state: "done", result });
      setBaseline(structuredClone(result.config));
      setDraft(structuredClone(result.config));
      setRevision((value) => value + 1);
      onSaved?.(result);
    } catch (cause) {
      setSaved({ state: "failed", message: cause instanceof ApiError ? cause.advice : String(cause) });
    }
  }

  return (
    <>
      <Blueprint className="lp-settings-card lp-config-card">
        <div className="lp-settings-kicker">CLI config</div>
        <div className="lp-note lp-config-head">
          The daemon&rsquo;s own configuration, read from{" "}
          <code>{document.path}</code>
          {document.exists ? "" : " — which does not exist yet; saving creates it"}. A save changes only the
          fields you changed and leaves the file&rsquo;s comments alone, and the poller and receiver pick it up
          on their next cycle.
        </div>
        <div className="lp-config-actions">
          <button type="button" className="btn btn-primary" disabled={!changedCount || blocked || saved.state === "saving"} onClick={() => void save()}>
            {saved.state === "saving" ? "Saving…" : "Save changes"}
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            disabled={!changedCount}
            onClick={() => {
              setDraft(structuredClone(baseline));
              setInvalid({});
              setSaved({ state: "idle" });
              setRevision((value) => value + 1);
            }}
          >
            Discard
          </button>
          <span className="lp-config-count">{summarize(changedCount, blocked)}</span>
        </div>
        <SaveReport saved={saved} onRestart={onRestart} />
      </Blueprint>

      {sections.map((section) => (
        <Blueprint key={`${section.path.join(".")}:${revision}`} className="lp-settings-card lp-config-card">
          <div className="lp-settings-kicker">{section.label}</div>
          {section.description ? <div className="lp-config-prose">{section.description}</div> : null}
          <GroupBody group={section} draft={draft} onChange={update} onInvalid={markInvalid} invalid={invalid} />
        </Blueprint>
      ))}
    </>
  );
}

function summarize(changed: number, blocked: boolean): string {
  if (blocked) return "fix the highlighted field before saving";
  if (!changed) return "no changes";
  return `${changed} section${changed === 1 ? "" : "s"} changed`;
}

function SaveReport({ saved, onRestart }: { saved: Saved; onRestart?: (() => Promise<RestartSchedule>) | undefined }) {
  if (saved.state === "failed") return <div className="lp-config-report fail">{saved.message}</div>;
  if (saved.state !== "done") return null;
  const { result } = saved;
  if (!result.written) return <div className="lp-config-report">Nothing to save — the file already says that.</div>;
  return (
    <div className="lp-config-report ok">
      Saved {result.changed.join(", ")} to {result.path}.
      {result.restartRequired.length
        ? ` ${result.restartRequired.join(", ")} ${result.restartRequired.length === 1 ? "takes" : "take"} effect when the service restarts.`
        : " Live now."}
      {result.restartRequired.length && onRestart ? <RestartNow onRestart={onRestart} /> : null}
    </div>
  );
}

/** The one-click follow-through on "…when the service restarts" (issue-228). */
function RestartNow({ onRestart }: { onRestart: () => Promise<RestartSchedule> }) {
  const [state, setState] = useState<"idle" | "asking" | "scheduled" | "failed">("idle");
  async function go(): Promise<void> {
    setState("asking");
    try {
      await onRestart();
      setState("scheduled");
    } catch {
      setState("failed");
    }
  }
  if (state === "scheduled") return <span> Restart scheduled — the service will drop and come back.</span>;
  if (state === "failed") return <span> The restart could not be scheduled; run `the-loop restart` on the workstation.</span>;
  return (
    <>
      {" "}
      <button type="button" className="btn btn-secondary lp-restart-now" disabled={state === "asking"} onClick={() => void go()}>
        {state === "asking" ? "Scheduling…" : "Restart now"}
      </button>
    </>
  );
}

interface BodyProps {
  group: ConfigGroup;
  draft: Record<string, unknown>;
  invalid: Record<string, string>;
  onChange: (path: string[], value: unknown) => void;
  onInvalid: (key: string, message: string | null) => void;
}

function GroupBody({ group, draft, invalid, onChange, onInvalid }: BodyProps) {
  return (
    <>
      {group.fields.map((field) => (
        <Field
          key={field.path.join(".")}
          field={field}
          value={getIn(draft, field.path)}
          error={invalid[field.path.join(".")]}
          onChange={onChange}
          onInvalid={onInvalid}
        />
      ))}
      {group.groups.map((child) => (
        <div className="lp-config-group" key={child.path.join(".")}>
          <div className="lp-config-group-name">{child.path.join(".")}</div>
          {child.description ? <div className="lp-config-prose">{child.description}</div> : null}
          <GroupBody group={child} draft={draft} invalid={invalid} onChange={onChange} onInvalid={onInvalid} />
        </div>
      ))}
    </>
  );
}

interface FieldProps {
  field: ConfigField;
  value: unknown;
  error?: string | undefined;
  onChange: (path: string[], value: unknown) => void;
  onInvalid: (key: string, message: string | null) => void;
}

function Field({ field, value, error, onChange, onInvalid }: FieldProps) {
  const id = `cfg-${field.path.join("-")}`;
  const describedBy = field.description ? `${id}-note` : undefined;
  return (
    <div className="lp-config-field">
      <label className="lp-settings-label" htmlFor={id}>
        {field.path.join(".")}
      </label>
      <Control field={field} id={id} describedBy={describedBy} value={value} onChange={onChange} onInvalid={onInvalid} />
      {field.description ? (
        <div className="lp-config-prose" id={describedBy}>
          {field.description}
        </div>
      ) : null}
      {error ? <div className="lp-config-report fail">{error}</div> : null}
    </div>
  );
}

interface ControlProps extends FieldProps {
  id: string;
  describedBy?: string | undefined;
}

function Control({ field, id, describedBy, value, onChange, onInvalid }: ControlProps) {
  const placeholder = field.default === undefined ? "" : rendered(field.default);

  switch (field.kind) {
    case "boolean":
      return (
        <input
          id={id}
          type="checkbox"
          aria-describedby={describedBy}
          checked={value === true}
          onChange={(event) => onChange(field.path, event.target.checked)}
        />
      );
    case "enum":
      return (
        <select
          id={id}
          className="input"
          aria-describedby={describedBy}
          value={typeof value === "string" ? value : ""}
          // "" is the unset option, and unset means *remove the key* — an empty string
          // would be a value, and one the schema's enum would rightly refuse.
          onChange={(event) => onChange(field.path, event.target.value || null)}
        >
          <option value="">{placeholder ? `${placeholder} (default)` : "unset"}</option>
          {(field.options ?? []).map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      );
    case "integer":
    case "number":
      return (
        <input
          id={id}
          className="input"
          type="number"
          inputMode="numeric"
          aria-describedby={describedBy}
          min={field.minimum}
          max={field.maximum}
          placeholder={placeholder}
          value={typeof value === "number" ? String(value) : ""}
          onChange={(event) => {
            const text = event.target.value;
            // Cleared means unset, which is a removal: `undefined` would vanish in
            // JSON.stringify and the key would silently keep its old value.
            if (text === "") return onChange(field.path, null);
            const parsed = field.kind === "integer" ? Number.parseInt(text, 10) : Number.parseFloat(text);
            if (!Number.isNaN(parsed)) onChange(field.path, parsed);
          }}
        />
      );
    case "stringList":
      return (
        <textarea
          id={id}
          className="input lp-config-list"
          rows={Math.max(2, Array.isArray(value) ? value.length + 1 : 2)}
          aria-describedby={describedBy}
          placeholder={placeholder}
          value={Array.isArray(value) ? value.join("\n") : ""}
          onChange={(event) =>
            onChange(
              field.path,
              event.target.value
                .split("\n")
                .map((line) => line.trim())
                .filter(Boolean),
            )
          }
        />
      );
    case "structured":
      return <StructuredControl field={field} id={id} describedBy={describedBy} value={value} onChange={onChange} onInvalid={onInvalid} />;
    default:
      return (
        <input
          id={id}
          className="input"
          type="text"
          spellCheck={false}
          autoComplete="off"
          aria-describedby={describedBy}
          placeholder={placeholder}
          value={typeof value === "string" ? value : ""}
          onChange={(event) => onChange(field.path, event.target.value)}
        />
      );
  }
}

/**
 * The escape hatch: a subtree the form cannot type — a list of poll sources, the
 * collaborator records — edited as JSON. It is a real control, not a read-only dump,
 * because the alternative is a screen that quietly cannot reach part of the config.
 * A parse error is reported in words and blocks the save; it never reaches the service.
 */
function StructuredControl({ field, id, describedBy, value, onChange, onInvalid }: ControlProps) {
  const key = field.path.join(".");
  const [text, setText] = useState(() => JSON.stringify(value ?? field.default ?? null, null, 2));
  return (
    <textarea
      id={id}
      className="input lp-config-json"
      rows={Math.min(14, Math.max(3, text.split("\n").length))}
      spellCheck={false}
      aria-describedby={describedBy}
      value={text}
      onChange={(event) => {
        setText(event.target.value);
        try {
          const parsed: unknown = JSON.parse(event.target.value);
          onInvalid(key, null);
          onChange(field.path, parsed);
        } catch {
          onInvalid(key, "this is not valid JSON, so it will not be saved");
        }
      }}
    />
  );
}

function rendered(value: unknown): string {
  if (Array.isArray(value)) return value.join(", ");
  if (isRecord(value)) return JSON.stringify(value);
  return String(value);
}
