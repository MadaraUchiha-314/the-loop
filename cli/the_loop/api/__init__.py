"""the-loop's control-plane API service (issue-161, decision-058).

Transport and serialization over :mod:`the_loop.core` — nothing else (auth is
the deploying gateway's job, decision-059). FastAPI, uvicorn and the official
MCP SDK are required dependencies, so every install can host a service.
"""
