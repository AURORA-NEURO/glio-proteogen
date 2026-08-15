"""Focused provisional M05-06 ABI smoke checks."""

import pytest
from evals.m05_05.run import build_scenario

from glio_proteogen.contracts.m05_05 import PtmLocalizationArtifactDisposition
from glio_proteogen.contracts.m05_06 import (
    M0506_OPERATION,
    M0506_UPSTREAM_DETECTOR_COUNT,
    contract_json_schemas,
)
from glio_proteogen.modules.c05_ptm_localization.m05_05_artifact_detection import (
    detect_ptm_localization_artifacts,
)
from glio_proteogen.modules.c05_ptm_localization.m05_06_harmonization import (
    M0506Plugin,
    M0506Service,
)
from glio_proteogen.modules.c05_ptm_localization.m05_06_harmonization.engine import (
    PtmLocalizationHarmonizationAuthorizationError,
    artifact_harmonization_receipt,
)

_EXPECTED_SCHEMA_COUNT = 14


def test_provisional_schema_and_full_m0505_projection() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _EXPECTED_SCHEMA_COUNT
    assert schemas["request"]["x-glio-contract"]["provisionalAbi"] is True
    assert schemas["request"]["x-glio-contract"]["pendingOwnerConfirmation"] is True
    assert M0506_OPERATION == "harmonize_ptm_localization_analysis"

    result = detect_ptm_localization_artifacts(build_scenario("clear").request)
    assert result.disposition is PtmLocalizationArtifactDisposition.CLEARED
    receipt = artifact_harmonization_receipt(result)
    assert receipt.artifact_result_digest == result.result_digest
    assert receipt.target_count == 1
    assert len(receipt.targets[0].posterior_digests) == M0506_UPSTREAM_DETECTOR_COUNT

    plugin = M0506Plugin(M0506Service())
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M05-06"
    with pytest.raises(PtmLocalizationHarmonizationAuthorizationError):
        M0506Service.validate_request({})
