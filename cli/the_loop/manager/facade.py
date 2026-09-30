"""The manager's facade: the same surface, over its own core plus the fleet (issue-374).

The router calls one method per operation on whichever facade ``create_app`` picked
(decision-138 D3). This is the manager's. Every method is one of four shapes — the
design's § 4 table, row by row:

* **fan-out**: a list read is the manager's own rows (through the worker's
  :class:`~the_loop.api.facade.CoreFacade`, R1.3) followed by every live member's,
  each row stamped ``instance`` with the *registered* name (R2.2, R6.3); a member
  that could not answer is named in ``The-Loop-Instances-Unreachable`` (R2.9).
* **by ref / by standing name**: routed to the one instance that manages the key
  (R2.3); none is 404, several is 409 unless ``instance`` names one (R2.4).
* **by instance**: an operation keyed by a checkout path or a daemon acts on the
  manager's own machine unless ``instance`` names a member (R2.5) — the worker
  behaviour, so a client that never learned the parameter is unchanged.
* **self-or-instance**: ``health``, ``instance``, ``config``, ``restart`` are the
  manager's own without ``instance`` and proxied with it (R2.7) — how one instance is
  managed individually.

Nothing here keeps a copy of any member's records; every answer is read on the
request that needs it, through :class:`~the_loop.manager.fleet.Fleet`.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from ..api.facade import CoreFacade, note_left_out
from ..cli_config import ConfigHolder
from ..core import instances as core_instances
from ..instance import Member
from .fleet import Fleet, Transport, urllib_transport
from .stream import urllib_opener

__all__ = ["ManagerFacade"]


def _stamp(rows: Any, name: str) -> Any:
    """``instance`` on every row (overwriting one a member sent, R6.3)."""
    if isinstance(rows, dict):
        rows["instance"] = name
        return rows
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict):
                row["instance"] = name
        return rows
    return rows


class ManagerFacade:
    role = "manager"

    def __init__(
        self,
        holder: ConfigHolder,
        core: CoreFacade,
        *,
        transport: Transport = urllib_transport,
        opener: Any = None,
    ) -> None:
        self.holder = holder
        self.core = core
        self._broker: Any = None
        self._opener = opener or urllib_opener
        self.fleet = Fleet(
            lambda: holder.current,
            transport=transport,
            local_refs=self._local_refs,
            local_standing=self._local_standing,
        )

    # -- helpers ------------------------------------------------------------------------

    @property
    def own_name(self) -> str:
        return self.fleet.own_name

    def _local_refs(self) -> List[str]:
        doc = self.core.get_instance()
        return [row["ref"] for row in doc.get("managed") or [] if isinstance(row, dict)]

    def _local_standing(self) -> List[str]:
        return [
            str(row.get("name"))
            for row in self.core.list_standing_sessions()
            if isinstance(row, dict)
        ]

    def _union(
        self,
        operation: str,
        path: str,
        local: Callable[[], List[Dict[str, Any]]],
        *,
        query: Optional[Mapping[str, Any]] = None,
        sort_key: Optional[Callable[[Dict[str, Any]], Any]] = None,
    ) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = _stamp(list(local()), self.own_name)
        answers, left_out = self.fleet.fan_out(
            "GET", path, query=query, expect=list, operation=operation
        )
        for member in self.fleet.members():
            answer = answers.get(member.name)
            if answer is None:
                continue
            rows.extend(_stamp([r for r in answer if isinstance(r, dict)], member.name))
        note_left_out(left_out)
        if sort_key is not None:
            rows.sort(key=sort_key)
        return rows

    def _proxy(
        self,
        member: Member,
        method: str,
        path: str,
        *,
        query: Optional[Mapping[str, Any]] = None,
        body: Optional[Mapping[str, Any]] = None,
        expect: type = dict,
        operation: str = "",
    ) -> Any:
        answer = self.fleet.call(
            member,
            method,
            path,
            query=query,
            body=body,
            expect=expect,
            operation=operation or path,
        )
        return _stamp(answer, member.name)

    def _target(self, instance: str) -> Member:
        return self.fleet.by_instance(instance)

    # -- identity and health --------------------------------------------------------------

    def health(self, instance: str = "") -> Dict[str, Any]:
        member = self._target(instance)
        if not self.fleet.is_local(member):
            return self._proxy(member, "GET", "/api/v1/health", operation="health")
        doc = self.core.health()
        probes = self.fleet.probes()
        rows = [
            {
                "name": probe.member.name,
                "url": probe.member.url,
                "state": probe.state,
                "detail": probe.detail,
            }
            for probe in probes
        ]
        # `ok` only while every own ingress holds its lock AND every member is live
        # (R2.9); the status CODE stays 200 for the reason the worker's does.
        if any(not probe.live for probe in probes):
            doc["status"] = "degraded"
        doc["role"] = "manager"
        doc["instances"] = rows
        return doc

    def get_instance(self, instance: str = "") -> Dict[str, Any]:
        member = self._target(instance)
        if not self.fleet.is_local(member):
            return self._proxy(member, "GET", "/api/v1/instance", operation="instance")
        doc = self.core.get_instance()
        managed: List[Dict[str, Any]] = _stamp(
            list(doc.get("managed") or []), self.own_name
        )
        for probe in self.fleet.live():
            rows = [
                dict(row)
                for row in (probe.document or {}).get("managed") or []
                if isinstance(row, dict)
            ]
            managed.extend(_stamp(rows, probe.member.name))
        managed.sort(
            key=lambda row: (str(row.get("ref", "")), str(row.get("instance", "")))
        )
        doc["managed"] = managed
        return doc

    def list_instances(self) -> Dict[str, Any]:
        return core_instances.list_instances(self.holder.current, fleet=self.fleet)

    def register_instance(self, name: str, url: str) -> Dict[str, Any]:
        return self.core.register_instance(name, url)

    def unregister_instance(self, name: str) -> Dict[str, Any]:
        return self.core.unregister_instance(name)

    # -- list reads -----------------------------------------------------------------------------

    def list_work_items(self) -> List[Dict[str, Any]]:
        return self._union(
            "listWorkItems",
            "/api/v1/work-items",
            self.core.list_work_items,
            sort_key=lambda row: (
                str(row.get("ref", "")),
                str(row.get("instance", "")),
            ),
        )

    def list_sessions(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        return self._union(
            "listSessions",
            "/api/v1/sessions",
            lambda: self.core.list_sessions(status=status),
            query={"status": status},
        )

    def list_standing_sessions(self) -> List[Dict[str, Any]]:
        return self._union(
            "listStandingSessions",
            "/api/v1/standing-sessions",
            self.core.list_standing_sessions,
        )

    def list_attention(self) -> List[Dict[str, Any]]:
        return self._union(
            "listAttention", "/api/v1/attention", self.core.list_attention
        )

    def list_daemons(self) -> List[Dict[str, Any]]:
        return self._union("listDaemons", "/api/v1/daemons", self.core.list_daemons)

    def query_events(
        self,
        types: Sequence[str] = (),
        work_item: Optional[str] = None,
        delivery_id: Optional[str] = None,
        source: Optional[str] = None,
        min_level: Optional[str] = None,
        since: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        query = {
            "type": list(types),
            "workItem": work_item,
            "deliveryId": delivery_id,
            "source": source,
            "level": min_level,
            "since": since,
            "limit": limit,
        }
        rows = self._union(
            "queryEvents",
            "/api/v1/events",
            lambda: self.core.query_events(
                types=types,
                work_item=work_item,
                delivery_id=delivery_id,
                source=source,
                min_level=min_level,
                since=since,
                limit=limit,
            ),
            query=query,
            # Merged by timestamp, stable by instance (R2.2); the limit is applied
            # after the merge so the newest across the fleet win.
            sort_key=lambda row: (str(row.get("ts", "")), str(row.get("instance", ""))),
        )
        if limit and len(rows) > limit:
            rows = rows[-limit:]
        return rows

    def event_types(self) -> Dict[str, str]:
        merged = dict(self.core.event_types())
        answers, _ = self.fleet.fan_out(
            "GET", "/api/v1/events/types", expect=dict, operation="eventTypes"
        )
        for answer in answers.values():
            for key, value in answer.items():
                merged.setdefault(str(key), str(value))
        return merged

    # -- keyed by ref -------------------------------------------------------------------------------

    def get_work_item(self, ref: str, instance: str = "") -> Dict[str, Any]:
        member = self.fleet.by_ref(ref, instance)
        if self.fleet.is_local(member):
            return _stamp(self.core.get_work_item(ref), self.own_name)
        return self._proxy(member, "GET", "/api/v1/work-items/one", query={"ref": ref})

    def get_session(self, ref: str, instance: str = "") -> Dict[str, Any]:
        member = self.fleet.by_ref(ref, instance)
        if self.fleet.is_local(member):
            return _stamp(self.core.get_session(ref), self.own_name)
        return self._proxy(member, "GET", "/api/v1/sessions/one", query={"ref": ref})

    def session_transcript(
        self, ref: str, tail: int = 200, instance: str = ""
    ) -> Dict[str, Any]:
        member = self.fleet.by_ref(ref, instance)
        if self.fleet.is_local(member):
            return _stamp(self.core.session_transcript(ref, tail=tail), self.own_name)
        return self._proxy(
            member,
            "GET",
            "/api/v1/sessions/transcript",
            query={"ref": ref, "tail": tail},
        )

    def control_session(
        self, ref: str, verb: str, comment: bool = True, instance: str = ""
    ) -> Dict[str, Any]:
        member = self.fleet.by_ref(ref, instance)
        if self.fleet.is_local(member):
            return _stamp(
                self.core.control_session(ref, verb, comment=comment), self.own_name
            )
        return self._proxy(
            member,
            "POST",
            "/api/v1/sessions/control",
            body={"ref": ref, "verb": verb, "comment": comment},
        )

    def reply_session(
        self,
        ref: str,
        text: str,
        actor: str = "",
        comment: bool = True,
        instance: str = "",
    ) -> Dict[str, Any]:
        member = self.fleet.by_ref(ref, instance)
        if self.fleet.is_local(member):
            return _stamp(
                self.core.reply_session(ref, text, actor=actor, comment=comment),
                self.own_name,
            )
        return self._proxy(
            member,
            "POST",
            "/api/v1/sessions/reply",
            body={"ref": ref, "text": text, "actor": actor, "comment": comment},
        )

    def register_session(
        self,
        ref: str,
        harness: str,
        harness_session_id: str,
        cwd: str = ".",
        force: bool = False,
        instance: str = "",
    ) -> Dict[str, Any]:
        # A registration creates the managed-set entry, so nothing can resolve its
        # ref beforehand: `instance` absent registers on the manager itself.
        member = self._target(instance)
        if self.fleet.is_local(member):
            return _stamp(
                self.core.register_session(
                    ref, harness, harness_session_id, cwd=cwd, force=force
                ),
                self.own_name,
            )
        return self._proxy(
            member,
            "POST",
            "/api/v1/sessions/register",
            body={
                "ref": ref,
                "harness": harness,
                "harnessSessionId": harness_session_id,
                "cwd": cwd,
                "force": force,
            },
        )

    def link_session_pull_request(
        self, ref: str, pull_request: str, instance: str = ""
    ) -> Dict[str, Any]:
        member = self.fleet.by_ref(ref, instance)
        if self.fleet.is_local(member):
            return _stamp(
                self.core.link_session_pull_request(ref, pull_request), self.own_name
            )
        return self._proxy(
            member,
            "POST",
            "/api/v1/sessions/link-pr",
            body={"ref": ref, "pullRequest": pull_request},
        )

    def close_session(
        self, ref: str, keep_tmux: Optional[bool] = None, instance: str = ""
    ) -> Dict[str, Any]:
        member = self.fleet.by_ref(ref, instance)
        if self.fleet.is_local(member):
            return _stamp(
                self.core.close_session(ref, keep_tmux=keep_tmux), self.own_name
            )
        return self._proxy(
            member,
            "POST",
            "/api/v1/sessions/close",
            body={"ref": ref, "keepTmux": keep_tmux},
        )

    # -- keyed by standing name ---------------------------------------------------------------

    def get_standing_session(self, name: str, instance: str = "") -> Dict[str, Any]:
        member = self.fleet.by_standing_name(name, instance)
        if self.fleet.is_local(member):
            return _stamp(self.core.get_standing_session(name), self.own_name)
        return self._proxy(
            member, "GET", "/api/v1/standing-sessions/one", query={"name": name}
        )

    def create_standing_session(
        self,
        name: str,
        harness: str = "",
        cwd: str = "",
        prompt: str = "",
        description: str = "",
        harness_args: Optional[List[str]] = None,
        slack_enabled: bool = False,
        slack_channel: str = "",
        auto_start: bool = True,
        start: bool = True,
        instance: str = "",
    ) -> Dict[str, Any]:
        member = self._target(instance)
        if self.fleet.is_local(member):
            return _stamp(
                self.core.create_standing_session(
                    name,
                    harness=harness,
                    cwd=cwd,
                    prompt=prompt,
                    description=description,
                    harness_args=harness_args,
                    slack_enabled=slack_enabled,
                    slack_channel=slack_channel,
                    auto_start=auto_start,
                    start=start,
                ),
                self.own_name,
            )
        return self._proxy(
            member,
            "POST",
            "/api/v1/standing-sessions/create",
            body={
                "name": name,
                "harness": harness,
                "cwd": cwd,
                "prompt": prompt,
                "description": description,
                "harnessArgs": harness_args,
                "slackEnabled": slack_enabled,
                "slackChannel": slack_channel,
                "autoStart": auto_start,
                "start": start,
            },
        )

    def delete_standing_session(self, name: str, instance: str = "") -> Dict[str, Any]:
        member = self.fleet.by_standing_name(name, instance)
        if self.fleet.is_local(member):
            return _stamp(self.core.delete_standing_session(name), self.own_name)
        return self._proxy(
            member, "POST", "/api/v1/standing-sessions/delete", body={"name": name}
        )

    def control_standing_session(
        self, name: str, verb: str, instance: str = ""
    ) -> Dict[str, Any]:
        # An empty name means every session — of the manager's own, or of the
        # member `instance` names; a fleet-wide start/stop is not one operation.
        member = (
            self._target(instance)
            if not name
            else self.fleet.by_standing_name(name, instance)
        )
        if self.fleet.is_local(member):
            return _stamp(self.core.control_standing_session(name, verb), self.own_name)
        return self._proxy(
            member,
            "POST",
            "/api/v1/standing-sessions/control",
            body={"name": name, "verb": verb},
        )

    def say_to_standing_session(
        self, name: str, text: str, actor: str = "", instance: str = ""
    ) -> Dict[str, Any]:
        member = self.fleet.by_standing_name(name, instance)
        if self.fleet.is_local(member):
            return _stamp(
                self.core.say_to_standing_session(name, text, actor=actor),
                self.own_name,
            )
        return self._proxy(
            member,
            "POST",
            "/api/v1/standing-sessions/say",
            body={"name": name, "text": text, "actor": actor},
        )

    # -- keyed by instance (a checkout path, a daemon) --------------------------------------

    def graph_show(
        self,
        repo: str,
        pr: Optional[int] = None,
        pr_repo: str = "",
        spec_dir: str = "",
        instance: str = "",
    ) -> Dict[str, Any]:
        member = self._target(instance)
        if self.fleet.is_local(member):
            return self.core.graph_show(repo, pr=pr, pr_repo=pr_repo, spec_dir=spec_dir)
        return self._proxy(
            member,
            "GET",
            "/api/v1/graph",
            query={"repo": repo, "pr": pr, "prRepo": pr_repo, "specDir": spec_dir},
        )

    def _graph(
        self, verb: str, instance: str, body: Dict[str, Any], local: Callable[[], Any]
    ) -> Any:
        member = self._target(instance)
        if self.fleet.is_local(member):
            return local()
        return self._proxy(member, "POST", f"/api/v1/graph/{verb}", body=body)

    def graph_check(
        self,
        repo: str,
        work_item: str,
        recompute: bool = False,
        pr: Optional[int] = None,
        pr_repo: str = "",
        spec_dir: str = "",
        instance: str = "",
    ) -> Dict[str, Any]:
        return self._graph(
            "check",
            instance,
            {
                "repo": repo,
                "workItem": work_item,
                "recompute": recompute,
                "pr": pr,
                "prRepo": pr_repo,
                "specDir": spec_dir,
            },
            lambda: self.core.graph_check(
                repo,
                work_item,
                recompute=recompute,
                pr=pr,
                pr_repo=pr_repo,
                spec_dir=spec_dir,
            ),
        )

    def graph_complete(
        self,
        repo: str,
        work_item: str,
        node: str = "",
        actor: str = "",
        ref: str = "",
        pr: Optional[int] = None,
        pr_repo: str = "",
        spec_dir: str = "",
        instance: str = "",
    ) -> Dict[str, Any]:
        return self._graph(
            "complete",
            instance,
            {
                "repo": repo,
                "workItem": work_item,
                "node": node,
                "actor": actor,
                "ref": ref,
                "pr": pr,
                "prRepo": pr_repo,
                "specDir": spec_dir,
            },
            lambda: self.core.graph_complete(
                repo,
                work_item,
                node=node,
                actor=actor,
                ref=ref,
                pr=pr,
                pr_repo=pr_repo,
                spec_dir=spec_dir,
            ),
        )

    def graph_advance(
        self,
        repo: str,
        work_item: str,
        ref: str = "",
        pr: Optional[int] = None,
        pr_repo: str = "",
        spec_dir: str = "",
        instance: str = "",
    ) -> Dict[str, Any]:
        return self._graph(
            "advance",
            instance,
            {
                "repo": repo,
                "workItem": work_item,
                "ref": ref,
                "pr": pr,
                "prRepo": pr_repo,
                "specDir": spec_dir,
            },
            lambda: self.core.graph_advance(
                repo, work_item, ref=ref, pr=pr, pr_repo=pr_repo, spec_dir=spec_dir
            ),
        )

    def graph_force(
        self,
        repo: str,
        work_item: str,
        to_node: str,
        reason: str,
        actor: str = "",
        ref: str = "",
        pr: Optional[int] = None,
        pr_repo: str = "",
        spec_dir: str = "",
        instance: str = "",
    ) -> Dict[str, Any]:
        return self._graph(
            "force",
            instance,
            {
                "repo": repo,
                "workItem": work_item,
                "toNode": to_node,
                "reason": reason,
                "actor": actor,
                "ref": ref,
                "pr": pr,
                "prRepo": pr_repo,
                "specDir": spec_dir,
            },
            lambda: self.core.graph_force(
                repo,
                work_item,
                to_node,
                reason,
                actor=actor,
                ref=ref,
                pr=pr,
                pr_repo=pr_repo,
                spec_dir=spec_dir,
            ),
        )

    def graph_skip(
        self,
        repo: str,
        work_item: str,
        nodes: List[str],
        reason: str,
        actor: str = "",
        ref: str = "",
        pr: Optional[int] = None,
        pr_repo: str = "",
        spec_dir: str = "",
        instance: str = "",
    ) -> Dict[str, Any]:
        return self._graph(
            "skip",
            instance,
            {
                "repo": repo,
                "workItem": work_item,
                "nodes": list(nodes),
                "reason": reason,
                "actor": actor,
                "ref": ref,
                "pr": pr,
                "prRepo": pr_repo,
                "specDir": spec_dir,
            },
            lambda: self.core.graph_skip(
                repo,
                work_item,
                nodes,
                reason,
                actor=actor,
                ref=ref,
                pr=pr,
                pr_repo=pr_repo,
                spec_dir=spec_dir,
            ),
        )

    def graph_repos(
        self,
        repo: str,
        work_item: str,
        repositories: Optional[List[str]] = None,
        clear: bool = False,
        ref: str = "",
        pr: Optional[int] = None,
        pr_repo: str = "",
        spec_dir: str = "",
        instance: str = "",
    ) -> Dict[str, Any]:
        return self._graph(
            "repos",
            instance,
            {
                "repo": repo,
                "workItem": work_item,
                "repositories": repositories,
                "clear": clear,
                "ref": ref,
                "pr": pr,
                "prRepo": pr_repo,
                "specDir": spec_dir,
            },
            lambda: self.core.graph_repos(
                repo,
                work_item,
                repositories,
                clear=clear,
                ref=ref,
                pr=pr,
                pr_repo=pr_repo,
                spec_dir=spec_dir,
            ),
        )

    def repo_scenarios(
        self, repo: str, globs: Optional[List[str]] = None, instance: str = ""
    ) -> Dict[str, Any]:
        member = self._target(instance)
        if self.fleet.is_local(member):
            return self.core.repo_scenarios(repo, globs=globs)
        return self._proxy(
            member,
            "GET",
            "/api/v1/repo/scenarios",
            query={"repo": repo, "glob": list(globs or [])},
        )

    def repo_instructions(
        self,
        repo: str,
        docs: Optional[List[str]] = None,
        on_missing: str = "warn",
        instance: str = "",
    ) -> Dict[str, Any]:
        member = self._target(instance)
        if self.fleet.is_local(member):
            return self.core.repo_instructions(repo, docs=docs, on_missing=on_missing)
        return self._proxy(
            member,
            "GET",
            "/api/v1/repo/instructions",
            query={"repo": repo, "doc": list(docs or []), "onMissing": on_missing},
        )

    def repo_critics(self, repo: str, instance: str = "") -> List[Dict[str, Any]]:
        member = self._target(instance)
        if self.fleet.is_local(member):
            return self.core.repo_critics(repo)
        return self._proxy(
            member, "GET", "/api/v1/repo/critics", query={"repo": repo}, expect=list
        )

    def repo_review_policy(self, repo: str, instance: str = "") -> Dict[str, Any]:
        member = self._target(instance)
        if self.fleet.is_local(member):
            return self.core.repo_review_policy(repo)
        return self._proxy(
            member, "GET", "/api/v1/repo/critics/policy", query={"repo": repo}
        )

    def repo_critic_run(
        self,
        repo: str,
        name: str,
        prompt: str = "",
        prompt_file: str = "",
        work_item: str = "",
        spec_dir: str = "",
        timeout: Optional[float] = None,
        cwd: str = "",
        instance: str = "",
    ) -> Dict[str, Any]:
        member = self._target(instance)
        if self.fleet.is_local(member):
            return self.core.repo_critic_run(
                repo,
                name,
                prompt,
                prompt_file,
                work_item=work_item,
                spec_dir=spec_dir,
                timeout=timeout,
                cwd=cwd,
            )
        return self._proxy(
            member,
            "POST",
            "/api/v1/repo/critics/run",
            body={
                "repo": repo,
                "name": name,
                "prompt": prompt,
                "promptFile": prompt_file,
                "workItem": work_item,
                "specDir": spec_dir,
                "timeout": timeout,
                "cwd": cwd,
            },
        )

    def control_daemon(
        self, daemon: str, verb: str, instance: str = ""
    ) -> Dict[str, Any]:
        member = self._target(instance)
        if self.fleet.is_local(member):
            return _stamp(self.core.control_daemon(daemon, verb), self.own_name)
        return self._proxy(
            member,
            "POST",
            "/api/v1/daemons/control",
            body={"daemon": daemon, "verb": verb},
        )

    # -- self-or-instance ---------------------------------------------------------------------

    def get_config(self, instance: str = "") -> Dict[str, Any]:
        member = self._target(instance)
        if self.fleet.is_local(member):
            return self.core.get_config()
        return self._proxy(member, "GET", "/api/v1/config", operation="getConfig")

    def get_config_schema(self, instance: str = "") -> Dict[str, Any]:
        member = self._target(instance)
        if self.fleet.is_local(member):
            return self.core.get_config_schema()
        return self._proxy(
            member, "GET", "/api/v1/config/schema", operation="getConfigSchema"
        )

    def update_config(
        self, patch: Dict[str, Any], instance: str = ""
    ) -> Dict[str, Any]:
        member = self._target(instance)
        if self.fleet.is_local(member):
            return self.core.update_config(patch)
        return self._proxy(
            member,
            "POST",
            "/api/v1/config",
            body={"patch": patch},
            operation="updateConfig",
        )

    def restart(self, with_upgrade: bool = False, instance: str = "") -> Dict[str, Any]:
        member = self._target(instance)
        if self.fleet.is_local(member):
            return self.core.restart(with_upgrade=with_upgrade)
        return self._proxy(
            member,
            "POST",
            "/api/v1/restart",
            body={"withUpgrade": with_upgrade},
            operation="restart",
        )

    # -- the stream (R2.8) ------------------------------------------------------------------

    def stream_broker(self):
        """The fleet broker: the own log plus one upstream per live member — built once."""
        if self._broker is None:
            from ..api.config import stream_config
            from ..core import sessions as core_sessions
            from ..state import layout_from_config
            from .stream import FleetBroker

            conf = stream_config(self.holder.current)

            def resolve(ref: str):
                try:
                    return core_sessions.transcript_path(
                        ref, config=self.holder.current
                    )
                except (LookupError, ValueError):
                    return None

            self._broker = FleetBroker(
                self.fleet,
                layout_from_config(self.holder.current or {}).event_log,
                self.own_name,
                max_subscribers=conf["maxSubscribers"],
                transcript_path=resolve,
                opener=self._opener,
                keepalive_hint=float(conf["keepAliveSeconds"]),
            )
        return self._broker

    def parse_cursor(self, raw: Optional[str]):
        from .stream import parse_fleet_cursor

        return parse_fleet_cursor(raw)

    def serve_stream(self, broker, subscriber, cursor, keep_alive: int):
        from .stream import serve_fleet

        return serve_fleet(broker, subscriber, cursor=cursor, keep_alive=keep_alive)
