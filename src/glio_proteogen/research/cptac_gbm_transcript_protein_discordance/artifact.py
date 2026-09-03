"""Compact local artifact storage with exact integrity and privacy boundaries."""

from __future__ import annotations

import hashlib
import os
from contextlib import ExitStack
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import BinaryIO, Literal, Mapping, Self

from pydantic import Field, TypeAdapter, ValidationError, model_validator

from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import FrozenModel, Sha256Digest
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

from .canonical import artifact_content_digest
from .contracts import (
    ALGORITHM_ID,
    ARTIFACT_SCHEMA,
    MAX_ARTIFACT_BYTES,
    MAX_QUERY_GENES,
    PROFILE_ID,
    CohortArtifactSummary,
    DerivationStatus,
    ExactSourceLock,
    GeneDiscordanceStatistics,
    GeneSymbol,
)
from .errors import DiscordanceArtifactIntegrityError
from .profile import algorithm_profile

_READ_BLOCK_BYTES = 64 * 1_024


class ArtifactGeneEntry(FrozenModel):
    gene_symbol: GeneSymbol
    statistics: GeneDiscordanceStatistics


class TranscriptProteinDiscordanceArtifact(FrozenModel):
    schema_version: Literal["cptac-gbm-transcript-protein-discordance-artifact/1.0.0"] = (
        "cptac-gbm-transcript-protein-discordance-artifact/1.0.0"
    )
    algorithm_id: Literal["cptac-gbm-transcript-protein-discordance"] = (
        "cptac-gbm-transcript-protein-discordance"
    )
    profile_id: Literal["cptac-gbm-transcript-protein-discordance/1.0.0"] = (
        "cptac-gbm-transcript-protein-discordance/1.0.0"
    )
    profile_digest: Sha256Digest
    artifact_content_digest: Sha256Digest
    derivation_status: DerivationStatus
    source_locks: tuple[ExactSourceLock, ...] = Field(min_length=2, max_length=2)
    cohort: CohortArtifactSummary
    attempted_gene_symbols: tuple[GeneSymbol, ...] = Field(
        min_length=1,
        max_length=MAX_QUERY_GENES,
    )
    genes: tuple[ArtifactGeneEntry, ...] = Field(min_length=1, max_length=MAX_QUERY_GENES)
    redistribution_status: Literal["local_only_terms_unverified"] = "local_only_terms_unverified"

    @model_validator(mode="after")
    def content_is_canonical_and_bound(self) -> Self:
        if self.schema_version != ARTIFACT_SCHEMA:
            raise ValueError("artifact schema is not supported")
        if self.algorithm_id != ALGORITHM_ID or self.profile_id != PROFILE_ID:
            raise ValueError("artifact algorithm identity is invalid")
        symbols = tuple(entry.gene_symbol for entry in self.genes)
        if symbols != tuple(sorted(symbols)) or len(symbols) != len(set(symbols)):
            raise ValueError("artifact genes must be unique and sorted")
        attempted = self.attempted_gene_symbols
        if attempted != tuple(sorted(attempted)) or len(attempted) != len(set(attempted)):
            raise ValueError("attempted artifact genes must be unique and sorted")
        if not set(symbols).issubset(attempted):
            raise ValueError("fitted artifact genes must be a subset of attempted genes")
        if self.cohort.fitted_gene_count != len(self.genes):
            raise ValueError("artifact fitted-gene count does not match its entries")
        source_ids = tuple(lock.source_id for lock in self.source_locks)
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("artifact source locks must be unique")
        if source_ids != tuple(sorted(source_ids)):
            raise ValueError("artifact source locks must be sorted by source ID")
        if self.artifact_content_digest != artifact_content_digest(self):
            raise ValueError("artifact content digest does not match canonical content")
        return self


_ARTIFACT_ADAPTER = TypeAdapter(TranscriptProteinDiscordanceArtifact)


