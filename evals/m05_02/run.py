"""Genuine deterministic builders for M05-02 identity-lineage reconciliation."""

from __future__ import annotations

import copy
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Final, cast

from pydantic import TypeAdapter

from evals.m05_01.run import build_scenario_request as build_m0501_request
from glio_proteogen.contracts.m01_02 import (
    IdentityLineageResolution,
    ReconcileIdentityLineageRequest,
)
from glio_proteogen.contracts.m05_01 import (
    EvaluatePtmLocalizationProtocolRequest,
    PtmLocalizationProtocolConformanceResult,
)
from glio_proteogen.contracts.m05_02 import (
    ApprovedPtmLocalizationDerivationMethod,
    ApprovedPtmLocalizationLineageConfiguration,
    PtmLocalizationIdentityLineagePolicy,
    PtmLocalizationIdentityLineageResolution,
    PtmLocalizationLineageArtifactClaim,
    PtmLocalizationLineageArtifactDerivation,
    PtmLocalizationLineageArtifactRole,
    PtmLocalizationLineageEvidenceState,
    ReconcilePtmLocalizationIdentityLineageRequest,
    configuration_digest,
    opaque_ptm_localization_lineage_identifier,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import ArtifactReference, ExecutionContext
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.event_store import (
    M0102EventStore,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.service import M0102Service
from glio_proteogen.modules.c05_ptm_localization.m05_01_protocol_metadata import (
    evaluate_ptm_localization_protocol,
)
from glio_proteogen.modules.c05_ptm_localization.m05_02_identity_lineage import (
    reconcile_ptm_localization_identity_lineage,
)

ROOT: Final = Path(__file__).parents[2]
M0102_SCENARIO_PATH: Final = ROOT / "tests" / "fixtures" / "m01_02" / "scenarios.json"
PROTOCOL_TIME: Final = datetime(2026, 8, 12, 12, tzinfo=UTC)
RECONCILIATION_TIME: Final = datetime(2026, 8, 13, 12, tzinfo=UTC)
POLICY_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m05-02.policy+json"
CONFIGURATION_MEDIA_TYPE: Final = (
    "application/vnd.glio-proteogen.m05-02.approved-configuration+json"
)
DERIVATION_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m05-02.derivation+json"
ROLE_MEDIA_TYPES: Final = {
    PtmLocalizationLineageArtifactRole.MASS_SPECTROMETRY_PROTEOME_MANIFEST: (
        "application/vnd.glio-proteogen.m05-02.mass-spectrometry-proteome-manifest+json"
    ),
    PtmLocalizationLineageArtifactRole.GENOME_MANIFEST: (
        "application/vnd.glio-proteogen.m05-02.genome-manifest+json"
    ),
    PtmLocalizationLineageArtifactRole.TRANSCRIPTOME_MANIFEST: (
        "application/vnd.glio-proteogen.m05-02.transcriptome-manifest+json"
    ),
    PtmLocalizationLineageArtifactRole.PTM_ANNOTATION_MANIFEST: (
        "application/vnd.glio-proteogen.m05-02.ptm-annotation-manifest+json"
    ),
    PtmLocalizationLineageArtifactRole.VARIANT_PEPTIDE_INPUT_BUNDLE: (
        "application/vnd.glio-proteogen.m05-02.variant-peptide-input-bundle+json"
    ),
}
_M0102_REQUEST_ADAPTER: Final = TypeAdapter(ReconcileIdentityLineageRequest)


class _MissingIdentityFixtureError(ValueError):
    def __init__(self) -> None:
        super().__init__("M01-02 canonical identity fixture is missing")


class _UnknownScenarioError(ValueError):
    def __init__(self) -> None:
        super().__init__("unknown M05-02 scenario")


def _oid(namespace: str, label: object) -> str:
    value = f"{namespace}.{sha256_digest({'m0502': label}).removeprefix('sha256:')}"
    return opaque_ptm_localization_lineage_identifier(cast("Any", namespace), value)


def _artifact(label: str, *, media_type: str, digest: str | None = None) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=_oid("evidence", label),
        version="1.0.0",
        digest=digest or sha256_digest({"m0502_evidence": label}),
        media_type=media_type,
    )


def _m0102_payload() -> dict[str, Any]:
    corpus = cast("dict[str, Any]", strict_json_loads(M0102_SCENARIO_PATH.read_bytes()))
    for scenario in cast("list[dict[str, Any]]", corpus["scenarios"]):
        if scenario["case_id"] == "complete_ordinary_lineage":
            return copy.deepcopy(cast("dict[str, Any]", scenario["request"]))
    raise _MissingIdentityFixtureError


def _genuine_identity_resolution() -> IdentityLineageResolution:
    request = _M0102_REQUEST_ADAPTER.validate_json(
        canonical_json_bytes(_m0102_payload()), strict=True
    )
    with TemporaryDirectory(prefix="m0502-m0102-") as temporary:
        store = M0102EventStore(Path(temporary) / "identity.sqlite3")
        with M0102Service(store) as service:
            return service.execute(request)


def _genuine_protocol_result(
    identity: IdentityLineageResolution,
    *,
    scenario: str,
) -> PtmLocalizationProtocolConformanceResult:
    m0501_scenario = (
        "compatibility_failure_quarantined"
        if scenario == "upstream_protocol_quarantined"
        else "canonical_conformant"
    )
    payload = build_m0501_request(m0501_scenario).model_dump(mode="python", exclude_none=False)
    payload["context"]["occurred_at"] = PROTOCOL_TIME
    payload["context"]["references"]["identity_lineage"]["binding_digest"] = (
        identity.resolution_digest
    )
    request = EvaluatePtmLocalizationProtocolRequest.model_validate(payload, strict=True)
    return evaluate_ptm_localization_protocol(request)


def _policy(
    protocol: PtmLocalizationProtocolConformanceResult,
    *,
    approve_configuration: bool,
) -> PtmLocalizationIdentityLineagePolicy:
    approved_configuration = ApprovedPtmLocalizationLineageConfiguration(
        configuration_id=_oid("configuration", "canonical"),
        protocol_result_version=protocol.result_version,
        configuration_digest=(
            protocol.configuration_digest
            if approve_configuration
            else sha256_digest({"unsupported": protocol.configuration_digest})
        ),
        reference_bundle_digest=protocol.receipt.reference_bundle_digest,
        assay_specimen_policy_digest=protocol.receipt.assay_specimen_policy_digest,
        evidence=_artifact("approved-configuration", media_type=CONFIGURATION_MEDIA_TYPE),
    )
    method = ApprovedPtmLocalizationDerivationMethod(
        method_id=_oid("method", "deterministic-lineage"),
        version="1.0.0",
        evidence=_artifact("method", media_type=DERIVATION_MEDIA_TYPE),
    )
    return PtmLocalizationIdentityLineagePolicy(
        policy_id=_oid("policy", "canonical"),
        version="1.0.0",
        max_artifact_claims=16,
        max_derivation_sources=15,
        approved_configurations=(approved_configuration,),
        approved_derivation_methods=(method,),
        evidence=_artifact("policy", media_type=POLICY_MEDIA_TYPE),
        reviewed_by=_oid("reviewer", "synthetic"),
        reviewed_at=PROTOCOL_TIME,
    )


def _anchor_subjects(
    identity: IdentityLineageResolution,
    entity_id: str = "obj-a",
) -> tuple[str, ...]:
    return next(
        node.subject_component_ids for node in identity.graph.nodes if node.entity_id == entity_id
    )


def _claims(
    identity: IdentityLineageResolution,
    protocol: PtmLocalizationProtocolConformanceResult,
) -> tuple[PtmLocalizationLineageArtifactClaim, ...]:
    return tuple(
        PtmLocalizationLineageArtifactClaim(
            claim_id=_oid("claim", role.value),
            role=role,
            artifact=_artifact(role.value, media_type=ROLE_MEDIA_TYPES[role]),
            identity_entity_id="obj-a",
            declared_subject_component_ids=_anchor_subjects(identity),
            producer_identity_resolution_digest=identity.resolution_digest,
            producer_protocol_result_digest=protocol.result_digest,
            producer_reference_bundle_digest=protocol.receipt.reference_bundle_digest,
            producer_configuration_digest=protocol.configuration_digest,
            producer_assay_specimen_policy_digest=(protocol.receipt.assay_specimen_policy_digest),
            evidence_state=PtmLocalizationLineageEvidenceState.OBSERVED,
        )
        for role in PtmLocalizationLineageArtifactRole
    )


def _derivation(
    claims: tuple[PtmLocalizationLineageArtifactClaim, ...],
    policy: PtmLocalizationIdentityLineagePolicy,
) -> PtmLocalizationLineageArtifactDerivation:
    target = next(
        item
        for item in claims
        if item.role is PtmLocalizationLineageArtifactRole.VARIANT_PEPTIDE_INPUT_BUNDLE
    )
    method = policy.approved_derivation_methods[0]
    return PtmLocalizationLineageArtifactDerivation(
        derivation_id=_oid("derivation", "variant-peptide"),
        source_claim_ids=tuple(item.claim_id for item in claims if item is not target),
        target_claim_id=target.claim_id,
        method_id=method.method_id,
        method_version=method.version,
        evidence=_artifact("derivation", media_type=DERIVATION_MEDIA_TYPE),
    )


def _context(
    protocol: PtmLocalizationProtocolConformanceResult,
    identity: IdentityLineageResolution,
    policy: PtmLocalizationIdentityLineagePolicy,
) -> ExecutionContext:
    base = protocol.request.context
    references = base.references.model_copy(
        update={
            "approved_configuration": base.references.approved_configuration.model_copy(
                update={
                    "evidence": base.references.approved_configuration.evidence.model_copy(
                        update={"digest": configuration_digest(policy)}
                    )
                }
            ),
            "identity_lineage": base.references.identity_lineage.model_copy(
                update={"binding_digest": identity.resolution_digest}
            ),
            "quality": base.references.quality.model_copy(
                update={
                    "evidence": base.references.quality.evidence.model_copy(
                        update={"digest": protocol.result_digest}
                    )
                }
            ),
        }
    )
    return base.model_copy(update={"occurred_at": RECONCILIATION_TIME, "references": references})


def build_scenario_request(
    scenario: str = "canonical_reconciled",
) -> ReconcilePtmLocalizationIdentityLineageRequest:
    """Build one genuine strict M05-02 request through public upstream operations."""

    if scenario not in {
        "canonical_reconciled",
        "unsupported_configuration_abstained",
        "upstream_protocol_quarantined",
    }:
        raise _UnknownScenarioError
    identity = _genuine_identity_resolution()
    protocol = _genuine_protocol_result(identity, scenario=scenario)
    policy = _policy(
        protocol,
        approve_configuration=scenario != "unsupported_configuration_abstained",
    )
    traversable = scenario == "canonical_reconciled" and protocol.disposition.value == "conformant"
    claims = _claims(identity, protocol) if traversable else ()
    derivations = (_derivation(claims, policy),) if traversable else ()
    context = _context(protocol, identity, policy)
    return ReconcilePtmLocalizationIdentityLineageRequest(
        request_id=context.request_id,
        context=context,
        identity_resolution=identity,
        protocol_result=protocol,
        policy=policy,
        artifact_claims=claims,
        derivations=derivations,
    )


def build_scenario_result(
    scenario: str = "canonical_reconciled",
) -> PtmLocalizationIdentityLineageResolution:
    """Execute one genuine M05-02 scenario through the public operation."""

    return reconcile_ptm_localization_identity_lineage(build_scenario_request(scenario))


__all__ = ["build_scenario_request", "build_scenario_result"]
