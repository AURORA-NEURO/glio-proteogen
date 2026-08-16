"""Evaluator corpus closure for M16-03."""

from evals.m16_03.run import main


def test_m1603_evaluator_corpus_passes() -> None:
    assert main() == 0
