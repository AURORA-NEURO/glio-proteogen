"""Runtime, plugin, and safe-failure tests for M05-07."""

from typing import Any, cast

import pytest

from glio_proteogen.contracts.m05_07 import (
    PtmLocalizationAbstentionCode,
    PtmLocalizationDeclaredSupportState,
    PtmLocalizationDimensionSupportDecision,
    PtmLocalizationSupportDisposition,
    PtmLocalizationSupportRouteResult,
)
from glio_proteogen.kernel.models import SupportStatus, UpstreamDecisionState
from glio_proteogen.kernel.strict_json import StrictJsonError
from glio_proteogen.modules.c05_ptm_localization.m05_07_unsupported_abstention_router import (
    M0507Plugin,
    M0507PtmLocalizationSupportEngine,
    M0507Service,
    M0507Submission,
    PtmLocalizationSupportAuthorizationError,
    PtmLocalizationSupportInputError,
    ValidatedM0507Request,
)
from glio_proteogen.modules.c05_ptm_localization.m05_07_unsupported_abstention_router import (
    engine as engine_module,
)
from tests.contract.test_m05_07_hardening import _context, _request

_TWO_FAILURES = 2


def test_supported_route_is_deterministic_and_canonically_bound() -> None:
    request = _request()
    first = M0507PtmLocalizationSupportEngine().route(request)
    second = M0507PtmLocalizationSupportEngine().route(request.model_dump(mode="json"))

    assert first == second
    assert first.disposition is PtmLocalizationSupportDisposition.SUPPORTED
    assert first.support_decision.status is SupportStatus.SUPPORTED
    assert first.request_digest == first.receipt.request_digest
    assert first.result_digest.startswith("sha256:")


def test_outside_domain_routes_to_typed_abstention() -> None:
    request = _request(
        declared_facts=(
            _request()
            .declared_facts[0]
            .model_copy(
                update={
                    "decision": PtmLocalizationDimensionSupportDecision.OUTSIDE_DOMAIN,
                }
            ),
            *_request().declared_facts[1:],
        )
    )
    result = M0507Service().execute(request)

    assert result.disposition is PtmLocalizationSupportDisposition.ABSTAINED
    assert result.abstention_code is PtmLocalizationAbstentionCode.DIMENSION_OUTSIDE_DOMAIN
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert result.parent_target == "variant_peptide"


def test_indeterminate_route_never_emits_negative_finding() -> None:
    base = _request()
    facts = list(base.declared_facts)
    facts[1] = facts[1].model_copy(
        update={
            "decision": PtmLocalizationDimensionSupportDecision.INDETERMINATE,
            "state": PtmLocalizationDeclaredSupportState.UNKNOWN,
        }
    )
    result = M0507Service().execute(_request(declared_facts=tuple(facts)))

    assert result.disposition is PtmLocalizationSupportDisposition.ABSTAINED
    assert result.abstention_code is PtmLocalizationAbstentionCode.DIMENSION_INDETERMINATE
    assert result.support_decision.status is not SupportStatus.SUPPORTED
    assert "finding" not in result.model_dump(mode="json")


def test_authorization_preflight_rejects_denied_control() -> None:
    context = _context().model_copy(
        update={
            "references": _context().references.model_copy(
                update={
                    "quality": _context().references.quality.model_copy(
                        update={"state": UpstreamDecisionState.REJECTED}
                    )
                }
            )
        }
    )
    with pytest.raises(PtmLocalizationSupportAuthorizationError):
        M0507PtmLocalizationSupportEngine().route(_request(context=context))


def test_engine_rejects_unsupported_request_type() -> None:
    with pytest.raises(PtmLocalizationSupportInputError):
        M0507PtmLocalizationSupportEngine().route(object())


def test_strict_mapping_rejects_unknown_field() -> None:
    payload = _request().model_dump(mode="json")
    payload["untrusted"] = "do not traverse"
    with pytest.raises(PtmLocalizationSupportInputError):
        M0507Service().execute(payload)


def test_plugin_typed_and_json_paths_are_equal() -> None:
    service = M0507Service()
    plugin = M0507Plugin(service)
    request = _request()
    typed = plugin.run(plugin.validate(M0507Submission(request)))
    serialized = plugin.run(plugin.validate(request.model_dump_json()))

    assert typed == serialized
    assert isinstance(typed, PtmLocalizationSupportRouteResult)
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M05-07"


def test_plugin_rejects_unissued_execution_token() -> None:
    plugin = M0507Plugin(M0507Service())
    token = ValidatedM0507Request(request=_request(), _seal=object())
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(token)


def test_plugin_rejects_duplicate_json_keys() -> None:
    plugin = M0507Plugin(M0507Service())
    with pytest.raises(StrictJsonError, match="duplicate JSON object key"):
        plugin.validate('{"request_id":"request.1","request_id":"request.2"}')


def test_service_validates_before_engine_execution() -> None:
    service = M0507Service()
    request = _request()
    assert service.validate_request(request) == request
    assert service.execute(request).request == request


def test_authorization_rejects_non_mapping_and_hostile_mapping() -> None:
    with pytest.raises(PtmLocalizationSupportAuthorizationError):
        engine_module.preflight_ptm_localization_support_authorization(object())

    class ExplodingMapping(dict[str, object]):
        def get(self, key: str, default: object = None) -> object:
            del key, default
            raise RuntimeError

    with pytest.raises(PtmLocalizationSupportAuthorizationError):
        engine_module.preflight_ptm_localization_support_authorization(ExplodingMapping())


def test_strict_json_boundary_rejects_non_mapping_and_non_plain_values() -> None:
    with pytest.raises(PtmLocalizationSupportInputError):
        engine_module._validate_json_request([], b"[]")

    payload = cast("dict[object, object]", _request().model_dump(mode="json"))
    payload[1] = "non-string key"
    with pytest.raises(PtmLocalizationSupportInputError):
        engine_module._validate_json_request(payload, b"{}")

    payload = cast("dict[object, object]", _request().model_dump(mode="json"))
    payload["unsupported"] = object()
    with pytest.raises(PtmLocalizationSupportInputError):
        engine_module._validate_json_request(payload, b"{}")


def test_request_byte_caps_fail_closed_for_mapping_and_typed_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = cast("dict[str, object]", _request().model_dump(mode="json"))
    payload["padding"] = "x" * (cast("Any", engine_module).M0507_MAX_CANONICAL_REQUEST_BYTES + 1)
    with pytest.raises(ValueError, match="canonical request exceeds"):
        M0507PtmLocalizationSupportEngine().route(payload)

    monkeypatch.setattr(cast("Any", engine_module), "M0507_MAX_CANONICAL_REQUEST_BYTES", 0)
    with pytest.raises(ValueError, match="canonical request exceeds"):
        M0507PtmLocalizationSupportEngine().route(_request())


def test_duplicate_unsupported_dimensions_keep_one_remediation_path() -> None:
    base = _request()
    facts = list(base.declared_facts)
    facts[0] = facts[0].model_copy(
        update={"decision": PtmLocalizationDimensionSupportDecision.OUTSIDE_DOMAIN}
    )
    facts[1] = facts[1].model_copy(
        update={"decision": PtmLocalizationDimensionSupportDecision.OUTSIDE_DOMAIN}
    )
    result = M0507PtmLocalizationSupportEngine().route(_request(declared_facts=tuple(facts)))

    assert len(result.receipt.unsupported_dimensions) == _TWO_FAILURES
    assert len(result.remediation) == 1
