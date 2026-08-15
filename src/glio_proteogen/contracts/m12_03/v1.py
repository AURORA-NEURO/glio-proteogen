"""Provisional M12-03 mechanistic feature-constructor contracts.

The M12-03 dossier requires interpretable pathway, topology, state, lineage,
kinetics, spatial, and regulatory features tied to a biomarker panel, with
source evidence, topology/unit invariants, negative-control gating, and safe
abstention. The public ABI is not frozen; every symbol in this module is
provisional scaffolding pending owner confirmation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m12_03.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentState,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    ExecutionContext,
    FrozenModel,
    Identifier,
    Limitation,
    NonEmptyStr,
    ProvenanceRecord,
    SemanticVersion,
    Sha256Digest,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
)

# PROVISIONAL ABI: inferred solely from the M12-03 dossier slice.
M1203_MODULE_ID: Final = "GLIO-PROTEOGEN-M12-03"
M1203_OPERATION: Final = "construct_biomarker_panel_mechanistic_features"
M1203_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1203_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m12-03+json"
M1203_M1202_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m12-02+json"
M1203_PARENT: Final = "biomarker_panel"
M1203_OWNER: Final = "Clinical science"
M1203_SAFETY_CLASS: Final = "S2"
M1203_GATE: Final = "G1"
M1203_PROVISIONAL_ABI: Final = True
M1203_MAX_FEATURES: Final = 2_048
M1203_MAX_RELATIONS: Final = 4_096
M1203_MAX_TRANSFORMATIONS: Final = 512
M1203_MAX_EVIDENCE: Final = 64
M1203_MAX_DIAGNOSTICS: Final = 128
M1203_MAX_FINDINGS: Final = 64
M1203_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1203_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M1203_EVIDENCE_CLAIM: Final = (
    "Caller-declared M12-03 mechanistic feature evidence; issuer authority is not authenticated."
)


class MechanisticFeatureKind(StrEnum):
    PATHWAY = "pathway"
    TOPOLOGY = "topology"
    STATE = "state"
    LINEAGE = "lineage"
    KINETICS = "kinetics"
    SPATIAL = "spatial"
    REGULATORY = "regulatory"


class MechanisticValueKind(StrEnum):
    SCALAR = "scalar"
    INTERVAL = "interval"
    CATEGORICAL = "categorical"


class MechanisticConstructionStatus(StrEnum):
    CONSTRUCTED = "constructed"
    ABSTAINED = "abstained"


class MechanisticDiagnosticStatus(StrEnum):
    PASS = "pass"  # noqa: S105
    WARNING = "warning"
    FAIL = "fail"
    NOT_EVALUABLE = "not_evaluable"


class MechanisticQualityStatus(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


class NegativeControlStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_EVALUABLE = "not_evaluable"


class MechanisticFindingCode(StrEnum):
    INPUT_INCOMPLETE = "input_incomplete"
    UNIT_INVARIANT_FAILED = "unit_invariant_failed"
    TOPOLOGY_INVARIANT_FAILED = "topology_invariant_failed"
    NEGATIVE_CONTROL_FAILED = "negative_control_failed"
    UPSTREAM_UNSUPPORTED = "upstream_unsupported"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class MechanisticRelationKind(StrEnum):
    ACTIVATES = "activates"
    INHIBITS = "inhibits"
    PARTICIPATES = "participates"
    PRECEDES = "precedes"
    COLOCALIZES = "colocalizes"
    REGULATES = "regulates"


class MechanisticFeatureLineage(FrozenModel):
    """Complete source attribution for one mechanistic feature."""

    feature_id: Identifier
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1203_MAX_EVIDENCE
    )
    claim: NonEmptyStr
    transformation_ids: tuple[Identifier, ...] = Field(
        default=(), max_length=M1203_MAX_TRANSFORMATIONS
    )
    complete: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1203_MAX_EVIDENCE)


class MechanisticFeature(FrozenModel):
    feature_id: Identifier
    version: SemanticVersion
    kind: MechanisticFeatureKind
    value_kind: MechanisticValueKind
    unit: NonEmptyStr
    scalar_value: float | None = None
    lower_bound: float | None = None
    upper_bound: float | None = None
    category: NonEmptyStr | None = None
    lineage: MechanisticFeatureLineage
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1203_MAX_EVIDENCE)

    @model_validator(mode="after")
    def value_shape_is_closed(self) -> MechanisticFeature:
        has_interval = self.lower_bound is not None or self.upper_bound is not None
        present = sum((self.scalar_value is not None, has_interval, self.category is not None))
        if self.value_kind is MechanisticValueKind.SCALAR:
            if self.scalar_value is None or has_interval or self.category is not None:
                raise ValueError("scalar feature requires exactly one scalar value")
        elif self.value_kind is MechanisticValueKind.INTERVAL:
            if (
                self.lower_bound is None
                or self.upper_bound is None
                or self.lower_bound > self.upper_bound
                or self.category is not None
                or self.scalar_value is not None
            ):
                raise ValueError("interval feature requires ordered bounds")
        elif self.category is None or self.scalar_value is not None or has_interval:
            raise ValueError("categorical feature requires only a category")
        if present != 1:
            raise ValueError("mechanistic feature requires one value representation")
        if self.lineage.feature_id != self.feature_id:
            raise ValueError("feature lineage id must match feature id")
        return self


class MechanisticRelation(FrozenModel):
    relation_id: Identifier
    source_feature_id: Identifier
    target_feature_id: Identifier
    kind: MechanisticRelationKind
    weight: float | None = None
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1203_MAX_EVIDENCE)

    @model_validator(mode="after")
    def relation_is_not_self_loop(self) -> MechanisticRelation:
        if self.source_feature_id == self.target_feature_id:
            raise ValueError("mechanistic relation cannot be a self-loop")
        return self


class MechanisticFeatureConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    model_family: NonEmptyStr
    transformation_ids: tuple[Identifier, ...] = Field(
        min_length=1, max_length=M1203_MAX_TRANSFORMATIONS
    )
    topology_reference: ArtifactReference
    negative_control_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1203_MAX_EVIDENCE
    )
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1203_MAX_EVIDENCE)


class MechanisticFeatureObject(FrozenModel):
    """Versioned mechanistic features with topology and source closure."""

    object_id: Identifier
    version: SemanticVersion
    features: tuple[MechanisticFeature, ...] = Field(min_length=1, max_length=M1203_MAX_FEATURES)
    relations: tuple[MechanisticRelation, ...] = Field(default=(), max_length=M1203_MAX_RELATIONS)
    configuration: MechanisticFeatureConfiguration
    lineage_complete: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1203_MAX_EVIDENCE)

    @model_validator(mode="after")
    def object_is_closed(self) -> MechanisticFeatureObject:
        feature_ids = tuple(item.feature_id for item in self.features)
        if len(feature_ids) != len(set(feature_ids)):
            raise ValueError("mechanistic feature ids must be unique")
        known = set(feature_ids)
        relation_ids = tuple(item.relation_id for item in self.relations)
        if len(relation_ids) != len(set(relation_ids)):
            raise ValueError("mechanistic relation ids must be unique")
        for relation in self.relations:
            if relation.source_feature_id not in known or relation.target_feature_id not in known:
                raise ValueError("mechanistic relation references an unknown feature")
        transformation_ids = set(self.configuration.transformation_ids)
        for feature in self.features:
            if not set(feature.lineage.transformation_ids) <= transformation_ids:
                raise ValueError("feature lineage references an unknown transformation")
        return self


class MechanisticFeatureDiagnostic(FrozenModel):
    diagnostic_id: Identifier
    status: MechanisticDiagnosticStatus
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1203_MAX_EVIDENCE)


class ConstructBiomarkerPanelMechanisticFeaturesRequest(FrozenModel):
    """Provisional request ABI bound to the M12-02 upstream artifact."""

    operation: Literal["construct_biomarker_panel_mechanistic_features"] = M1203_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1203_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_result: ArtifactReference
    configuration: MechanisticFeatureConfiguration
    feature_inputs: tuple[MechanisticFeature, ...] = Field(
        min_length=1, max_length=M1203_MAX_FEATURES
    )
    relations: tuple[MechanisticRelation, ...] = Field(default=(), max_length=M1203_MAX_RELATIONS)
    quality_status: MechanisticQualityStatus = MechanisticQualityStatus.ACCEPTED
    negative_control_status: NegativeControlStatus = NegativeControlStatus.PASSED
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1203_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> ConstructBiomarkerPanelMechanisticFeaturesRequest:
        if self.upstream_result.media_type != M1203_M1202_INPUT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M12-02 upstream result")
        keys = tuple(
            (item.artifact_id, item.version, item.digest, item.media_type)
            for item in self.source_artifacts
        )
        if len(keys) != len(set(keys)):
            raise ValueError("source artifact references must be unique")
        feature_ids = tuple(item.feature_id for item in self.feature_inputs)
        if len(feature_ids) != len(set(feature_ids)):
            raise ValueError("feature input ids must be unique")
        relation_ids = tuple(item.relation_id for item in self.relations)
        if len(relation_ids) != len(set(relation_ids)):
            raise ValueError("relation ids must be unique")
        known = set(feature_ids)
        for relation in self.relations:
            if relation.source_feature_id not in known or relation.target_feature_id not in known:
                raise ValueError("relation references an unknown feature input")
        return self


class BiomarkerPanelMechanisticFeatureResult(FrozenModel):
    """Mechanistic feature result with invariant diagnostics and abstention."""

    output_type: Literal["biomarker_panel_mechanistic_features"] = (
        "biomarker_panel_mechanistic_features"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1203_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: ConstructBiomarkerPanelMechanisticFeaturesRequest
    status: MechanisticConstructionStatus
    feature_object: MechanisticFeatureObject | None = None
    diagnostics: tuple[MechanisticFeatureDiagnostic, ...] = Field(
        min_length=1, max_length=M1203_MAX_DIAGNOSTICS
    )
    findings: tuple[MechanisticFindingCode, ...] = Field(default=(), max_length=M1203_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["biomarker_panel"] = M1203_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1203_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> BiomarkerPanelMechanisticFeatureResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        diagnostic_ids = tuple(item.diagnostic_id for item in self.diagnostics)
        if len(diagnostic_ids) != len(set(diagnostic_ids)):
            raise ValueError("diagnostic ids must be unique")
        if self.evidence and {item.role for item in self.evidence} != {"evidence"}:
            raise ValueError("M12-03 result evidence cannot relabel counter-evidence")
        failed = {MechanisticDiagnosticStatus.FAIL, MechanisticDiagnosticStatus.NOT_EVALUABLE}
        if self.status is MechanisticConstructionStatus.CONSTRUCTED:
            if (
                self.feature_object is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
                or any(item.status in failed for item in self.diagnostics)
                or self.request.quality_status is not MechanisticQualityStatus.ACCEPTED
                or self.request.negative_control_status is not NegativeControlStatus.PASSED
            ):
                raise ValueError("constructed result requires supported, invariant-safe output")
        elif (
            self.feature_object is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no feature object and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


def expected_uncertainty() -> UncertaintyProfile:
    """Return explicit seven-dimension uncertainty for deterministic construction."""

    rationales = (
        "Source assay measurement uncertainty is not modeled by this deterministic constructor.",
        "Sampling uncertainty is not estimable from caller-declared source artifacts.",
        "No parameters are fitted during feature construction.",
        "The selected mechanistic rule and graph representation are fixed by configuration.",
        "Feature identity is inherited from caller-declared artifact references.",
        "Support is limited to the declared topology, units, and negative-control domain.",
        "Transport to a new assay, site, or population requires external validation.",
    )
    estimates = tuple(
        UncertaintyEstimate(state=EstimateState.NOT_ESTIMABLE, rationale=rationale)
        for rationale in rationales
    )
    return UncertaintyProfile(
        measurement=estimates[0],
        sampling=estimates[1],
        parameter=estimates[2],
        model_form=estimates[3],
        identification=estimates[4],
        support=estimates[5],
        transport=estimates[6],
        sensitivity_notes=(
            "Missing, unsupported, and non-evaluable evidence never becomes a negative finding.",
            "Configuration, topology, unit, and negative-control changes require re-evaluation.",
        ),
    )


def expected_limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="provisional_abi",
            statement="M12-03 ABI remains provisional pending owner confirmation.",
        ),
        Limitation(
            code="caller_declared_evidence",
            statement="Evidence is referenced but not authenticated or traversed by this module.",
        ),
        Limitation(
            code="ownership_boundary",
            statement=(
                "Kinase activity, all-omics fusion, and treatment recommendation are excluded."
            ),
        ),
    )


def expected_provenance(
    request: ConstructBiomarkerPanelMechanisticFeaturesRequest,
    request_digest: Sha256Digest | None = None,
) -> ProvenanceRecord:
    """Derive auditable provenance from controls and content-addressed references."""

    digest = request_digest or canonical_request_digest(request)
    refs = request.context.references
    controls = (
        ControlDecisionRecord(
            role=ControlRole.APPROVED_CONFIGURATION,
            decision_id=refs.approved_configuration.decision_id,
            state=refs.approved_configuration.state.value,
            policy_version=refs.approved_configuration.policy_version,
            evidence_digest=refs.approved_configuration.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.IDENTITY_LINEAGE,
            decision_id=refs.identity_lineage.decision_id,
            state=refs.identity_lineage.state.value,
            policy_version=refs.identity_lineage.policy_version,
            evidence_digest=refs.identity_lineage.evidence.digest,
            subject_digest=refs.identity_lineage.binding_digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.PROVENANCE,
            decision_id=refs.provenance.decision_id,
            state=refs.provenance.state.value,
            policy_version=refs.provenance.policy_version,
            evidence_digest=refs.provenance.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.CONSENT,
            decision_id=refs.consent.decision_id,
            state=refs.consent.state.value,
            policy_version=refs.consent.policy_version,
            evidence_digest=refs.consent.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.QUALITY,
            decision_id=refs.quality.decision_id,
            state=refs.quality.state.value,
            policy_version=refs.quality.policy_version,
            evidence_digest=refs.quality.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.SUPPORT,
            decision_id=refs.support.decision_id,
            state=refs.support.state.value,
            policy_version=refs.support.policy_version,
            evidence_digest=refs.support.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.INTENDED_USE,
            decision_id=refs.intended_use.decision_id,
            state=refs.intended_use.state.value,
            policy_version=refs.intended_use.policy_version,
            evidence_digest=refs.intended_use.evidence.digest,
        ),
    )
    control_digests = tuple(
        item.evidence.digest
        for item in (
            refs.approved_configuration,
            refs.identity_lineage,
            refs.provenance,
            refs.consent,
            refs.quality,
            refs.support,
            refs.intended_use,
        )
    )
    input_digests = {
        digest,
        request.upstream_result.digest,
        request.configuration.topology_reference.digest,
        *control_digests,
        *(item.digest for item in request.source_artifacts),
        *(item.reference.digest for item in request.configuration.evidence),
        *(
            artifact.digest
            for feature in request.feature_inputs
            for artifact in feature.lineage.source_artifacts
        ),
    }
    return ProvenanceRecord(
        activity_id=f"activity.m1203.{digest.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M1203_MODULE_ID,
        module_version=M1203_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(sorted(input_digests)),
        configuration_digest=sha256_digest(request.configuration),
        consent_decision_id=refs.consent.decision_id,
        consent_state=ConsentState.GRANTED,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=controls,
    )


__all__ = [
    "M1203_CONTRACT_VERSION",
    "M1203_EVIDENCE_CLAIM",
    "M1203_GATE",
    "M1203_M1202_INPUT_MEDIA_TYPE",
    "M1203_MAX_CANONICAL_REQUEST_BYTES",
    "M1203_MAX_CANONICAL_RESULT_BYTES",
    "M1203_MAX_DIAGNOSTICS",
    "M1203_MAX_EVIDENCE",
    "M1203_MAX_FEATURES",
    "M1203_MAX_FINDINGS",
    "M1203_MAX_RELATIONS",
    "M1203_MAX_TRANSFORMATIONS",
    "M1203_MODULE_ID",
    "M1203_OPERATION",
    "M1203_OUTPUT_MEDIA_TYPE",
    "M1203_OWNER",
    "M1203_PARENT",
    "M1203_PROVISIONAL_ABI",
    "M1203_SAFETY_CLASS",
    "BiomarkerPanelMechanisticFeatureResult",
    "ConstructBiomarkerPanelMechanisticFeaturesRequest",
    "MechanisticConstructionStatus",
    "MechanisticDiagnosticStatus",
    "MechanisticFeature",
    "MechanisticFeatureConfiguration",
    "MechanisticFeatureDiagnostic",
    "MechanisticFeatureKind",
    "MechanisticFeatureLineage",
    "MechanisticFeatureObject",
    "MechanisticFindingCode",
    "MechanisticQualityStatus",
    "MechanisticRelation",
    "MechanisticRelationKind",
    "MechanisticValueKind",
    "NegativeControlStatus",
    "expected_limitations",
    "expected_provenance",
    "expected_uncertainty",
]
