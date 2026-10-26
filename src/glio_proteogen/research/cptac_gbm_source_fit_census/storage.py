"""Closed aggregate receipt codecs and a fresh, bounded source-only page store.

Hydration restores the original aggregate dataclasses, never fitted predictors.
Only a complete manifest seals a source phase; opening an existing store is
read-only and cannot resume a process whose private predictors were lost.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import stat
from dataclasses import asdict, fields
from pathlib import Path
from typing import Final, NoReturn, Protocol, cast

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.research.cptac_gbm_external_admission.contracts import GeneIdentity
from glio_proteogen.research.cptac_gbm_external_admission.transfer import (
    PROFILE_ID as LEGACY_PROFILE_ID,
)
from glio_proteogen.research.cptac_gbm_external_admission.transfer import (
    FinalFitEvidence,
    FinalSelectionEvidence,
    SourceFitReceipt,
)
from glio_proteogen.research.cptac_gbm_feature_space.contracts import MAX_FEATURES
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance.nested_selection import (
    CANDIDATE_ORDER,
    CandidateSelectionEvidence,
    NestedPointSummary,
    OuterFitEvidence,
    OuterSelectionTrace,
    PairedMetricDelta,
    ReconstructionMetrics,
    SelectionCount,
)

from .contracts import (
    INPUT_DOMAIN_REJECTION,
    MANIFEST_NAME,
    MAX_MANIFEST_BYTES,
    MAX_PAGE_BYTES,
    MAX_SOURCE_BYTES,
    PROFILE_ID,
    CensusError,
    ReceiptPageBinding,
    SourceCensusReceipt,
    SourceGeneReceipt,
    SourceManifestBinding,
    SourceReceiptPage,
    manifest_bytes,
    page_bytes,
    require_digest,
)

MAX_RECEIPT_BYTES: Final = 64 * 1024
_MAX_CASES: Final = 10_000
_FIT_FAILURES: Final = (
    "candidate is numerically unidentified",
    "candidate did not converge within 240 iterations",
)
_OUTER_SUPPORT: Final = (
    "insufficient outer training complete cases",
    "insufficient outer held-out complete cases",
)
_INNER_SUPPORT: Final = "inner support gates failed; training-median fallback without a MAE winner"
_NO_WINNER: Final = "no candidate had complete finite inner OOF support"
_SOURCE_FAILURES: Final = (
    "source nested support, numerical or null-variation gates failed",
    "all-five-fold common source OOF selection support unavailable",
    "one or more full-source fixed candidate refits unavailable",
)
_OUTER_FAILURE: Final = "one or more fixed outer refits unavailable on common comparison support"
_INNER_FAILURES: Final = (
    *_OUTER_SUPPORT,
    _INNER_SUPPORT,
    "non-finite inner OOF MAE",
    *(
        f"inner fold {fold}: {reason}"
        for fold in range(5)
        for reason in (*_FIT_FAILURES, "non-finite prediction")
    ),
)
_FALLBACKS: Final = (
    _INNER_SUPPORT,
    _NO_WINNER,
    *(
        f"selected {candidate} outer-training refit failed; training-median fallback without consulting outer-test outcomes"
        for candidate in CANDIDATE_ORDER
    ),
)


class _HasCandidate(Protocol):
    @property
    def candidate(self) -> str: ...


def _fail() -> NoReturn:
    raise CensusError("aggregate source receipt did not satisfy its closed schema")


def _object(value: object, kind: type[object], *, extra: tuple[str, ...] = ()) -> dict[str, object]:
    expected = {item.name for item in fields(kind)} | set(extra)  # type: ignore[arg-type]
    if type(value) is not dict or set(value) != expected:
        _fail()
    return cast("dict[str, object]", value)


def _integer(value: object, maximum: int = _MAX_CASES) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        _fail()
    return value


def _boolean(value: object) -> bool:
    if type(value) is not bool:
        _fail()
    return value


def _number(value: object, *, nonnegative: bool = False) -> float:
    if type(value) is not float or not math.isfinite(value) or (nonnegative and value < 0):
        _fail()
    return value


def _literal(value: object, allowed: tuple[str, ...], *, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    if type(value) is not str or value not in allowed:
        _fail()
    return value


def _candidate(value: object) -> str:
    result = _literal(value, CANDIDATE_ORDER)
    if result is None:  # pragma: no cover - required literal never returns None.
        _fail()
    return result


def _sequence(value: object, lengths: tuple[int, ...]) -> list[object]:
    if type(value) is not list or len(value) not in lengths:
        _fail()
    return value


def _ordered[T: _HasCandidate](values: tuple[T, ...]) -> tuple[T, ...]:
    if tuple(item.candidate for item in values) != CANDIDATE_ORDER:
        _fail()
    return values


def _metric(value: object, *, selected: bool = False) -> ReconstructionMetrics:
    row = _object(value, ReconstructionMetrics)
    candidate = (
        _literal(row["candidate"], ("selected_policy",))
        if selected
        else _candidate(row["candidate"])
    )
    return ReconstructionMetrics(
        cast("str", candidate),
        _integer(row["observed_count"]),
        _number(row["mae"], nonnegative=True),
        _number(row["rmse"], nonnegative=True),
        _number(row["r2_vs_fold_train_median"]),
    )


def _point(value: object) -> NestedPointSummary | None:
    if value is None:
        return None
    row = _object(value, NestedPointSummary)
    fixed = _ordered(tuple(_metric(item) for item in _sequence(row["fixed"], (4,))))
    deltas = []
    for item in _sequence(row["deltas"], (4,)):
        record = _object(item, PairedMetricDelta)
        deltas.append(
            PairedMetricDelta(
                _candidate(record["candidate"]),
                _number(record["mae_difference"]),
                _number(record["r2_difference"]),
            )
        )
    counts = []
    for item in _sequence(row["selection_counts"], (4,)):
        record = _object(item, SelectionCount)
        counts.append(
            SelectionCount(
                _candidate(record["candidate"]),
                _integer(record["fold_decisions"], 5),
                _integer(record["comparison_observations"]),
            )
        )
    result = NestedPointSummary(
        _integer(row["common_oof_count"]),
        _integer(row["valid_outer_folds"], 5),
        _metric(row["selected"], selected=True),
        fixed,
        _ordered(tuple(deltas)),
        _ordered(tuple(counts)),
        _integer(row["selection_decision_denominator"], 5),
    )
    if (
        any(item.observed_count != result.common_oof_count for item in (result.selected, *fixed))
        or sum(item.fold_decisions for item in counts) != result.selection_decision_denominator
        or result.selection_decision_denominator != result.valid_outer_folds
        or sum(item.comparison_observations for item in counts) != result.common_oof_count
    ):
        _fail()
    return result


def _inner(value: object) -> CandidateSelectionEvidence:
    row = _object(value, CandidateSelectionEvidence)
    eligible = _boolean(row["eligible"])
    reasons = tuple(
        cast("str", _literal(item, _INNER_FAILURES))
        for item in _sequence(row["failure_reasons"], (0, 1, 2, 3, 4))
    )
    mae = None if row["inner_mae"] is None else _number(row["inner_mae"], nonnegative=True)
    if eligible != (mae is not None) or (eligible and reasons):
        _fail()
    return CandidateSelectionEvidence(
        _candidate(row["candidate"]), eligible, _integer(row["inner_oof_count"]), mae, reasons
    )


def _fit_evidence(value: object, *, final: bool) -> OuterFitEvidence | FinalFitEvidence:
    kind = FinalFitEvidence if final else OuterFitEvidence
    row = _object(value, kind)
    candidate = _candidate(row["candidate"])
    available = _boolean(row["available"])
    iterations = None if row["iterations"] is None else _integer(row["iterations"], 240)
    reason = _literal(
        row["failure_reason"],
        _FIT_FAILURES if final else (*_FIT_FAILURES, "non-finite outer prediction"),
        optional=True,
    )
    if available != (reason is None) or (candidate == "training_median" and iterations is not None):
        _fail()
    return kind(candidate, available, iterations, reason)


def _trace(value: object) -> OuterSelectionTrace:
    row = _object(value, OuterSelectionTrace)
    basis = cast(
        "str",
        _literal(
            row["selection_basis"],
            (
                "outer_support_abstention",
                "fallback_inner_support",
                "inner_mae",
                "fallback_selected_refit",
            ),
        ),
    )
    fits = tuple(
        cast("OuterFitEvidence", _fit_evidence(item, final=False))
        for item in _sequence(row["outer_fits"], (0, 4))
    )
    if fits:
        _ordered(fits)
    candidates = _ordered(tuple(_inner(item) for item in _sequence(row["candidates"], (4,))))
    trace = OuterSelectionTrace(
        _integer(row["fold"], 4),
        _integer(row["training_complete"]),
        _integer(row["held_out_complete"]),
        _candidate(row["selected_candidate"]),
        basis,
        _literal(row["fallback_reason"], _FALLBACKS, optional=True),
        candidates,
        fits,
        _boolean(row["selected_prediction_available"]),
        _boolean(row["comparison_accepted"]),
        _literal(row["failure_reason"], (*_OUTER_SUPPORT, _OUTER_FAILURE), optional=True),
    )
    if (basis == "outer_support_abstention") != (not fits) or (
        trace.comparison_accepted
        and (
            not trace.selected_prediction_available
            or not all(item.available for item in fits)
            or trace.failure_reason is not None
        )
    ):
        _fail()
    return trace


def hydrate_source_fit_receipt(value: object) -> SourceFitReceipt:
    """Hydrate only the closed original aggregate receipt, without predictors."""
    row = _object(value, SourceFitReceipt)
    if row["profile_id"] != LEGACY_PROFILE_ID:
        _fail()
    selection = []
    for item in _sequence(row["selection_evidence"], (4,)):
        record = _object(item, FinalSelectionEvidence)
        eligible = _boolean(record["eligible"])
        mae = (
            None
            if record["source_oof_mae"] is None
            else _number(record["source_oof_mae"], nonnegative=True)
        )
        if eligible != (mae is not None):
            _fail()
        selection.append(
            FinalSelectionEvidence(
                _candidate(record["candidate"]), eligible, _integer(record["source_oof_count"]), mae
            )
        )
    traces = tuple(_trace(item) for item in _sequence(row["fold_trace"], (5,)))
    if tuple(trace.fold for trace in traces) != tuple(range(5)):
        _fail()
    final_fits = tuple(
        cast("FinalFitEvidence", _fit_evidence(item, final=True))
        for item in _sequence(row["final_fits"], (0, 4))
    )
    if final_fits:
        _ordered(final_fits)
    result = SourceFitReceipt(
        LEGACY_PROFILE_ID,
        _boolean(row["accepted"]),
        _integer(row["complete_count"]),
        _integer(row["common_oof_count"]),
        _integer(row["valid_outer_folds"], 5),
        _literal(row["selected_candidate"], CANDIDATE_ORDER, optional=True),
        _ordered(tuple(selection)),
        _point(row["nested_point_summary"]),
        traces,
        tuple(
            None if item is None else _integer(item, 240)
            for item in _sequence(row["final_fit_iterations"], (0, 4))
        ),
        _literal(row["failure_reason"], _SOURCE_FAILURES, optional=True),
        final_fits,
    )
    if (
        result.accepted != (result.failure_reason is None)
        or result.common_oof_count > result.complete_count
        or sum(trace.held_out_complete for trace in traces) != result.complete_count
        or any(
            trace.training_complete + trace.held_out_complete != result.complete_count
            for trace in traces
        )
        or result.valid_outer_folds != sum(trace.comparison_accepted for trace in traces)
        or result.common_oof_count
        != sum(trace.held_out_complete for trace in traces if trace.comparison_accepted)
        or any(item.source_oof_count > result.complete_count for item in selection)
        or (result.selected_candidate is None) != (not final_fits)
        or result.final_fit_iterations != tuple(item.iterations for item in final_fits)
        or (
            result.accepted
            and (
                result.nested_point_summary is None
                or result.common_oof_count < 60
                or result.valid_outer_folds < 4
                or not all(item.available for item in final_fits)
            )
        )
        or (
            result.nested_point_summary is not None
            and (
                result.nested_point_summary.common_oof_count != result.common_oof_count
                or result.nested_point_summary.valid_outer_folds != result.valid_outer_folds
            )
        )
    ):
        _fail()
    return result


def source_fit_receipt_document(receipt: SourceFitReceipt) -> dict[str, object]:
    if type(receipt) is not SourceFitReceipt:
        _fail()
    try:
        payload = canonical_json_bytes(asdict(receipt))
        if len(payload) > MAX_RECEIPT_BYTES:
            _fail()
        document: object = json.loads(payload)
        hydrated = hydrate_source_fit_receipt(document)
        if hydrated != receipt:
            _fail()
    except CensusError:
        raise
    except (TypeError, ValueError, RecursionError):
        raise CensusError("original source receipt cannot be safely encoded") from None
    return cast("dict[str, object]", document)


def _pairs(items: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in items:
        if key in result:
            _fail()
        result[key] = value
    return result


def _invalid_constant(_value: str) -> NoReturn:
    _fail()


def _json(payload: bytes, *, maximum: int) -> dict[str, object]:
    if type(payload) is not bytes or not 1 <= len(payload) <= maximum:
        _fail()
    try:
        value: object = json.loads(
            payload.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_invalid_constant
        )
        if type(value) is not dict or canonical_json_bytes(value) != payload:
            _fail()
    except CensusError:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise CensusError("source receipt JSON is not bounded canonical data") from None
    return cast("dict[str, object]", value)


def _identity(value: object) -> GeneIdentity:
    row = _object(value, GeneIdentity)
    if any(type(item) is not str or len(item) > 128 for item in (row["hgnc_id"], row["symbol"])):
        _fail()
    if any(
        item is not None and (type(item) is not str or len(item) > 128)
        for item in (row["entrez_id"], row["ensembl_gene_id"])
    ):
        _fail()
    try:
        return GeneIdentity(**cast("dict[str, str | None]", row))  # type: ignore[arg-type]
    except ValueError:
        raise CensusError("source gene identity did not satisfy its closed schema") from None


def _gene(value: object) -> SourceGeneReceipt:
    row = _object(value, SourceGeneReceipt)
    source = None if row["source"] is None else hydrate_source_fit_receipt(row["source"])
    rejection = _literal(row["input_domain_rejection"], (INPUT_DOMAIN_REJECTION,), optional=True)
    return SourceGeneReceipt(_identity(row["identity"]), source, rejection)


def _digest(value: object) -> str:
    if type(value) is not str:
        _fail()
    return require_digest(value)


def decode_page(payload: bytes) -> SourceReceiptPage:
    row = _object(_json(payload, maximum=MAX_PAGE_BYTES), SourceReceiptPage, extra=("page_digest",))
    genes = row.pop("genes")
    digest = row.pop("page_digest")
    if type(genes) is not list or not 1 <= len(genes) <= 64:
        _fail()
    try:
        page = SourceReceiptPage(
            profile_id=cast("str", _literal(row["profile_id"], (PROFILE_ID,))),
            request_digest=_digest(row["request_digest"]),
            feature_axis_digest=_digest(row["feature_axis_digest"]),
            candidate_digest=_digest(row["candidate_digest"]),
            source_catalog_digest=_digest(row["source_catalog_digest"]),
            source_fold_assignment_digest=_digest(row["source_fold_assignment_digest"]),
            page_number=_integer(row["page_number"], MAX_FEATURES - 1),
            genes=tuple(_gene(item) for item in genes),
        )
        if page.digest != digest or page_bytes(page) != payload:
            _fail()
    except CensusError:
        raise
    except (TypeError, ValueError):
        raise CensusError("source receipt page does not satisfy its closed contract") from None
    return page


def decode_manifest(payload: bytes) -> SourceCensusReceipt:
    row = _object(
        _json(payload, maximum=MAX_MANIFEST_BYTES), SourceCensusReceipt, extra=("manifest_digest",)
    )
    pages, digests, digest = (
        row.pop("pages"),
        row.pop("gene_record_digests"),
        row.pop("manifest_digest"),
    )
    if (
        type(pages) is not list
        or not 1 <= len(pages) <= MAX_FEATURES
        or type(digests) is not list
        or not 1 <= len(digests) <= MAX_FEATURES
    ):
        _fail()
    parsed = []
    for item in pages:
        binding = _object(item, ReceiptPageBinding)
        parsed.append(ReceiptPageBinding(**binding))  # type: ignore[arg-type]
    try:
        manifest = SourceCensusReceipt(
            profile_id=cast("str", _literal(row["profile_id"], (PROFILE_ID,))),
            request_digest=_digest(row["request_digest"]),
            feature_axis_digest=_digest(row["feature_axis_digest"]),
            candidate_digest=_digest(row["candidate_digest"]),
            source_catalog_digest=_digest(row["source_catalog_digest"]),
            source_fold_assignment_digest=_digest(row["source_fold_assignment_digest"]),
            total_genes=_integer(row["total_genes"], MAX_FEATURES),
            accepted_genes=_integer(row["accepted_genes"], MAX_FEATURES),
            abstained_genes=_integer(row["abstained_genes"], MAX_FEATURES),
            input_domain_rejected_genes=_integer(row["input_domain_rejected_genes"], MAX_FEATURES),
            page_size=_integer(row["page_size"], 64),
            pages=tuple(parsed),
            gene_record_digests=tuple(digests),
            external_measurements_read=_boolean(row["external_measurements_read"]),
            complete=_boolean(row["complete"]),
        )
        if manifest.digest != digest or manifest_bytes(manifest) != payload:
            _fail()
    except CensusError:
        raise
    except (ValueError, TypeError):
        raise CensusError("source manifest does not satisfy its closed contract") from None
    return manifest


def _snapshot(metadata: os.stat_result, *, directory: bool = False) -> tuple[int, ...]:
    if (
        stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(metadata.st_mode)
    ) is False or (
        getattr(metadata, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    ):
        raise CensusError("source store requires regular non-link paths")
    identity = (metadata.st_dev, metadata.st_ino)
    return (
        identity
        if directory
        else (
            *identity,
            metadata.st_size,
            metadata.st_mtime_ns,
            getattr(metadata, "st_birthtime_ns", metadata.st_ctime_ns),
        )
    )


def _directory(path: Path) -> tuple[int, ...]:
    for ancestor in (*reversed(path.parents), path):
        _snapshot(ancestor.lstat(), directory=True)
    return _snapshot(path.lstat(), directory=True)


def _read(path: Path, *, size: int, sha256: str, maximum: int) -> bytes:
    require_digest(sha256)
    if type(size) is not int or not 1 <= size <= maximum:
        _fail()
    try:
        before = _snapshot(path.lstat())
        if before[2] != size:
            _fail()
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        with os.fdopen(os.open(path, flags), "rb") as stream:
            opened = os.fstat(stream.fileno())
            if _snapshot(opened) != before:
                _fail()
            payload = stream.read(size + 1)
            after = os.fstat(stream.fileno())
        if (
            _snapshot(after) != before
            or opened.st_ctime_ns != after.st_ctime_ns
            or _snapshot(path.lstat()) != before
            or len(payload) != size
        ):
            _fail()
        if "sha256:" + hashlib.sha256(payload).hexdigest() != sha256:
            _fail()
    except CensusError:
        raise
    except (OSError, ValueError, TypeError):
        raise CensusError("source aggregate file could not be safely verified") from None
    return payload


def _context(value: SourceReceiptPage | SourceCensusReceipt) -> tuple[str, ...]:
    return (
        value.profile_id,
        value.request_digest,
        value.feature_axis_digest,
        value.candidate_digest,
        value.source_catalog_digest,
        value.source_fold_assignment_digest,
    )


class JsonCensusReceiptStore:
    """Create one fresh aggregate phase; keep incomplete files on every failure."""

    def __init__(self, directory: Path) -> None:
        if not isinstance(directory, Path):
            _fail()
        self.directory = directory.absolute()
        self._bindings: list[ReceiptPageBinding] = []
        self._context: tuple[str, ...] | None = None
        self._sealed = False
        self._manifest_binding: SourceManifestBinding | None = None
        try:
            _directory(self.directory.parent)
            self.directory.mkdir()
            (self.directory / "pages").mkdir()
            self._root_identity = _directory(self.directory)
            self._pages_identity = _directory(self.directory / "pages")
        except (OSError, ValueError):
            raise CensusError("source store requires a fresh non-link directory") from None

    def _guard(self) -> None:
        try:
            if (
                _directory(self.directory) != self._root_identity
                or _directory(self.directory / "pages") != self._pages_identity
            ):
                _fail()
        except CensusError:
            raise
        except OSError:
            raise CensusError("source store directory binding was not retained") from None

    def _write(self, file_name: str, payload: bytes) -> None:
        self._guard()
        try:
            with (self.directory / file_name).open("xb") as stream:
                stream.write(payload)
        except OSError:
            raise CensusError("source aggregate file could not be written exclusively") from None
        self._guard()

    def write_page(self, page: SourceReceiptPage) -> ReceiptPageBinding:
        if (
            self._sealed
            or type(page) is not SourceReceiptPage
            or page.page_number != len(self._bindings)
        ):
            raise CensusError("source pages require a fresh contiguous unsealed sequence")
        payload = page_bytes(page)
        decoded = decode_page(payload)
        if self._context is not None and _context(decoded) != self._context:
            raise CensusError("source page context differs from the frozen source phase")
        if self._bindings and self._bindings[-1].last_hgnc_id >= decoded.genes[0].identity.hgnc_id:
            raise CensusError("source pages repeat or reorder approved gene identities")
        if (
            sum(binding.bytes for binding in self._bindings) + len(payload) > MAX_SOURCE_BYTES
            or sum(binding.gene_count for binding in self._bindings) + len(decoded.genes)
            > MAX_FEATURES
        ):
            raise CensusError("source pages exceed the bounded source phase")
        binding = ReceiptPageBinding(
            decoded.page_number,
            f"pages/{decoded.page_number:05d}.json",
            len(payload),
            "sha256:" + hashlib.sha256(payload).hexdigest(),
            decoded.digest,
            len(decoded.genes),
            decoded.genes[0].identity.hgnc_id,
            decoded.genes[-1].identity.hgnc_id,
        )
        self._write(binding.file_name, payload)
        self._context = _context(decoded)
        self._bindings.append(binding)
        self.read_page(binding)
        return binding

    def read_page(self, binding: ReceiptPageBinding) -> SourceReceiptPage:
        if type(binding) is not ReceiptPageBinding or binding not in self._bindings:
            raise CensusError("source page binding is outside the retained inventory")
        self._guard()
        payload = _read(
            self.directory / binding.file_name,
            size=binding.bytes,
            sha256=binding.sha256,
            maximum=MAX_PAGE_BYTES,
        )
        page = decode_page(payload)
        if (
            page.digest != binding.page_digest
            or page.page_number != binding.page_number
            or len(page.genes) != binding.gene_count
            or page.genes[0].identity.hgnc_id != binding.first_hgnc_id
            or page.genes[-1].identity.hgnc_id != binding.last_hgnc_id
            or _context(page) != self._context
        ):
            _fail()
        self._guard()
        return page

    def _validate_manifest(self, manifest: SourceCensusReceipt) -> None:
        if (
            type(manifest) is not SourceCensusReceipt
            or manifest.pages != tuple(self._bindings)
            or _context(manifest) != self._context
        ):
            raise CensusError("source manifest does not match all written source pages")
        identities, digests = [], []
        accepted = abstained = rejected = 0
        for binding in manifest.pages:
            for record in self.read_page(binding).genes:
                identities.append(asdict(record.identity))
                digests.append(record.digest)
                if record.source is None:
                    rejected += 1
                elif record.source.accepted:
                    accepted += 1
                else:
                    abstained += 1
        if (
            len(identities) != manifest.total_genes
            or len({identity["symbol"] for identity in identities}) != manifest.total_genes
            or sha256_digest(tuple(identities)) != manifest.feature_axis_digest
            or tuple(digests) != manifest.gene_record_digests
            or (accepted, abstained, rejected)
            != (
                manifest.accepted_genes,
                manifest.abstained_genes,
                manifest.input_domain_rejected_genes,
            )
        ):
            raise CensusError("source manifest does not seal the exact complete source axis")

    def seal(self, manifest: SourceCensusReceipt) -> SourceManifestBinding:
        if self._sealed:
            raise CensusError("source census manifest is already sealed")
        self._validate_manifest(manifest)
        payload = manifest_bytes(manifest)
        if sum(binding.bytes for binding in self._bindings) + len(payload) > MAX_SOURCE_BYTES:
            raise CensusError("source manifest and pages exceed the bounded source phase")
        self._write(MANIFEST_NAME, payload)
        binding = SourceManifestBinding(
            MANIFEST_NAME,
            len(payload),
            "sha256:" + hashlib.sha256(payload).hexdigest(),
            manifest.digest,
        )
        self._manifest_binding, self._sealed = binding, True
        self.read_manifest(binding)
        return binding

    def read_manifest(self, binding: SourceManifestBinding) -> SourceCensusReceipt:
        if type(binding) is not SourceManifestBinding or binding != self._manifest_binding:
            raise CensusError("source manifest binding is outside the sealed inventory")
        self._guard()
        manifest = decode_manifest(
            _read(
                self.directory / binding.file_name,
                size=binding.bytes,
                sha256=binding.sha256,
                maximum=MAX_MANIFEST_BYTES,
            )
        )
        if manifest.digest != binding.manifest_digest:
            _fail()
        self._validate_manifest(manifest)
        self._guard()
        return manifest

    @classmethod
    def open_existing(
        cls, directory: Path, binding: SourceManifestBinding
    ) -> JsonCensusReceiptStore:
        """Verify and open a complete store read-only; never resume source fits."""
        if not isinstance(directory, Path) or type(binding) is not SourceManifestBinding:
            _fail()
        instance = cls.__new__(cls)
        instance.directory = directory.absolute()
        try:
            instance._root_identity = _directory(instance.directory)
            instance._pages_identity = _directory(instance.directory / "pages")
            manifest = decode_manifest(
                _read(
                    instance.directory / binding.file_name,
                    size=binding.bytes,
                    sha256=binding.sha256,
                    maximum=MAX_MANIFEST_BYTES,
                )
            )
        except CensusError:
            raise
        except OSError:
            raise CensusError("complete source census directory could not be opened") from None
        instance._bindings = list(manifest.pages)
        instance._context = _context(manifest)
        instance._sealed = True
        instance._manifest_binding = binding
        instance.read_manifest(binding)
        return instance


__all__ = [
    "MAX_RECEIPT_BYTES",
    "JsonCensusReceiptStore",
    "decode_manifest",
    "decode_page",
    "hydrate_source_fit_receipt",
    "source_fit_receipt_document",
]
