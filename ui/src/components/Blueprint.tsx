/**
 * A plain framed container. The Industry system's `+` corner registration
 * marks and all-caps blueprint styling were retired in the issue-283 calm-down
 * (bloat #5): the data — refs, rails, dots — provides the texture, so cards
 * are quiet hairline boxes. The component keeps its name and prop shape so the
 * call sites that predate the change read unchanged.
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
