"""Evaluator corpus and benchmark smoke tests."""

from __future__ import annotations

import json

from evals.m15_02.run import main

_SCENARIO_COUNT = 8


def test_locked_m1502_evaluator_corpus_passes(capsys: object) -> None:
    assert main() == 0
    output = capsys.readouterr().out  # type: ignore[attr-defined]
    report = json.loads(output)
    assert report["passed"] is True
    assert report["declared"] == _SCENARIO_COUNT
    assert report["dossier_sha256"].startswith("sha256:")
