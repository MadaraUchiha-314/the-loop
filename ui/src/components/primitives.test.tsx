import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { renderInline } from "./primitives.tsx";

describe("renderInline", () => {
  it("turns **bold** into strong and `code` into a ref chip, as text", () => {
    render(<p>{renderInline("PR **#326** passed `gate` and `ui`.")}</p>);
    expect(screen.getByText("#326").tagName).toBe("STRONG");
    expect(screen.getByText("gate").tagName).toBe("CODE");
    expect(screen.getByText("gate").className).toBe("ref-chip");
    expect(screen.getByText("ui").tagName).toBe("CODE");
  });

  it("renders attacker-shaped text as text — no element is created from it", () => {
    render(<p>{renderInline('see **<img src=x onerror="alert(1)">** and `<script>alert(2)</script>`')}</p>);
    expect(document.querySelector("img")).toBeNull();
    expect(document.querySelector("script")).toBeNull();
    expect(screen.getByText('<img src=x onerror="alert(1)">').tagName).toBe("STRONG");
    expect(screen.getByText("<script>alert(2)</script>").tagName).toBe("CODE");
  });

  it("leaves unmatched markers alone", () => {
    render(<p>{renderInline("a ** lone marker and ` a stray tick")}</p>);
    expect(screen.getByText("a ** lone marker and ` a stray tick")).toBeInTheDocument();
  });
});
