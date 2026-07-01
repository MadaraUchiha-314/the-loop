"""Entry point so both ``the-loop`` and ``python -m the_loop`` work."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
