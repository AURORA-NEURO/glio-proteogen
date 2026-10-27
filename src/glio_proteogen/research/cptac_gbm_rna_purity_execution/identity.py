"""Frozen GENCODE v36 source coordinates for the unchanged released model axis.

Historical source coordinates and current approved HGNC identity are separate.
In particular, the historical ALOX12-AS1 locus is never replaced by MIR497HG,
and absent current HGNC Ensembl links remain absent. No model is loaded here.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import math
import re
from collections import Counter
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final, Literal, NoReturn, Self, SupportsIndex

from pydantic import model_validator

from glio_proteogen.kernel.models import FrozenModel, Sha256Digest
from glio_proteogen.research.cptac_gbm_external_admission.contracts import (
    HgncReference,
    SourceLock,
    SourceVerificationError,
)
from glio_proteogen.research.cptac_gbm_external_admission.identity import (
    HGNC_LOCK,
    normalize_ensembl_gene_id,
)
from glio_proteogen.research.cptac_gbm_external_admission.source import read_verified_source
from glio_proteogen.research.cptac_gbm_rna_purity_admission.identity import (
    _released_metadata,
    canonical_hgnc_reference_digest,
)
from glio_proteogen.research.gbm_rna_purity.catalog import (
    EXPECTED_ARTIFACT_SHA256,
    EXPECTED_CONTENT_DIGEST,
    EXPECTED_FEATURE_ORDER_DIGEST,
    EXPECTED_SOURCE_FEATURE_SHA256,
)

from .contracts import PROFILE_ID, ExecutionError, digest

COORDINATE_POLICY_ID: Final = "gbmpurity-gencode-v36-source-coordinate-bridge/1.0.0"
GTF_URL: Final = "https://ftp.ebi.ac.uk/pub/databases/gencode/Gencode_human/release_36/gencode.v36.annotation.gtf.gz"
HGNC_METADATA_URL: Final = "https://ftp.ebi.ac.uk/pub/databases/gencode/Gencode_human/release_36/gencode.v36.metadata.HGNC.gz"
AUTHOR_FEATURE_URL: Final = "https://raw.githubusercontent.com/scmpht/GBMPurity/af054edcf4c54e9bbcf0dbe6d89dfac6e20aa950/model/input-genes-lengths.csv"
GTF_LOCK: Final = SourceLock(
    44_507_458,
    "c03931958d4572148650d62eb6dec41a",
    "81359865bab048361cbeaf91c9441aac4c700b63978e6691d579d78bf2322d30",
)
HGNC_METADATA_LOCK: Final = SourceLock(
    1_484_010,
    "59e4d4aebad66fcadecbbc7a363c81d3",
    "457690081684ad9908fca9533ecd0208caa918fdd4ee6563db1791fc1afe4841",
)
AUTHOR_FEATURE_LOCK: Final = SourceLock(
    67_177,
    "2e796bbf54f64ef60afa36a6ec36e823",
    "2f81ea201380a13a0432b670228dbd356ed1c771a64a271e0eb83bd6e060db80",
)
EXPECTED_HGNC_REFERENCE_DIGEST: Final = (
    "sha256:a8678e81ed784a45d3880cbf32413cb567a2912dc31c6da3d173b42455023214"
)
# Independently reproducible canonical mapping from the three locked sources and
# the fixed HGNC snapshot. A caller cannot reseal an invented coordinate mapping.
EXPECTED_MAPPING_DIGEST: Final = (
    "sha256:b729be401b71cd7257cfc34d77082946c09c9928a2fbca77d1eb4f8f906c2b72"
)
MAX_REFERENCE_LINE_BYTES: Final = 65_536
MAX_REFERENCE_LINES: Final = 4_000_000
MAX_GTF_UNCOMPRESSED_BYTES: Final = 1_500_000_000
MAX_HGNC_UNCOMPRESSED_BYTES: Final = 8_000_000
EVIDENCE_CATEGORIES: Final = (
    "current_hgnc_coordinate_agreement",
    "current_hgnc_rename_agreement",
    "historical_hgnc_name_link",
    "historical_coordinate_current_ensembl_unasserted",
    "historical_coordinate_current_nomenclature_conflict",
)
EvidenceCategory = Literal[
    "current_hgnc_coordinate_agreement",
    "current_hgnc_rename_agreement",
    "historical_hgnc_name_link",
    "historical_coordinate_current_ensembl_unasserted",
    "historical_coordinate_current_nomenclature_conflict",
]
_ENSEMBL_VERSIONED: Final = re.compile(r"ENSG[0-9]{11}\.[1-9][0-9]*(?:_PAR_Y)?")
_ENSEMBL_STABLE: Final = re.compile(r"ENSG[0-9]{11}(?:_PAR_Y)?")
_TRANSCRIPT: Final = re.compile(r"ENST[0-9]{11}\.[1-9][0-9]*(?:_PAR_Y)?")
_HGNC: Final = re.compile(r"HGNC:[1-9][0-9]*")


class ModelAxisError(ExecutionError):
    """A sanitized reference lock, released-axis or source-coordinate failure."""


@dataclass(frozen=True, slots=True)
class ModelInputFeature:
    """Original model feature with a separately attributed historical coordinate."""

    source_symbol: str
    source_length: float
    release_gene_id: str
    ensembl_gene_id: str
    release_hgnc_id: str
    gene_type: str
    current_hgnc_symbol: str | None
    current_hgnc_ensembl_gene_id: str | None
    evidence_category: EvidenceCategory

    def __post_init__(self) -> None:
        if (
            not _valid_name(self.source_symbol)
            or type(self.source_length) is not float
            or not math.isfinite(self.source_length)
            or self.source_length <= 0
            or type(self.release_gene_id) is not str
            or _ENSEMBL_VERSIONED.fullmatch(self.release_gene_id) is None
            or normalize_ensembl_gene_id(self.release_gene_id) != self.ensembl_gene_id
            or type(self.release_hgnc_id) is not str
            or _HGNC.fullmatch(self.release_hgnc_id) is None
            or not _valid_name(self.gene_type)
            or self.evidence_category not in EVIDENCE_CATEGORIES
            or (self.current_hgnc_symbol is not None and not _valid_name(self.current_hgnc_symbol))
            or (
                self.current_hgnc_ensembl_gene_id is not None
                and (
                    type(self.current_hgnc_ensembl_gene_id) is not str
                    or _ENSEMBL_STABLE.fullmatch(self.current_hgnc_ensembl_gene_id) is None
                )
            )
        ):
            raise ModelAxisError("released source coordinate is invalid")


class ModelAxisReceipt(FrozenModel):
    """Aggregate proof of the exact release/reference policy; no specimen data."""

    schema_version: Literal["glio-proteogen.purity-source-coordinate-receipt/1.0.0"] = (
        "glio-proteogen.purity-source-coordinate-receipt/1.0.0"
    )
    profile_id: Literal["cptac-gbm-native-star-purity-execution/1.0.0"] = PROFILE_ID
    coordinate_policy_id: Literal["gbmpurity-gencode-v36-source-coordinate-bridge/1.0.0"] = (
        COORDINATE_POLICY_ID
    )
    model_artifact_sha256: Sha256Digest = EXPECTED_ARTIFACT_SHA256
    model_content_digest: Sha256Digest = EXPECTED_CONTENT_DIGEST
    feature_order_digest: Sha256Digest = EXPECTED_FEATURE_ORDER_DIGEST
    feature_length_digest: Sha256Digest
    feature_mapping_digest: Sha256Digest
    canonical_hgnc_reference_digest: Sha256Digest = EXPECTED_HGNC_REFERENCE_DIGEST
    hgnc_source_sha256: Sha256Digest = "sha256:" + HGNC_LOCK.sha256
    gencode_gtf_sha256: Sha256Digest = "sha256:" + GTF_LOCK.sha256
    gencode_gtf_bytes: Literal[44_507_458] = 44_507_458
    gencode_hgnc_metadata_sha256: Sha256Digest = "sha256:" + HGNC_METADATA_LOCK.sha256
    gencode_hgnc_metadata_bytes: Literal[1_484_010] = 1_484_010
    author_feature_lf_sha256: Sha256Digest = "sha256:" + AUTHOR_FEATURE_LOCK.sha256
    author_feature_lf_bytes: Literal[67_177] = 67_177
    author_feature_crlf_sha256: Sha256Digest = EXPECTED_SOURCE_FEATURE_SHA256
    annotation_release: Literal["GENCODE v36"] = "GENCODE v36"
    assembly: Literal["GRCh38.p13"] = "GRCh38.p13"
    model_feature_count: Literal[5_829] = 5_829
    unique_source_coordinates: Literal[5_829] = 5_829
    prior_exact_hgnc_features: Literal[5_735] = 5_735
    current_hgnc_rename_features: Literal[89] = 89
    historical_hgnc_name_link_features: Literal[1] = 1
    current_ensembl_unasserted_features: Literal[3] = 3
    current_nomenclature_conflict_features: Literal[1] = 1
    unresolved_source_coordinates: Literal[0] = 0
    source_alias_fallback_used: Literal[False] = False
    model_executed: Literal[False] = False

    @model_validator(mode="after")
    def fixed_bindings(self) -> Self:
        expected = {
            "model_artifact_sha256": EXPECTED_ARTIFACT_SHA256,
            "model_content_digest": EXPECTED_CONTENT_DIGEST,
            "feature_order_digest": EXPECTED_FEATURE_ORDER_DIGEST,
            "feature_mapping_digest": EXPECTED_MAPPING_DIGEST,
            "canonical_hgnc_reference_digest": EXPECTED_HGNC_REFERENCE_DIGEST,
            "hgnc_source_sha256": "sha256:" + HGNC_LOCK.sha256,
            "gencode_gtf_sha256": "sha256:" + GTF_LOCK.sha256,
            "gencode_hgnc_metadata_sha256": "sha256:" + HGNC_METADATA_LOCK.sha256,
            "author_feature_lf_sha256": "sha256:" + AUTHOR_FEATURE_LOCK.sha256,
            "author_feature_crlf_sha256": EXPECTED_SOURCE_FEATURE_SHA256,
            "feature_length_digest": digest(_released_metadata()[1]),
        }
        if any(getattr(self, key) != value for key, value in expected.items()):
            raise ValueError("source coordinate receipt differs from the fixed evidence")
        return self


def _valid_name(value: object) -> bool:
    return (
        type(value) is str
        and 1 <= len(value) <= 128
        and not any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value)
    )


def _gzip_lines(payload: bytes, *, max_bytes: int) -> Iterator[str]:
    """Bound both expansion and individual records, including truncated gzip CRCs."""
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(payload), mode="rb") as stream:
            total = lines = 0
            while raw := stream.readline(MAX_REFERENCE_LINE_BYTES + 1):
                total += len(raw)
                lines += 1
                if (
                    len(raw) > MAX_REFERENCE_LINE_BYTES
                    or total > max_bytes
                    or lines > MAX_REFERENCE_LINES
                ):
                    raise ModelAxisError("reference expansion exceeds its bounded grammar")
                yield raw.decode("utf-8", errors="strict").rstrip("\r\n")
    except (OSError, EOFError, UnicodeError, ValueError) as error:
        if isinstance(error, ModelAxisError):
            raise
        raise ModelAxisError("compressed reference could not be safely decoded") from None


def _attribute(attributes: str, name: str) -> str:
    matches: list[str] = re.findall(r"(?:^|; )" + name + r' "([^"\r\n]*)"(?:;|$)', attributes)
    if len(matches) != 1 or not matches[0]:
        raise ModelAxisError("release reference has an invalid required attribute")
    return matches[0]


@dataclass(frozen=True, slots=True)
class _ReleaseGene:
    source_symbol: str
    release_gene_id: str
    gene_type: str


def _decode_gtf(
    payload: bytes, names: tuple[str, ...]
) -> tuple[dict[str, _ReleaseGene], dict[str, tuple[str, str]]]:
    wanted = frozenset(names)
    genes: dict[str, _ReleaseGene] = {}
    gene_ids: set[str] = set()
    transcripts: dict[str, tuple[str, str]] = {}
    for line in _gzip_lines(payload, max_bytes=MAX_GTF_UNCOMPRESSED_BYTES):
        if line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) != 9:
            raise ModelAxisError("release annotation row width is invalid")
        if fields[2] not in {"gene", "transcript"}:
            continue
        gene_id = _attribute(fields[8], "gene_id")
        symbol = _attribute(fields[8], "gene_name")
        if _ENSEMBL_VERSIONED.fullmatch(gene_id) is None or not _valid_name(symbol):
            raise ModelAxisError("release annotation identity is invalid")
        if fields[2] == "gene":
            if gene_id in gene_ids:
                raise ModelAxisError("release annotation gene IDs are duplicated")
            gene_ids.add(gene_id)
            if symbol in wanted:
                if symbol in genes:
                    raise ModelAxisError("model source name has multiple release coordinates")
                genes[symbol] = _ReleaseGene(symbol, gene_id, _attribute(fields[8], "gene_type"))
        else:
            transcript = _attribute(fields[8], "transcript_id")
            if _TRANSCRIPT.fullmatch(transcript) is None or transcript in transcripts:
                raise ModelAxisError("release annotation transcript identity is invalid")
            transcripts[transcript] = (gene_id, symbol)
    if set(genes) != wanted:
        raise ModelAxisError("release annotation does not cover the exact source axis")
    return genes, transcripts


def _decode_hgnc_metadata(
    payload: bytes, genes: dict[str, _ReleaseGene], transcripts: dict[str, tuple[str, str]]
) -> dict[str, str]:
    candidates: dict[str, set[str]] = {symbol: set() for symbol in genes}
    joined: set[str] = set()
    seen: set[str] = set()
    for line in _gzip_lines(payload, max_bytes=MAX_HGNC_UNCOMPRESSED_BYTES):
        row = line.split("\t")
        if (
            len(row) != 3
            or _TRANSCRIPT.fullmatch(row[0]) is None
            or not _valid_name(row[1])
            or _HGNC.fullmatch(row[2]) is None
            or row[0] in seen
        ):
            raise ModelAxisError("release HGNC metadata row is invalid or duplicated")
        seen.add(row[0])
        if row[1] not in genes:
            continue
        candidates[row[1]].add(row[2])
        link = transcripts.get(row[0])
        # Metadata is ALL regions, whereas the locked GTF is CHR. Missing ALL
        # transcripts create no join. Every feature still needs an exact CHR join.
        if link is not None:
            if link != (genes[row[1]].release_gene_id, row[1]):
                raise ModelAxisError("release HGNC transcript points to a different coordinate")
            joined.add(row[1])
    if joined != set(genes) or any(len(values) != 1 for values in candidates.values()):
        raise ModelAxisError("release HGNC joins are absent or ambiguous")
    return {symbol: next(iter(values)) for symbol, values in candidates.items()}


def _author_table(payload: bytes) -> None:
    names, lengths = _released_metadata()
    if b"\r" in payload or (
        "sha256:" + hashlib.sha256(payload.replace(b"\n", b"\r\n")).hexdigest()
        != EXPECTED_SOURCE_FEATURE_SHA256
    ):
        raise ModelAxisError("author feature table does not reproduce the imported CRLF lock")
    try:
        reader = csv.reader(io.StringIO(payload.decode("utf-8"), newline=""), strict=True)
        if next(reader) != ["feature_name", "feature_length"]:
            raise ModelAxisError("author feature table header is invalid")
        rows = tuple(reader)
        if len(rows) != len(names) or any(
            len(row) != 2 or row[0] != name or float(row[1]) != length
            for row, name, length in zip(rows, names, lengths, strict=True)
        ):
            raise ModelAxisError("author feature table differs from the exact released axis")
    except (csv.Error, UnicodeError, ValueError, StopIteration) as error:
        if isinstance(error, ModelAxisError):
            raise
        raise ModelAxisError("author feature table could not be safely decoded") from None


def _feature(
    symbol: str, length: float, gene: _ReleaseGene, hgnc_id: str, hgnc: HgncReference
) -> ModelInputFeature:
    coordinate = normalize_ensembl_gene_id(gene.release_gene_id)
    current = hgnc.by_hgnc.get(hgnc_id)
    exact = hgnc.by_symbol.get(symbol)
    if exact is not None and exact == current and exact.ensembl_gene_id == coordinate:
        category: EvidenceCategory = "current_hgnc_coordinate_agreement"
    elif current is not None and current.ensembl_gene_id == coordinate:
        category = (
            "historical_hgnc_name_link" if symbol == "IQCD" else "current_hgnc_rename_agreement"
        )
    elif (
        current is not None
        and current.symbol == symbol
        and current.ensembl_gene_id is None
        and symbol in {"MTRNR2L1", "MTRNR2L12", "MTRNR2L8"}
    ):
        category = "historical_coordinate_current_ensembl_unasserted"
    elif (
        current is None
        and symbol == "ALOX12-AS1"
        and hgnc_id == "HGNC:51342"
        and gene.release_gene_id == "ENSG00000215067.10"
    ):
        category = "historical_coordinate_current_nomenclature_conflict"
    else:
        raise ModelAxisError("release coordinate has unsupported current-reference evidence")
    return ModelInputFeature(
        symbol,
        length,
        gene.release_gene_id,
        coordinate,
        hgnc_id,
        gene.gene_type,
        current.symbol if current is not None else None,
        current.ensembl_gene_id if current is not None else None,
        category,
    )


class ModelInputAxis:
    """Complete immutable axis sealed to independently verified source coordinates."""

    __slots__ = ("_features", "_receipt")
    _features: tuple[ModelInputFeature, ...]
    _receipt: ModelAxisReceipt

    def __init__(self, features: tuple[ModelInputFeature, ...], receipt: ModelAxisReceipt) -> None:
        if (
            type(features) is not tuple
            or any(type(item) is not ModelInputFeature for item in features)
            or type(receipt) is not ModelAxisReceipt
        ):
            raise ModelAxisError("an exact released coordinate axis and receipt are required")
        try:
            checked = ModelAxisReceipt.model_validate(
                receipt.model_dump(mode="python"), strict=True
            )
            reconstructed = tuple(ModelInputFeature(**asdict(item)) for item in features)
        except (AttributeError, TypeError, ValueError):
            raise ModelAxisError("released coordinate axis is invalid") from None
        names, lengths = _released_metadata()
        categories = Counter(item.evidence_category for item in reconstructed)
        if (
            tuple(item.source_symbol for item in reconstructed) != names
            or tuple(item.source_length for item in reconstructed) != lengths
            or len({item.ensembl_gene_id for item in reconstructed}) != len(names)
            or len({item.release_hgnc_id for item in reconstructed}) != len(names)
            or tuple(categories[category] for category in EVIDENCE_CATEGORIES)
            != (5_735, 89, 1, 3, 1)
            or digest(tuple(asdict(item) for item in reconstructed)) != EXPECTED_MAPPING_DIGEST
        ):
            raise ModelAxisError("released axis differs from its fixed source-coordinate proof")
        object.__setattr__(self, "_features", reconstructed)
        object.__setattr__(self, "_receipt", checked)

    def __setattr__(self, _name: str, _value: object) -> NoReturn:
        raise AttributeError("released source coordinate axis is immutable")

    @property
    def features(self) -> tuple[ModelInputFeature, ...]:
        return self._features

    @property
    def receipt(self) -> ModelAxisReceipt:
        return self._receipt

    @property
    def digest(self) -> str:
        return digest(self.receipt.model_dump(mode="json"))

    def __repr__(self) -> str:
        return "ModelInputAxis(released_source_coordinates=5829)"

    def __getstate__(self) -> NoReturn:
        raise TypeError("source coordinate axis cannot be implicitly serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("source coordinate axis cannot be implicitly serialized")


def admit_model_axis(
    *,
    hgnc: HgncReference,
    gencode_gtf_path: str | Path,
    gencode_hgnc_path: str | Path,
    author_feature_path: str | Path,
) -> ModelInputAxis:
    """Reverify each reference on preparation; never open assays or model weights."""
    try:
        reference_digest = canonical_hgnc_reference_digest(hgnc)
        if reference_digest != EXPECTED_HGNC_REFERENCE_DIGEST:
            raise ModelAxisError("approved HGNC indexes differ from the fixed snapshot")
        author = read_verified_source(
            author_feature_path, AUTHOR_FEATURE_LOCK, max_bytes=AUTHOR_FEATURE_LOCK.bytes
        )
        _author_table(author)
        gt = read_verified_source(gencode_gtf_path, GTF_LOCK, max_bytes=GTF_LOCK.bytes)
        hm = read_verified_source(
            gencode_hgnc_path, HGNC_METADATA_LOCK, max_bytes=HGNC_METADATA_LOCK.bytes
        )
        names, lengths = _released_metadata()
        genes, transcripts = _decode_gtf(gt, names)
        hgnc_ids = _decode_hgnc_metadata(hm, genes, transcripts)
        features = tuple(
            _feature(symbol, length, genes[symbol], hgnc_ids[symbol], hgnc)
            for symbol, length in zip(names, lengths, strict=True)
        )
        receipt = ModelAxisReceipt(
            feature_length_digest=digest(lengths),
            feature_mapping_digest=digest(tuple(asdict(item) for item in features)),
            canonical_hgnc_reference_digest=reference_digest,
        )
        return ModelInputAxis(features, receipt)
    except (SourceVerificationError, AttributeError, TypeError, ValueError) as error:
        if isinstance(error, ModelAxisError):
            raise
        raise ModelAxisError("fixed source coordinates could not be admitted") from None


def validate_model_axis(model_axis: ModelInputAxis) -> None:
    """Reject mutated coordinates or resealed caller mappings without reference I/O."""
    if type(model_axis) is not ModelInputAxis:
        raise ModelAxisError("an exact released source coordinate axis is required")
    try:
        ModelInputAxis(model_axis.features, model_axis.receipt)
    except (AttributeError, TypeError, ValueError):
        raise ModelAxisError("released source coordinate proof is invalid") from None


__all__ = [
    "AUTHOR_FEATURE_LOCK",
    "AUTHOR_FEATURE_URL",
    "COORDINATE_POLICY_ID",
    "EVIDENCE_CATEGORIES",
    "EXPECTED_HGNC_REFERENCE_DIGEST",
    "EXPECTED_MAPPING_DIGEST",
    "GTF_LOCK",
    "GTF_URL",
    "HGNC_METADATA_LOCK",
    "HGNC_METADATA_URL",
    "ModelAxisError",
    "ModelAxisReceipt",
    "ModelInputAxis",
    "ModelInputFeature",
    "admit_model_axis",
    "validate_model_axis",
]
