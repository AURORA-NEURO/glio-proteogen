"""Artifact-backed cohort query and exact replay for discordance evidence."""

from __future__ import annotations

from pathlib import Path

from glio_proteogen.kernel.canonical import canonical_json_bytes

from .artifact import TranscriptProteinDiscordanceArtifact, load_artifact
from .canonical import request_digest, result_digest
from .contracts import (
    DiscordancePattern,
    DiscordanceProvenance,
    EvidenceSupport,
    GeneDiscordanceStatistics,
    GeneTranscriptProteinEvidence,
    ReplayVerificationRequest,
    ReplayVerificationResult,
    TranscriptProteinDiscordanceRequest,
    TranscriptProteinDiscordanceResult,
    UnverifiedTranscriptProteinDiscordanceResult,
)
from .errors import DiscordanceArtifactIntegrityError
from .profile import EXACT_SOURCE_LOCKS, algorithm_profile

_LIMITATIONS = (
    "Results are internal held-out patterns from 96 CPTAC GBM patient groups and do not establish external or clinical validity.",
    "Conditional RNA association and residual fit are observational; they are not biological buffering, causal mediation, or a treatment mechanism.",
    "CPTAC protein and RNA axes are cohort- and pipeline-relative, so this lane never accepts or scores new patient measurements.",
    "Bootstrap intervals quantify source-cohort sampling variability and are not calibrated patient-prediction intervals.",
    "The model conditions on CNV but not the full age, sex, purity, mutation, and other-alteration covariate set used by iProFun; it is not an iProFun reproduction.",
    "The 90% zero-boundary rule is repository policy without genome-wide multiplicity calibration and is not a discovery-significance threshold.",
    "Redistribution terms for the exact supplement snapshots remain unverified, so fitted artifacts are local-only.",
)


def _validate_artifact(artifact: TranscriptProteinDiscordanceArtifact) -> None:
    profile = algorithm_profile()
    if artifact.profile_digest != profile.profile_digest:
        raise DiscordanceArtifactIntegrityError(
            "discordance artifact profile digest does not match this runtime"
        )
    if artifact.derivation_status.value != "locally_verified_exact_sources":
        raise DiscordanceArtifactIntegrityError(
            "discordance artifact was not derived from locally staged exact sources"
        )
    if (
        artifact.cohort.exact_common_measurement_count != 96
        or artifact.cohort.patient_group_count != 96
        or artifact.cohort.common_gene_count != 10_430
    ):
        raise DiscordanceArtifactIntegrityError(
            "discordance artifact cohort invariants do not match the exact source"
        )
    if any(entry.statistics.bootstrap.requested_replicates != 128 for entry in artifact.genes):
        raise DiscordanceArtifactIntegrityError(
            "discordance artifact bootstrap profile does not match this runtime"
        )
    observed = {lock.source_id: lock for lock in artifact.source_locks}
    expected = {lock.source_id: lock for lock in EXACT_SOURCE_LOCKS}
    if len(observed) != len(artifact.source_locks) or observed != expected:
        raise DiscordanceArtifactIntegrityError(
            "discordance artifact source locks do not match the exact fitting sources"
        )


def _pattern(statistics: GeneDiscordanceStatistics) -> DiscordancePattern:
    bootstrap = statistics.bootstrap
    delta = bootstrap.delta_r2_vs_cnv_only
    slope = bootstrap.conditional_rna_slope
    stable = (statistics.folds.conditional_rna_sign_stability or 0.0) >= 0.8
    if delta.lower > 0.0 and stable:
        if slope.lower > 0.0:
            return DiscordancePattern.POSITIVE_CONDITIONAL_RNA_ASSOCIATION
        if slope.upper < 0.0:
            return DiscordancePattern.INVERSE_CONDITIONAL_RNA_ASSOCIATION
    if delta.lower > 0.0 and bootstrap.full_r2.lower > 0.0:
        return DiscordancePattern.PREDICTIVE_DIRECTION_INDETERMINATE
    if delta.upper <= 0.0:
        return DiscordancePattern.NO_INCREMENTAL_RNA_SUPPORT
    return DiscordancePattern.INDETERMINATE


