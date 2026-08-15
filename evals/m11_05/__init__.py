"""Provisional M11-05 longitudinal-evolution evaluation namespace."""

from .benchmark import BenchmarkReport, run_benchmark
from .run import EvaluationReport, build_request, run_evaluator

MODULE_ID = "GLIO-PROTEOGEN-M11-05"
ABI_STATUS = "provisional-dossier-behavioral-brief-only"

__all__ = [
    "ABI_STATUS",
    "MODULE_ID",
    "BenchmarkReport",
    "EvaluationReport",
    "build_request",
    "run_benchmark",
    "run_evaluator",
]
