"""Adversarial closure for the M05-05 strict boundary and replay firewall."""

from __future__ import annotations

import json
from typing import Any, cast

import pytest
from evals.m05_05.run import build_scenario

from glio_proteogen.contracts.m05_05 import (
    PtmLocalizationArtifactDisposition,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c05_ptm_localization.m05_05_artifact_detection import (
    M0505Plugin,
    M0505Service,
    PtmLocalizationArtifactAuthorizationError,
    PtmLocalizationArtifactInputError,
    detect_ptm_localization_artifacts,
)


class _ExplodingMapping:
    """A hostile mapping that must never be traversed by the request firewall."""

    accesses = 0

    def __getitem__(self, _key: object) -> object:
        type(self).accesses += 1
        raise AssertionError


def test_non_builtin_mapping_is_rejected_without_key_access() -> None:
    _ExplodingMapping.accesses = 0

    with pytest.raises(
        (
            PtmLocalizationArtifactAuthorizationError,
            PtmLocalizationArtifactInputError,
            TypeError,
            ValueError,
        )
    ):
        detect_ptm_localization_artifacts(cast("Any", _ExplodingMapping()))

    assert _ExplodingMapping.accesses == 0


def test_unknown_outer_member_is_rejected_before_execution() -> None:
    request = build_scenario("clear").request
    payload = request.model_dump(mode="python", exclude_none=False)
    payload["unlocked_output"] = {"protein": "forbidden"}

    with pytest.raises((PtmLocalizationArtifactInputError, TypeError, ValueError)):
        M0505Service.validate_request(payload)


def test_serialized_duplicate_key_is_rejected_before_model_validation() -> None:
    request = build_scenario("clear").request
    serialized = canonical_json_bytes(request).decode("utf-8")
    duplicate = serialized[:-1] + ',"context":null}'
    plugin = M0505Plugin(M0505Service())

    with pytest.raises((TypeError, ValueError)):
        plugin.validate(duplicate)


def test_serialized_unknown_nested_member_is_rejected() -> None:
    request = build_scenario("clear").request
    payload = request.model_dump(mode="json", exclude_none=False)
    context = payload["context"]
    assert isinstance(context, dict)
    context["identity_inference"] = True
    serialized = json.dumps(payload, separators=(",", ":"))

    with pytest.raises((PtmLocalizationArtifactInputError, TypeError, ValueError)):
        M0505Plugin(M0505Service()).validate(serialized)


def test_nested_raw_digest_tamper_is_not_reflected_in_result() -> None:
    request = build_scenario("clear").request
    raw_result = request.raw_input_result.model_copy(
        update={"request_digest": "sha256:" + ("f" * 64)}
    )
    candidate = request.model_copy(update={"raw_input_result": raw_result})

    with pytest.raises(PtmLocalizationArtifactInputError):
        detect_ptm_localization_artifacts(candidate)


def test_quality_binding_tamper_is_rejected_before_ledger_traversal() -> None:
    request = build_scenario("clear").request
    candidate = request.model_copy(update={"quality_result_digest": "sha256:" + ("0" * 64)})

    with pytest.raises(PtmLocalizationArtifactInputError):
        detect_ptm_localization_artifacts(candidate)


@pytest.mark.parametrize("case_id", ["missing_required", "unsupported_required"])
def test_non_evaluable_inputs_abstain_without_negative_finding(case_id: str) -> None:
    result = detect_ptm_localization_artifacts(build_scenario(case_id).request)

    assert result.disposition is PtmLocalizationArtifactDisposition.ABSTAINED
    assert result.contamination_flags == ()
    assert result.exclusion_mask == ()
    assert all(item.posterior_ppm in (0, None) for item in result.artifact_posteriors)


def test_plugin_token_cannot_be_forged_by_copying_request() -> None:
    request = build_scenario("clear").request
    plugin = M0505Plugin(M0505Service())
    token = plugin.validate(request)
    forged = type(token)(request=token.request.model_copy(), _seal=token._seal)

    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(forged)
