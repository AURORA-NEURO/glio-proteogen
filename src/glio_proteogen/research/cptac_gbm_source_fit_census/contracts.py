"""Closed aggregate contracts for an additive source-only fitting census."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Final, Protocol

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.research.cptac_gbm_external_admission.contracts import GeneIdentity
from glio_proteogen.research.cptac_gbm_external_admission.transfer import SourceFitReceipt
from glio_proteogen.research.cptac_gbm_feature_space.contracts import MAX_FEATURES

PROFILE_ID: Final = "cptac-gbm-source-fit-census/1.0.0"
DEFAULT_PAGE_SIZE: Final = 32
MAX_PAGE_SIZE: Final = 64
MAX_PAGE_BYTES: Final = 8 * 1024 * 1024
MAX_MANIFEST_BYTES: Final = MAX_PAGE_BYTES
MAX_SOURCE_BYTES: Final = 512 * 1024 * 1024
MANIFEST_NAME: Final = "source-census-manifest.json"
INPUT_DOMAIN_REJECTION: Final = "source finite inputs exceed the frozen fitting magnitude domain"


class CensusError(ValueError):
    """A sanitized source-census contract failure without private measurements."""


def require_digest(value: str) -> str:
    if type(value) is not str or re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None:
        raise CensusError("a canonical source-census digest is required")
    return value


def require_integer(value: int, *, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise CensusError("source-census count is outside its declared bound")
    return value


def _hgnc_id(value: str) -> bool:
    return type(value) is str and re.fullmatch(r"HGNC:[1-9][0-9]*", value) is not None


def _context(profile_id: str, *digests: str) -> None:
    if type(profile_id) is not str or profile_id != PROFILE_ID:
        raise CensusError("source-census profile does not match the frozen method")
    for digest in digests:
        require_digest(digest)


@dataclass(frozen=True, slots=True)
class SourceGeneReceipt:
    identity: GeneIdentity
    source: SourceFitReceipt | None
    input_domain_rejection: str | None

    def __post_init__(self) -> None:
        if (
            type(self.identity) is not GeneIdentity
            or (self.source is None) == (self.input_domain_rejection is None)
            or (self.source is not None and type(self.source) is not SourceFitReceipt)
            or (
                self.input_domain_rejection is not None
                and self.input_domain_rejection != INPUT_DOMAIN_REJECTION
            )
        ):
            raise CensusError(
                "gene receipt requires an original fit receipt or exact domain rejection"
            )

    @property
    def digest(self) -> str:
        return sha256_digest(asdict(self))


@dataclass(frozen=True, slots=True)
class SourceReceiptPage:
    profile_id: str
    request_digest: str
    feature_axis_digest: str
    candidate_digest: str
    source_catalog_digest: str
    source_fold_assignment_digest: str
    page_number: int
    genes: tuple[SourceGeneReceipt, ...]

    def __post_init__(self) -> None:
        _context(
            self.profile_id,
            self.request_digest,
            self.feature_axis_digest,
            self.candidate_digest,
            self.source_catalog_digest,
            self.source_fold_assignment_digest,
        )
        require_integer(self.page_number, minimum=0, maximum=MAX_FEATURES - 1)
        if (
            type(self.genes) is not tuple
            or not 1 <= len(self.genes) <= MAX_PAGE_SIZE
            or any(type(record) is not SourceGeneReceipt for record in self.genes)
        ):
            raise CensusError("source receipt page requires bounded typed gene records")
        keys = tuple(record.identity.hgnc_id for record in self.genes)
        if keys != tuple(sorted(set(keys))):
            raise CensusError("source receipt page identities must be unique and ordered")

    @property
    def digest(self) -> str:
        return sha256_digest(asdict(self))


@dataclass(frozen=True, slots=True)
class ReceiptPageBinding:
    page_number: int
    file_name: str
    bytes: int
    sha256: str
    page_digest: str
    gene_count: int
    first_hgnc_id: str
    last_hgnc_id: str

    def __post_init__(self) -> None:
        require_integer(self.page_number, minimum=0, maximum=MAX_FEATURES - 1)
        require_integer(self.bytes, minimum=1, maximum=MAX_PAGE_BYTES)
        require_integer(self.gene_count, minimum=1, maximum=MAX_PAGE_SIZE)
        require_digest(self.sha256)
        require_digest(self.page_digest)
        if (
            self.file_name != f"pages/{self.page_number:05d}.json"
            or not _hgnc_id(self.first_hgnc_id)
            or not _hgnc_id(self.last_hgnc_id)
            or (self.first_hgnc_id == self.last_hgnc_id) != (self.gene_count == 1)
            or self.first_hgnc_id > self.last_hgnc_id
        ):
            raise CensusError("source page binding path or gene range is invalid")


@dataclass(frozen=True, slots=True)
class SourceCensusReceipt:
    profile_id: str
    request_digest: str
    feature_axis_digest: str
    candidate_digest: str
    source_catalog_digest: str
    source_fold_assignment_digest: str
    total_genes: int
    accepted_genes: int
    abstained_genes: int
    input_domain_rejected_genes: int
    page_size: int
    pages: tuple[ReceiptPageBinding, ...]
    gene_record_digests: tuple[str, ...]
    external_measurements_read: bool = False
    complete: bool = True

    def __post_init__(self) -> None:
        _context(
            self.profile_id,
            self.request_digest,
            self.feature_axis_digest,
            self.candidate_digest,
            self.source_catalog_digest,
            self.source_fold_assignment_digest,
        )
        require_integer(self.total_genes, minimum=1, maximum=MAX_FEATURES)
        require_integer(self.page_size, minimum=1, maximum=MAX_PAGE_SIZE)
        for count in (self.accepted_genes, self.abstained_genes, self.input_domain_rejected_genes):
            require_integer(count, minimum=0, maximum=self.total_genes)
        if (
            self.accepted_genes + self.abstained_genes + self.input_domain_rejected_genes
            != self.total_genes
            or type(self.pages) is not tuple
            or len(self.pages) != (self.total_genes + self.page_size - 1) // self.page_size
            or any(type(page) is not ReceiptPageBinding for page in self.pages)
            or type(self.gene_record_digests) is not tuple
            or len(self.gene_record_digests) != self.total_genes
            or any(type(digest) is not str for digest in self.gene_record_digests)
            or len(set(self.gene_record_digests)) != self.total_genes
            or self.external_measurements_read is not False
            or self.complete is not True
        ):
            raise CensusError("source-census manifest does not retain a complete ordered inventory")
        for digest in self.gene_record_digests:
            require_digest(digest)
        for index, page in enumerate(self.pages):
            remaining = self.total_genes - index * self.page_size
            if (
                page.page_number != index
                or page.gene_count != min(self.page_size, remaining)
                or (index and self.pages[index - 1].last_hgnc_id >= page.first_hgnc_id)
            ):
                raise CensusError("source-census page ranges do not partition the gene inventory")
        if sum(page.bytes for page in self.pages) > MAX_SOURCE_BYTES:
            raise CensusError("source receipt pages exceed their total byte bound")

    @property
    def digest(self) -> str:
        return sha256_digest(asdict(self))


@dataclass(frozen=True, slots=True)
class SourceManifestBinding:
    file_name: str
    bytes: int
    sha256: str
    manifest_digest: str

    def __post_init__(self) -> None:
        require_integer(self.bytes, minimum=1, maximum=MAX_MANIFEST_BYTES)
        require_digest(self.sha256)
        require_digest(self.manifest_digest)
        if self.file_name != MANIFEST_NAME:
            raise CensusError("source manifest file name is not the declared aggregate path")


def page_document(page: SourceReceiptPage) -> dict[str, object]:
    if type(page) is not SourceReceiptPage:
        raise CensusError("a typed source receipt page is required")
    return {**asdict(page), "page_digest": page.digest}


def manifest_document(manifest: SourceCensusReceipt) -> dict[str, object]:
    if type(manifest) is not SourceCensusReceipt:
        raise CensusError("a typed source census manifest is required")
    return {**asdict(manifest), "manifest_digest": manifest.digest}


def page_bytes(page: SourceReceiptPage) -> bytes:
    payload = canonical_json_bytes(page_document(page))
    if len(payload) > MAX_PAGE_BYTES:
        raise CensusError("canonical source receipt page exceeds its byte bound")
    return payload


def manifest_bytes(manifest: SourceCensusReceipt) -> bytes:
    payload = canonical_json_bytes(manifest_document(manifest))
    if len(payload) > MAX_MANIFEST_BYTES:
        raise CensusError("canonical source census manifest exceeds its byte bound")
    return payload


class CensusReceiptStore(Protocol):
    def write_page(self, page: SourceReceiptPage) -> ReceiptPageBinding: ...

    def seal(self, manifest: SourceCensusReceipt) -> SourceManifestBinding: ...

    def read_page(self, binding: ReceiptPageBinding) -> SourceReceiptPage: ...
