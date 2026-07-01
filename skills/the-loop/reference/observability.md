# Observability reference

Config: `observability` in `.the-loop/config.yaml`.

## Core rule: dev-time == run-time

Logging and observability for debugging MUST be **EXACTLY the same** during development
and at runtime (when the system is actually running). The ONLY advantage at dev-time is
that you can set **breakpoints** and inspect variable values. Do not add log statements
or instrumentation that exist only in dev — that defeats the purpose.

## Configurable levels

There are different, configurable levels of observability:
- **Dev-time** (`observability.devLevel`, default `debug`): all `debug` logs and above
  are accessible.
- **Run-time** (`observability.runtimeLevel`, default `info`): all `info` logs and above
  are available.

Use the same logger and the same log lines in both; only the active level differs.

## Observing services

- **Locally running services**: prefer **file-system based logging** that the agent
  harness can read directly (tail/grep the log files).
- **Browser-based logging**: surface browser console/network logs to the harness via
  `observability.browserLogging` (default `chrome-devtools-mcp` — the Chrome DevTools
  MCP server).
  - _Open question:_ confirm chrome-devtools MCP is the right mechanism for browser
    logging, and document the setup. Record a decision once validated.
