"""Deterministic M04-07 proteoform joint support-envelope router."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from threading import RLock
from typing import Final, cast
from weakref import ReferenceType, WeakKeyDictionary, ref

from pydantic import BaseModel, TypeAdapter

from glio_proteogen.contracts.m04_04 import ProteoformQualityResult
from glio_proteogen.contracts.m04_06 import ProteoformHarmonizationResult
from glio_proteogen.contracts.m04_07 import (
    M0407_CONTRACT_VERSION,
    M0407_ZERO_DIGEST,
    ProteoformContextReceipt,
    ProteoformDeclaredSupportFact,
    ProteoformHarmonizationSupportReceipt,
    ProteoformQualitySupportReceipt,
    ProteoformSupportDisposition,
    ProteoformSupportPolicy,
    ProteoformSupportPrerequisites,
    ProteoformSupportProfile,
    ProteoformSupportRouteResult,
    RouteProteoformSupportRequest,
    canonical_request_digest,
    harmonization_support_receipt,
    normalized_request,
    quality_support_receipt,
    result_payload_digest,
)
from glio_proteogen.contracts.m04_07.v1 import (
    _expected_support_route_bundle,
    _issue_prerequisites_replay_capability,
    _issue_validated_request_capability,
    _ReplayedM0407PrerequisitesCapability,
    _validate_request_with_prerequisites_capability,
    _validate_result_with_capability,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import ExecutionContext

_CONTEXT_ADAPTER: Final = TypeAdapter(ExecutionContext)
_PREREQUISITES_ADAPTER: Final = TypeAdapter(ProteoformSupportPrerequisites)
_PROFILE_ADAPTER: Final = TypeAdapter(ProteoformSupportProfile)
_POLICY_ADAPTER: Final = TypeAdapter(ProteoformSupportPolicy)
_FACTS_ADAPTER: Final = TypeAdapter(tuple[ProteoformDeclaredSupportFact, ...])
_CONTEXT_RECEIPTS_ADAPTER: Final = TypeAdapter(tuple[ProteoformContextReceipt, ...])
_MISSING: Final = object()
_MAX_PLAIN_DEPTH: Final = 96
_MAX_PLAIN_DICT_ITEMS: Final = 512
_MAX_PLAIN_SEQUENCE_ITEMS: Final = 4096
_MAX_PLAIN_NODES: Final = 500_000
_ADMISSION_SNAPSHOT_LENGTH: Final = 13
_ADMISSION_CAPABILITY_SEAL: Final = object()
_REQUEST_FIELDS: Final = frozenset(
    {
        "operation",
        "contract_version",
        "request_id",
        "context",
        "prerequisites",
        "profile",
        "policy",
        "declared_facts",
        "context_receipts",
        "supersedes_result_digest",
    }
)


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class _AdmittedM0407RequestCapability:
    source_request: ReferenceType[RouteProteoformSupportRequest]
    source_identity: int
    source_prerequisites_identity: int
    source_quality_identity: int
    source_harmonization_identity: int
    validated_request: RouteProteoformSupportRequest
    validated_identity: int
    validated_prerequisites_identity: int
    validated_quality_identity: int
    validated_harmonization_identity: int
    request_digest: str
    raw_snapshot: bytes
    normalized_snapshot: bytes
    seal: object


_ADMISSION_LOCK: Final = RLock()
_ISSUED_ADMISSION_CAPABILITIES: Final[
    WeakKeyDictionary[_AdmittedM0407RequestCapability, tuple[object, ...]]
] = WeakKeyDictionary()
_ADMISSION_CACHE: Final[
    dict[
        int,
        tuple[
            ReferenceType[RouteProteoformSupportRequest],
            _AdmittedM0407RequestCapability,
        ],
    ]
] = {}


class ProteoformSupportAuthorizationError(PermissionError):
    """Denied controls detected before prerequisite or fact traversal."""

    def __init__(self) -> None:
        super().__init__("upstream controls do not authorize proteoform support routing")


class ProteoformSupportReceiptError(ValueError):
    """Strict upstream results cannot form one M04-07 prerequisite chain."""

    @classmethod
    def quality(cls) -> ProteoformSupportReceiptError:
        return cls("M04-04 result cannot form a strict M04-07 quality receipt")

    @classmethod
    def harmonization(cls) -> ProteoformSupportReceiptError:
        return cls("M04-06 result cannot form a strict M04-07 harmonization receipt")

    @classmethod
    def chain(cls) -> ProteoformSupportReceiptError:
        return cls("M04-04 and M04-06 results do not form one M04-07 prerequisite chain")


class _InvalidAdmissionCapabilityError(TypeError):
    def __init__(self) -> None:
        super().__init__("invalid M04-07 admitted request capability")


def _drop_cached_admission(
    dead_request: ReferenceType[RouteProteoformSupportRequest],
) -> None:
    with _ADMISSION_LOCK:
        stale = tuple(
            identity
            for identity, (request_reference, _capability) in _ADMISSION_CACHE.items()
            if request_reference is dead_request
        )
        for identity in stale:
            _ADMISSION_CACHE.pop(identity, None)


def _issue_admission_capability(
    source: RouteProteoformSupportRequest,
    validated: RouteProteoformSupportRequest,
) -> _AdmittedM0407RequestCapability:
    if (
        type(source) is not RouteProteoformSupportRequest
        or type(validated) is not RouteProteoformSupportRequest
    ):
        raise _InvalidAdmissionCapabilityError
    source_prerequisites = source.prerequisites
    validated_prerequisites = validated.prerequisites
    if (
        type(source_prerequisites) is not ProteoformSupportPrerequisites
        or type(validated_prerequisites) is not ProteoformSupportPrerequisites
        or type(source_prerequisites.quality_result) is not ProteoformQualityResult
        or type(source_prerequisites.harmonization_result) is not ProteoformHarmonizationResult
        or type(validated_prerequisites.quality_result) is not ProteoformQualityResult
        or type(validated_prerequisites.harmonization_result) is not ProteoformHarmonizationResult
    ):
        raise _InvalidAdmissionCapabilityError
    raw_snapshot = canonical_json_bytes(source)
    normalized_snapshot = canonical_json_bytes(normalized_request(source))
    request_digest = canonical_request_digest(source)
    if (
        source is validated
        or raw_snapshot != canonical_json_bytes(validated)
        or normalized_snapshot != canonical_json_bytes(normalized_request(validated))
        or request_digest != canonical_request_digest(validated)
    ):
        raise _InvalidAdmissionCapabilityError
    source_reference = ref(source, _drop_cached_admission)
    capability = _AdmittedM0407RequestCapability(
        source_request=source_reference,
        source_identity=id(source),
        source_prerequisites_identity=id(source_prerequisites),
        source_quality_identity=id(source_prerequisites.quality_result),
        source_harmonization_identity=id(source_prerequisites.harmonization_result),
        validated_request=validated,
        validated_identity=id(validated),
        validated_prerequisites_identity=id(validated_prerequisites),
        validated_quality_identity=id(validated_prerequisites.quality_result),
        validated_harmonization_identity=id(validated_prerequisites.harmonization_result),
        request_digest=request_digest,
        raw_snapshot=raw_snapshot,
        normalized_snapshot=normalized_snapshot,
        seal=_ADMISSION_CAPABILITY_SEAL,
    )
    issued_snapshot: tuple[object, ...] = (
        source_reference,
        capability.source_identity,
        capability.source_prerequisites_identity,
        capability.source_quality_identity,
        capability.source_harmonization_identity,
        validated,
        capability.validated_identity,
        capability.validated_prerequisites_identity,
        capability.validated_quality_identity,
        capability.validated_harmonization_identity,
        request_digest,
        raw_snapshot,
        normalized_snapshot,
    )
    with _ADMISSION_LOCK:
        _ISSUED_ADMISSION_CAPABILITIES[capability] = issued_snapshot
        _ADMISSION_CACHE[id(source)] = (source_reference, capability)
    return capability


def _admission_capability_is_issued(
    capability: _AdmittedM0407RequestCapability,
    source: RouteProteoformSupportRequest,
) -> bool:
    if (
        type(capability) is not _AdmittedM0407RequestCapability
        or type(source) is not RouteProteoformSupportRequest
        or capability.seal is not _ADMISSION_CAPABILITY_SEAL
        or type(capability.source_request) is not ReferenceType
        or type(capability.validated_request) is not RouteProteoformSupportRequest
        or any(
            type(value) is not int
            for value in (
                capability.source_identity,
                capability.source_prerequisites_identity,
                capability.source_quality_identity,
                capability.source_harmonization_identity,
                capability.validated_identity,
                capability.validated_prerequisites_identity,
                capability.validated_quality_identity,
                capability.validated_harmonization_identity,
            )
        )
        or type(capability.request_digest) is not str
        or type(capability.raw_snapshot) is not bytes
        or type(capability.normalized_snapshot) is not bytes
    ):
        return False
    snapshot = _ISSUED_ADMISSION_CAPABILITIES.get(capability)
    if (
        snapshot is None
        or type(snapshot) is not tuple
        or len(snapshot) != _ADMISSION_SNAPSHOT_LENGTH
        or type(snapshot[0]) is not ReferenceType
        or any(type(snapshot[index]) is not int for index in (1, 2, 3, 4, 6, 7, 8, 9))
        or type(snapshot[5]) is not RouteProteoformSupportRequest
        or type(snapshot[10]) is not str
        or type(snapshot[11]) is not bytes
        or type(snapshot[12]) is not bytes
    ):
        return False
    source_prerequisites = source.prerequisites
    validated = capability.validated_request
    validated_prerequisites = validated.prerequisites
    if (
        type(source_prerequisites) is not ProteoformSupportPrerequisites
        or type(validated_prerequisites) is not ProteoformSupportPrerequisites
    ):
        return False
    source_quality = source_prerequisites.quality_result
    source_harmonization = source_prerequisites.harmonization_result
    validated_quality = validated_prerequisites.quality_result
    validated_harmonization = validated_prerequisites.harmonization_result
    if (
        type(source_quality) is not ProteoformQualityResult
        or type(source_harmonization) is not ProteoformHarmonizationResult
        or type(validated_quality) is not ProteoformQualityResult
        or type(validated_harmonization) is not ProteoformHarmonizationResult
    ):
        return False
    return (
        snapshot[0] is capability.source_request
        and snapshot[1] == capability.source_identity == id(source)
        and snapshot[2] == capability.source_prerequisites_identity == id(source_prerequisites)
        and snapshot[3] == capability.source_quality_identity == id(source_quality)
        and snapshot[4] == capability.source_harmonization_identity == id(source_harmonization)
        and snapshot[5] is validated
        and snapshot[6] == capability.validated_identity == id(validated)
        and snapshot[7]
        == capability.validated_prerequisites_identity
        == id(validated_prerequisites)
        and snapshot[8] == capability.validated_quality_identity == id(validated_quality)
        and snapshot[9]
        == capability.validated_harmonization_identity
        == id(validated_harmonization)
        and snapshot[10] == capability.request_digest
        and snapshot[11] == capability.raw_snapshot
        and snapshot[12] == capability.normalized_snapshot
        and capability.source_request() is source
        and canonical_request_digest(source) == capability.request_digest
        and canonical_request_digest(validated) == capability.request_digest
        and canonical_json_bytes(source) == capability.raw_snapshot
        and canonical_json_bytes(validated) == capability.raw_snapshot
        and canonical_json_bytes(normalized_request(source)) == capability.normalized_snapshot
        and canonical_json_bytes(normalized_request(validated)) == capability.normalized_snapshot
    )


def _admitted_request(
    source: RouteProteoformSupportRequest,
) -> RouteProteoformSupportRequest | None:
    with _ADMISSION_LOCK:
        entry = _ADMISSION_CACHE.get(id(source))
        if entry is None:
            return None
        source_reference, capability = entry
        if source_reference() is not source:
            _ADMISSION_CACHE.pop(id(source), None)
            return None
        try:
            issued = _admission_capability_is_issued(capability, source)
        except Exception:  # noqa: BLE001 - mutated issued state fails closed.
            issued = False
        if not issued:
            _ADMISSION_CACHE.pop(id(source), None)
            raise _InvalidAdmissionCapabilityError
        return capability.validated_request


class M0407ProteoformSupportRouterEngine:
    """Produce one immutable replay-closed support-routing result."""

    __slots__ = ()

    def route(self, request: object) -> ProteoformSupportRouteResult:
        """Authorize, strictly reconstruct, route, and self-validate one request."""

        if type(request) is RouteProteoformSupportRequest:
            typed_request = request
            preflight_proteoform_support_authorization(typed_request)
            admitted = _admitted_request(typed_request)
            if admitted is not None:
                return self._route_validated(admitted)
        validated = _validate_prepared_request(_prepare_support_request_candidate(request))
        if type(request) is RouteProteoformSupportRequest:
            _issue_admission_capability(request, validated)
        return self._route_validated(validated)

    @staticmethod
    def _route_validated(
        request: RouteProteoformSupportRequest,
    ) -> ProteoformSupportRouteResult:
        """Route one request whose exact validation capability is held by the caller."""

        return _support_route_result(request)


def route_proteoform_support(request: object) -> ProteoformSupportRouteResult:
    """Public stateless M04-07 operation."""

    return M0407ProteoformSupportRouterEngine().route(request)


def preflight_proteoform_support_authorization(candidate: object) -> None:
    """Check seven controls without traversing prerequisites or declared facts."""

    candidate_mro = type.__getattribute__(type(candidate), "__mro__")
    if type(candidate) is not RouteProteoformSupportRequest and dict not in candidate_mro:
        raise ProteoformSupportAuthorizationError
    try:
        context = _member(candidate, "context")
        references = _member(context, "references")
        expected = {
            "approved_configuration": "accepted",
            "identity_lineage": "resolved",
            "provenance": "accepted",
            "consent": "granted",
            "quality": "accepted",
            "support": "accepted",
            "intended_use": "accepted",
        }
        states = {
            role: _state_text(_member(_member(references, role), "state")) for role in expected
        }
    except Exception:  # noqa: BLE001 - hostile ordinary exceptions fail closed.
        raise ProteoformSupportAuthorizationError from None
    if states != expected:
        raise ProteoformSupportAuthorizationError


def _validate_json_request(
    candidate: object,
    _raw_payload: bytes | bytearray | str,
) -> RouteProteoformSupportRequest:
    """Validate an already strict-decoded JSON object exactly once."""

    return _validate_prepared_request(_prepare_support_request_candidate(candidate))


def _prepare_support_request_candidate(
    candidate: object,
) -> tuple[dict[str, object], _ReplayedM0407PrerequisitesCapability]:
    """Authorize controls before safely materializing governed support inputs."""

    preflight_proteoform_support_authorization(candidate)
    prerequisites = _PREREQUISITES_ADAPTER.validate_json(
        canonical_json_bytes(_plain_value(_member(candidate, "prerequisites"))),
        strict=True,
    )
    prerequisites_capability = _issue_prerequisites_replay_capability(prerequisites)
    payload: dict[str, object] = {
        "request_id": _plain_value(_member(candidate, "request_id")),
        "context": _CONTEXT_ADAPTER.validate_json(
            canonical_json_bytes(_plain_value(_member(candidate, "context"))),
            strict=True,
        ),
        "prerequisites": prerequisites,
        "profile": _PROFILE_ADAPTER.validate_json(
            canonical_json_bytes(_plain_value(_member(candidate, "profile"))),
            strict=True,
        ),
        "policy": _POLICY_ADAPTER.validate_json(
            canonical_json_bytes(_plain_value(_member(candidate, "policy"))),
            strict=True,
        ),
        "declared_facts": _FACTS_ADAPTER.validate_json(
            canonical_json_bytes(_plain_value(_member(candidate, "declared_facts"))),
            strict=True,
        ),
        "context_receipts": _CONTEXT_RECEIPTS_ADAPTER.validate_json(
            canonical_json_bytes(_plain_value(_member(candidate, "context_receipts"))),
            strict=True,
        ),
        "supersedes_result_digest": _optional_plain_member(
            candidate,
            "supersedes_result_digest",
        ),
    }
    for field in ("operation", "contract_version"):
        value = _member(candidate, field)
        if value is not _MISSING:
            payload[field] = _plain_value(value)
    for field in _request_member_names(candidate):
        if field not in _REQUEST_FIELDS:
            payload[field] = None
    return payload, prerequisites_capability


def _validate_prepared_request(
    prepared: tuple[dict[str, object], _ReplayedM0407PrerequisitesCapability],
) -> RouteProteoformSupportRequest:
    candidate, prerequisites_capability = prepared
    return _validate_request_with_prerequisites_capability(
        candidate,
        prerequisites_capability,
    )


def _member(candidate: object, field: str) -> object:
    candidate_mro = type.__getattribute__(type(candidate), "__mro__")
    if dict in candidate_mro:
        mapping = cast("dict[object, object]", candidate)
    elif BaseModel in candidate_mro:
        mapping = cast(
            "dict[object, object]",
            object.__getattribute__(candidate, "__dict__"),
        )
    else:
        return _MISSING
    if (
        type(mapping) is not dict
        or dict.__len__(mapping) > _MAX_PLAIN_DICT_ITEMS
        or any(type(key) is not str for key in dict.keys(mapping))
    ):
        raise _InvalidPlainValueError
    return dict.__getitem__(mapping, field) if dict.__contains__(mapping, field) else _MISSING


def _request_member_names(candidate: object) -> tuple[str, ...]:
    candidate_mro = type.__getattribute__(type(candidate), "__mro__")
    if dict in candidate_mro:
        mapping = cast("dict[object, object]", candidate)
    elif BaseModel in candidate_mro:
        mapping = cast(
            "dict[object, object]",
            object.__getattribute__(candidate, "__dict__"),
        )
    else:
        raise _InvalidPlainValueError
    if (
        type(mapping) is not dict
        or dict.__len__(mapping) > _MAX_PLAIN_DICT_ITEMS
        or any(type(key) is not str for key in dict.keys(mapping))
    ):
        raise _InvalidPlainValueError
    return cast("tuple[str, ...]", tuple(dict.keys(mapping)))


def _optional_plain_member(candidate: object, field: str) -> object:
    value = _member(candidate, field)
    return None if value is _MISSING else _plain_value(value)


def _state_text(candidate: object) -> object:
    if type(candidate) is str:
        return candidate
    candidate_mro = type.__getattribute__(type(candidate), "__mro__")
    if StrEnum in candidate_mro:
        value = object.__getattribute__(candidate, "_value_")
        return value if type(value) is str else None
    return None


class _InvalidPlainValueError(TypeError):
    def __init__(self) -> None:
        super().__init__("M04-07 strict request values require exact built-in containers")


def _plain_value(  # noqa: C901 - exact built-in traversal firewall.
    candidate: object,
    *,
    _depth: int = 0,
    _budget: list[int] | None = None,
) -> object:
    if _depth > _MAX_PLAIN_DEPTH:
        raise _InvalidPlainValueError
    budget = [_MAX_PLAIN_NODES] if _budget is None else _budget
    budget[0] -= 1
    if budget[0] < 0:
        raise _InvalidPlainValueError
    candidate_mro = type.__getattribute__(type(candidate), "__mro__")
    if BaseModel in candidate_mro:
        storage = cast(
            "dict[object, object]",
            object.__getattribute__(candidate, "__dict__"),
        )
        if (
            type(storage) is not dict
            or dict.__len__(storage) > _MAX_PLAIN_DICT_ITEMS
            or any(type(key) is not str for key in dict.keys(storage))
        ):
            raise _InvalidPlainValueError
        return {
            key: _plain_value(
                dict.__getitem__(storage, key),
                _depth=_depth + 1,
                _budget=budget,
            )
            for key in dict.keys(storage)
        }
    if dict in candidate_mro:
        mapping = cast("dict[object, object]", candidate)
        if (
            type(mapping) is not dict
            or dict.__len__(mapping) > _MAX_PLAIN_DICT_ITEMS
            or any(type(key) is not str for key in dict.keys(mapping))
        ):
            raise _InvalidPlainValueError
        return {
            key: _plain_value(
                dict.__getitem__(mapping, key),
                _depth=_depth + 1,
                _budget=budget,
            )
            for key in dict.keys(mapping)
        }
    if list in candidate_mro:
        list_values = cast("list[object]", candidate)
        if type(list_values) is not list or list.__len__(list_values) > _MAX_PLAIN_SEQUENCE_ITEMS:
            raise _InvalidPlainValueError
        return [
            _plain_value(item, _depth=_depth + 1, _budget=budget)
            for item in list.__iter__(list_values)
        ]
    if tuple in candidate_mro:
        tuple_values = cast("tuple[object, ...]", candidate)
        if (
            type(tuple_values) is not tuple
            or tuple.__len__(tuple_values) > _MAX_PLAIN_SEQUENCE_ITEMS
        ):
            raise _InvalidPlainValueError
        return tuple(
            _plain_value(item, _depth=_depth + 1, _budget=budget)
            for item in tuple.__iter__(tuple_values)
        )
    if isinstance(candidate, Mapping) or (
        isinstance(candidate, Sequence) and not isinstance(candidate, (str, bytes, bytearray))
    ):
        raise _InvalidPlainValueError
    return candidate


def proteoform_quality_support_receipt(
    result: object,
) -> ProteoformQualitySupportReceipt:
    """Strictly project a genuine full M04-04 result to the M04-07 boundary."""

    try:
        validated = ProteoformQualityResult.model_validate_json(
            canonical_json_bytes(result),
            strict=True,
        )
        return quality_support_receipt(validated)
    except (TypeError, ValueError) as error:
        raise ProteoformSupportReceiptError.quality() from error


def proteoform_harmonization_support_receipt(
    result: object,
) -> ProteoformHarmonizationSupportReceipt:
    """Strictly project a genuine full M04-06 result to the M04-07 boundary."""

    try:
        validated = ProteoformHarmonizationResult.model_validate_json(
            canonical_json_bytes(result),
            strict=True,
        )
        return harmonization_support_receipt(validated)
    except (TypeError, ValueError) as error:
        raise ProteoformSupportReceiptError.harmonization() from error


def proteoform_support_prerequisites(
    quality_result: object,
    harmonization_result: object,
) -> ProteoformSupportPrerequisites:
    """Build one digest-, identity-, version-, and chronology-closed compact bundle."""

    try:
        return ProteoformSupportPrerequisites(
            quality_result=ProteoformQualityResult.model_validate_json(
                canonical_json_bytes(quality_result), strict=True
            ),
            harmonization_result=ProteoformHarmonizationResult.model_validate_json(
                canonical_json_bytes(harmonization_result), strict=True
            ),
            quality=proteoform_quality_support_receipt(quality_result),
            harmonization=proteoform_harmonization_support_receipt(harmonization_result),
        )
    except (TypeError, ValueError) as error:
        if isinstance(error, ProteoformSupportReceiptError):
            raise
        raise ProteoformSupportReceiptError.chain() from error


def _support_route_result(
    request: RouteProteoformSupportRequest,
) -> ProteoformSupportRouteResult:
    bundle = _expected_support_route_bundle(request)
    payload: dict[str, object] = {
        "output_type": "proteoform_support_route_result",
        "route_id": f"route.{bundle.request_digest.removeprefix('sha256:')}",
        "result_version": M0407_CONTRACT_VERSION,
        "request_digest": bundle.request_digest,
        "profile_digest": bundle.profile_digest,
        "policy_digest": bundle.policy_digest,
        "configuration_digest": bundle.configuration_digest,
        "result_digest": M0407_ZERO_DIGEST,
        "request": request,
        "disposition": bundle.disposition,
        "matched_envelope_ids": bundle.matched_envelope_ids,
        "envelope_assessments": bundle.envelope_assessments,
        "abstention_reasons": bundle.abstention_reasons,
        "parent_target": "protein_rna_discordance",
        "emits_protein_rna_discordance": False,
        "emits_proteogenomic_state": False,
        "emits_proteotype": False,
        "emits_protein_level_subtype": False,
        "infers_identity": False,
        "infers_consent": False,
        "infers_protein": False,
        "infers_proteoform": False,
        "infers_isoform": False,
        "localizes_modification": False,
        "infers_kinase_activity": False,
        "performs_cn_to_protein_regression": False,
        "performs_all_omics_fusion": False,
        "recommends_treatment": False,
        "mutates_upstream": False,
        "executes_model": False,
        "support": bundle.support,
        "uncertainty": bundle.uncertainty,
        "provenance": bundle.provenance,
        "evidence": bundle.evidence,
        "limitations": bundle.limitations,
        "human_review_required": (bundle.disposition is ProteoformSupportDisposition.ABSTAINED),
        "completed_at": request.context.occurred_at,
    }
    expected_result_digest = result_payload_digest(
        ProteoformSupportRouteResult.model_construct(**payload)  # type: ignore[arg-type]
    )
    payload["result_digest"] = expected_result_digest
    capability = _issue_validated_request_capability(
        request,
        bundle,
        expected_result_digest,
    )
    return _validate_result_with_capability(payload, capability)


__all__ = [
    "M0407ProteoformSupportRouterEngine",
    "ProteoformSupportAuthorizationError",
    "ProteoformSupportReceiptError",
    "preflight_proteoform_support_authorization",
    "proteoform_harmonization_support_receipt",
    "proteoform_quality_support_receipt",
    "proteoform_support_prerequisites",
    "route_proteoform_support",
]
