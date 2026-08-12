/**
 * The frame every card, figure and primary button wears in the Industry system:
 * square, hairline-bordered, with `+` registration marks at the four corners.
 *
 * The marks are four `<i class="corner …">` children the stylesheet draws
 * outside the box — the readme is explicit that a framed element never drops
 * them, so they are baked in here rather than left to each call site to repeat.
 */

import type { ElementType, ReactNode } from "react";

export function Corners() {
  return (
    <>
      <i className="corner tl" />
      <i className="corner tr" />
      <i className="corner bl" />
      <i className="corner br" />
    </>
  );
}

interface BlueprintProps {
  as?: ElementType;
  className?: string;
  children: ReactNode;
  [key: string]: unknown;
}

export function Blueprint({ as: Tag = "div", className = "", children, ...rest }: BlueprintProps) {
  return (
    <Tag className={`blueprint ${className}`.trim()} {...rest}>
      <Corners />
      {children}
    </Tag>
  );
}
