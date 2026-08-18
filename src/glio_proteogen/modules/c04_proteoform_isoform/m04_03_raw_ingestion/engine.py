"""Deterministic M04-03 canonical raw-manifest ingestion engine."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import TYPE_CHECKING, Any, Final, cast, get_args, get_origin

from pydantic import BaseModel, TypeAdapter, ValidationError

from glio_proteogen.contracts import m04_03 as _m0403_contracts
from glio_proteogen.contracts.m04_02 import ProteoformIdentityLineageResolution
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

if TYPE_CHECKING:
    from glio_proteogen.contracts.m04_03 import (
        IngestProteoformRawInputsRequest,
        ProteoformRawInputValidationResult,
    )

_AUTHORIZATION_MESSAGE: Final = "proteoform raw-input ingestion requires accepted upstream controls"
_MAX_PLAIN_DEPTH: Final = 64
_MAX_PLAIN_DICT_ITEMS: Final = 512
_MAX_PLAIN_SEQUENCE_ITEMS: Final = 250_000
_MAX_PLAIN_NODES: Final = 250_000


def _contracts() -> Any:  # noqa: ANN401 - shared private module accessor.
    return _m0403_contracts


class ProteoformRawInputAuthorizationError(PermissionError):
    """Authorization failed before request or raw-manifest traversal."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class ProteoformRawInputErrorCode(StrEnum):
    """Stable, content-free structural and integrity failures."""

    ARTIFACT_MAPPING_MISMATCH = "artifact_mapping_mismatch"
    ARTIFACT_TYPE_INVALID = "artifact_type_invalid"
    ARTIFACT_SIZE_MISMATCH = "artifact_size_mismatch"
    ARTIFACT_DIGEST_MISMATCH = "artifact_digest_mismatch"
    DOCUMENT_JSON_INVALID = "document_json_invalid"
    DOCUMENT_NOT_CANONICAL = "document_not_canonical"
    DOCUMENT_TYPE_MISMATCH = "document_type_mismatch"


class ProteoformRawInputError(ValueError):
    """A submitted manifest mapping or document failed the strict boundary."""

    def __init__(self, code: ProteoformRawInputErrorCode) -> None:
        self.code = code
        super().__init__(f"M04-03 input rejected: {code.value}")


class _InvalidPreparedInputError(TypeError):
    def __init__(self) -> None:
        super().__init__("M04-03 prepared input capability is invalid")


class _InvalidDocumentContractError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("M04-03 document model lacks one exact document type")


class _InvalidPlainValueError(TypeError):
    def __init__(self) -> None:
        super().__init__("M04-03 strict request values require exact string keys")


@dataclass(frozen=True, slots=True)
class _PreparedProteoformRawInputs:
    """Once-read immutable bytes and their strict parsed document projections."""

    snapshots: tuple[tuple[object, bytes], ...]
    documents: tuple[BaseModel, ...]


class M0403ProteoformRawInputIngester:
    """Validate four exact canonical manifest documents without opening their content refs."""

    __slots__ = ()

    def ingest(
        self,
        request: object,
        artifacts_by_role: object,
    ) -> ProteoformRawInputValidationResult:
        """Authorize, replay, snapshot, validate, and seal one immutable result."""

        contracts = _contracts()
        preflight_proteoform_raw_input_authorization(request)
        adapter: TypeAdapter[Any] = TypeAdapter(contracts.IngestProteoformRawInputsRequest)
        validated = adapter.validate_python(_plain_value(request), strict=True)
        canonical = adapter.validate_json(
            canonical_json_bytes(contracts.normalized_request(validated)),
            strict=True,
        )
        # Revalidate the full public M04-02 envelope independently of compact projections.
        TypeAdapter(ProteoformIdentityLineageResolution).validate_python(
            canonical.lineage_result,
            strict=True,
        )
        upstream_disposition = canonical.lineage_result.disposition.value
        if upstream_disposition != "reconciled":
            return _result(canonical, ())
        prepared = _prepare_proteoform_raw_inputs(canonical, artifacts_by_role)
        return self._ingest_prepared(canonical, prepared)

    def _ingest_prepared(
        self,
        request: IngestProteoformRawInputsRequest,
        prepared: _PreparedProteoformRawInputs,
    ) -> ProteoformRawInputValidationResult:
        """Seal a result from one private capability without re-reading caller bytes."""

        if type(prepared) is not _PreparedProteoformRawInputs:
            raise _InvalidPreparedInputError
        return _result(request, prepared.documents)


