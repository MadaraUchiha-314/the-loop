"""the-loop — lightweight, extensible CLI for the-loop.

Primary CLI: ``the-loop``. Sub-commands self-register (see ``commands/base.py``),
so adding a command is just adding a module under ``the_loop/commands/``.
"""

from importlib.metadata import PackageNotFoundError, version as _dist_version

# Derive the version from installed package metadata (distribution name
# ``the-loopy-one`` — see cli/pyproject.toml) rather than hardcoding it, so
# ``the-loop --version`` always reports the actually-installed version. A
# hardcoded string here is invisible to commitizen's ``version_files`` lockstep
# (it is not listed there) and silently froze at 0.1.0 while releases advanced —
# issue #78.
try:
    __version__ = _dist_version("the-loopy-one")
except PackageNotFoundError:
    # Running from an uninstalled source tree (no package metadata).
    __version__ = "0.0.0+unknown"
