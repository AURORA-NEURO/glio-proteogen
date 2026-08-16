"""Repository benchmark entry point for M07-07."""

from evals.m07_07.benchmark import benchmark

if __name__ == "__main__":
    import json

    print(json.dumps(benchmark(), indent=2, sort_keys=True))  # noqa: T201
