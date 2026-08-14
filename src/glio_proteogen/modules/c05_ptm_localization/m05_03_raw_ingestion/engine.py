"""Deterministic M05-03 canonical raw-manifest ingestion engine."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import TYPE_CHECKING, Any, Final, cast, get_args, get_origin

from pydantic import BaseModel, TypeAdapter, ValidationError

from glio_proteogen.contracts import m05_03 as _m0503_contracts
from glio_proteogen.contracts.m05_02 import PtmLocalizationIdentityLineageResolution
from glio_proteogen.contracts.m05_03.v1 import _validate_exact_request_storage
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)

if TYPE_CHECKING:
    from glio_proteogen.contracts.m05_03 import (
        IngestPtmLocalizationRawInputsRequest,
        PtmLocalizationRawInputValidationResult,
    )

_AUTHORIZATION_MESSAGE: Final = (
    "ptm_localization raw-input ingestion requires accepted upstream controls"
)
_MAX_PLAIN_DEPTH: Final = 72
_MAX_PLAIN_DICT_ITEMS: Final = 512
_MAX_PLAIN_NODES: Final = 150_000
_MAX_PLAIN_SEQUENCE: Final = 4_096
_REQUEST_FIELDS: Final = frozenset(
    {
        "operation",
        "contract_version",
        "request_id",
        "context",
        "lineage_result",
        "policy",
        "artifacts",
        "supersedes_result_digest",
    }
)


def _contracts() -> Any:  # noqa: ANN401 - shared private module accessor.
    return _m0503_contracts


class PtmLocalizationRawInputAuthorizationError(PermissionError):
    """Authorization failed before request or raw-manifest traversal."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class PtmLocalizationRawInputErrorCode(StrEnum):
    """Stable, content-free structural and integrity failures."""

    ARTIFACT_MAPPING_MISMATCH = "artifact_mapping_mismatch"
    ARTIFACT_TYPE_INVALID = "artifact_type_invalid"
    ARTIFACT_SIZE_MISMATCH = "artifact_size_mismatch"
    ARTIFACT_DIGEST_MISMATCH = "artifact_digest_mismatch"
    DOCUMENT_JSON_INVALID = "document_json_invalid"
    DOCUMENT_NOT_CANONICAL = "document_not_canonical"
    DOCUMENT_TYPE_MISMATCH = "document_type_mismatch"


class PtmLocalizationRawInputError(ValueError):
    """A submitted manifest mapping or document failed the strict boundary."""

    def __init__(self, code: PtmLocalizationRawInputErrorCode) -> None:
        self.code = code
        super().__init__(f"M05-03 input rejected: {code.value}")


class _InvalidPreparedInputError(TypeError):
    def __init__(self) -> None:
        super().__init__("M05-03 prepared input capability is invalid")


class _InvalidDocumentContractError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("M05-03 document model lacks one exact document type")


class _InvalidPlainValueError(TypeError):
    def __init__(self) -> None:
        super().__init__("M05-03 strict request values require exact string keys")


@dataclass(frozen=True, slots=True)
class _PreparedPtmLocalizationRawInputs:
    """Once-read immutable bytes and their strict parsed document projections."""

    snapshots: tuple[tuple[object, bytes], ...]
    documents: tuple[BaseModel, ...]


class M0503PtmLocalizationRawInputIngester:
    """Validate four exact canonical manifest documents without opening their content refs."""

    __slots__ = ()

    def ingest(
        self,
        request: object,
        artifacts_by_role: object,
    ) -> PtmLocalizationRawInputValidationResult:
        """Authorize, replay, snapshot, validate, and seal one immutable result."""

        contracts = _contracts()
        preflight_ptm_localization_raw_input_authorization(request)
        _validate_outer_request_shape(request, contracts)
        adapter: TypeAdapter[Any] = TypeAdapter(contracts.IngestPtmLocalizationRawInputsRequest)
        validated = adapter.validate_python(_plain_value(request), strict=True)
        canonical = adapter.validate_json(
            canonical_json_bytes(contracts.normalized_request(validated)),
            strict=True,
        )
        # Revalidate the full public M05-02 envelope independently of compact projections.
        TypeAdapter(PtmLocalizationIdentityLineageResolution).validate_json(
            canonical_json_bytes(contracts.normalized_lineage_result(canonical.lineage_result)),
            strict=True,
        )
        upstream_disposition = canonical.lineage_result.disposition.value
        if upstream_disposition != "reconciled":
            return _result(canonical, ())
        prepared = _prepare_ptm_localization_raw_inputs(canonical, artifacts_by_role)
        return self._ingest_prepared(canonical, prepared)

    def _ingest_prepared(
        self,
        request: IngestPtmLocalizationRawInputsRequest,
        prepared: _PreparedPtmLocalizationRawInputs,
    ) -> PtmLocalizationRawInputValidationResult:
        """Seal a result from one private capability without re-reading caller bytes."""

        if type(prepared) is not _PreparedPtmLocalizationRawInputs:
            raise _InvalidPreparedInputError
        return _result(request, prepared.documents)


