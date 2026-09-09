import { describe, expect, it } from "vitest";

import { applyTheme, otherTheme, resolveTheme } from "./theme.ts";

describe("resolveTheme", () => {
  it("follows the browser when nothing was chosen", () => {
    expect(resolveTheme(undefined, true)).toBe("dark");
    expect(resolveTheme(undefined, false)).toBe("light");
  });

  it("prefers the operator's choice over the browser", () => {
    expect(resolveTheme("light", true)).toBe("light");
    expect(resolveTheme("dark", false)).toBe("dark");
  });

  it("flips between the two", () => {
    expect(otherTheme("dark")).toBe("light");
    expect(otherTheme("light")).toBe("dark");
  });
});

describe("applyTheme", () => {
  it("keys the stylesheet on a `dark` class and sets color-scheme", () => {
    const root = document.createElement("html");
    applyTheme("dark", root);
    expect(root.classList.contains("dark")).toBe(true);
    expect(root.style.colorScheme).toBe("dark");
    applyTheme("light", root);
    expect(root.classList.contains("dark")).toBe(false);
    expect(root.style.colorScheme).toBe("light");
  });
});
