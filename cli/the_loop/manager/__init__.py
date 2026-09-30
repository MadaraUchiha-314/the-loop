"""A manager instance: the fleet it serves, and the facade that serves it (issue-374).

``the_loop.manager.fleet`` is the client side — the registry, the probes, the fan-out
and the resolvers; ``the_loop.manager.facade`` is the implementation the router calls
when ``instance.role`` is ``manager``, wrapping the worker's core facade for the
manager's own state; ``the_loop.manager.stream`` fans the members' event streams in.
Spec: docs/specs/issue-374/design.md.
"""
