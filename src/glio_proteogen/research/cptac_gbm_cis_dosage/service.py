"""Artifact-backed cohort evidence query and exact replay verification."""

from __future__ import annotations

from pathlib import Path

from glio_proteogen.kernel.canonical import canonical_json_bytes

from .artifact import CisDosageArtifact, decode_gene_evidence, load_artifact
from .canonical import request_digest, result_digest
from .contracts import (
    CisDosageEvidenceRequest,
    CisDosageEvidenceResult,
    CisDosageProvenance,
    DerivationStatus,
    EvidenceSupport,
    GeneCisDosageEvidence,
    ReplayVerificationRequest,
    ReplayVerificationResult,
    SourcePositiveFlag,
    TableS3SourceFlags,
    UnverifiedCisDosageEvidenceResult,
)
from .errors import ArtifactIntegrityError
from .profile import algorithm_profile
from .source import HGNC_LOCK, TABLE_S2_LOCK, TABLE_S3_LOCK

_LIMITATIONS = (
    "Internal cross-validation estimates transport within the locked 96-measurement CPTAC GBM cohort; it does not establish external or clinical validity.",
    "The CNV-to-RNA-to-protein decomposition is observational and must not be interpreted as an individual causal or mediated effect.",
    "This runtime only queries cohort-fitted gene evidence and never accepts or scores patient measurements.",
    "Table S3 is post-hoc source annotation only; not-reported-positive never means negative, tested-null, or absent biology.",
    "Redistribution terms for the CPTAC supplement snapshots remain unverified, so artifacts are local-only.",
)


def _validate_artifact_source_locks(artifact: CisDosageArtifact) -> None:
    profile = algorithm_profile()
    if artifact.profile_digest != profile.profile_digest:
        raise ArtifactIntegrityError("artifact profile digest does not match this runtime")
    if artifact.derivation_status is not DerivationStatus.LOCALLY_VERIFIED_EXACT_SOURCES:
        raise ArtifactIntegrityError(
            "artifact was not derived from locally staged exact source snapshots"
        )
    constants = profile.constants
    if (
        artifact.cohort.exact_common_measurement_count
        != constants.production_exact_common_measurements
        or artifact.cohort.patient_group_count != constants.production_patient_groups
        or artifact.cohort.common_gene_count != constants.production_common_genes
        or artifact.cohort.fitted_gene_count != constants.production_fitted_genes
    ):
        raise ArtifactIntegrityError("artifact production cohort invariants do not match")
    observed = {lock.source_id: lock for lock in artifact.source_locks}
    if len(observed) != len(artifact.source_locks):
        raise ArtifactIntegrityError("artifact contains duplicate source locks")
    allowed = {
        TABLE_S2_LOCK.source_id: TABLE_S2_LOCK,
        TABLE_S3_LOCK.source_id: TABLE_S3_LOCK,
        HGNC_LOCK.source_id: HGNC_LOCK,
    }
    if set(observed).difference(allowed):
        raise ArtifactIntegrityError("artifact contains an unrecognized source lock")
    for required in (TABLE_S2_LOCK, HGNC_LOCK):
        if observed.get(required.source_id) != required:
            raise ArtifactIntegrityError("artifact is missing an exact required source lock")
    if TABLE_S3_LOCK.source_id in observed and observed[TABLE_S3_LOCK.source_id] != TABLE_S3_LOCK:
        raise ArtifactIntegrityError("artifact Table S3 lock does not match the profile")
    has_s3_lock = TABLE_S3_LOCK.source_id in observed
    if has_s3_lock != artifact.cohort.table_s3_flags_included:
        raise ArtifactIntegrityError("artifact Table S3 provenance does not reconcile")


def _source_flags(symbol: str, artifact: CisDosageArtifact) -> TableS3SourceFlags:
    if not artifact.cohort.table_s3_flags_included:
        return TableS3SourceFlags(
            cnv_rna=SourcePositiveFlag.NOT_AVAILABLE,
            cnv_protein=SourcePositiveFlag.NOT_AVAILABLE,
        )
    rna_positive = symbol in artifact.table_s3_reported_positive.cnv_rna
    protein_positive = symbol in artifact.table_s3_reported_positive.cnv_protein
    return TableS3SourceFlags(
        cnv_rna=(
            SourcePositiveFlag.REPORTED_POSITIVE
            if rna_positive
            else SourcePositiveFlag.NOT_REPORTED_POSITIVE
        ),
        cnv_protein=(
            SourcePositiveFlag.REPORTED_POSITIVE
            if protein_positive
            else SourcePositiveFlag.NOT_REPORTED_POSITIVE
        ),
    )


