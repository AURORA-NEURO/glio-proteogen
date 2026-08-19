"""Opaque parse-once plugin boundary for provisional M23-04."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from glio_proteogen.contracts.m23_04 import (
    EvaluateVariantPeptideExternalTransportRequest,
    VariantPeptideExternalTransportResult,
    canonical_request_digest,
)

from .service import M2304Service

_REQUEST_ADAPTER: Final = TypeAdapter(EvaluateVariantPeptideExternalTransportRequest)
_TOKENS: WeakKeyDictionary[
    ValidatedM2304Request,
    tuple[object, EvaluateVariantPeptideExternalTransportRequest, str],
] = WeakKeyDictionary()


class ValidatedM2304Request:
    """Opaque token coupling one validated request to one plugin instance."""

    __slots__ = ("__weakref__", "_seal", "request")

    def __init__(
        self, request: EvaluateVariantPeptideExternalTransportRequest, seal: object
    ) -> None:
        self.request = request
        self._seal = seal


def _token_is_issued(token: ValidatedM2304Request, seal: object) -> bool:
    snapshot = _TOKENS.get(token)
    return (
        snapshot is not None
        and snapshot[0] is seal
        and snapshot[1] is token.request
        and snapshot[2] == canonical_request_digest(token.request)
    )


class M2304TokenError(TypeError):
    """A plugin token was forged or issued by another plugin."""

    def __init__(self) -> None:
        super().__init__("M23-04 requires a validated request token")


@dataclass(frozen=True, slots=True)
class M2304PluginDescriptor:
    module_id: str = "GLIO-PROTEOGEN-M23-04"
    operation: str = "evaluate_variant_peptide_external_transport"
    output_media_type: str = "application/vnd.glio-proteogen.m23-04+json"
    parent_target: str = "variant peptide"
    owner: str = "Computational biology"
    safety_class: str = "S3"
    evidence_gate: str = "G3"
    provisional_abi: bool = True
    external_transport: bool = True
    isoform_aware_quantification: bool = True
    calibration_floors: bool = True
    support_domain_narrowing: bool = True
    unsupported_to_negative: bool = False
    kinase_activity: bool = False
    all_omics_fusion: bool = False
    treatment_recommendation: bool = False
    identity_inference: bool = False
    consent_inference: bool = False


class M2304Plugin:
    """Strict plugin with a non-forgeable validation token."""

    __slots__ = ("_seal", "_service")
    descriptor: Final = M2304PluginDescriptor()

    def __init__(self, service: M2304Service | None = None) -> None:
        self._service = service or M2304Service()
        self._seal = object()

    def validate(self, request: object) -> ValidatedM2304Request:
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        token = ValidatedM2304Request(validated, self._seal)
        _TOKENS[token] = (self._seal, validated, canonical_request_digest(validated))
        return token

    def validate_request(self, request: object) -> EvaluateVariantPeptideExternalTransportRequest:
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def run(self, token: ValidatedM2304Request) -> VariantPeptideExternalTransportResult:
        if (
            not isinstance(token, ValidatedM2304Request)
            or token._seal is not self._seal
            or not _token_is_issued(token, self._seal)
        ):
            raise M2304TokenError
        return self._service._engine.evaluate(token.request)

    def replay(self, result: object) -> VariantPeptideExternalTransportResult:
        return self._service.verify_replay(result)


__all__ = [
    "M2304Plugin",
    "M2304PluginDescriptor",
    "M2304TokenError",
    "ValidatedM2304Request",
]
