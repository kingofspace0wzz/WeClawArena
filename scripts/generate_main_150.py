"""Compatibility wrapper for the benchmark scaffold materializer.

The filename is historical. The current benchmark contract is 550 scenario
variants; new automation should use ``scripts/orchestrate_benchmark.py``.
"""

from __future__ import annotations

from scripts.generate_benchmark_scaffold import *  # noqa: F403
from scripts.generate_benchmark_scaffold import main


if __name__ == "__main__":
    raise SystemExit(main())
