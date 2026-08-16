"""Repository benchmark entry point for M06-02."""

from evals.m06_02.benchmark import benchmark, main

__all__ = ["benchmark", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
