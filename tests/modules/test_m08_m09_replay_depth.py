"""Adversarial replay closure for the M08-07/M09-07 calibration pair."""

from __future__ import annotations

from typing import Any

import pytest

from glio_proteogen.contracts.m08_07 import result_payload_digest as digest_m0807
from glio_proteogen.contracts.m09_07 import result_payload_digest as digest_m0907
from glio_proteogen.modules.c08_transcript_protein_discordance import (
    m08_07_calibration_selective_prediction as m0807,
)
from glio_proteogen.modules.c09_complex_stoichiometry import (
    m09_07_calibration_selective_prediction as m0907,
)
from tests.contract.test_m08_07_contract_hardening import _request as request_m0807
from tests.contract.test_m09_07_contract_hardening import _request as request_m0907
from tests.modules.test_m08_07_runtime import _candidate as candidate_m0807
from tests.modules.test_m09_07_runtime import _candidate as candidate_m0907


@pytest.mark.parametrize("module", ["m0807", "m0907"])
def test_self_rehashed_control_output_is_rejected_with_request(module: str) -> None:
    """A valid digest cannot turn a changed control decision into a replay."""

    if module == "m0807":
        request: Any = request_m0807().model_copy(update={"candidate": candidate_m0807()})
        result: Any = m0807.M0807Service().execute(request)
        forged = result.model_copy(
            update={
                "support_decision": result.support_decision.model_copy(
                    update={"rationale": "forged control decision"}
                )
            }
        )
        forged = forged.model_copy(update={"result_digest": digest_m0807(forged)})
        assert m0807.M0807Service.verify(forged) is True
        assert m0807.M0807Service.verify(forged, request) is False
    else:
        request = request_m0907().model_copy(update={"candidate": candidate_m0907()})
        result = m0907.M0907Service().execute(request)
        forged = result.model_copy(
            update={
                "support_decision": result.support_decision.model_copy(
                    update={"rationale": "forged control decision"}
                )
            }
        )
        forged = forged.model_copy(update={"result_digest": digest_m0907(forged)})
        assert m0907.M0907Service.verify(forged) is True
        assert m0907.M0907Service.verify(forged, request) is False


def test_m0807_self_rehashed_provenance_and_uncertainty_are_closed() -> None:
    """M08-07 must enforce the same safe uncertainty/provenance closure as M09-07."""

    request = request_m0807().model_copy(update={"candidate": candidate_m0807()})
    result = m0807.M0807Service().execute(request)

    forged_provenance = result.model_copy(
        update={"provenance": result.provenance.model_copy(update={"actor_id": "attacker"})}
    )
    forged_provenance = forged_provenance.model_copy(
        update={"result_digest": digest_m0807(forged_provenance)}
    )
    assert m0807.M0807Service.verify(forged_provenance) is False

    forged_uncertainty = result.model_copy(
        update={"uncertainty": result.uncertainty.model_copy(update={"sensitivity_notes": ()})}
    )
    forged_uncertainty = forged_uncertainty.model_copy(
        update={"result_digest": digest_m0807(forged_uncertainty)}
    )
    assert m0807.M0807Service.verify(forged_uncertainty) is False
