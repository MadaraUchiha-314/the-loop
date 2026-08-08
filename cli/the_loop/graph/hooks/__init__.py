"""Built-in hooks. Importing the package registers every one of them.

Same shape as ``the_loop/commands/__init__.py``: new behaviour is a new module
imported here for its registration side effect.
"""

from . import artifacts  # noqa: F401
from . import assignment  # noqa: F401
from . import lint  # noqa: F401
from . import loops  # noqa: F401
from . import tests as _tests  # noqa: F401
from . import sideeffects  # noqa: F401
from . import feedback  # noqa: F401
from . import selection  # noqa: F401
from . import mcp  # noqa: F401

__all__ = [
    "artifacts",
    "assignment",
    "feedback",
    "lint",
    "loops",
    "mcp",
    "selection",
    "sideeffects",
]