def ingest_ptm_localization_raw_inputs(
    request: object,
    artifacts_by_role: object,
) -> PtmLocalizationRawInputValidationResult:
    """Public stateless M05-03 operation."""

    return M0503PtmLocalizationRawInputIngester().ingest(request, artifacts_by_role)


def preflight_ptm_localization_raw_input_authorization(candidate: object) -> None:
    """Check seven states before touching governed or byte-bearing fields."""

    try:
        contracts = _contracts()
        supported = type(candidate) in {
            contracts.IngestPtmLocalizationRawInputsRequest,
            dict,
        }
        context = _member(candidate, "context") if supported else None
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
        authorized = supported and states == expected
    except Exception:  # noqa: BLE001 - hostile caller objects fail closed.
        raise PtmLocalizationRawInputAuthorizationError from None
    if not authorized:
        raise PtmLocalizationRawInputAuthorizationError


def _prepare_ptm_localization_raw_inputs(
    request: IngestPtmLocalizationRawInputsRequest,
    supplied: object,
) -> _PreparedPtmLocalizationRawInputs:
    """Snapshot, cap, hash, and parse an exact built-in role mapping once."""

    contracts = _contracts()
    snapshots = _snapshot_role_mapping(supplied, contracts)
    artifacts_by_role = _trusted_artifacts_by_role(request, contracts)
    _enforce_snapshot_caps(request, snapshots, artifacts_by_role, contracts)
    _verify_snapshot_digests(snapshots, artifacts_by_role)
    return _PreparedPtmLocalizationRawInputs(
        snapshots=snapshots,
        documents=_parse_snapshot_documents(request, snapshots, contracts),
    )


def _snapshot_role_mapping(
    supplied: object,
    contracts: Any,  # noqa: ANN401 - delayed public contract module.
) -> tuple[tuple[object, bytes], ...]:
    if type(supplied) is not dict:
        raise PtmLocalizationRawInputError(
            PtmLocalizationRawInputErrorCode.ARTIFACT_MAPPING_MISMATCH
        )
    mapping = cast("dict[object, object]", supplied)
    role_type = contracts.PtmLocalizationRawInputRole
    expected_roles = tuple(role_type)
    if dict.__len__(mapping) != contracts.M0503_ROLE_COUNT:
        raise PtmLocalizationRawInputError(
            PtmLocalizationRawInputErrorCode.ARTIFACT_MAPPING_MISMATCH
        )
    caller_keys = tuple(dict.__iter__(mapping))
    if any(type(key) is not role_type for key in caller_keys) or any(
        not any(key is expected for key in caller_keys) for expected in expected_roles
    ):
        raise PtmLocalizationRawInputError(
            PtmLocalizationRawInputErrorCode.ARTIFACT_MAPPING_MISMATCH
        )
    raw_snapshots = tuple((role, dict.__getitem__(mapping, role)) for role in expected_roles)
    if any(type(value) is not bytes for _, value in raw_snapshots):
        raise PtmLocalizationRawInputError(PtmLocalizationRawInputErrorCode.ARTIFACT_TYPE_INVALID)
    return cast("tuple[tuple[object, bytes], ...]", raw_snapshots)


def _trusted_artifacts_by_role(
    request: IngestPtmLocalizationRawInputsRequest,
    contracts: Any,  # noqa: ANN401 - delayed public contract module.
) -> dict[object, Any]:
    artifacts_by_role: dict[object, Any] = {
        artifact.role: artifact for artifact in request.artifacts
    }
    expected_roles = tuple(contracts.PtmLocalizationRawInputRole)
    if len(artifacts_by_role) != contracts.M0503_ROLE_COUNT or any(
        role not in artifacts_by_role for role in expected_roles
    ):
        raise PtmLocalizationRawInputError(
            PtmLocalizationRawInputErrorCode.ARTIFACT_MAPPING_MISMATCH
        )
    return artifacts_by_role


