"""Evaluator corpus closure for M15-08."""

from evals.m15_08.run import main


def test_m1508_evaluator_corpus_passes() -> None:
    assert main() == 0
