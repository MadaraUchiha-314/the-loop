"""Command package. Importing it registers all built-in commands."""

from .base import Command, iter_commands, register  # noqa: F401

# Import command modules for their registration side effects.
from . import ask_cmd  # noqa: F401,E402
from . import critic_cmd  # noqa: F401,E402
from . import events  # noqa: F401,E402
from . import gh_webhook  # noqa: F401,E402
from . import graph_cmd  # noqa: F401,E402
from . import install_cmd  # noqa: F401,E402
from . import instructions_cmd  # noqa: F401,E402
from . import migrate_cmd  # noqa: F401,E402
from . import poll  # noqa: F401,E402
from . import scenarios  # noqa: F401,E402
from . import service_cmd  # noqa: F401,E402  (registers the `service` command)
from . import sessions_cmd  # noqa: F401,E402

__all__ = ["Command", "iter_commands", "register"]
