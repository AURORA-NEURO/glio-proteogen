"""Locked M10-03 evaluator checks."""

from evals.m10_03.run import evaluate, main


def test_evaluator_matrix_passes() -> None:
    report = evaluate()
    assert all(report["cases"].values())


def test_evaluator_is_deterministic() -> None:
    assert evaluate() == evaluate()


def test_evaluator_main_returns_success() -> None:
    assert main() == 0