def ingest_proteoform_raw_inputs(
    request: object,
    artifacts_by_role: object,
) -> ProteoformRawInputValidationResult:
    """Public stateless M04-03 operation."""

    return M0403ProteoformRawInputIngester().ingest(request, artifacts_by_role)


def preflight_proteoform_raw_input_authorization(candidate: object) -> None:
    """Check seven states before touching governed or byte-bearing fields."""

    try:
        contracts = _contracts()
        candidate_mro = type.__getattribute__(type(candidate), "__mro__")
        supported = (
            type(candidate) is contracts.IngestProteoformRawInputsRequest or dict in candidate_mro
        )
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
        raise ProteoformRawInputAuthorizationError from None
    if not authorized:
        raise ProteoformRawInputAuthorizationError


def _prepare_proteoform_raw_inputs(
    request: IngestProteoformRawInputsRequest,
    supplied: object,
) -> _PreparedProteoformRawInputs:
    """Snapshot, cap, hash, and parse an exact built-in role mapping once."""

    contracts = _contracts()
    snapshots = _snapshot_role_mapping(supplied, contracts)
    artifacts_by_role = _trusted_artifacts_by_role(request, contracts)
    _enforce_snapshot_caps(request, snapshots, artifacts_by_role, contracts)
    _verify_snapshot_digests(snapshots, artifacts_by_role)
    return _PreparedProteoformRawInputs(
        snapshots=snapshots,
        documents=_parse_snapshot_documents(request, snapshots, contracts),
    )


def _snapshot_role_mapping(
    supplied: object,
    contracts: Any,  # noqa: ANN401 - delayed public contract module.
) -> tuple[tuple[object, bytes], ...]:
    supplied_mro = type.__getattribute__(type(supplied), "__mro__")
    if dict not in supplied_mro:
        raise ProteoformRawInputError(ProteoformRawInputErrorCode.ARTIFACT_MAPPING_MISMATCH)
    mapping = cast("dict[object, object]", supplied)
    role_type = contracts.ProteoformRawInputRole
    expected_roles = tuple(role_type)
    if dict.__len__(mapping) != contracts.M0403_ROLE_COUNT:
        raise ProteoformRawInputError(ProteoformRawInputErrorCode.ARTIFACT_MAPPING_MISMATCH)
    caller_keys = tuple(dict.__iter__(mapping))
    if any(type(key) is not role_type for key in caller_keys) or any(
        not any(key is expected for key in caller_keys) for expected in expected_roles
    ):
        raise ProteoformRawInputError(ProteoformRawInputErrorCode.ARTIFACT_MAPPING_MISMATCH)
    raw_snapshots = tuple((role, dict.__getitem__(mapping, role)) for role in expected_roles)
    if any(type(value) is not bytes for _, value in raw_snapshots):
        raise ProteoformRawInputError(ProteoformRawInputErrorCode.ARTIFACT_TYPE_INVALID)
    return cast("tuple[tuple[object, bytes], ...]", raw_snapshots)


def _trusted_artifacts_by_role(
    request: IngestProteoformRawInputsRequest,
    contracts: Any,  # noqa: ANN401 - delayed public contract module.
) -> dict[object, Any]:
    artifacts_by_role: dict[object, Any] = {
        artifact.role: artifact for artifact in request.artifacts
    }
    expected_roles = tuple(contracts.ProteoformRawInputRole)
    if len(artifacts_by_role) != contracts.M0403_ROLE_COUNT or any(
        role not in artifacts_by_role for role in expected_roles
    ):
        raise ProteoformRawInputError(ProteoformRawInputErrorCode.ARTIFACT_MAPPING_MISMATCH)
    return artifacts_by_role


