"""Executable M28-04 evaluator assertions."""

from evals.m28_04.run import EXPECTED_CHECK_COUNT, run_evaluator


def test_m2804_evaluator_matrix_passes() -> None:
    report = run_evaluator()
    assert len(report.checks) == EXPECTED_CHECK_COUNT
    assert report.passed
    assert all(check.passed for check in report.checks)
