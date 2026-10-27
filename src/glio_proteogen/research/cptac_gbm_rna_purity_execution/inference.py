"""Private source-qualified bridge to the unchanged published GBMPurity service.

Source retrieval, clinical interpretation and exact lineage admission belong to
the owning orchestration. This module binds its owned assessments to immutable
count snapshots; a checksum is not an authentication of a clinical assertion.
No private request, individual result or feature buffer is implicitly exported.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Literal, NoReturn, Protocol, Self, SupportsIndex

import numpy as np
import numpy.typing as npt
from pydantic import Field, model_validator

from glio_proteogen.kernel.models import FrozenModel, Sha256Digest
from glio_proteogen.research.cptac_gbm_rna_purity_admission.context import ContextState
from glio_proteogen.research.cptac_gbm_rna_purity_admission.identity import _released_metadata
from glio_proteogen.research.gbm_rna_purity.catalog import (
    EXPECTED_ARTIFACT_SHA256,
    EXPECTED_CONTENT_DIGEST,
    EXPECTED_FEATURE_ORDER_DIGEST,
    EXPECTED_SOURCE_FEATURE_SHA256,
    EXPECTED_SOURCE_MODEL_SHA256,
    EXPECTED_WEIGHT_TENSOR_DIGEST,
)
from glio_proteogen.research.gbm_rna_purity.contracts import (
    REQUIRED_CONTEXT,
    ClippingState,
    GbmRnaPurityRequest,
    GbmRnaPurityResult,
    PuritySupport,
    RawGeneCount,
    request_digest,
)
from glio_proteogen.research.gbm_rna_purity.profile import algorithm_profile
from glio_proteogen.research.gbm_rna_purity.service import analyze_gbm_rna_purity

from .contracts import (
    ExecutionError,
    ExecutionPolicy,
    canonical_bytes,
    checked_policy,
    digest,
    validate_digest,
)

_FEATURE_COUNT = 5_829
_MAX_COUNT = 10**15
_MINIMUM_RECOGNIZED = 4_664
_SUPPORTED_RECOGNIZED = 5_771
_Count = Annotated[int, Field(ge=0, le=_FEATURE_COUNT)]
ComponentStates = tuple[
    ContextState,
    ContextState,
    ContextState,
    ContextState,
    ContextState,
    ContextState,
    ContextState,
]
InferenceOutcome = Literal[
    "estimated",
    "context_unknown",
    "context_out_of_scope",
    "context_conflicting",
    "below_coverage_gate",
    "zero_recognized_sum",
    "limited_support_disallowed",
]


class ProjectionReceipt(Protocol):
    """Only the aggregate fields needed to revalidate an owned native projection."""

    @property
    def model_axis_digest(self) -> str: ...

    @property
    def recognized_model_gene_count(self) -> int: ...

    @property
    def nonzero_model_gene_count(self) -> int: ...

    @property
    def observed_zero_model_gene_count(self) -> int: ...

    @property
    def recognized_raw_count_sum(self) -> int: ...

    @property
    def count_ready(self) -> bool: ...

    @property
    def coverage_supported(self) -> bool: ...


class QualifiedProjection(Protocol):
    @property
    def counts(self) -> npt.NDArray[np.int64]: ...

    @property
    def states(self) -> npt.NDArray[np.uint8]: ...

    @property
    def receipt(self) -> ProjectionReceipt: ...

    @property
    def binding_digest(self) -> str: ...


class SourceFeature(Protocol):
    @property
    def source_symbol(self) -> str: ...

    @property
    def source_length(self) -> float: ...


class SourceAxis(Protocol):
    @property
    def features(self) -> tuple[SourceFeature, ...]: ...

    @property
    def digest(self) -> str: ...


class _ProjectionMetadata(FrozenModel):
    model_axis_digest: Sha256Digest
    recognized_model_gene_count: _Count
    nonzero_model_gene_count: _Count
    observed_zero_model_gene_count: _Count
    recognized_raw_count_sum: int = Field(ge=0, le=_FEATURE_COUNT * _MAX_COUNT)
    count_ready: bool
    coverage_supported: bool


@dataclass(frozen=True, slots=True, repr=False)
class _ProjectionSnapshot:
    count_bytes: bytes = field(repr=False)
    state_bytes: bytes = field(repr=False)
    metadata: _ProjectionMetadata = field(repr=False)
    binding_digest: str
    content_digest: str

    @property
    def counts(self) -> npt.NDArray[np.int64]:
        return np.frombuffer(self.count_bytes, dtype=np.int64)

    @property
    def states(self) -> npt.NDArray[np.uint8]:
        return np.frombuffer(self.state_bytes, dtype=np.uint8)


def _snapshot_projection(projection: QualifiedProjection) -> _ProjectionSnapshot:
    try:
        receipt = projection.receipt
        metadata = _ProjectionMetadata(
            model_axis_digest=receipt.model_axis_digest,
            recognized_model_gene_count=receipt.recognized_model_gene_count,
            nonzero_model_gene_count=receipt.nonzero_model_gene_count,
            observed_zero_model_gene_count=receipt.observed_zero_model_gene_count,
            recognized_raw_count_sum=receipt.recognized_raw_count_sum,
            count_ready=receipt.count_ready,
            coverage_supported=receipt.coverage_supported,
        )
        declared_binding = validate_digest(projection.binding_digest)
        counts = projection.counts
        states = projection.states
        if (
            type(counts) is not np.ndarray
            or counts.dtype != np.dtype(np.int64)
            or counts.shape != (_FEATURE_COUNT,)
            or type(states) is not np.ndarray
            or states.dtype != np.dtype(np.uint8)
            or states.shape != counts.shape
        ):
            raise ExecutionError("native projection buffers are invalid")  # noqa: TRY301 -- sanitized boundary
        count_bytes = np.ascontiguousarray(counts).tobytes()
        state_bytes = np.ascontiguousarray(states).tobytes()
        counts = np.frombuffer(count_bytes, dtype=np.int64)
        states = np.frombuffer(state_bytes, dtype=np.uint8)
        if (
            bool(np.any(states >= 6))
            or bool(np.any((states == 0) & ((counts <= 0) | (counts > _MAX_COUNT))))
            or bool(np.any((states == 1) & (counts != 0)))
            or bool(np.any((states >= 2) & (counts != -1)))
        ):
            raise ExecutionError("native projection availability is inconsistent")  # noqa: TRY301 -- sanitized boundary
        positive = int(np.sum(states == 0))
        zero = int(np.sum(states == 1))
        recognized = positive + zero
        total = sum(int(value) for value in counts[counts >= 0])
        if (
            metadata.recognized_model_gene_count != recognized
            or metadata.nonzero_model_gene_count != positive
            or metadata.observed_zero_model_gene_count != zero
            or metadata.recognized_raw_count_sum != total
            or metadata.count_ready != (recognized >= _MINIMUM_RECOGNIZED and total > 0)
            or metadata.coverage_supported != (recognized >= _SUPPORTED_RECOGNIZED)
        ):
            raise ExecutionError("native projection receipt disagrees with its snapshot")  # noqa: TRY301 -- sanitized boundary
        content_digest = digest(
            {
                "receipt": metadata.model_dump(mode="json"),
                "counts": counts.tolist(),
                "states": states.tolist(),
            }
        )
    except ExecutionError:
        raise
    except (AttributeError, TypeError, ValueError, OverflowError):
        raise ExecutionError("native projection was not accepted") from None
    return _ProjectionSnapshot(count_bytes, state_bytes, metadata, declared_binding, content_digest)


def projection_content_digest(projection: QualifiedProjection) -> str:
    """Bind the actual copied buffers, separately from the producer's declared seal."""
    return _snapshot_projection(projection).content_digest


