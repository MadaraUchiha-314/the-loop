"""the-loop's control-plane API service (issue-161, decision-058).

Transport, serialization and authn over :mod:`the_loop.core` — nothing else.
Import of this package requires the ``[service]`` extra (FastAPI); the base
install imports :mod:`the_loop.client` instead and talks to a running service.
"""
