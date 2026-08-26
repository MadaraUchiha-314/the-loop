/**
 * A plain framed container: the Classical system's bordered, unfilled surface
 * (issue-298) — a quiet hairline box, drawn with the divider token rather than
 * a fill. The component keeps its Industry-era name and prop shape so the call
 * sites that predate the redesigns read unchanged.
 */

import type { ElementType, ReactNode } from "react";

interface BlueprintProps {
  as?: ElementType;
  className?: string;
  children: ReactNode;
  [key: string]: unknown;
}

export function Blueprint({ as: Tag = "div", className = "", children, ...rest }: BlueprintProps) {
  return (
    <Tag className={`lp-card ${className}`.trim()} {...rest}>
      {children}
    </Tag>
  );
}