class _Private:
    __slots__ = ()

    def __setattr__(self, _name: str, _value: object) -> NoReturn:
        raise AttributeError("private execution data is immutable")

    def __delattr__(self, _name: str) -> NoReturn:
        raise AttributeError("private execution data is immutable")

    def __repr__(self) -> str:
        return f"<{type(self).__name__} private>"

    def __getstate__(self) -> NoReturn:
        raise TypeError("private execution data cannot be implicitly serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("private execution data cannot be implicitly serialized")


class _QualificationDocument(FrozenModel):
    schema_version: Literal["cptac-gbm-rna-purity-execution-qualification/1.0.0"] = (
        "cptac-gbm-rna-purity-execution-qualification/1.0.0"
    )
    component_states: ComponentStates
    protocol_digest: Sha256Digest
    model_axis_digest: Sha256Digest
    projection_digest: Sha256Digest
    projection_content_digest: Sha256Digest
    context_evidence_digest: Sha256Digest
    context_source_set_digest: Sha256Digest
    lineage_digest: Sha256Digest
    policy_digest: Sha256Digest
    qualification_digest: Sha256Digest

    @model_validator(mode="after")
    def qualification_seal_matches(self) -> Self:
        values = self.model_dump(mode="json")
        declared = values.pop("qualification_digest")
        if digest(values) != declared:
            raise ValueError("execution qualification seal is invalid")
        return self


def _validated_qualification(payload: bytes) -> _QualificationDocument:
    try:
        if type(payload) is not bytes or not 1 <= len(payload) <= 8_192:
            raise ExecutionError("execution qualification storage is invalid")  # noqa: TRY301 -- sanitized boundary
        checked = _QualificationDocument.model_validate_json(payload)
        if canonical_bytes(checked.model_dump(mode="json")) != payload:
            raise ExecutionError("execution qualification storage is not canonical")  # noqa: TRY301 -- sanitized boundary
    except ExecutionError:
        raise
    except (TypeError, ValueError):
        raise ExecutionError("execution qualification was not accepted") from None
    return checked


class ExecutionQualification(_Private):
    """Owned source assessments bound to one exact projection and execution policy.

    Only the source-admitting orchestration may establish the component claims.
    This object checks bindings and corruption; it does not authenticate medicine.
    """

    __slots__ = ("_payload",)
    _payload: bytes

    def __init__(self, document: _QualificationDocument) -> None:
        if type(document) is not _QualificationDocument:
            raise ExecutionError("a validated execution qualification is required")
        payload = canonical_bytes(document.model_dump(mode="json"))
        _validated_qualification(payload)
        object.__setattr__(self, "_payload", payload)

    @property
    def binding_digest(self) -> str:
        return _validated_qualification(self._payload).qualification_digest

    @property
    def component_states(self) -> ComponentStates:
        return _validated_qualification(self._payload).component_states


def qualify_execution(
    projection: QualifiedProjection,
    *,
    component_states: ComponentStates,
    protocol_digest: str,
    model_axis_digest: str,
    context_evidence_digest: str,
    context_source_set_digest: str,
    lineage_digest: str,
    policy: ExecutionPolicy,
) -> ExecutionQualification:
    """Bind caller-owned verified assessments; never infer support from clinical text."""
    checked = checked_policy(policy)
    snapshot = _snapshot_projection(projection)
    if model_axis_digest != snapshot.metadata.model_axis_digest:
        raise ExecutionError("qualification differs from its native projection axis")
    try:
        values: dict[str, object] = {
            "schema_version": "cptac-gbm-rna-purity-execution-qualification/1.0.0",
            "component_states": component_states,
            "protocol_digest": protocol_digest,
            "model_axis_digest": model_axis_digest,
            "projection_digest": snapshot.binding_digest,
            "projection_content_digest": snapshot.content_digest,
            "context_evidence_digest": context_evidence_digest,
            "context_source_set_digest": context_source_set_digest,
            "lineage_digest": lineage_digest,
            "policy_digest": digest(checked.model_dump(mode="json")),
        }
        document = _QualificationDocument.model_validate(
            {**values, "qualification_digest": digest(values)}, strict=True
        )
    except (TypeError, ValueError):
        raise ExecutionError("source qualification bindings are invalid") from None
    return ExecutionQualification(document)


class _InferenceDocument(FrozenModel):
    outcome: InferenceOutcome
    qualification_digest: Sha256Digest
    support: PuritySupport | None = None
    clipping_state: ClippingState | None = None
    estimate: float | None = Field(default=None, ge=0.0, le=1.0)
    legacy_result_digest: Sha256Digest | None = None
    request_digest: Sha256Digest | None = None
    explanation_reconstruction_error: float | None = Field(default=None, ge=0.0)
    summary_digest: Sha256Digest

    @model_validator(mode="after")
    def outcome_and_private_payload_agree(self) -> Self:
        inferred = self.outcome == "estimated"
        present = (
            self.support,
            self.clipping_state,
            self.estimate,
            self.legacy_result_digest,
            self.request_digest,
            self.explanation_reconstruction_error,
        )
        values = self.model_dump(mode="json")
        declared = values.pop("summary_digest")
        if (
            (inferred and any(value is None for value in present))
            or (not inferred and any(value is not None for value in present))
            or self.support is PuritySupport.ABSTAINED
            or digest(values) != declared
        ):
            raise ValueError("private inference summary is inconsistent")
        return self


class InferenceSummary(_Private):
    """Transient individual result; orchestration must export aggregate totals only."""

    __slots__ = ("_payload",)
    _payload: bytes

    def __init__(self, document: _InferenceDocument) -> None:
        if type(document) is not _InferenceDocument:
            raise ExecutionError("a validated private inference summary is required")
        payload = canonical_bytes(document.model_dump(mode="json"))
        self._checked(payload)
        object.__setattr__(self, "_payload", payload)

    @staticmethod
    def _checked(payload: bytes) -> _InferenceDocument:
        try:
            if type(payload) is not bytes or not 1 <= len(payload) <= 4_096:
                raise ExecutionError("private inference summary storage is invalid")  # noqa: TRY301 -- sanitized boundary
            document = _InferenceDocument.model_validate_json(payload)
            if canonical_bytes(document.model_dump(mode="json")) != payload:
                raise ExecutionError("private inference summary is not canonical")  # noqa: TRY301 -- sanitized boundary
        except ExecutionError:
            raise
        except (TypeError, ValueError):
            raise ExecutionError("private inference summary was not accepted") from None
        return document

    @property
    def outcome(self) -> InferenceOutcome:
        return self._checked(self._payload).outcome

    @property
    def support(self) -> PuritySupport | None:
        return self._checked(self._payload).support

    @property
    def clipping_state(self) -> ClippingState | None:
        return self._checked(self._payload).clipping_state

    @property
    def estimate(self) -> float | None:
        return self._checked(self._payload).estimate

    @property
    def legacy_result_digest(self) -> str | None:
        return self._checked(self._payload).legacy_result_digest

    @property
    def request_digest(self) -> str | None:
        return self._checked(self._payload).request_digest

    @property
    def explanation_reconstruction_error(self) -> float | None:
        return self._checked(self._payload).explanation_reconstruction_error

    @property
    def binding_digest(self) -> str:
        return self._checked(self._payload).summary_digest

    @property
    def inference_executed(self) -> bool:
        return self.outcome == "estimated"


def _summary(
    outcome: InferenceOutcome,
    qualification: _QualificationDocument,
    result: GbmRnaPurityResult | None = None,
) -> InferenceSummary:
    values: dict[str, object] = {
        "outcome": outcome,
        "qualification_digest": qualification.qualification_digest,
        "support": None if result is None else result.support,
        "clipping_state": None
        if result is None or result.estimate is None
        else result.estimate.clipping_state,
        "estimate": None
        if result is None or result.estimate is None
        else result.estimate.malignant_cell_fraction,
        "legacy_result_digest": None if result is None else result.result_digest,
        "request_digest": None if result is None else result.request_digest,
        "explanation_reconstruction_error": None
        if result is None or result.explanation is None
        else result.explanation.reconstruction_absolute_error,
    }
    return InferenceSummary(
        _InferenceDocument.model_validate({**values, "summary_digest": digest(values)})
    )


def _source_names(model_axis: SourceAxis) -> tuple[str, ...]:
    try:
        validate_digest(model_axis.digest)
        features = model_axis.features
        names, lengths = _released_metadata()
        if (
            type(features) is not tuple
            or len(features) != _FEATURE_COUNT
            or tuple(feature.source_symbol for feature in features) != names
            or any(type(feature.source_length) is not float for feature in features)
            or tuple(feature.source_length for feature in features) != lengths
        ):
            raise ExecutionError("execution axis differs from the exact released metadata")  # noqa: TRY301 -- sanitized boundary
    except ExecutionError:
        raise
    except (AttributeError, TypeError, ValueError):
        raise ExecutionError("execution model axis was not accepted") from None
    return names


def _abstention(
    qualification: _QualificationDocument,
    snapshot: _ProjectionSnapshot,
    policy: ExecutionPolicy,
) -> InferenceOutcome | None:
    states = qualification.component_states
    priorities: tuple[tuple[ContextState, InferenceOutcome], ...] = (
        (ContextState.CONFLICTING, "context_conflicting"),
        (ContextState.OUT_OF_SCOPE, "context_out_of_scope"),
        (ContextState.UNKNOWN, "context_unknown"),
    )
    for state, outcome in priorities:
        if state in states:
            return outcome
    if snapshot.metadata.recognized_model_gene_count < _MINIMUM_RECOGNIZED:
        return "below_coverage_gate"
    if snapshot.metadata.recognized_raw_count_sum == 0:
        return "zero_recognized_sum"
    if not policy.allow_limited_support and not snapshot.metadata.coverage_supported:
        return "limited_support_disallowed"
    return None


def _checked_result(
    result: GbmRnaPurityResult,
    *,
    request: GbmRnaPurityRequest,
    snapshot: _ProjectionSnapshot,
    expected_profile_digest: str,
) -> GbmRnaPurityResult:
    try:
        if type(result) is not GbmRnaPurityResult:
            raise ExecutionError("the purity service returned an invalid result type")  # noqa: TRY301 -- sanitized boundary
        values = result.model_dump(mode="python")
        checked = GbmRnaPurityResult.model_validate(values, strict=True)
        if canonical_bytes(result.model_dump(mode="json")) != canonical_bytes(
            checked.model_dump(mode="json")
        ):
            raise ExecutionError("the purity result contains a semantic scalar alias")  # noqa: TRY301 -- sanitized boundary
        coverage = checked.coverage
        provenance = checked.provenance
        positive = snapshot.metadata.nonzero_model_gene_count
        recognized = snapshot.metadata.recognized_model_gene_count
        expected_support = (
            PuritySupport.SUPPORTED
            if snapshot.metadata.coverage_supported
            else PuritySupport.LIMITED
        )
        # Match the original engine's float64 vector reduction, not a rounded
        # Python integer sum that may exceed float64's exact-integer range.
        vector = np.where(snapshot.states < 2, snapshot.counts, 0).astype(np.float64)
        expected_sum = float(np.sum(vector, dtype=np.float64))
        if (
            checked.request_digest != request_digest(request)
            or checked.sample_id != request.sample_id
            or checked.profile_digest != expected_profile_digest
            or checked.support is not expected_support
            or checked.estimate is None
            or checked.explanation is None
            or not checked.diagnostics.finite_inference
            or checked.diagnostics.hidden_trace is None
            or coverage.supplied_gene_count != recognized
            or coverage.recognized_model_gene_count != recognized
            or coverage.missing_model_gene_count != _FEATURE_COUNT - recognized
            or coverage.ignored_non_model_gene_count != 0
            or coverage.nonzero_model_gene_count != positive
            or coverage.coverage_fraction != recognized / _FEATURE_COUNT
            or coverage.recognized_raw_count_sum != expected_sum
            or provenance.converted_artifact_file_sha256 != EXPECTED_ARTIFACT_SHA256
            or provenance.converted_artifact_digest != EXPECTED_CONTENT_DIGEST
            or provenance.feature_order_digest != EXPECTED_FEATURE_ORDER_DIGEST
            or provenance.weight_tensor_digest != EXPECTED_WEIGHT_TENSOR_DIGEST
            or provenance.source_model_sha256 != EXPECTED_SOURCE_MODEL_SHA256
            or provenance.source_gene_lengths_sha256 != EXPECTED_SOURCE_FEATURE_SHA256
        ):
            raise ExecutionError(  # noqa: TRY301 -- sanitized boundary
                "the purity result differs from its frozen source-qualified request"
            )
    except ExecutionError:
        raise
    except (AttributeError, TypeError, ValueError, OverflowError):
        raise ExecutionError("the purity service result was not accepted") from None
    return checked


def run_qualified_projection(
    projection: QualifiedProjection,
    *,
    model_axis: SourceAxis,
    qualification: ExecutionQualification,
    policy: ExecutionPolicy,
) -> InferenceSummary:
    """Abstain before request/model access, or call the unchanged exact old service."""
    checked = checked_policy(policy)
    if type(qualification) is not ExecutionQualification:
        raise ExecutionError("an owned source-qualified execution binding is required")
    document = _validated_qualification(qualification._payload)
    snapshot = _snapshot_projection(projection)
    names = _source_names(model_axis)
    if (
        document.policy_digest != digest(checked.model_dump(mode="json"))
        or document.projection_digest != snapshot.binding_digest
        or document.projection_content_digest != snapshot.content_digest
        or document.model_axis_digest != snapshot.metadata.model_axis_digest
        or document.model_axis_digest != model_axis.digest
    ):
        raise ExecutionError("execution inputs differ from their owned qualification")
    outcome = _abstention(document, snapshot, checked)
    if outcome is not None:
        return _summary(outcome, document)
    # The caller's seven independently source-supported components and separate
    # execution policy precede construction of any specimen runtime attestation.
    provenance_digest = digest(
        {
            "qualification_digest": document.qualification_digest,
            "projection_digest": snapshot.binding_digest,
            "projection_content_digest": snapshot.content_digest,
            "protocol_digest": document.protocol_digest,
            "model_axis_digest": document.model_axis_digest,
            "context_evidence_digest": document.context_evidence_digest,
            "context_source_set_digest": document.context_source_set_digest,
            "lineage_digest": document.lineage_digest,
            "policy_digest": document.policy_digest,
        }
    )
    request = GbmRnaPurityRequest(
        # Internal deterministic token; no clinical or assay identifier is exposed
        # to the model, logs, or the bridge summary.
        sample_id="source-qualified-purity",
        context=REQUIRED_CONTEXT,
        counts_provenance_digest=provenance_digest,
        counts=tuple(
            RawGeneCount(gene_symbol=symbol, raw_count=float(snapshot.counts[index]))
            for index, symbol in enumerate(names)
            if snapshot.states[index] < 2
        ),
    )
    expected_profile = algorithm_profile()
    result = analyze_gbm_rna_purity(request)
    return _summary(
        "estimated",
        document,
        _checked_result(
            result,
            request=request,
            snapshot=snapshot,
            expected_profile_digest=expected_profile.profile_digest,
        ),
    )


__all__ = [
    "ComponentStates",
    "ExecutionQualification",
    "InferenceOutcome",
    "InferenceSummary",
    "ProjectionReceipt",
    "QualifiedProjection",
    "SourceAxis",
    "SourceFeature",
    "projection_content_digest",
    "qualify_execution",
    "run_qualified_projection",
]