def _enforce_snapshot_caps(
    request: IngestProteoformRawInputsRequest,
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
                contracts.M0403_MAX_TOTAL_DOCUMENT_BYTES,
            )
        ):
            raise ProteoformRawInputError(ProteoformRawInputErrorCode.ARTIFACT_SIZE_MISMATCH)


def _verify_snapshot_digests(
    snapshots: tuple[tuple[object, bytes], ...],
    artifacts_by_role: dict[object, Any],
) -> None:
    for role, payload in snapshots:
        payload_digest = f"sha256:{sha256(payload).hexdigest()}"
        if payload_digest != artifacts_by_role[role].manifest_reference.digest:
            raise ProteoformRawInputError(ProteoformRawInputErrorCode.ARTIFACT_DIGEST_MISMATCH)


def _parse_snapshot_documents(
    request: IngestProteoformRawInputsRequest,
    snapshots: tuple[tuple[object, bytes], ...],
    contracts: Any,  # noqa: ANN401 - delayed public contract module.
) -> tuple[BaseModel, ...]:
    document_models = {
        contracts.ProteoformRawInputRole.MASS_SPECTROMETRY_PROTEOME: (
            contracts.MassSpectrometryProteomeInputDocument
        ),
        contracts.ProteoformRawInputRole.GENOME: contracts.GenomeInputDocument,
        contracts.ProteoformRawInputRole.TRANSCRIPTOME: contracts.TranscriptomeInputDocument,
        contracts.ProteoformRawInputRole.PTM_ANNOTATIONS: contracts.PtmAnnotationInputDocument,
    }
    documents: list[BaseModel] = []
    for role, payload in snapshots:
        model = document_models[role]
        artifact = next(item for item in request.artifacts if item.role is role)
        active_limit = _active_document_limit(request, artifact, contracts)
        try:
            decoded = strict_json_loads(payload, max_bytes=active_limit)
        except (StrictJsonError, ValueError):
            raise ProteoformRawInputError(
                ProteoformRawInputErrorCode.DOCUMENT_JSON_INVALID
            ) from None
        expected_type = _document_type_literal(model)
        if type(decoded) is not dict or dict.get(decoded, "document_type") != expected_type:
            raise ProteoformRawInputError(ProteoformRawInputErrorCode.DOCUMENT_TYPE_MISMATCH)
        try:
            python_value = _strict_document_python_value(model, decoded)
            document = TypeAdapter(model).validate_python(python_value, strict=True)
        except (ValidationError, ValueError):
            raise ProteoformRawInputError(
                ProteoformRawInputErrorCode.DOCUMENT_JSON_INVALID
            ) from None
        if canonical_json_bytes(contracts.normalized_document(document)) != payload:
            raise ProteoformRawInputError(ProteoformRawInputErrorCode.DOCUMENT_NOT_CANONICAL)
        documents.append(document)
    return tuple(documents)


