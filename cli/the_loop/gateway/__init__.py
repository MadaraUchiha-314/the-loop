"""the-loop gateway — one ingress process, many polling instances (issue-496).

The gateway owns every inbound transport (GitHub and Jira webhooks, Slack Socket Mode
and HTTP routes, the pollers), stores each event on a per-work-item **subject** before
acknowledging the provider, and fans it out on write to the queue of every instance
that consumes that subject. Instances poll their own queue (``gateway/client.py``) and
commit what they handled; the gateway never reaches an instance.

Modules, in the order an event crosses them:

- :mod:`.config` — ``gateway-config.yaml``, validated against the fourth shipped schema;
- :mod:`.envelope` — the stored event's shape and the event-log families;
- :mod:`.store` — the SQLite queue behind the ``Store`` protocol;
- :mod:`.routing` — which instances consume a subject, decided at ingest;
- :mod:`.adapters` — one ingress per provider transport;
- :mod:`.consume` — the pull API (fetch and commit, claims, actors, bindings);
- :mod:`.client` — the instance's hosted ingress, a polling loop;
- :mod:`.ingresses`, :mod:`.serve` — the process.

The design is ``docs/specs/issue-496/design.md``.
"""
