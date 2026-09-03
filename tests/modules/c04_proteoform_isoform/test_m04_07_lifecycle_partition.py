"""Collection integrity for the runtime-balanced M04-07 lifecycle cases."""

from types import ModuleType

from tests.modules.c04_proteoform_isoform import m04_07_lifecycle_cases as cases
from tests.modules.c04_proteoform_isoform import test_m04_07_lifecycle_admission as admission
from tests.modules.c04_proteoform_isoform import (
    test_m04_07_lifecycle_capabilities as capabilities,
)
from tests.modules.c04_proteoform_isoform import test_m04_07_lifecycle_execution as execution


def _test_functions(module: ModuleType) -> set[str]:
    return {
        name for name, value in vars(module).items() if name.startswith("test_") and callable(value)
    }


def test_lifecycle_case_partitions_are_disjoint_and_complete() -> None:
    partitions = (
        set(admission.__all__),
        set(capabilities.__all__),
        set(execution.__all__),
    )

    assert all(partitions)
    assert not partitions[0].intersection(partitions[1])
    assert not partitions[0].intersection(partitions[2])
    assert not partitions[1].intersection(partitions[2])
    assert set.union(*partitions) == _test_functions(cases)
    assert partitions[0] == _test_functions(admission)
    assert partitions[1] == _test_functions(capabilities)
    assert partitions[2] == _test_functions(execution)
