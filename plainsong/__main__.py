"""Entry point for `python -m plainsong`."""

import sys

from .interfaces.cli import main

if __name__ == "__main__":
    sys.exit(main())
