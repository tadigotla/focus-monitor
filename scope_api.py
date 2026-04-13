#!/usr/bin/env python3
"""Back-compat shim — prefer `python -m scope.api` or `cli.py start scope`."""
from scope.api.__main__ import main

if __name__ == "__main__":
    main()
