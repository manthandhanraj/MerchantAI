#!/usr/bin/env python3
"""Start Mendel with one command: ``python runner.py``.

The project launcher lives in ``run.py``.  This small entry point keeps the
easy command users expect while forwarding every option unchanged, including:

    python runner.py          # Docker (preferred)
    python runner.py --local  # use local PostgreSQL and Maven
    python runner.py --down   # stop Docker services
"""

from run import main


if __name__ == "__main__":
    raise SystemExit(main())
