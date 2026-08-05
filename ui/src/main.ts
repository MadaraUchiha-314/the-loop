// the-loop's control-plane UI (issue-161 R6): three views over /api/v1 —
// work items in flight, one item's graph state + session controls, and the
// needs-attention list. Vanilla TypeScript on Vite (decision-058); the visual
// contract is docs/specs/issue-161/design/control-plane.html.

import "./style.css";
import {
  api,
  apiBase,
  getToken,
  setToken,
  type AttentionItem,
  type SessionInfo,
  type WorkItemRecord,
} from "./api";

const app = document.getElementById("app")!;

type View =
  | { name: "items" }
  | { name: "attention" }
  | { name: "detail"; ref: string };

let view: View = { name: "items" };

function esc(text: string): string {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function chip(text: string, kind = ""): string {
  return `<span class="chip ${kind}">${esc(text)}</span>`;
}

function shell(content: string): void {
  app.innerHTML = `
    <header>
      <h1>the-loop · control plane</h1>
      <span class="api">
        API <input id="api-base" size="20" value="${esc(apiBase())}" />
        token <input id="api-token" type="password" size="10" value="${esc(getToken())}" />
      </span>
    </header>
    <nav>
      <button id="nav-items" class="${view.name === "items" || view.name === "detail" ? "active" : ""}">Work items</button>
      <button id="nav-attention" class="${view.name === "attention" ? "active" : ""}">Needs attention</button>
    </nav>
    <main>${content}</main>`;
  document.getElementById("nav-items")!.addEventListener("click", () => {
    view = { name: "items" };
    void render();
  });
  document.getElementById("nav-attention")!.addEventListener("click", () => {
    view = { name: "attention" };
    void render();
  });
  const tokenInput = document.getElementById("api-token") as HTMLInputElement;
  tokenInput.addEventListener("change", () => {
    setToken(tokenInput.value.trim());
    void render();
  });
  const baseInput = document.getElementById("api-base") as HTMLInputElement;
  baseInput.addEventListener("change", () => {
    localStorage.setItem("the-loop:apiBase", baseInput.value.trim());
    void render();
  });
}

function errorBox(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error);
  return `<div class="error">Cannot reach the control plane: ${esc(message)}.
    Check the API base, the bearer token
    (<code>&lt;state.root&gt;/local/service.token</code> on the service's
    machine), and that <code>the-loop service start</code> has run.</div>`;
}

async function render(): Promise<void> {
  try {
    if (view.name === "items") await renderItems();
    else if (view.name === "attention") await renderAttention();
    else await renderDetail(view.ref);
  } catch (error) {
    shell(errorBox(error));
  }
}

async function renderItems(): Promise<void> {
  const [items, sessions, attention] = await Promise.all([
    api.workItems(),
    api.sessions(),
    api.attention(),
  ]);
  const sessionBy = new Map<string, SessionInfo>(
    sessions.map((s) => [s.workItem, s]),
  );
  const flagged = new Set(attention.map((a) => a.workItem));
  const cards = items.length
    ? items
        .map((item: WorkItemRecord) => {
          const session = sessionBy.get(item.ref);
          return `
      <div class="card ${flagged.has(item.ref) ? "attn" : ""}" data-ref="${esc(item.ref)}">
        <h3>${esc(item.ref)}</h3>
        <div class="ref">${item.url ? `<a href="${esc(item.url)}" target="_blank" rel="noreferrer">${esc(item.url)}</a>` : ""}</div>
        ${chip(`session: ${session?.status ?? "none"}`, session?.status === "active" ? "ok" : "")}
        ${item.control?.command ? chip(`control: ${item.control.command}`, "phase") : ""}
        ${flagged.has(item.ref) ? chip("needs attention", "wait") : ""}
      </div>`;
        })
        .join("")
    : `<p class="note">No work items on this machine yet — records appear when
       the poller or webhook receiver sees one.</p>`;
  shell(`<div class="grid">${cards}</div>`);
  for (const card of app.querySelectorAll<HTMLElement>(".card[data-ref]")) {
    card.addEventListener("click", () => {
      view = { name: "detail", ref: card.dataset.ref! };
      void render();
    });
  }
}

async function renderAttention(): Promise<void> {
  const items = await api.attention();
  const rows = items.length
    ? items
        .map(
          (item: AttentionItem) => `
      <tr><td>${esc(item.workItem || "—")}</td>
          <td>${chip(item.kind, "wait")}</td>
          <td>${esc(item.detail)}</td></tr>`,
        )
        .join("")
    : `<tr><td colspan="3" class="note">Nothing needs attention.</td></tr>`;
  shell(
    `<table><tr><th>Work item</th><th>Kind</th><th>Detail</th></tr>${rows}</table>`,
  );
}

async function renderDetail(ref: string): Promise<void> {
  const [sessions, events] = await Promise.all([api.sessions(), api.events(20)]);
  const session = sessions.find((s) => s.workItem === ref);
  const related = events.filter((e) => (e.work_item ?? "") === ref);
  const eventLines = related.length
    ? related
        .map((e) => `${e.ts ?? "-"}  ${e.event ?? "-"}  ${e.level ?? "-"}`)
        .join("\n")
    : "no recent events for this work item";

  shell(`
    <button class="back" id="back">← all work items</button>
    <h2 style="margin:0 0 2px">${esc(ref)}</h2>
    <div class="ref">${session ? chip(`session: ${session.status}`, "ok") + chip(session.harness, "phase") : chip("no session on this machine", "")}</div>
    <div class="controls">
      ${["start", "pause", "resume", "stop"].map((verb) => `<button data-verb="${verb}">${verb}</button>`).join("")}
    </div>
    <div id="verb-result"></div>
    <div class="events">${esc(eventLines)}</div>
    <p class="note">Graph state is repo-scoped: POST /api/v1/graph/check with a
    repo path on the service's machine returns the full node report.</p>`);
  document.getElementById("back")!.addEventListener("click", () => {
    view = { name: "items" };
    void render();
  });
  for (const button of app.querySelectorAll<HTMLElement>("[data-verb]")) {
    button.addEventListener("click", () => {
      void (async () => {
        const box = document.getElementById("verb-result")!;
        try {
          const result = await api.controlSession(ref, button.dataset.verb!);
          box.innerHTML = `<div class="events">${esc(result.output || `exit ${result.exitCode}`)}</div>`;
        } catch (error) {
          box.innerHTML = errorBox(error);
        }
      })();
    });
  }
}

void render();