def _enforce_snapshot_caps(
    request: IngestPtmLocalizationRawInputsRequest,
    snapshots: tuple[tuple[object, bytes], ...],
    artifacts_by_role: dict[object, Any],
    contracts: Any,  # noqa: ANN401 - delayed public contract module.
) -> None:
    # Complete every declared/per-document/aggregate cap before hashing or parsing.
    total = 0
    for role, payload in snapshots:
        artifact = artifacts_by_role[role]
        total += len(payload)
        active_limit = _active_document_limit(request, artifact, contracts)
        if (
            len(payload) > active_limit
            or len(payload) != artifact.declared_size_bytes
            or total
            > min(
                request.policy.max_total_bytes,
                contracts.M0503_MAX_TOTAL_DOCUMENT_BYTES,
            )
        ):
            raise PtmLocalizationRawInputError(
                PtmLocalizationRawInputErrorCode.ARTIFACT_SIZE_MISMATCH
            )


def _verify_snapshot_digests(
    snapshots: tuple[tuple[object, bytes], ...],
    artifacts_by_role: dict[object, Any],
) -> None:
    for role, payload in snapshots:
        payload_digest = f"sha256:{sha256(payload).hexdigest()}"
        if payload_digest != artifacts_by_role[role].manifest_reference.digest:
            raise PtmLocalizationRawInputError(
                PtmLocalizationRawInputErrorCode.ARTIFACT_DIGEST_MISMATCH
            )


def _parse_snapshot_documents(
    request: IngestPtmLocalizationRawInputsRequest,
    snapshots: tuple[tuple[object, bytes], ...],
    contracts: Any,  # noqa: ANN401 - delayed public contract module.
) -> tuple[BaseModel, ...]:
    document_models = {
        contracts.PtmLocalizationRawInputRole.MASS_SPECTROMETRY_PROTEOME: (
            contracts.MassSpectrometryProteomeInputDocument
        ),
        contracts.PtmLocalizationRawInputRole.GENOME: contracts.GenomeInputDocument,
        contracts.PtmLocalizationRawInputRole.TRANSCRIPTOME: contracts.TranscriptomeInputDocument,
        contracts.PtmLocalizationRawInputRole.PTM_ANNOTATIONS: contracts.PtmAnnotationInputDocument,
    }
    documents: list[BaseModel] = []
    for role, payload in snapshots:
        model = document_models[role]
        artifact = next(item for item in request.artifacts if item.role is role)
        active_limit = _active_document_limit(request, artifact, contracts)
        try:
            decoded = strict_json_loads(payload, max_bytes=active_limit)
        except (StrictJsonError, ValueError):
            raise PtmLocalizationRawInputError(
                PtmLocalizationRawInputErrorCode.DOCUMENT_JSON_INVALID
            ) from None
        expected_type = _document_type_literal(model)
        if type(decoded) is not dict or dict.get(decoded, "document_type") != expected_type:
            raise PtmLocalizationRawInputError(
                PtmLocalizationRawInputErrorCode.DOCUMENT_TYPE_MISMATCH
            )
        try:
            python_value = _strict_document_python_value(model, decoded)
            document = TypeAdapter(model).validate_python(python_value, strict=True)
        except (ValidationError, ValueError):
            raise PtmLocalizationRawInputError(
                PtmLocalizationRawInputErrorCode.DOCUMENT_JSON_INVALID
            ) from None
        if canonical_json_bytes(contracts.normalized_document(document)) != payload:
            raise PtmLocalizationRawInputError(
                PtmLocalizationRawInputErrorCode.DOCUMENT_NOT_CANONICAL
            )
        documents.append(document)
    return tuple(documents)