def artifact_byte_digest(payload: bytes) -> Sha256Digest:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def build_artifact(
    *,
    source_locks: tuple[ExactSourceLock, ...],
    cohort: CohortArtifactSummary,
    attempted_gene_symbols: tuple[GeneSymbol, ...],
    gene_statistics: Mapping[str, GeneDiscordanceStatistics],
    derivation_status: DerivationStatus,
) -> TranscriptProteinDiscordanceArtifact:
    """Build one deidentified aggregate artifact; transient OOF arrays are excluded."""

    profile = algorithm_profile()
    ordered_source_locks = tuple(sorted(source_locks, key=lambda lock: lock.source_id))
    ordered = tuple(
        ArtifactGeneEntry(gene_symbol=symbol, statistics=gene_statistics[symbol])
        for symbol in sorted(gene_statistics)
    )
    payload = {
        "schema_version": ARTIFACT_SCHEMA,
        "algorithm_id": ALGORITHM_ID,
        "profile_id": PROFILE_ID,
        "profile_digest": profile.profile_digest,
        "artifact_content_digest": "sha256:" + "0" * 64,
        "derivation_status": derivation_status.value,
        "source_locks": [lock.model_dump(mode="json") for lock in ordered_source_locks],
        "cohort": cohort.model_dump(mode="json"),
        "attempted_gene_symbols": sorted(attempted_gene_symbols),
        "genes": [entry.model_dump(mode="json") for entry in ordered],
        "redistribution_status": "local_only_terms_unverified",
    }
    payload["artifact_content_digest"] = artifact_content_digest(payload)
    try:
        artifact = _ARTIFACT_ADAPTER.validate_json(canonical_json_bytes(payload), strict=True)
    except ValidationError as error:
        raise DiscordanceArtifactIntegrityError(
            "generated discordance artifact does not satisfy its schema"
        ) from error
    if len(canonical_json_bytes(artifact)) > MAX_ARTIFACT_BYTES:
        raise DiscordanceArtifactIntegrityError(
            "generated discordance artifact exceeds the 32 MiB safety bound"
        )
    return artifact


def write_artifact(
    path: Path,
    artifact: TranscriptProteinDiscordanceArtifact,
) -> tuple[Sha256Digest, int]:
    """Publish canonical bytes atomically without overwriting a caller file."""

    payload = canonical_json_bytes(artifact)
    if len(payload) > MAX_ARTIFACT_BYTES:
        raise DiscordanceArtifactIntegrityError(
            "discordance artifact exceeds the 32 MiB safety bound"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    with ExitStack() as cleanup:
        try:
            with NamedTemporaryFile(
                mode="wb",
                prefix=f".{path.name}.",
                suffix=".tmp",
                dir=path.parent,
                delete=False,
            ) as stream:
                temporary_path = Path(stream.name)
                cleanup.callback(temporary_path.unlink, missing_ok=True)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.link(temporary_path, path)
        except FileExistsError:
            raise DiscordanceArtifactIntegrityError(
                "refusing to overwrite an existing discordance artifact"
            ) from None
        except OSError as error:
            raise DiscordanceArtifactIntegrityError(
                "discordance artifact could not be published atomically"
            ) from error
    return artifact_byte_digest(payload), len(payload)


def _read_bounded_artifact_stream(stream: BinaryIO) -> bytes:
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
        raise DiscordanceArtifactIntegrityError(
            "discordance artifact exceeds the 32 MiB safety bound"
        )
    return b"".join(chunks)


def _read_artifact_bytes(path: Path) -> bytes:
    with path.open("rb") as stream:
        return _read_bounded_artifact_stream(stream)


def load_artifact(
    path: Path,
) -> tuple[TranscriptProteinDiscordanceArtifact, Sha256Digest]:
    try:
        payload = _read_artifact_bytes(path)
        strict_json_loads(payload, max_bytes=MAX_ARTIFACT_BYTES)
        artifact = _ARTIFACT_ADAPTER.validate_json(payload, strict=True)
    except DiscordanceArtifactIntegrityError:
        raise
    except (OSError, StrictJsonError, ValidationError) as error:
        raise DiscordanceArtifactIntegrityError(
            "discordance artifact is unavailable or invalid"
        ) from error
    if payload != canonical_json_bytes(artifact):
        raise DiscordanceArtifactIntegrityError(
            "discordance artifact bytes are not in canonical form"
        )
    return artifact, artifact_byte_digest(payload)


__all__ = [
    "ArtifactGeneEntry",
    "TranscriptProteinDiscordanceArtifact",
    "artifact_byte_digest",
    "build_artifact",
    "load_artifact",
    "write_artifact",
]