def _strict_document_python_value(
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
                raise ProteoformRawInputError(ProteoformRawInputErrorCode.DOCUMENT_JSON_INVALID)
            result[field_name] = cast("type[StrEnum]", annotation)(value)
            continue
        if get_origin(annotation) is tuple:
            if type(value) is not list:
                raise ProteoformRawInputError(ProteoformRawInputErrorCode.DOCUMENT_JSON_INVALID)
            item_annotation = get_args(annotation)[0]
            item_mro = (
                type.__getattribute__(item_annotation, "__mro__")
                if isinstance(item_annotation, type)
                else ()
            )
            if StrEnum in item_mro:
                if any(type(item) is not str for item in value):
                    raise ProteoformRawInputError(ProteoformRawInputErrorCode.DOCUMENT_JSON_INVALID)
                enum_type = cast("type[StrEnum]", item_annotation)
                result[field_name] = tuple(enum_type(item) for item in value)
            else:
                result[field_name] = tuple(value)
    return result


def _active_document_limit(
    request: IngestProteoformRawInputsRequest,
    artifact: Any,  # noqa: ANN401 - delayed public contract model.
    contracts: Any,  # noqa: ANN401 - delayed public contract module.
) -> int:
    base_limit: int = min(
        request.policy.max_document_bytes,
        cast("int", contracts.M0403_MAX_DOCUMENT_BYTES),
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
    request: IngestProteoformRawInputsRequest,
    documents: tuple[BaseModel, ...],
) -> ProteoformRawInputValidationResult:
    contracts = _contracts()
    diagnostics = contracts.expected_diagnostics(request, documents)
    validated_inputs = contracts.expected_validated_inputs(
        request,
        documents,
        diagnostics,
    )
    actions = {item.action.value for item in diagnostics}
    disposition = (
        contracts.ProteoformRawInputDisposition.QUARANTINED
        if "quarantine" in actions
        else contracts.ProteoformRawInputDisposition.ABSTAINED
        if "abstain" in actions
        else contracts.ProteoformRawInputDisposition.VALIDATED
    )
    request_hash = contracts.canonical_request_digest(request)
    policy_hash = contracts.policy_digest(request.policy)
    configuration_hash = contracts.configuration_digest(request.policy)
    payload: dict[str, object] = {
        "output_type": "proteoform_raw_input_validation_result",
        "result_id": f"result.m0403.{request_hash.removeprefix('sha256:')}",
        "result_version": "1.0.0",
        "request_digest": request_hash,
        "lineage_result_digest": request.lineage_result.result_digest,
        "policy_digest": policy_hash,
        "configuration_digest": configuration_hash,
        "context_digest": contracts.context_digest(request),
        "result_digest": contracts.M0403_ZERO_DIGEST,
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
        "infers_glioma_specific_biology": False,
        "infers_kinase_activity": False,
        "performs_cn_to_protein_regression": False,
        "performs_all_omics_fusion": False,
        "recommends_treatment": False,
        "mutates_upstream": False,
        "executes_model": False,
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
        "ProteoformRawInputValidationResult",
        TypeAdapter(contracts.ProteoformRawInputValidationResult).validate_python(
            payload,
            strict=True,
        ),
    )


def _member(candidate: object, field: str) -> object:
    candidate_mro = type.__getattribute__(type(candidate), "__mro__")
    if dict in candidate_mro:
        return dict.get(cast("dict[object, object]", candidate), field)
    if BaseModel in candidate_mro:
        storage = object.__getattribute__(candidate, "__dict__")
        return dict.get(cast("dict[object, object]", storage), field)
    return None


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
        if type(storage) is not dict or any(type(key) is not str for key in dict.keys(storage)):
            raise _InvalidPlainValueError
        if dict.__len__(storage) > _MAX_PLAIN_DICT_ITEMS:
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
        if dict.__len__(mapping) > _MAX_PLAIN_DICT_ITEMS or any(
            type(key) is not str for key in dict.keys(mapping)
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
        if list.__len__(list_values) > _MAX_PLAIN_SEQUENCE_ITEMS:
            raise _InvalidPlainValueError
        return [
            _plain_value(item, _depth=_depth + 1, _budget=budget)
            for item in list.__iter__(list_values)
        ]
    if tuple in candidate_mro:
        tuple_values = cast("tuple[object, ...]", candidate)
        if tuple.__len__(tuple_values) > _MAX_PLAIN_SEQUENCE_ITEMS:
            raise _InvalidPlainValueError
        return tuple(
            _plain_value(item, _depth=_depth + 1, _budget=budget)
            for item in tuple.__iter__(tuple_values)
        )
    if Mapping in candidate_mro:
        raise _InvalidPlainValueError
    return candidate


__all__ = [
    "M0403ProteoformRawInputIngester",
    "ProteoformRawInputAuthorizationError",
    "ProteoformRawInputError",
    "ProteoformRawInputErrorCode",
    "ingest_proteoform_raw_inputs",
    "preflight_proteoform_raw_input_authorization",
]