def _strict_document_python_value(  # noqa: C901 - closed strict annotation matrix.
    model: type[BaseModel],
    decoded: Mapping[str, object],
) -> dict[str, object]:
    """Materialize only exact JSON enum and tuple shapes for strict Python validation."""

    result = dict(decoded)
    for field_name, field in model.model_fields.items():
        if field_name not in result:
            continue
        annotation = field.annotation
        value = result[field_name]
        annotation_mro = (
            type.__getattribute__(annotation, "__mro__") if isinstance(annotation, type) else ()
        )
        if StrEnum in annotation_mro:
            if type(value) is not str:
                raise PtmLocalizationRawInputError(
                    PtmLocalizationRawInputErrorCode.DOCUMENT_JSON_INVALID
                )
            result[field_name] = cast("type[StrEnum]", annotation)(value)
            continue
        if get_origin(annotation) is tuple:
            if type(value) is not list:
                raise PtmLocalizationRawInputError(
                    PtmLocalizationRawInputErrorCode.DOCUMENT_JSON_INVALID
                )
            item_annotation = get_args(annotation)[0]
            item_mro = (
                type.__getattribute__(item_annotation, "__mro__")
                if isinstance(item_annotation, type)
                else ()
            )
            if StrEnum in item_mro:
                if any(type(item) is not str for item in value):
                    raise PtmLocalizationRawInputError(
                        PtmLocalizationRawInputErrorCode.DOCUMENT_JSON_INVALID
                    )
                enum_type = cast("type[StrEnum]", item_annotation)
                result[field_name] = tuple(enum_type(item) for item in value)
            elif BaseModel in item_mro:
                if any(type(item) is not dict for item in value):
                    raise PtmLocalizationRawInputError(
                        PtmLocalizationRawInputErrorCode.DOCUMENT_JSON_INVALID
                    )
                nested_model = cast("type[BaseModel]", item_annotation)
                try:
                    result[field_name] = tuple(
                        TypeAdapter(nested_model).validate_python(item, strict=True)
                        for item in value
                    )
                except ValidationError:
                    raise PtmLocalizationRawInputError(
                        PtmLocalizationRawInputErrorCode.DOCUMENT_JSON_INVALID
                    ) from None
            else:
                result[field_name] = tuple(value)
    return result


def _active_document_limit(
    request: IngestPtmLocalizationRawInputsRequest,
    artifact: Any,  # noqa: ANN401 - delayed public contract model.
    contracts: Any,  # noqa: ANN401 - delayed public contract module.
) -> int:
    base_limit: int = min(
        request.policy.max_document_bytes,
        cast("int", contracts.M0503_MAX_DOCUMENT_BYTES),
    )
    matching = next(
        (
            parser
            for parser in request.policy.approved_parsers
            if parser.role is artifact.role
            and parser.format is artifact.format
            and parser.format_version == artifact.format_version
            and parser.parser_version == artifact.parser_version
        ),
        None,
    )
    return base_limit if matching is None else min(base_limit, matching.max_document_bytes)


def _document_type_literal(model: type[BaseModel]) -> object:
    field = model.model_fields["document_type"]
    if type(field.default) is str:
        return field.default
    literals = get_args(field.annotation)
    if len(literals) == 1 and type(literals[0]) is str:
        return literals[0]
    raise _InvalidDocumentContractError


def _result(
    request: IngestPtmLocalizationRawInputsRequest,
    documents: tuple[BaseModel, ...],
) -> PtmLocalizationRawInputValidationResult:
    contracts = _contracts()
    diagnostics = contracts.expected_diagnostics(request, documents)
    validated_inputs = contracts.expected_validated_inputs(
        request,
        documents,
        diagnostics,
    )
    actions = {item.action.value for item in diagnostics}
    disposition = (
        contracts.PtmLocalizationRawInputDisposition.QUARANTINED
        if "quarantine" in actions
        else contracts.PtmLocalizationRawInputDisposition.ABSTAINED
        if "abstain" in actions
        else contracts.PtmLocalizationRawInputDisposition.VALIDATED
    )
    request_hash = contracts.canonical_request_digest(request)
    policy_hash = contracts.policy_digest(request.policy)
    configuration_hash = contracts.configuration_digest(request.policy)
    payload: dict[str, object] = {
        "output_type": "ptm_localization_raw_input_validation_result",
        "result_id": f"result.m0503.{request_hash.removeprefix('sha256:')}",
        "result_version": "1.0.0",
        "request_digest": request_hash,
        "lineage_result_digest": request.lineage_result.result_digest,
        "policy_digest": policy_hash,
        "configuration_digest": configuration_hash,
        "context_digest": contracts.context_digest(request),
        "result_digest": _ZERO_DIGEST,
        "request": request,
        "receipt": contracts.expected_receipt(
            request,
            validated_inputs,
            diagnostics,
            disposition,
        ),
        "validated_inputs": validated_inputs,
        "diagnostics": diagnostics,
        "disposition": disposition,
        "parent_target": "variant_peptide",
        "emits_variant_peptide": False,
        "emits_proteogenomic_state": False,
        "emits_proteotype": False,
        "emits_protein_level_subtype": False,
        "infers_identity": False,
        "infers_consent": False,
        "infers_protein": False,
        "infers_proteoform": False,
        "infers_ptm_localization": False,
        "infers_kinase_activity": False,
        "performs_cn_to_protein_regression": False,
        "performs_all_omics_fusion": False,
        "recommends_treatment": False,
        "mutates_upstream": False,
        "executes_model": False,
        "persists_events": False,
        "support": contracts.expected_support(disposition),
        "uncertainty": contracts.expected_uncertainty(),
        "provenance": contracts.expected_provenance(
            request,
            request_hash,
            validated_inputs,
        ),
        "evidence": contracts.raw_input_evidence_index(request),
        "limitations": contracts.expected_limitations(),
        "human_review_required": disposition.value != "validated",
        "completed_at": request.context.occurred_at,
    }
    payload["result_digest"] = contracts.result_payload_digest(payload)
    return cast(
        "PtmLocalizationRawInputValidationResult",
        TypeAdapter(contracts.PtmLocalizationRawInputValidationResult).validate_python(
            payload,
            strict=True,
        ),
    )