def _gene_result(symbol: str, artifact: CisDosageArtifact) -> GeneCisDosageEvidence:
    source_flags = _source_flags(symbol, artifact)
    vector = artifact.gene_evidence.get(symbol)
    if vector is None:
        return GeneCisDosageEvidence(
            gene_symbol=symbol,
            support=EvidenceSupport.ABSTAINED,
            table_s3_source_flags=source_flags,
            reasons=(
                "No cross-validated fit met the minimum four-fold and sixty-OOF-observation support gate for this exact gene.",
            ),
        )
    record = decode_gene_evidence(vector)
    coefficient = record.coefficients
    if coefficient.converged_rna_folds < 4 or coefficient.converged_protein_folds < 4:
        return GeneCisDosageEvidence(
            gene_symbol=symbol,
            support=EvidenceSupport.ABSTAINED,
            table_s3_source_flags=source_flags,
            reasons=(
                "Fewer than four outer-fold estimator sets converged; fitted values were withheld.",
            ),
        )
    indirect_stability = coefficient.indirect_sign_consistency or 0.0
    total_stability = coefficient.total_sign_consistency or 0.0
    if indirect_stability < 0.8 or total_stability < 0.8:
        return GeneCisDosageEvidence(
            gene_symbol=symbol,
            support=EvidenceSupport.ABSTAINED,
            table_s3_source_flags=source_flags,
            reasons=(
                "Indirect or total dosage direction was stable in fewer than eighty percent of valid folds; fitted values were withheld.",
            ),
        )
    supported = record.rna_evidence_gate and record.protein_evidence_gate
    reasons = (
        (
            "Passed the prespecified RNA and protein held-out evidence gates; interpretation remains observational and cohort-level."
        )
        if supported
        else (
            "The estimator converged with stable fold direction, but one or both prespecified held-out evidence gates were not met."
        )
    )
    return GeneCisDosageEvidence(
        gene_symbol=symbol,
        support=EvidenceSupport.SUPPORTED if supported else EvidenceSupport.LIMITED,
        rna=record.rna,
        protein=record.protein,
        coefficients=coefficient,
        mechanism=record.mechanism,
        rna_evidence_gate=record.rna_evidence_gate,
        protein_evidence_gate=record.protein_evidence_gate,
        table_s3_source_flags=source_flags,
        reasons=(reasons,),
    )


def _unverified_result(
    request: CisDosageEvidenceRequest,
    artifact: CisDosageArtifact,
    artifact_byte_digest: str,
) -> UnverifiedCisDosageEvidenceResult:
    profile = algorithm_profile()
    digest = request_digest(request)
    genes = tuple(_gene_result(symbol, artifact) for symbol in sorted(request.gene_symbols))
    provenance = CisDosageProvenance(
        artifact_content_digest=artifact.artifact_content_digest,
        artifact_byte_digest=artifact_byte_digest,
        profile_digest=profile.profile_digest,
        request_digest=digest,
        source_locks=artifact.source_locks,
        cohort=artifact.cohort,
        derivation_status=artifact.derivation_status,
        numpy_version=profile.numpy_version,
    )
    return UnverifiedCisDosageEvidenceResult(
        query_id=request.query_id,
        profile_digest=profile.profile_digest,
        request_digest=digest,
        result_digest="sha256:" + "0" * 64,
        artifact_content_digest=artifact.artifact_content_digest,
        genes=genes,
        provenance=provenance,
        limitations=_LIMITATIONS,
    )


def analyze_cis_dosage_evidence(
    request: CisDosageEvidenceRequest,
    *,
    artifact_path: Path,
) -> CisDosageEvidenceResult:
    artifact, byte_digest = load_artifact(artifact_path)
    _validate_artifact_source_locks(artifact)
    if request.artifact_content_digest != artifact.artifact_content_digest:
        raise ArtifactIntegrityError("request artifact digest does not match the loaded artifact")
    draft = _unverified_result(request, artifact, byte_digest)
    payload = draft.model_dump(mode="json")
    payload["result_digest"] = result_digest(payload)
    return CisDosageEvidenceResult.model_validate_json(canonical_json_bytes(payload), strict=True)


def verify_cis_dosage_replay(
    envelope: ReplayVerificationRequest,
    *,
    artifact_path: Path,
) -> ReplayVerificationResult:
    recomputed = analyze_cis_dosage_evidence(envelope.request, artifact_path=artifact_path)
    provided = envelope.result
    recomputed_request = recomputed.request_digest
    recomputed_result = recomputed.result_digest
    request_match = provided.request_digest == recomputed_request
    profile_match = provided.profile_digest == recomputed.profile_digest
    artifact_match = (
        envelope.request.artifact_content_digest
        == provided.artifact_content_digest
        == recomputed.artifact_content_digest
    )
    provided_payload = provided.model_dump(mode="json")
    provided_digest_valid = provided.result_digest == result_digest(provided_payload)
    recomputed_digest_match = provided.result_digest == recomputed_result
    semantic_match = provided_payload == recomputed.model_dump(mode="json")
    verified = all(
        (
            request_match,
            profile_match,
            artifact_match,
            provided_digest_valid,
            recomputed_digest_match,
            semantic_match,
        )
    )
    return ReplayVerificationResult(
        verified=verified,
        request_digest_match=request_match,
        profile_digest_match=profile_match,
        artifact_digest_match=artifact_match,
        provided_result_digest_valid=provided_digest_valid,
        recomputed_result_digest_match=recomputed_digest_match,
        semantic_match=semantic_match,
        recomputed_request_digest=recomputed_request,
        recomputed_result_digest=recomputed_result,
        provided_result_digest=provided.result_digest,
        message=(
            "Exact local artifact replay verified."
            if verified
            else "Replay verification failed one or more exact content checks."
        ),
    )


__all__ = ["analyze_cis_dosage_evidence", "verify_cis_dosage_replay"]
