"""Compact, de-identified local artifact storage and integrity validation."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, BinaryIO, Final, Literal, Self

from pydantic import Field, TypeAdapter, ValidationError, model_validator

from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import FrozenModel, Sha256Digest
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

from .canonical import artifact_content_digest
from .contracts import (
    ALGORITHM_ID,
    ARTIFACT_SCHEMA,
    MAX_ARTIFACT_BYTES,
    PROFILE_ID,
    CohortArtifactSummary,
    DerivationStatus,
    ExactSourceLock,
    FoldCoefficientEvidence,
    GeneSymbol,
    MechanismCategory,
    OutOfFoldMetrics,
    ProteinOutOfFoldMetrics,
)
from .errors import ArtifactIntegrityError
from .profile import algorithm_profile


class ArtifactGeneEvidence(FrozenModel):
    rna: OutOfFoldMetrics
    protein: ProteinOutOfFoldMetrics
    coefficients: FoldCoefficientEvidence
    mechanism: MechanismCategory
    rna_evidence_gate: bool
    protein_evidence_gate: bool


class ReportedPositiveSets(FrozenModel):
    cnv_rna: tuple[GeneSymbol, ...] = Field(default=(), max_length=50_000)
    cnv_protein: tuple[GeneSymbol, ...] = Field(default=(), max_length=50_000)

    @model_validator(mode="after")
    def values_are_unique_and_sorted(self) -> Self:
        for values in (self.cnv_rna, self.cnv_protein):
            if values != tuple(sorted(values)) or len(values) != len(set(values)):
                raise ValueError("Table S3 reported-positive genes must be unique and sorted")
        return self


type GeneScalar = bool | int | float | str | None
type GeneVector = tuple[GeneScalar, ...]

GENE_VECTOR_SCHEMA = "cv-metrics-v1"
GENE_VECTOR_LENGTH = 32


def encode_gene_evidence(value: dict[str, Any]) -> GeneVector:
    """Encode one validated verbose record into a compact fixed-order vector."""

    try:
        normalized = dict(value)
        normalized["mechanism"] = MechanismCategory(str(value["mechanism"]))
        validated = ArtifactGeneEvidence.model_validate(normalized, strict=True)
    except (KeyError, ValueError, ValidationError) as error:
        raise ArtifactIntegrityError("fitted gene evidence is invalid") from error
    rna = validated.rna
    protein = validated.protein
    coefficient = validated.coefficients
    return (
        rna.n_oof,
        rna.pearson,
        rna.spearman,
        rna.r2_vs_fold_train_median,
        rna.direction_accuracy_vs_fold_train_median,
        protein.n_oof,
        protein.pearson,
        protein.spearman,
        protein.r2_vs_fold_train_median,
        protein.direction_accuracy_vs_fold_train_median,
        protein.delta_r2_vs_rna_only,
        protein.delta_r2_vs_cnv_only,
        coefficient.valid_rna_folds,
        coefficient.valid_protein_folds,
        coefficient.converged_rna_folds,
        coefficient.converged_protein_folds,
        coefficient.a_cnv_to_rna_median,
        coefficient.b_rna_to_protein_given_cnv_median,
        coefficient.cprime_cnv_to_protein_given_rna_median,
        coefficient.indirect_a_times_b_median,
        coefficient.total_proxy_median,
        coefficient.a_sign_consistency,
        coefficient.b_sign_consistency,
        coefficient.cprime_sign_consistency,
        coefficient.indirect_sign_consistency,
        coefficient.total_sign_consistency,
        coefficient.a_fold_mad,
        coefficient.b_fold_mad,
        coefficient.cprime_fold_mad,
        validated.mechanism.value,
        validated.rna_evidence_gate,
        validated.protein_evidence_gate,
    )


def decode_gene_evidence(value: GeneVector) -> ArtifactGeneEvidence:
    """Decode and strictly validate a compact fixed-order vector."""

    if len(value) != GENE_VECTOR_LENGTH:
        raise ArtifactIntegrityError("artifact gene vector has an invalid length")
    payload = {
        "rna": {
            "n_oof": value[0],
            "pearson": value[1],
            "spearman": value[2],
            "r2_vs_fold_train_median": value[3],
            "direction_accuracy_vs_fold_train_median": value[4],
        },
        "protein": {
            "n_oof": value[5],
            "pearson": value[6],
            "spearman": value[7],
            "r2_vs_fold_train_median": value[8],
            "direction_accuracy_vs_fold_train_median": value[9],
            "delta_r2_vs_rna_only": value[10],
            "delta_r2_vs_cnv_only": value[11],
        },
        "coefficients": {
            "valid_rna_folds": value[12],
            "valid_protein_folds": value[13],
            "converged_rna_folds": value[14],
            "converged_protein_folds": value[15],
            "a_cnv_to_rna_median": value[16],
            "b_rna_to_protein_given_cnv_median": value[17],
            "cprime_cnv_to_protein_given_rna_median": value[18],
            "indirect_a_times_b_median": value[19],
            "total_proxy_median": value[20],
            "a_sign_consistency": value[21],
            "b_sign_consistency": value[22],
            "cprime_sign_consistency": value[23],
            "indirect_sign_consistency": value[24],
            "total_sign_consistency": value[25],
            "a_fold_mad": value[26],
            "b_fold_mad": value[27],
            "cprime_fold_mad": value[28],
        },
        "mechanism": MechanismCategory(str(value[29])),
        "rna_evidence_gate": value[30],
        "protein_evidence_gate": value[31],
    }
    try:
        return ArtifactGeneEvidence.model_validate(payload, strict=True)
    except (ValueError, ValidationError) as error:
        raise ArtifactIntegrityError("artifact gene vector is invalid") from error


class CisDosageArtifact(FrozenModel):
    artifact_schema: Literal["cptac-gbm-cis-dosage-artifact/1.0.0"] = (
        "cptac-gbm-cis-dosage-artifact/1.0.0"
    )
    algorithm_id: Literal["cptac-gbm-cis-dosage"] = "cptac-gbm-cis-dosage"
    profile_id: Literal["cptac-gbm-cis-dosage/1.0.0"] = "cptac-gbm-cis-dosage/1.0.0"
    profile_digest: Sha256Digest
    derivation_status: DerivationStatus
    artifact_content_digest: Sha256Digest
    redistribution_status: Literal["local_only_terms_unverified"] = "local_only_terms_unverified"
    gene_vector_schema: Literal["cv-metrics-v1"] = "cv-metrics-v1"
    source_locks: tuple[ExactSourceLock, ...] = Field(min_length=2, max_length=3)
    cohort: CohortArtifactSummary
    table_s3_reported_positive: ReportedPositiveSets
    gene_evidence: dict[GeneSymbol, GeneVector] = Field(min_length=1, max_length=50_000)

    @model_validator(mode="after")
    def content_is_canonical_and_deidentified(self) -> Self:
        symbols = tuple(self.gene_evidence)
        if symbols != tuple(sorted(symbols)):
            raise ValueError("artifact genes must be sorted")
        if len(symbols) != self.cohort.fitted_gene_count:
            raise ValueError("artifact fitted-gene count does not reconcile")
        if self.cohort.common_gene_count < self.cohort.fitted_gene_count:
            raise ValueError("common-gene count cannot be below fitted-gene count")
        if not self.cohort.table_s3_flags_included and (
            self.table_s3_reported_positive.cnv_rna or self.table_s3_reported_positive.cnv_protein
        ):
            raise ValueError("an artifact without Table S3 cannot carry source-positive flags")
        for value in self.gene_evidence.values():
            decode_gene_evidence(value)
        if self.artifact_content_digest != artifact_content_digest(self.model_dump(mode="json")):
            raise ValueError("artifact content digest mismatch")
        return self


_ARTIFACT_ADAPTER = TypeAdapter(CisDosageArtifact)
_READ_BLOCK_BYTES: Final = 64 * 1_024


def artifact_byte_digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def build_artifact(
    *,
    source_locks: tuple[ExactSourceLock, ...],
    cohort: CohortArtifactSummary,
    gene_evidence: dict[str, dict[str, Any]],
    derivation_status: DerivationStatus,
    table_s3_flags: dict[str, tuple[bool, bool]] | None = None,
) -> CisDosageArtifact:
    ordered = {symbol: gene_evidence[symbol] for symbol in sorted(gene_evidence)}
    bound_profile_digest = algorithm_profile().profile_digest
    payload: dict[str, Any] = {
        "artifact_schema": ARTIFACT_SCHEMA,
        "algorithm_id": ALGORITHM_ID,
        "profile_id": PROFILE_ID,
        "profile_digest": bound_profile_digest,
        "derivation_status": derivation_status,
        "redistribution_status": "local_only_terms_unverified",
        "gene_vector_schema": GENE_VECTOR_SCHEMA,
        "source_locks": source_locks,
        "cohort": cohort.model_dump(mode="json"),
        "table_s3_reported_positive": {
            "cnv_rna": tuple(
                sorted(gene for gene, flags in (table_s3_flags or {}).items() if flags[0])
            ),
            "cnv_protein": tuple(
                sorted(gene for gene, flags in (table_s3_flags or {}).items() if flags[1])
            ),
        },
        "gene_evidence": {symbol: encode_gene_evidence(ordered[symbol]) for symbol in ordered},
    }
    payload["artifact_content_digest"] = artifact_content_digest(payload)
    try:
        artifact = _ARTIFACT_ADAPTER.validate_python(payload, strict=True)
    except ValidationError as error:
        raise ArtifactIntegrityError("generated artifact does not satisfy its schema") from error
    encoded = canonical_json_bytes(artifact)
    if len(encoded) > MAX_ARTIFACT_BYTES:
        raise ArtifactIntegrityError("generated artifact exceeds the eight MiB safety bound")
    return artifact


def write_artifact(path: Path, artifact: CisDosageArtifact) -> tuple[str, int]:
    """Write a new canonical artifact atomically without overwriting a caller file."""

    payload = canonical_json_bytes(artifact)
    if len(payload) > MAX_ARTIFACT_BYTES:
        raise ArtifactIntegrityError("artifact exceeds the eight MiB safety bound")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="wb",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary_path, path)
        except FileExistsError:
            raise ArtifactIntegrityError("refusing to overwrite an existing artifact") from None
        except OSError as error:
            raise ArtifactIntegrityError(
                "artifact could not be published with atomic no-overwrite semantics"
            ) from error
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return artifact_byte_digest(payload), len(payload)


def _read_bounded_artifact_stream(stream: BinaryIO) -> bytes:
    """Read at most the artifact limit plus one overflow-detection byte."""

    chunks: list[bytes] = []
    received = 0
    while received <= MAX_ARTIFACT_BYTES:
        requested = min(_READ_BLOCK_BYTES, MAX_ARTIFACT_BYTES + 1 - received)
        chunk = stream.read(requested)
        if not chunk:
            break
        received += len(chunk)
        chunks.append(chunk)
    if received > MAX_ARTIFACT_BYTES:
        raise ArtifactIntegrityError("artifact exceeds the eight MiB safety bound")
    return b"".join(chunks)


def _read_artifact_bytes(path: Path) -> bytes:
    with path.open("rb") as stream:
        return _read_bounded_artifact_stream(stream)


def load_artifact(path: Path) -> tuple[CisDosageArtifact, str]:
    try:
        payload = _read_artifact_bytes(path)
        strict_json_loads(payload, max_bytes=MAX_ARTIFACT_BYTES)
        artifact = _ARTIFACT_ADAPTER.validate_json(payload, strict=True)
    except ArtifactIntegrityError:
        raise
    except (OSError, StrictJsonError, ValidationError) as error:
        raise ArtifactIntegrityError("artifact is unavailable or invalid") from error
    if payload != canonical_json_bytes(artifact):
        raise ArtifactIntegrityError("artifact bytes are not in canonical form")
    return artifact, artifact_byte_digest(payload)


__all__ = [
    "GENE_VECTOR_LENGTH",
    "GENE_VECTOR_SCHEMA",
    "ArtifactGeneEvidence",
    "CisDosageArtifact",
    "ReportedPositiveSets",
    "artifact_byte_digest",
    "build_artifact",
    "decode_gene_evidence",
    "encode_gene_evidence",
    "load_artifact",
    "write_artifact",
]