def _validate_outer_request_shape(candidate: object, contracts: Any) -> None:  # noqa: ANN401
    if type(candidate) is contracts.IngestPtmLocalizationRawInputsRequest:
        try:
            _validate_exact_request_storage(candidate)
        except ValueError:
            raise _InvalidPlainValueError from None
        return
    if type(candidate) is not dict:
        raise _InvalidPlainValueError
    mapping = cast("dict[object, object]", candidate)
    _validate_plain_mapping(mapping)
    if any(key not in _REQUEST_FIELDS for key in dict.keys(mapping)):
        raise _InvalidPlainValueError


def _member(candidate: object, field: str) -> object:
    candidate_mro = type.__getattribute__(type(candidate), "__mro__")
    if type(candidate) is dict:
        mapping = cast("dict[object, object]", candidate)
        _validate_plain_mapping(mapping)
        return dict.get(mapping, field)
    if BaseModel in candidate_mro:
        storage = cast("dict[object, object]", object.__getattribute__(candidate, "__dict__"))
        _validate_plain_mapping(storage)
        return dict.get(storage, field)
    return None


def _validate_plain_mapping(mapping: dict[object, object]) -> None:
    if (
        type(mapping) is not dict
        or dict.__len__(mapping) > _MAX_PLAIN_DICT_ITEMS
        or any(type(key) is not str for key in dict.keys(mapping))
    ):
        raise _InvalidPlainValueError


def _state_text(candidate: object) -> object:
    candidate_type = type(candidate)
    if candidate_type is str:
        return candidate
    candidate_mro = type.__getattribute__(candidate_type, "__mro__")
    if StrEnum in candidate_mro:
        value = object.__getattribute__(candidate, "_value_")
        return value if type(value) is str else None
    return None


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
        storage = cast("dict[object, object]", object.__getattribute__(candidate, "__dict__"))
        _validate_plain_mapping(storage)
        return {
            key: _plain_value(
                dict.__getitem__(storage, key),
                _depth=_depth + 1,
                _budget=budget,
            )
            for key in dict.keys(storage)
        }
    if type(candidate) is dict:
        mapping = cast("dict[object, object]", candidate)
        _validate_plain_mapping(mapping)
        return {
            key: _plain_value(
                dict.__getitem__(mapping, key),
                _depth=_depth + 1,
                _budget=budget,
            )
            for key in dict.keys(mapping)
        }
    if type(candidate) is list:
        list_values = cast("list[object]", candidate)
        if list.__len__(list_values) > _MAX_PLAIN_SEQUENCE:
            raise _InvalidPlainValueError
        return [
            _plain_value(item, _depth=_depth + 1, _budget=budget)
            for item in list.__iter__(list_values)
        ]
    if type(candidate) is tuple:
        tuple_values = cast("tuple[object, ...]", candidate)
        if tuple.__len__(tuple_values) > _MAX_PLAIN_SEQUENCE:
            raise _InvalidPlainValueError
        return tuple(
            _plain_value(item, _depth=_depth + 1, _budget=budget)
            for item in tuple.__iter__(tuple_values)
        )
    if StrEnum in candidate_mro:
        value = object.__getattribute__(candidate, "_value_")
        if type(value) is not str:
            raise _InvalidPlainValueError
        return candidate
    if isinstance(candidate, Mapping) or (
        not isinstance(candidate, str) and isinstance(candidate, Sequence)
    ):
        raise _InvalidPlainValueError
    return candidate


__all__ = [
    "M0503PtmLocalizationRawInputIngester",
    "PtmLocalizationRawInputAuthorizationError",
    "PtmLocalizationRawInputError",
    "PtmLocalizationRawInputErrorCode",
    "ingest_ptm_localization_raw_inputs",
    "preflight_ptm_localization_raw_input_authorization",
]
