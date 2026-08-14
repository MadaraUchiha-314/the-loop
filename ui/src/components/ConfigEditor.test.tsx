/**
 * The config editor, rendered (issue-222).
 *
 * Four claims are worth a test: the sections mirror the schema, an unset field offers its
 * default without adopting it, a subtree with no typed control is still editable, and Save
 * sends the diff rather than the document.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ConfigEditor } from "./ConfigEditor.tsx";
import { DEMO_CONFIG, DEMO_CONFIG_SCHEMA } from "../demo/fixture.ts";
import type { ConfigSaveResult, RestartSchedule } from "../api/types.ts";

function renderEditor(
  save?: (patch: Record<string, unknown>) => Promise<ConfigSaveResult>,
  restart?: () => Promise<RestartSchedule>,
) {
  const onSave =
    save ??
    vi.fn(
      (patch: Record<string, unknown>): Promise<ConfigSaveResult> =>
        Promise.resolve({
          ...DEMO_CONFIG,
          changed: Object.keys(patch),
          restartRequired: [],
          written: true,
        }),
    );
  render(
    <ConfigEditor
      document={DEMO_CONFIG}
      schema={DEMO_CONFIG_SCHEMA}
      onSave={onSave}
      {...(restart ? { onRestart: restart } : {})}
    />,
  );
  return onSave;
}

describe("the CLI config editor", () => {
  it("renders one section per top-level property, with the schema's prose", () => {
    renderEditor();
    expect(screen.getByText("routing")).toBeInTheDocument();
    expect(screen.getByText("polling")).toBeInTheDocument();
    expect(screen.getByText(/who may drive the loop/)).toBeInTheDocument();
  });

  it("labels every control with its key path, so a field is findable by name", () => {
    renderEditor();
    expect(screen.getByLabelText("routing.enabled")).toBeInTheDocument();
    expect(screen.getByLabelText("routing.defaultHarness")).toBeInTheDocument();
    expect(screen.getByLabelText("polling.sources")).toBeInTheDocument();
  });

  it("says where the file is", () => {
    renderEditor();
    expect(screen.getByText("~/.the-loop/cli-config.yaml")).toBeInTheDocument();
  });

  it("offers an unset field's default as a placeholder rather than adopting it", () => {
    renderEditor();
    const path = screen.getByLabelText("eventLog.path");
    expect(path).toHaveValue(".the-loop/logs/events.jsonl"); // this one IS set
    const sources = screen.getByLabelText("polling.sources");
    expect(sources).toHaveValue("[]");
    expect(screen.getByText("no changes")).toBeInTheDocument(); // nothing was adopted
  });

  it("keeps a subtree with no typed control editable, as JSON", async () => {
    const onSave = renderEditor();
    // Typed through `paste` rather than `type`: user-event reads `{` as the start of a
    // key descriptor, and JSON is mostly braces.
    const sources = screen.getByLabelText("polling.sources");
    await userEvent.clear(sources);
    await userEvent.click(sources);
    await userEvent.paste('[{"provider": "github"}]');

    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => {
      expect(onSave).toHaveBeenCalledWith({ polling: { sources: [{ provider: "github" }] } });
    });
  });

  it("refuses to save JSON that does not parse, and says why", async () => {
    const onSave = renderEditor();
    const sources = screen.getByLabelText("polling.sources");
    await userEvent.clear(sources);
    await userEvent.click(sources);
    await userEvent.paste("[{");

    expect(screen.getByText(/not valid JSON/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
    expect(onSave).not.toHaveBeenCalled();
  });

  it("sends only what changed", async () => {
    const onSave = renderEditor();
    await userEvent.click(screen.getByLabelText("routing.enabled")); // true -> false
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => {
      expect(onSave).toHaveBeenCalledWith({ routing: { enabled: false } });
    });
  });

  it("reports what was saved, and what waits for a restart", async () => {
    renderEditor(() =>
      Promise.resolve({
        ...DEMO_CONFIG,
        changed: ["service.port"],
        restartRequired: ["service.port"],
        written: true,
      }),
    );
    await userEvent.click(screen.getByLabelText("routing.enabled"));
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText(/service\.port takes effect when the service restarts/)).toBeInTheDocument();
  });

  it("offers Restart now when a saved key waits for one, and reports the schedule", async () => {
    const restart = vi.fn(
      (): Promise<RestartSchedule> =>
        Promise.resolve({ scheduled: true, pid: 99, withUpgrade: false, logfile: "logs/restart.out" }),
    );
    renderEditor(
      () =>
        Promise.resolve({
          ...DEMO_CONFIG,
          changed: ["service.port"],
          restartRequired: ["service.port"],
          written: true,
        }),
      restart,
    );
    await userEvent.click(screen.getByLabelText("routing.enabled"));
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await userEvent.click(await screen.findByRole("button", { name: "Restart now" }));
    expect(restart).toHaveBeenCalledTimes(1);
    expect(await screen.findByText(/Restart scheduled/)).toBeInTheDocument();
  });

  it("keeps the report button-free when nothing waits for a restart", async () => {
    const restart = vi.fn(
      (): Promise<RestartSchedule> =>
        Promise.resolve({ scheduled: true, pid: 99, withUpgrade: false, logfile: "logs/restart.out" }),
    );
    renderEditor(undefined, restart);
    await userEvent.click(screen.getByLabelText("routing.enabled"));
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText(/Live now/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Restart now" })).not.toBeInTheDocument();
  });

  it("shows the service's refusal instead of pretending the save landed", async () => {
    renderEditor(() => Promise.reject(new Error("routing.nope: unknown key")));
    await userEvent.click(screen.getByLabelText("routing.enabled"));
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText(/unknown key/)).toBeInTheDocument();
  });

  it("settles after a save instead of still reporting the change it just made", async () => {
    renderEditor();
    await userEvent.click(screen.getByLabelText("routing.enabled"));
    expect(screen.getByText("1 section changed")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => {
      expect(screen.getByText("no changes")).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
  });

  it("cannot save when nothing changed", () => {
    renderEditor();
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
  });
});
