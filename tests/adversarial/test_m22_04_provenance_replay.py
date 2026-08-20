"""Adversarial provenance and replay closure for M22-04."""

from __future__ import annotations

import pytest
from evals.m22_04.run import build_scenario_request

from glio_proteogen.contracts.m22_04.canonical import result_payload_digest
from glio_proteogen.modules.c21_reference_material.m22_04_external_transport_evaluator import (
    M2204Engine,
    M2204ReplayError,
)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("module_id", "GLIO-PROTEOGEN-M22-03"),
        ("module_version", "9.9.9"),
        ("configuration_digest", "sha256:" + "f" * 64),
        ("input_digests", ("sha256:" + "f" * 64,)),
    ],
)
def test_replay_rejects_self_rehashed_provenance_binding_forgery(
    field: str,
    value: object,
) -> None:
    engine = M2204Engine()
    result = engine.evaluate(build_scenario_request())
    forged = result.model_copy(
        update={"provenance": result.provenance.model_copy(update={field: value})}
    )
    forged = forged.model_copy(update={"result_digest": result_payload_digest(forged)})

    with pytest.raises(M2204ReplayError):
        engine.replay(forged)
