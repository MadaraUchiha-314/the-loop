/**
 * The small pieces the design repeats (issue-327): the phase chip, the 28 px
 * icon button, the session panel's titled section and key/value line, the
 * uppercase tracked label, the accent notice, and the trace's inline
 * renderer. Every class string here is the prototype's.
 */

import type { ReactNode } from "react";

import { STATUS_TEXT, StatusDot, type DotStatus } from "./StatusDot.tsx";

/** `loop:` + value in mono on the raised surface, with the state's dot. */
export function PhaseChip({ phase, status }: { phase: string; status: DotStatus }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-md border border-border bg-surface-2 px-2 py-0.5 font-mono text-[0.7rem] ${STATUS_TEXT[status]}`}
    >
      <StatusDot status={status} />
      <span className="text-muted-foreground">loop:</span>
      <span className="text-foreground">{phase}</span>
    </span>
  );
}

interface IconButtonProps {
  label: string;
  children: ReactNode;
  active?: boolean;
  disabled?: boolean;
  onClick?: (() => void) | undefined;
  /** Render as a link instead of a button (the footer's Settings, the header's GitHub). */
  href?: string | undefined;
  external?: boolean;
  className?: string | undefined;
}

/** The 28 px square icon control: transparent until hovered, named by `aria-label`. */
export function IconButton({ label, children, active = false, disabled = false, onClick, href, external = false, className = "" }: IconButtonProps) {
  const classes = `inline-flex h-7 w-7 items-center justify-center rounded-md border border-transparent text-muted-foreground transition-colors hover:border-border hover:bg-surface-2 hover:text-foreground disabled:opacity-40 disabled:hover:border-transparent disabled:hover:bg-transparent ${
    active ? "border-border bg-surface-2 text-foreground" : ""
  } ${className}`.trim();
  if (href !== undefined) {
    return (
      <a
        href={href}
        aria-label={label}
        title={label}
        className={classes}
        aria-current={active ? "page" : undefined}
        {...(external ? { target: "_blank", rel: "noreferrer" } : {})}
      >
        {children}
      </a>
    );
  }
  return (
    <button type="button" aria-label={label} title={label} className={classes} disabled={disabled} onClick={onClick}>
      {children}
    </button>
  );
}

/** The uppercase, tracked, muted label every group and section is headed by. */
export function Kicker({ children, className = "" }: { children: ReactNode; className?: string | undefined }) {
  return (
    <span className={`text-[0.68rem] font-medium uppercase tracking-widest text-muted-foreground ${className}`.trim()}>
      {children}
    </span>
  );
}

/** A titled block of the session panel (and of Settings / Standing): hairline above, kicker, rows. */
export function Section({
  title,
  children,
  actions,
  className = "",
}: {
  title: ReactNode;
  children: ReactNode;
  actions?: ReactNode;
  className?: string | undefined;
}) {
  return (
    <section className={`border-t border-border px-4 py-3 ${className}`.trim()}>
      <div className="flex items-center justify-between pb-2">
        <Kicker>{title}</Kicker>
        {actions}
      </div>
      <div className="space-y-1.5">{children}</div>
    </section>
  );
}

/** One key/value line: a fixed-width muted key, the value in mono when it is an identifier. */
export function KV({
  k,
  v,
  mono = true,
  title,
  children,
}: {
  k: string;
  v?: ReactNode;
  mono?: boolean;
  title?: string | undefined;
  children?: ReactNode;
}) {
  return (
    <div className="flex items-baseline gap-3 text-xs">
      <span className="w-20 shrink-0 text-muted-foreground">{k}</span>
      <span
        className={`min-w-0 flex-1 break-all text-foreground/90 ${mono ? "font-mono text-[0.7rem] leading-relaxed" : "break-words"}`.trim()}
        title={title}
      >
        {children ?? v}
      </span>
    </div>
  );
}

/** The accent notice — "needs a human": a warm tint, a hairline, the alert glyph. */
export function Notice({
  children,
  tone = "accent",
  role,
  className = "",
  icon,
}: {
  children: ReactNode;
  tone?: "accent" | "blocked" | "muted";
  role?: "alert" | "status" | undefined;
  className?: string | undefined;
  icon?: ReactNode;
}) {
  const tones = {
    accent: "border-border bg-accent text-accent-foreground",
    blocked: "border-state-blocked/40 bg-surface text-state-blocked",
    muted: "border-border bg-surface text-muted-foreground",
  };
  return (
    <div role={role} className={`flex gap-2 rounded-lg border px-3 py-2 text-xs ${tones[tone]} ${className}`.trim()}>
      {icon}
      <div className="min-w-0 flex-1 space-y-1">{children}</div>
    </div>
  );
}

/** The prototype's control button: mono, hairline, fills on hover. */
export function ControlButton({
  children,
  onClick,
  disabled = false,
  title,
  className = "",
  primary = false,
  type = "button",
}: {
  children: ReactNode;
  onClick?: (() => void) | undefined;
  disabled?: boolean;
  title?: string | undefined;
  className?: string | undefined;
  primary?: boolean;
  type?: "button" | "submit";
}) {
  return (
    <button
      type={type}
      title={title}
      disabled={disabled}
      onClick={onClick}
      className={`rounded-md border px-2 py-1.5 font-mono text-[0.7rem] transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
        primary
          ? "border-primary/50 bg-primary text-primary-foreground hover:opacity-90"
          : "border-border text-muted-foreground hover:bg-surface-2 hover:text-foreground"
      } ${className}`.trim()}
    >
      {children}
    </button>
  );
}

/** The design's text input: transparent on the surface, hairline, no ring. */
export const INPUT_CLASS =
  "w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground outline-none placeholder:text-muted-foreground focus:border-border-strong disabled:opacity-50";

/**
 * The trace's inline renderer: `**x**` → strong, `` `x` `` → a ref chip. Both
 * elements receive **strings** as children, so a payload that looks like markup
 * stays text — React escapes it (issue-327, abuse case 1).
 */
export function renderInline(text: string): ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/);
  return parts
    .filter((part) => part !== "")
    .map((part, index) => {
      if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
        return (
          <strong key={index} className="font-semibold">
            {part.slice(2, -2)}
          </strong>
        );
      }
      if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
        return (
          <code key={index} className="ref-chip">
            {part.slice(1, -1)}
          </code>
        );
      }
      return <span key={index}>{part}</span>;
    });
}

/** The muted empty/loading sentence, centred in its column. */
export function Empty({ children, className = "" }: { children: ReactNode; className?: string | undefined }) {
  return <p className={`py-6 text-center text-sm text-muted-foreground ${className}`.trim()}>{children}</p>;
}

/** A settings / standing card: the surface, a hairline, the design's radius. */
export function Card({ children, className = "", ...rest }: { children: ReactNode; className?: string | undefined; [key: string]: unknown }) {
  return (
    <section className={`space-y-3 rounded-lg border border-border bg-surface px-4 py-3 ${className}`.trim()} {...rest}>
      {children}
    </section>
  );
}

/** A form field's label line. */
export function FieldLabel({ htmlFor, children, className = "" }: { htmlFor?: string | undefined; children: ReactNode; className?: string | undefined }) {
  return (
    <label htmlFor={htmlFor} className={`block text-xs text-muted-foreground ${className}`.trim()}>
      {children}
    </label>
  );
}

/** The "Learn more" disclosure under a card, in the muted register. */
export function LearnMore({ children, summary = "Learn more" }: { children: ReactNode; summary?: string }) {
  return (
    <details className="group text-xs text-muted-foreground">
      <summary className="inline-flex items-center gap-1 rounded-md py-0.5 transition-colors hover:text-foreground">
        <span className="inline-block transition-transform group-open:rotate-90">›</span>
        {summary}
      </summary>
      <div className="mt-1.5 space-y-1.5 leading-relaxed">{children}</div>
    </details>
  );
}

/** An outcome line under a control: ok in green, a refusal in red, otherwise muted. */
export function Report({ tone = "muted", children, role }: { tone?: "ok" | "fail" | "muted"; children: ReactNode; role?: "alert" | "status" | undefined }) {
  const colour = tone === "ok" ? "text-state-done" : tone === "fail" ? "text-state-blocked" : "text-muted-foreground";
  return (
    <p role={role} className={`text-xs leading-relaxed ${colour}`}>
      {children}
    </p>
  );
}
