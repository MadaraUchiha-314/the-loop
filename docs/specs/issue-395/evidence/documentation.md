---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#395"
---

# Documentation: the hosted ingress set follows the config (issue-395)

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| `docs/capabilities/control-plane.md` | the hosted-ingress requirement gains the reconcile (what stops, what starts, the events, membership-only, `hostIngresses` stays boot-only); the hot-reload requirement says which ingresses are hosted is not boot-only either and what `status` prints instead of `running … [disabled]` | issue-395 row added |
| `docs/capabilities/channels.md` | the "service hosts the listener" bullet gains: `read.mode` leaving `socket` stops the hosted listener within the config check, coming back starts one with the edited config; the B5/B3 consequence; a running listener's own config stays frozen | issue-395 row added |

## Documentation

| Document | What changed |
|----------|--------------|
| `docs/cli/service.md` | the hot-reload paragraph: the hosted set follows the file too, `read.mode: off` closes the Socket Mode connection with no restart |
| `docs/guide/slack.md` | the hosting paragraph: setting `read.mode` off `socket` stops the hosted listener within seconds — the way to take one of two instances off a shared app |
| `docs/config/cli/channels-options.md` | `slack.read.mode`: a change takes effect in the running service without a restart |
| `docs/reports/followups/README.md`, `docs/reports/followups/b5-read-mode-hot-reload.md` | link the filed issue and record which of the two suggested fixes landed |
| `cli/the_loop/eventlog.py` (`EVENT_TYPES`) | `ingress.hosted`, `ingress.hosted_stopped`, `config.reloaded` descriptions name the `reason` field and the reconcile — the text `the-loop events --types` prints |
| README / operating-model skill | no change: neither describes the hosting at this level |
