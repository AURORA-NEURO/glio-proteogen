"""Compatibility wrapper for the M08-05 benchmark entry point."""

from evals.m08_05.benchmark import BenchmarkReport, benchmark, main

__all__ = ["BenchmarkReport", "benchmark", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