def _reason(pattern: DiscordancePattern) -> str:
    if pattern is DiscordancePattern.POSITIVE_CONDITIONAL_RNA_ASSOCIATION:
        return (
            "The 90% patient-bootstrap intervals support a positive conditional RNA coefficient "
            "and held-out improvement over the CNV-only comparator; interpretation remains cohort-level."
        )
    if pattern is DiscordancePattern.INVERSE_CONDITIONAL_RNA_ASSOCIATION:
        return (
            "The 90% patient-bootstrap intervals support an inverse conditional RNA coefficient "
            "and held-out improvement over the CNV-only comparator; no causal mechanism is claimed."
        )
    if pattern is DiscordancePattern.PREDICTIVE_DIRECTION_INDETERMINATE:
        return (
            "The full held-out model improves on CNV-only prediction, but conditional RNA direction "
            "is not stable and interval-supported."
        )
    if pattern is DiscordancePattern.NO_INCREMENTAL_RNA_SUPPORT:
        return (
            "The 90% patient-bootstrap interval does not support held-out improvement over the "
            "CNV-only comparator; this is not evidence of biological absence."
        )
    return (
        "The source-cohort intervals cross one or more prespecified zero boundaries, so the "
        "conditional pattern is indeterminate."
    )


def _gene_result(
    symbol: str,
    statistics_by_gene: dict[str, GeneDiscordanceStatistics],
    attempted_gene_symbols: frozenset[str],
) -> GeneTranscriptProteinEvidence:
    statistics = statistics_by_gene.get(symbol)
    if statistics is None:
        reason = (
            "The gene was predeclared for local fitting but no fit cleared the minimum four-fold, sixty-OOF-observation, convergence, and bootstrap support gates."
            if symbol in attempted_gene_symbols
            else "The gene was not predeclared when this local artifact was fitted, so no computation was attempted."
        )
        return GeneTranscriptProteinEvidence(
            gene_symbol=symbol,
            support=EvidenceSupport.ABSTAINED,
            reasons=(reason,),
        )
    pattern = _pattern(statistics)
    return GeneTranscriptProteinEvidence(
        gene_symbol=symbol,
        support=EvidenceSupport.LIMITED,
        pattern=pattern,
        statistics=statistics,
        reasons=(_reason(pattern),),
    )


def _unverified_result(
    request: TranscriptProteinDiscordanceRequest,
    artifact: TranscriptProteinDiscordanceArtifact,
    artifact_byte_digest: str,
) -> UnverifiedTranscriptProteinDiscordanceResult:
    profile = algorithm_profile()
    digest = request_digest(request)
    statistics_by_gene = {entry.gene_symbol: entry.statistics for entry in artifact.genes}
    attempted_gene_symbols = frozenset(artifact.attempted_gene_symbols)
    genes = tuple(
        _gene_result(symbol, statistics_by_gene, attempted_gene_symbols)
        for symbol in sorted(request.gene_symbols)
    )
    provenance = DiscordanceProvenance(
        artifact_content_digest=artifact.artifact_content_digest,
        artifact_byte_digest=artifact_byte_digest,
        profile_digest=profile.profile_digest,
        request_digest=digest,
        source_locks=artifact.source_locks,
        cohort=artifact.cohort,
        derivation_status=artifact.derivation_status,
    )
    return UnverifiedTranscriptProteinDiscordanceResult(
        query_id=request.query_id,
        profile_digest=profile.profile_digest,
        request_digest=digest,
        result_digest="sha256:" + "0" * 64,
        artifact_content_digest=artifact.artifact_content_digest,
        genes=genes,
        provenance=provenance,
        limitations=_LIMITATIONS,
    )


def analyze_transcript_protein_discordance(
    request: TranscriptProteinDiscordanceRequest,
    *,
    artifact_path: Path,
) -> TranscriptProteinDiscordanceResult:
    artifact, byte_digest = load_artifact(artifact_path)
    _validate_artifact(artifact)
    if request.artifact_content_digest != artifact.artifact_content_digest:
        raise DiscordanceArtifactIntegrityError(
            "request artifact digest does not match the loaded discordance artifact"
        )
    draft = _unverified_result(request, artifact, byte_digest)
    payload = draft.model_dump(mode="json")
    payload["result_digest"] = result_digest(payload)
    return TranscriptProteinDiscordanceResult.model_validate_json(
        canonical_json_bytes(payload),
        strict=True,
    )


def verify_transcript_protein_discordance_replay(
    envelope: ReplayVerificationRequest,
    *,
    artifact_path: Path,
) -> ReplayVerificationResult:
    recomputed = analyze_transcript_protein_discordance(
        envelope.request,
        artifact_path=artifact_path,
    )
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
            "Exact local discordance-artifact replay verified."
            if verified
            else "Replay verification failed one or more exact content checks."
        ),
    )


__all__ = [
    "analyze_transcript_protein_discordance",
    "verify_transcript_protein_discordance_replay",
]
