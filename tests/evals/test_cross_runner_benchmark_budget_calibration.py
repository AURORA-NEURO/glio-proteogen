"""Cross-runner calibration locks for the replay-heavy benchmark lanes."""

from __future__ import annotations

import pytest
from evals.m03_07.benchmark import MEAN_BUDGET_NS as M0307_MEAN_BUDGET_NS
from evals.m03_07.benchmark import MEASUREMENT_CLOCK as M0307_MEASUREMENT_CLOCK
from evals.m03_07.benchmark import P95_BUDGET_NS as M0307_P95_BUDGET_NS
from evals.m04_03.benchmark import MEAN_BUDGET_NS as M0403_MEAN_BUDGET_NS
from evals.m04_03.benchmark import MEASUREMENT_CLOCK as M0403_MEASUREMENT_CLOCK
from evals.m04_03.benchmark import P95_BUDGET_NS as M0403_P95_BUDGET_NS
from evals.m04_04.benchmark import MEAN_BUDGET_NS as M0404_MEAN_BUDGET_NS
from evals.m04_04.benchmark import MEASUREMENT_CLOCK as M0404_MEASUREMENT_CLOCK
from evals.m04_04.benchmark import P95_BUDGET_NS as M0404_P95_BUDGET_NS
from evals.m04_07.benchmark import MEAN_BUDGET_NS as M0407_MEAN_BUDGET_NS
from evals.m04_07.benchmark import MEASUREMENT_CLOCK as M0407_MEASUREMENT_CLOCK
from evals.m04_07.benchmark import P95_BUDGET_NS as M0407_P95_BUDGET_NS
from evals.m05_05.benchmark import MEASUREMENT_CLOCK as M0505_MEASUREMENT_CLOCK

from glio_proteogen.contracts.m05_05 import (
    M0505_MEAN_BUDGET_NS,
    M0505_P95_BUDGET_NS,
)


@pytest.mark.parametrize(
    ("mean_budget_ns", "p95_budget_ns"),
    [
        (M0307_MEAN_BUDGET_NS, M0307_P95_BUDGET_NS),
        (M0403_MEAN_BUDGET_NS, M0403_P95_BUDGET_NS),
        (M0404_MEAN_BUDGET_NS, M0404_P95_BUDGET_NS),
        (M0407_MEAN_BUDGET_NS, M0407_P95_BUDGET_NS),
    ],
)
def test_mean_ceiling_retains_exact_twenty_percent_tail_reserve(
    mean_budget_ns: int,
    p95_budget_ns: int,
) -> None:
    """The p95 ceiling is exactly 120% of the calibrated mean ceiling."""

    assert p95_budget_ns * 5 == mean_budget_ns * 6


def test_tail_regression_ceilings_remain_unchanged() -> None:
    """Calibration must not relax either installed tail-latency class."""

    assert {
        M0307_P95_BUDGET_NS,
        M0407_P95_BUDGET_NS,
        M0505_P95_BUDGET_NS,
    } == {3_000_000_000}
    assert {M0403_P95_BUDGET_NS, M0404_P95_BUDGET_NS} == {750_000_000}


def test_m0505_governed_budget_remains_unchanged() -> None:
    """The research lane must not recalibrate an existing governed v1 contract."""

    assert (M0505_MEAN_BUDGET_NS, M0505_P95_BUDGET_NS) == (2_000_000_000, 3_000_000_000)


def test_cpu_clock_excludes_unrelated_runner_preemption() -> None:
    """Every calibrated gate measures operation CPU rather than host wait time."""

    assert {
        M0307_MEASUREMENT_CLOCK,
        M0403_MEASUREMENT_CLOCK,
        M0404_MEASUREMENT_CLOCK,
        M0407_MEASUREMENT_CLOCK,
        M0505_MEASUREMENT_CLOCK,
    } == {"process_time_ns"}
