"""GitHub webhook receiver (stdlib-only, no runtime dependencies)."""

from .server import verify_signature, make_handler, serve

__all__ = ["verify_signature", "make_handler", "serve"]
