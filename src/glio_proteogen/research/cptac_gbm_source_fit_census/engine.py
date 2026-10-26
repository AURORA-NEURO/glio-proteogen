"""Complete source-only fitting with paged aggregate evidence and private predictors."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from types import MappingProxyType
from typing import NoReturn, SupportsIndex

import numpy as np
import numpy.typing as npt

from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.research.cptac_gbm_external_admission import transfer
from glio_proteogen.research.cptac_gbm_external_admission.transfer import (
    FrozenSourceGeneFit,
    SourceFitReceipt,
    fit_source_gene,
)
from glio_proteogen.research.cptac_gbm_feature_space.atlas import SourceFeatureCatalog
from glio_proteogen.research.cptac_gbm_feature_space.contracts import (
    PROFILE_ID as FEATURE_SPACE_PROFILE_ID,
)
from glio_proteogen.research.cptac_gbm_feature_space.contracts import FeatureMatrix
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance.nested_selection import (
    MAX_ABSOLUTE_INPUT,
)

from .contracts import (
    DEFAULT_PAGE_SIZE,
    INPUT_DOMAIN_REJECTION,
    MAX_PAGE_SIZE,
    MAX_SOURCE_BYTES,
    PROFILE_ID,
    CensusError,
    CensusReceiptStore,
    ReceiptPageBinding,
    SourceCensusReceipt,
    SourceGeneReceipt,
    SourceManifestBinding,
    SourceReceiptPage,
    manifest_bytes,
    page_bytes,
    require_digest,
    require_integer,
)

FoldArray = npt.NDArray[np.int8]
Predictors = tuple[transfer._FrozenPredictor, ...]


def _bytes_digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _check_page_binding(page: SourceReceiptPage, binding: ReceiptPageBinding) -> None:
    if type(page) is not SourceReceiptPage or type(binding) is not ReceiptPageBinding:
        raise CensusError("a typed persisted source page and binding are required")
    payload = page_bytes(page)
    if (
        binding.page_number != page.page_number
        or binding.bytes != len(payload)
        or binding.sha256 != _bytes_digest(payload)
        or binding.page_digest != page.digest
        or binding.gene_count != len(page.genes)
        or binding.first_hgnc_id != page.genes[0].identity.hgnc_id
        or binding.last_hgnc_id != page.genes[-1].identity.hgnc_id
    ):
        raise CensusError("persisted source page differs from its exact aggregate binding")


def _check_manifest_binding(receipt: SourceCensusReceipt, binding: SourceManifestBinding) -> None:
    if type(binding) is not SourceManifestBinding:
        raise CensusError("a typed sealed source manifest binding is required")
    payload = manifest_bytes(receipt)
    if (
        binding.bytes != len(payload)
        or binding.sha256 != _bytes_digest(payload)
        or binding.manifest_digest != receipt.digest
    ):
        raise CensusError("sealed source manifest differs from its exact aggregate binding")


def _check_predictors(receipt: SourceFitReceipt, predictors: Predictors) -> None:
    if (
        type(receipt) is not SourceFitReceipt
        or receipt.profile_id != transfer.PROFILE_ID
        or type(receipt.accepted) is not bool
        or type(predictors) is not tuple
        or any(type(item) is not transfer._FrozenPredictor for item in predictors)
        or (
            receipt.accepted
            and tuple(item.candidate for item in predictors) != transfer.CANDIDATE_ORDER
        )
        or (not receipt.accepted and bool(predictors))
    ):
        raise CensusError("original source fit receipt and transient predictors disagree")


class FrozenSourceCensus:
    """Nonserializable predictor vault with at most one aggregate receipt page cached."""

    __slots__ = ("_binding", "_cached_page", "_positions", "_predictors", "_receipt")
    _receipt: SourceCensusReceipt
    _binding: SourceManifestBinding
    _predictors: tuple[Predictors, ...]
    _positions: MappingProxyType[str, int]
    _cached_page: SourceReceiptPage | None

    def __init__(
        self,
        receipt: SourceCensusReceipt,
        binding: SourceManifestBinding,
        predictors: tuple[Predictors, ...],
        hgnc_ids: tuple[str, ...],
    ) -> None:
        if (
            type(receipt) is not SourceCensusReceipt
            or type(binding) is not SourceManifestBinding
            or type(predictors) is not tuple
            or any(type(items) is not tuple for items in predictors)
            or type(hgnc_ids) is not tuple
            or len(predictors) != receipt.total_genes
            or len(hgnc_ids) != receipt.total_genes
            or hgnc_ids != tuple(sorted(set(hgnc_ids)))
            or sum(bool(items) for items in predictors) != receipt.accepted_genes
        ):
            raise CensusError("a complete aligned source census is required")
        object.__setattr__(self, "_receipt", receipt)
        object.__setattr__(self, "_binding", binding)
        object.__setattr__(self, "_predictors", predictors)
        object.__setattr__(
            self, "_positions", MappingProxyType({key: index for index, key in enumerate(hgnc_ids)})
        )
        object.__setattr__(self, "_cached_page", None)

    @property
    def receipt(self) -> SourceCensusReceipt:
        return self._receipt

    @property
    def binding(self) -> SourceManifestBinding:
        return self._binding

    def __setattr__(self, _name: str, _value: object) -> NoReturn:
        raise AttributeError("the transient source census is immutable")

    def __getstate__(self) -> NoReturn:
        raise TypeError("transient source predictors cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("transient source predictors cannot be serialized")

    def __repr__(self) -> str:
        return f"FrozenSourceCensus(total_genes={self.receipt.total_genes}, complete=True)"

    def source_gene_record(self, hgnc_id: str, *, store: CensusReceiptStore) -> SourceGeneReceipt:
        """Read and verify one original aggregate gene receipt, never predictors."""
        if type(hgnc_id) is not str or hgnc_id not in self._positions:
            raise CensusError("requested gene is outside the frozen source census")
        position = self._positions[hgnc_id]
        page_number, offset = divmod(position, self.receipt.page_size)
        page = self._cached_page
        if page is None or page.page_number != page_number:
            binding = self.receipt.pages[page_number]
            page = store.read_page(binding)
            _check_page_binding(page, binding)
            context = (
                "profile_id",
                "request_digest",
                "feature_axis_digest",
                "candidate_digest",
                "source_catalog_digest",
                "source_fold_assignment_digest",
            )
            if any(getattr(page, name) != getattr(self.receipt, name) for name in context):
                raise CensusError("hydrated source page belongs to another frozen census")
            start = page_number * self.receipt.page_size
            expected = self.receipt.gene_record_digests[start : start + len(page.genes)]
            if tuple(record.digest for record in page.genes) != expected:
                raise CensusError("hydrated gene records differ from the sealed source census")
            object.__setattr__(self, "_cached_page", page)
        record = page.genes[offset]
        if record.identity.hgnc_id != hgnc_id:
            raise CensusError("hydrated gene identity differs from the frozen source census")
        return record

    def hydrate_gene(
        self, hgnc_id: str, *, store: CensusReceiptStore
    ) -> FrozenSourceGeneFit | None:
        """Attach the same live predictors to their verified receipt without refitting."""
        record = self.source_gene_record(hgnc_id, store=store)
        predictors = self._predictors[self._positions[hgnc_id]]
        if record.source is None:
            if predictors:
                raise CensusError("a source domain rejection cannot carry fitted predictors")
            return None
        _check_predictors(record.source, predictors)
        return FrozenSourceGeneFit(record.source, predictors)


def _validated_context(
    matrix: FeatureMatrix,
    folds: FoldArray,
    catalog: SourceFeatureCatalog,
) -> tuple[FoldArray, str, str, str]:
    if type(matrix) is not FeatureMatrix or type(catalog) is not SourceFeatureCatalog:
        raise CensusError("source fitting requires the admitted matrix and source catalog")
    if (
        type(folds) is not np.ndarray
        or folds.dtype != np.dtype(np.int8)
        or folds.shape != (matrix.case_count,)
        or {int(value) for value in np.unique(folds)} != set(range(5))
    ):
        raise CensusError("source fitting requires the original five aligned patient folds")
    frozen_folds = np.frombuffer(np.ascontiguousarray(folds).tobytes(), dtype=np.int8)
    fold_digest = sha256_digest(tuple(int(value) for value in frozen_folds))
    axis_digest = matrix.axis.digest
    if (
        catalog.profile_id != FEATURE_SPACE_PROFILE_ID
        or catalog.feature_axis_digest != axis_digest
        or catalog.candidate_digest != matrix.candidate_digest
        or catalog.source_case_count != matrix.case_count
        or catalog.source_fold_assignment_digest != fold_digest
        or tuple(feature.coverage.identity for feature in catalog.genes) != matrix.axis.identities
        or catalog.selection_uses_external_values is not False
    ):
        raise CensusError("source matrix, catalog and original fold bindings disagree")
    return frozen_folds, axis_digest, fold_digest, catalog.digest


def _exceeds_domain(matrix: FeatureMatrix, row: int) -> bool:
    return any(
        bool(np.any(np.abs(values[row][np.isfinite(values[row])]) > MAX_ABSOLUTE_INPUT))
        for values in (matrix.cnv, matrix.rna, matrix.protein)
    )


def _fit_record(
    matrix: FeatureMatrix, row: int, folds: FoldArray
) -> tuple[SourceGeneReceipt, Predictors]:
    identity = matrix.axis.identities[row]
    try:
        fitted = fit_source_gene(matrix.cnv[row], matrix.rna[row], matrix.protein[row], folds)
    except ValueError:
        if not _exceeds_domain(matrix, row):
            raise
        return SourceGeneReceipt(identity, None, INPUT_DOMAIN_REJECTION), ()
    if type(fitted) is not FrozenSourceGeneFit:
        raise CensusError("the original fitter did not return its declared source fit")
    _check_predictors(fitted.receipt, fitted._predictors)
    return SourceGeneReceipt(identity, fitted.receipt, None), fitted._predictors


def fit_source_census(
    matrix: FeatureMatrix,
    folds: FoldArray,
    *,
    catalog: SourceFeatureCatalog,
    request_digest: str,
    store: CensusReceiptStore,
    page_size: int = DEFAULT_PAGE_SIZE,
    checkpoint: Callable[[ReceiptPageBinding], None] | None = None,
    cancel: Callable[[], None] | None = None,
) -> FrozenSourceCensus:
    """Invoke the unchanged fitter for every gene; seal all evidence before return.

    A cancellation callback may raise before each fit or immediately before seal.
    Checkpoints run only after a page is persisted and its binding is verified.
    Unexpected valid-input failures propagate; they are never recoded as abstentions.
    """
    require_digest(request_digest)
    require_integer(page_size, minimum=1, maximum=MAX_PAGE_SIZE)
    if (
        any(
            not callable(getattr(store, name, None)) for name in ("write_page", "seal", "read_page")
        )
        or (checkpoint is not None and not callable(checkpoint))
        or (cancel is not None and not callable(cancel))
    ):
        raise CensusError("source fitting requires its bounded store and callable progress hooks")
    frozen_folds, axis_digest, fold_digest, catalog_digest = _validated_context(
        matrix, folds, catalog
    )
    pages: list[ReceiptPageBinding] = []
    digests: list[str] = []
    predictors: list[Predictors] = []
    records: list[SourceGeneReceipt] = []
    accepted = abstained = rejected = persisted_bytes = 0
    for row in range(len(matrix.axis.identities)):
        if cancel is not None:
            cancel()
        record, gene_predictors = _fit_record(matrix, row, frozen_folds)
        rejected += record.source is None
        accepted += record.source is not None and record.source.accepted
        abstained += record.source is not None and not record.source.accepted
        digests.append(record.digest)
        predictors.append(gene_predictors)
        records.append(record)
        if len(records) == page_size or row + 1 == len(matrix.axis.identities):
            page = SourceReceiptPage(
                PROFILE_ID,
                request_digest,
                axis_digest,
                matrix.candidate_digest,
                catalog_digest,
                fold_digest,
                len(pages),
                tuple(records),
            )
            payload = page_bytes(page)
            if persisted_bytes + len(payload) > MAX_SOURCE_BYTES:
                raise CensusError("source receipt phase exceeds its declared byte bound")
            binding = store.write_page(page)
            _check_page_binding(page, binding)
            pages.append(binding)
            persisted_bytes += len(payload)
            records.clear()
            if checkpoint is not None:
                checkpoint(binding)
    receipt = SourceCensusReceipt(
        PROFILE_ID,
        request_digest,
        axis_digest,
        matrix.candidate_digest,
        catalog_digest,
        fold_digest,
        len(matrix.axis.identities),
        accepted,
        abstained,
        rejected,
        page_size,
        tuple(pages),
        tuple(digests),
    )
    if persisted_bytes + len(manifest_bytes(receipt)) > MAX_SOURCE_BYTES:
        raise CensusError("source receipt phase including its manifest exceeds the byte bound")
    if cancel is not None:
        cancel()
    sealed = store.seal(receipt)
    _check_manifest_binding(receipt, sealed)
    return FrozenSourceCensus(receipt, sealed, tuple(predictors), matrix.axis.hgnc_ids)
