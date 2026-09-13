"""Run the source-locked GBmap development fit without publishing a model.

This maintainer-only driver keeps extraction aggregates, donor partitions, stable
gene selections, and fitted parameters inside one process. Its only durable output
is an exact projection of the existing de-identified extraction receipt,
validation-split receipt, and development training summary. It is intentionally
absent from the application API and public ``glio-proteogen`` CLI.

The run has no checkpoint or resume format. Any source, identity, extraction,
training, projection, or publication failure leaves no output and requires a
complete rerun from the unchanged locked H5AD.
"""

# ruff: noqa: T201, TRY003

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
import sys
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import IO, TYPE_CHECKING, Final, cast

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from glio_proteogen.research.gbmap_deconvolution import (
    PRODUCTION_SOURCE_LABELS,
    PRODUCTION_SOURCE_STUDY_CATEGORIES,
    CandidateFoldEvaluation,
    CandidateLineageSummary,
    DeidentifiedValidationFoldReceipt,
    DevelopmentTrainingResult,
    DevelopmentTrainingSummary,
    ExactGbmapH5adLock,
    GbmapDeconvolutionError,
    GbmapExtractionReceipt,
    GbmapExtractionResult,
    LabelFoldSupport,
    ShrinkageCandidateEvaluation,
    ValidationSplitReceipt,
    development_profile,
    extract_pinned_gbmap_reference,
    production_donor_crosswalk,
    production_extraction_recipe,
    production_label_taxonomy,
    production_reduction_recipe_digest,
    production_study_crosswalk,
    train_development_candidate,
)

OUTPUT_SCHEMA: Final = "glio-proteogen.gbmap-development-fit-receipts/1.0.0"
BUNDLE_DIGEST_BASIS: Final = (
    "SHA-256 of canonical UTF-8 JSON for every top-level field except bundle_digest; "
    "sorted keys, compact separators, ASCII escaping, no NaN"
)
MAX_OUTPUT_BYTES: Final = 4 * 1024 * 1024
_REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
_SHA256_PATTERN: Final = re.compile(r"^sha256:[0-9a-f]{64}$")
_FOLD_ID_PATTERN: Final = re.compile(r"^(?:whole-study|within-study-donor)-[0-9]{4}$")
_REPARSE_ATTRIBUTE: Final = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_ALLOWED_MODELED_LABELS: Final = frozenset(PRODUCTION_SOURCE_LABELS)
_ALLOWED_STUDY_KEYS: Final = frozenset(
    "Neftel2019" if value in {"Neftel2019_10x", "Neftel2019_smart"} else value
    for value in PRODUCTION_SOURCE_STUDY_CATEGORIES
)

_TOP_LEVEL_FIELDS: Final = frozenset(
    {
        "schema_version",
        "bundle_digest_basis",
        "bundle_digest",
        "extraction_receipt",
        "validation_split_receipt",
        "training_summary",
    }
)
_EXTRACTION_FIELDS: Final = frozenset(GbmapExtractionReceipt.model_fields)
_SPLIT_FIELDS: Final = frozenset(
    {
        "source_file_sha256",
        "source_bytes",
        "taxonomy_digest",
        "extraction_recipe_digest",
        "folds",
    }
)
_SPLIT_FOLD_FIELDS: Final = frozenset(
    {
        "fold_id",
        "kind",
        "training_study_keys",
        "held_study_keys",
        "training_donor_count",
        "held_donor_count",
        "label_support",
        "evaluable",
        "abstention_reasons",
    }
)
_LABEL_SUPPORT_FIELDS: Final = frozenset(
    {
        "modeled_label",
        "training_usable_donor_count",
        "training_usable_study_count",
        "held_usable_donor_count",
        "held_usable_study_count",
        "evaluable",
        "abstention_reasons",
    }
)
_TRAINING_FIELDS: Final = frozenset(
    {
        "fit_state",
        "source_file_sha256",
        "source_bytes",
        "taxonomy_digest",
        "extraction_recipe_digest",
        "feature_order_digest",
        "selected_shrinkage",
        "candidate_evaluations",
        "selected_feature_count",
        "lineage_summaries",
        "production_artifact_permitted",
        "runtime_mount_permitted",
    }
)
_CANDIDATE_FIELDS: Final = frozenset(
    {
        "shrinkage",
        "folds",
        "whole_study_fold_count",
        "within_study_donor_fold_count",
        "minimum_whole_study_folds",
        "minimum_within_study_donor_folds",
        "whole_study_mean_nll",
        "within_study_donor_mean_nll",
        "selection_score",
        "selectable",
    }
)
_CANDIDATE_FOLD_FIELDS: Final = frozenset(
    {
        "fold_id",
        "kind",
        "shrinkage",
        "state",
        "abstention_reason",
        "eligible_lineage_count",
        "selected_feature_count",
        "evaluated_held_record_count",
        "mean_per_count_nll",
    }
)
_LINEAGE_FIELDS: Final = frozenset(
    {
        "modeled_label",
        "usable_donor_count",
        "usable_study_count",
        "stable_gene_count",
        "concentration",
        "hierarchy_iterations",
        "hierarchy_kkt_residual",
    }
)

_MISSING: Final = object()


class GbmapDevelopmentFitDriverError(RuntimeError):
    """The offline development run could not produce a safe retained receipt."""


@dataclass(frozen=True, slots=True)
class _SourceSnapshot:
    lexical_path: Path
    source_identity: tuple[int, ...]
    ancestor_identities: tuple[tuple[str, tuple[int, ...]], ...]


@dataclass(frozen=True, slots=True)
class _ValidatedBundle:
    extraction: GbmapExtractionReceipt
    split: ValidationSplitReceipt
    training: DevelopmentTrainingSummary


def _privacy_call[T](message: str, action: Callable[[], T]) -> T:
    """Run a boundary operation without retaining a sensitive chained exception."""

    result: T | object = _MISSING
    failed = False
    try:
        result = action()
    except Exception:  # noqa: BLE001 - privacy boundary must sanitize all internals
        failed = True
    if failed:
        raise GbmapDevelopmentFitDriverError(message) from None
    return cast("T", result)


def _reviewed_sha256(value: str) -> str:
    if type(value) is not str or _SHA256_PATTERN.fullmatch(value) is None:
        raise GbmapDevelopmentFitDriverError(
            "reviewed SHA-256 must be canonical lowercase sha256:<64 hex>"
        )
    return value


def _require_acknowledgements(
    *,
    development_only_acknowledged: bool,
    sha256_independently_reviewed: bool,
) -> None:
    if development_only_acknowledged is not True:
        raise GbmapDevelopmentFitDriverError(
            "explicit development-only acknowledgement is required"
        )
    if sha256_independently_reviewed is not True:
        raise GbmapDevelopmentFitDriverError(
            "explicit independent SHA-256 review acknowledgement is required"
        )


def _lexical_absolute(path: Path) -> Path:
    # Resolving would follow the very links/reparse points that the lexical
    # ancestor walk below is required to reject.
    return Path(os.path.abspath(os.fspath(path)))  # noqa: PTH100


def _is_within(path: Path, root: Path) -> bool:
    normalized_path = os.path.normcase(os.fspath(path))
    normalized_root = os.path.normcase(os.fspath(root))
    try:
        common = os.path.commonpath((normalized_path, normalized_root))
    except ValueError:
        return False
    return os.path.normcase(common) == normalized_root


def _is_link_or_reparse(info: os.stat_result) -> bool:
    attributes = int(getattr(info, "st_file_attributes", 0))
    return stat.S_ISLNK(info.st_mode) or bool(attributes & _REPARSE_ATTRIBUTE)


def _file_identity(info: os.stat_result) -> tuple[int, ...]:
    # Keep the held-handle comparison to stable file/content identity fields.
    # Windows can update creation-time/attribute metadata asynchronously after a
    # newly written file closes; link/reparse/type checks remain independently
    # enforced on both lexical snapshots.
    return (
        int(info.st_dev),
        int(info.st_ino),
        int(info.st_size),
        int(info.st_mtime_ns),
    )


def _ancestor_identity(info: os.stat_result) -> tuple[int, ...]:
    return (
        int(info.st_dev),
        int(info.st_ino),
        int(info.st_mode),
        int(getattr(info, "st_file_attributes", 0)),
    )


def _capture_source_snapshot(source: Path) -> _SourceSnapshot:
    if not isinstance(source, Path):
        raise GbmapDevelopmentFitDriverError("source must be a pathlib Path")
    lexical = _privacy_call(
        "GBmap source path could not be normalized safely",
        lambda: _lexical_absolute(source),
    )
    if lexical.suffix.lower() != ".h5ad":
        raise GbmapDevelopmentFitDriverError("GBmap source must be an H5AD file")
    if _is_within(lexical, _REPOSITORY_ROOT):
        raise GbmapDevelopmentFitDriverError("GBmap source must remain outside the repository")

    chain: list[Path] = [lexical]
    cursor = lexical.parent
    while True:
        chain.append(cursor)
        if cursor == cursor.parent:
            break
        cursor = cursor.parent
    records = _privacy_call(
        "GBmap source path could not be inspected safely",
        lambda: tuple((path, os.lstat(path)) for path in chain),
    )
    source_info = records[0][1]
    if _is_link_or_reparse(source_info) or not stat.S_ISREG(source_info.st_mode):
        raise GbmapDevelopmentFitDriverError("GBmap source must be a regular non-reparse file")
    ancestor_records: list[tuple[str, tuple[int, ...]]] = []
    for path, info in records[1:]:
        if _is_link_or_reparse(info) or not stat.S_ISDIR(info.st_mode):
            raise GbmapDevelopmentFitDriverError(
                "GBmap source ancestors must be ordinary non-reparse directories"
            )
        ancestor_records.append((os.path.normcase(os.fspath(path)), _ancestor_identity(info)))
    return _SourceSnapshot(
        lexical_path=lexical,
        source_identity=_file_identity(source_info),
        ancestor_identities=tuple(ancestor_records),
    )


def _open_source_guard(snapshot: _SourceSnapshot) -> IO[bytes]:
    handle = _privacy_call(
        "GBmap source guard could not be opened safely",
        lambda: snapshot.lexical_path.open("rb"),
    )
    opened = _privacy_call(
        "GBmap source guard identity could not be inspected",
        lambda: os.fstat(handle.fileno()),
    )
    if _file_identity(opened) != snapshot.source_identity:
        handle.close()
        raise GbmapDevelopmentFitDriverError("GBmap source changed while its guard opened")
    return handle


def _require_source_unchanged(
    before: _SourceSnapshot,
    after: _SourceSnapshot,
    guard: IO[bytes],
) -> None:
    guarded = _privacy_call(
        "GBmap source guard identity could not be revalidated",
        lambda: os.fstat(guard.fileno()),
    )
    if (
        before.lexical_path != after.lexical_path
        or before.source_identity != after.source_identity
        or before.source_identity != _file_identity(guarded)
        or before.ancestor_identities != after.ancestor_identities
        or _is_within(after.lexical_path, _REPOSITORY_ROOT)
    ):
        raise GbmapDevelopmentFitDriverError("GBmap source identity or containment changed")


def _production_lock(reviewed_sha256: str) -> ExactGbmapH5adLock:
    digest = _reviewed_sha256(reviewed_sha256)

    def construct() -> ExactGbmapH5adLock:
        expectation = development_profile().source
        return ExactGbmapH5adLock(
            source_id=expectation.source_id,
            expected_bytes=expectation.expected_bytes,
            md5=expectation.source_md5,
            sha256=digest,
            sha256_independently_reviewed=True,
        )

    return _privacy_call("production GBmap source lock could not be constructed", construct)


def _exact_mapping(value: object, fields: frozenset[str]) -> dict[str, object]:
    if type(value) is not dict or set(value) != fields:
        raise ValueError("retained receipt fields are not exact")
    return cast("dict[str, object]", value)


def _exact_list(value: object) -> list[object]:
    if type(value) is not list:
        raise ValueError("retained receipt collection must be an exact list")
    return cast("list[object]", value)


def _exact_string(value: object) -> str:
    if type(value) is not str:
        raise ValueError("retained receipt text must be an exact string")
    return value


def _exact_int(value: object) -> int:
    if type(value) is not int:
        raise ValueError("retained receipt count must be an exact integer")
    return value


def _exact_bool(value: object) -> bool:
    if type(value) is not bool:
        raise ValueError("retained receipt flag must be an exact Boolean")
    return value


def _exact_float(value: object) -> float:
    if type(value) is not float or not math.isfinite(value):
        raise ValueError("retained receipt score must be a finite float")
    return value


def _optional_float(value: object) -> float | None:
    return None if value is None else _exact_float(value)


def _string_tuple(value: object) -> tuple[str, ...]:
    return tuple(_exact_string(item) for item in _exact_list(value))


def _project_extraction(value: object) -> dict[str, object]:
    if type(value) is not GbmapExtractionReceipt:
        raise ValueError("extraction receipt type is not exact")
    receipt = value
    payload: dict[str, object] = {
        "receipt_id": receipt.receipt_id,
        "receipt_digest": receipt.receipt_digest,
        "source_sha256": receipt.source_sha256,
        "source_bytes": receipt.source_bytes,
        "extraction_recipe_digest": receipt.extraction_recipe_digest,
        "taxonomy_digest": receipt.taxonomy_digest,
        "feature_order_digest": receipt.feature_order_digest,
        "h5py_version": receipt.h5py_version,
        "cell_count": receipt.cell_count,
        "retained_cell_count": receipt.retained_cell_count,
        "explicitly_excluded_cell_count": receipt.explicitly_excluded_cell_count,
        "source_donor_category_count": receipt.source_donor_category_count,
        "grouped_donor_category_count": receipt.grouped_donor_category_count,
        "source_study_category_count": receipt.source_study_category_count,
        "grouped_study_count": receipt.grouped_study_count,
        "source_label_count": receipt.source_label_count,
        "modeled_label_count": receipt.modeled_label_count,
        "record_count": receipt.record_count,
        "cell_level_material_retained": receipt.cell_level_material_retained,
        "donor_identifiers_retained": receipt.donor_identifiers_retained,
        "donor_hashes_retained": receipt.donor_hashes_retained,
        "donor_profiles_retained": receipt.donor_profiles_retained,
        "aggregate_content_digest_retained": receipt.aggregate_content_digest_retained,
    }
    GbmapExtractionReceipt.model_validate(payload, strict=True)
    return payload


def _project_label_support(value: object) -> dict[str, object]:
    if type(value) is not LabelFoldSupport:
        raise ValueError("label support type is not exact")
    support = value
    return {
        "modeled_label": support.modeled_label,
        "training_usable_donor_count": support.training_usable_donor_count,
        "training_usable_study_count": support.training_usable_study_count,
        "held_usable_donor_count": support.held_usable_donor_count,
        "held_usable_study_count": support.held_usable_study_count,
        "evaluable": support.evaluable,
        "abstention_reasons": list(support.abstention_reasons),
    }


def _project_split_fold(value: object) -> dict[str, object]:
    if type(value) is not DeidentifiedValidationFoldReceipt:
        raise ValueError("validation fold receipt type is not exact")
    fold = value
    return {
        "fold_id": fold.fold_id,
        "kind": fold.kind,
        "training_study_keys": list(fold.training_study_keys),
        "held_study_keys": list(fold.held_study_keys),
        "training_donor_count": fold.training_donor_count,
        "held_donor_count": fold.held_donor_count,
        "label_support": [_project_label_support(item) for item in fold.label_support],
        "evaluable": fold.evaluable,
        "abstention_reasons": list(fold.abstention_reasons),
    }


def _project_split(value: object) -> dict[str, object]:
    if type(value) is not ValidationSplitReceipt:
        raise ValueError("validation split receipt type is not exact")
    split = value
    return {
        "source_file_sha256": split.source_file_sha256,
        "source_bytes": split.source_bytes,
        "taxonomy_digest": split.taxonomy_digest,
        "extraction_recipe_digest": split.extraction_recipe_digest,
        "folds": [_project_split_fold(item) for item in split.folds],
    }


def _project_candidate_fold(value: object) -> dict[str, object]:
    if type(value) is not CandidateFoldEvaluation:
        raise ValueError("candidate fold type is not exact")
    fold = value
    return {
        "fold_id": fold.fold_id,
        "kind": fold.kind,
        "shrinkage": fold.shrinkage,
        "state": fold.state,
        "abstention_reason": fold.abstention_reason,
        "eligible_lineage_count": fold.eligible_lineage_count,
        "selected_feature_count": fold.selected_feature_count,
        "evaluated_held_record_count": fold.evaluated_held_record_count,
        "mean_per_count_nll": fold.mean_per_count_nll,
    }


def _project_candidate(value: object) -> dict[str, object]:
    if type(value) is not ShrinkageCandidateEvaluation:
        raise ValueError("candidate evaluation type is not exact")
    candidate = value
    return {
        "shrinkage": candidate.shrinkage,
        "folds": [_project_candidate_fold(item) for item in candidate.folds],
        "whole_study_fold_count": candidate.whole_study_fold_count,
        "within_study_donor_fold_count": candidate.within_study_donor_fold_count,
        "minimum_whole_study_folds": candidate.minimum_whole_study_folds,
        "minimum_within_study_donor_folds": candidate.minimum_within_study_donor_folds,
        "whole_study_mean_nll": candidate.whole_study_mean_nll,
        "within_study_donor_mean_nll": candidate.within_study_donor_mean_nll,
        "selection_score": candidate.selection_score,
        "selectable": candidate.selectable,
    }


def _project_lineage(value: object) -> dict[str, object]:
    if type(value) is not CandidateLineageSummary:
        raise ValueError("lineage summary type is not exact")
    lineage = value
    return {
        "modeled_label": lineage.modeled_label,
        "usable_donor_count": lineage.usable_donor_count,
        "usable_study_count": lineage.usable_study_count,
        "stable_gene_count": lineage.stable_gene_count,
        "concentration": lineage.concentration,
        "hierarchy_iterations": lineage.hierarchy_iterations,
        "hierarchy_kkt_residual": lineage.hierarchy_kkt_residual,
    }


def _project_training(value: object) -> dict[str, object]:
    if type(value) is not DevelopmentTrainingSummary:
        raise ValueError("development training summary type is not exact")
    summary = value
    return {
        "fit_state": summary.fit_state,
        "source_file_sha256": summary.source_file_sha256,
        "source_bytes": summary.source_bytes,
        "taxonomy_digest": summary.taxonomy_digest,
        "extraction_recipe_digest": summary.extraction_recipe_digest,
        "feature_order_digest": summary.feature_order_digest,
        "selected_shrinkage": summary.selected_shrinkage,
        "candidate_evaluations": [
            _project_candidate(item) for item in summary.candidate_evaluations
        ],
        "selected_feature_count": summary.selected_feature_count,
        "lineage_summaries": [_project_lineage(item) for item in summary.lineage_summaries],
        "production_artifact_permitted": summary.production_artifact_permitted,
        "runtime_mount_permitted": summary.runtime_mount_permitted,
    }


def _parse_label_support(value: object) -> LabelFoldSupport:
    item = _exact_mapping(value, _LABEL_SUPPORT_FIELDS)
    label = _exact_string(item["modeled_label"])
    if label not in _ALLOWED_MODELED_LABELS:
        raise ValueError("modeled label is outside the production taxonomy")
    return LabelFoldSupport(
        modeled_label=label,
        training_usable_donor_count=_exact_int(item["training_usable_donor_count"]),
        training_usable_study_count=_exact_int(item["training_usable_study_count"]),
        held_usable_donor_count=_exact_int(item["held_usable_donor_count"]),
        held_usable_study_count=_exact_int(item["held_usable_study_count"]),
        evaluable=_exact_bool(item["evaluable"]),
        abstention_reasons=_string_tuple(item["abstention_reasons"]),
    )


def _parse_split_fold(value: object) -> DeidentifiedValidationFoldReceipt:
    item = _exact_mapping(value, _SPLIT_FOLD_FIELDS)
    fold_id = _exact_string(item["fold_id"])
    if _FOLD_ID_PATTERN.fullmatch(fold_id) is None:
        raise ValueError("validation fold ID is outside the fixed domain")
    training_studies = _string_tuple(item["training_study_keys"])
    held_studies = _string_tuple(item["held_study_keys"])
    if not set(training_studies + held_studies).issubset(_ALLOWED_STUDY_KEYS):
        raise ValueError("validation receipt contains an unreviewed study key")
    return DeidentifiedValidationFoldReceipt(
        fold_id=fold_id,
        kind=_exact_string(item["kind"]),  # type: ignore[arg-type]
        training_study_keys=training_studies,
        held_study_keys=held_studies,
        training_donor_count=_exact_int(item["training_donor_count"]),
        held_donor_count=_exact_int(item["held_donor_count"]),
        label_support=tuple(
            _parse_label_support(entry) for entry in _exact_list(item["label_support"])
        ),
        evaluable=_exact_bool(item["evaluable"]),
        abstention_reasons=_string_tuple(item["abstention_reasons"]),
    )


def _parse_split(value: object) -> ValidationSplitReceipt:
    item = _exact_mapping(value, _SPLIT_FIELDS)
    return ValidationSplitReceipt(
        source_file_sha256=_exact_string(item["source_file_sha256"]),
        source_bytes=_exact_int(item["source_bytes"]),
        taxonomy_digest=_exact_string(item["taxonomy_digest"]),
        extraction_recipe_digest=_exact_string(item["extraction_recipe_digest"]),
        folds=tuple(_parse_split_fold(entry) for entry in _exact_list(item["folds"])),
    )


def _parse_candidate_fold(value: object) -> CandidateFoldEvaluation:
    item = _exact_mapping(value, _CANDIDATE_FOLD_FIELDS)
    fold_id = _exact_string(item["fold_id"])
    if _FOLD_ID_PATTERN.fullmatch(fold_id) is None:
        raise ValueError("candidate fold ID is outside the fixed domain")
    reason = item["abstention_reason"]
    return CandidateFoldEvaluation(
        fold_id=fold_id,
        kind=_exact_string(item["kind"]),  # type: ignore[arg-type]
        shrinkage=_exact_float(item["shrinkage"]),
        state=_exact_string(item["state"]),  # type: ignore[arg-type]
        abstention_reason=(None if reason is None else _exact_string(reason)),  # type: ignore[arg-type]
        eligible_lineage_count=_exact_int(item["eligible_lineage_count"]),
        selected_feature_count=_exact_int(item["selected_feature_count"]),
        evaluated_held_record_count=_exact_int(item["evaluated_held_record_count"]),
        mean_per_count_nll=_optional_float(item["mean_per_count_nll"]),
    )


def _parse_candidate(value: object) -> ShrinkageCandidateEvaluation:
    item = _exact_mapping(value, _CANDIDATE_FIELDS)
    return ShrinkageCandidateEvaluation(
        shrinkage=_exact_float(item["shrinkage"]),
        folds=tuple(_parse_candidate_fold(entry) for entry in _exact_list(item["folds"])),
        whole_study_fold_count=_exact_int(item["whole_study_fold_count"]),
        within_study_donor_fold_count=_exact_int(item["within_study_donor_fold_count"]),
        minimum_whole_study_folds=_exact_int(item["minimum_whole_study_folds"]),
        minimum_within_study_donor_folds=_exact_int(item["minimum_within_study_donor_folds"]),
        whole_study_mean_nll=_optional_float(item["whole_study_mean_nll"]),
        within_study_donor_mean_nll=_optional_float(item["within_study_donor_mean_nll"]),
        selection_score=_optional_float(item["selection_score"]),
        selectable=_exact_bool(item["selectable"]),
    )


def _parse_lineage(value: object) -> CandidateLineageSummary:
    item = _exact_mapping(value, _LINEAGE_FIELDS)
    label = _exact_string(item["modeled_label"])
    if label not in _ALLOWED_MODELED_LABELS:
        raise ValueError("lineage summary contains a non-production label")
    return CandidateLineageSummary(
        modeled_label=label,
        usable_donor_count=_exact_int(item["usable_donor_count"]),
        usable_study_count=_exact_int(item["usable_study_count"]),
        stable_gene_count=_exact_int(item["stable_gene_count"]),
        concentration=_exact_float(item["concentration"]),
        hierarchy_iterations=_exact_int(item["hierarchy_iterations"]),
        hierarchy_kkt_residual=_exact_float(item["hierarchy_kkt_residual"]),
    )


def _parse_training(value: object) -> DevelopmentTrainingSummary:
    item = _exact_mapping(value, _TRAINING_FIELDS)
    return DevelopmentTrainingSummary(
        fit_state=_exact_string(item["fit_state"]),  # type: ignore[arg-type]
        source_file_sha256=_exact_string(item["source_file_sha256"]),
        source_bytes=_exact_int(item["source_bytes"]),
        taxonomy_digest=_exact_string(item["taxonomy_digest"]),
        extraction_recipe_digest=_exact_string(item["extraction_recipe_digest"]),
        feature_order_digest=_exact_string(item["feature_order_digest"]),
        selected_shrinkage=_exact_float(item["selected_shrinkage"]),
        candidate_evaluations=tuple(
            _parse_candidate(entry) for entry in _exact_list(item["candidate_evaluations"])
        ),
        selected_feature_count=_exact_int(item["selected_feature_count"]),
        lineage_summaries=tuple(
            _parse_lineage(entry) for entry in _exact_list(item["lineage_summaries"])
        ),
        production_artifact_permitted=_exact_bool(  # type: ignore[arg-type]
            item["production_artifact_permitted"]
        ),
        runtime_mount_permitted=_exact_bool(item["runtime_mount_permitted"]),  # type: ignore[arg-type]
    )


def _canonical_fragment(payload: Mapping[str, object]) -> bytes:
    return json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _bundle_digest(payload_without_digest: Mapping[str, object]) -> str:
    return "sha256:" + hashlib.sha256(_canonical_fragment(payload_without_digest)).hexdigest()


def _validate_production_bindings(
    extraction: GbmapExtractionReceipt,
    split: ValidationSplitReceipt,
    training: DevelopmentTrainingSummary,
) -> None:
    expected_taxonomy = production_label_taxonomy().taxonomy_digest
    production_recipe = production_extraction_recipe()
    expected_recipe = production_reduction_recipe_digest()
    if extraction.source_bytes != development_profile().source.expected_bytes:
        raise ValueError("GBmap source byte length is outside the production lock")
    expected_inventory = (
        production_recipe.expected_cell_count,
        production_recipe.expected_cell_count,
        0,
        production_recipe.expected_source_donor_category_count,
        production_recipe.expected_grouped_donor_category_count,
        production_recipe.expected_source_study_category_count,
        production_recipe.expected_grouped_study_count,
        production_recipe.expected_source_label_count,
        len(_ALLOWED_MODELED_LABELS),
    )
    retained_inventory = (
        extraction.cell_count,
        extraction.retained_cell_count,
        extraction.explicitly_excluded_cell_count,
        extraction.source_donor_category_count,
        extraction.grouped_donor_category_count,
        extraction.source_study_category_count,
        extraction.grouped_study_count,
        extraction.source_label_count,
        extraction.modeled_label_count,
    )
    if retained_inventory != expected_inventory:
        raise ValueError("GBmap extraction inventory is outside the production recipe")
    if (
        extraction.taxonomy_digest != expected_taxonomy
        or split.taxonomy_digest != expected_taxonomy
        or training.taxonomy_digest != expected_taxonomy
        or extraction.extraction_recipe_digest != expected_recipe
        or split.extraction_recipe_digest != expected_recipe
        or training.extraction_recipe_digest != expected_recipe
    ):
        raise ValueError("GBmap production semantic digests do not reconcile")
    if not (
        extraction.source_sha256 == split.source_file_sha256 == training.source_file_sha256
    ) or not (extraction.source_bytes == split.source_bytes == training.source_bytes):
        raise ValueError("GBmap source identities do not reconcile across receipts")
    if extraction.feature_order_digest != training.feature_order_digest:
        raise ValueError("GBmap feature-order digests do not reconcile")


def _validate_privacy_gates(
    extraction: GbmapExtractionReceipt,
    training: DevelopmentTrainingSummary,
) -> None:
    if training.production_artifact_permitted or training.runtime_mount_permitted:
        raise ValueError("GBmap development output permits forbidden publication")
    if (
        extraction.cell_level_material_retained
        or extraction.donor_identifiers_retained
        or extraction.donor_hashes_retained
        or extraction.donor_profiles_retained
        or extraction.aggregate_content_digest_retained
    ):
        raise ValueError("GBmap extraction receipt does not prove de-identification")


def _validate_fold_inventory(
    split: ValidationSplitReceipt,
    training: DevelopmentTrainingSummary,
) -> None:
    split_folds = tuple((fold.fold_id, fold.kind) for fold in split.folds)
    if any(
        tuple((fold.fold_id, fold.kind) for fold in candidate.folds) != split_folds
        for candidate in training.candidate_evaluations
    ):
        raise ValueError("GBmap candidate and split fold inventories do not reconcile")


def _validate_bundle_raw(payload: object) -> _ValidatedBundle:
    bundle = _exact_mapping(payload, _TOP_LEVEL_FIELDS)
    if bundle["schema_version"] != OUTPUT_SCHEMA:
        raise ValueError("GBmap receipt bundle schema is not exact")
    if bundle["bundle_digest_basis"] != BUNDLE_DIGEST_BASIS:
        raise ValueError("GBmap receipt bundle digest basis is not exact")
    supplied_digest = _exact_string(bundle["bundle_digest"])
    if _SHA256_PATTERN.fullmatch(supplied_digest) is None:
        raise ValueError("GBmap receipt bundle digest is invalid")
    digest_body = {key: value for key, value in bundle.items() if key != "bundle_digest"}
    if supplied_digest != _bundle_digest(digest_body):
        raise ValueError("GBmap receipt bundle digest does not verify")

    extraction_data = _exact_mapping(bundle["extraction_receipt"], _EXTRACTION_FIELDS)
    extraction = GbmapExtractionReceipt.model_validate(extraction_data, strict=True)
    split = _parse_split(bundle["validation_split_receipt"])
    training = _parse_training(bundle["training_summary"])
    _validate_production_bindings(extraction, split, training)
    _validate_privacy_gates(extraction, training)
    _validate_fold_inventory(split, training)
    return _ValidatedBundle(extraction=extraction, split=split, training=training)


def _validate_bundle(payload: object) -> _ValidatedBundle:
    return _privacy_call(
        "GBmap retained receipt bundle failed strict validation",
        lambda: _validate_bundle_raw(payload),
    )


def _build_bundle(
    extraction: GbmapExtractionResult,
    training: DevelopmentTrainingResult,
    lock: ExactGbmapH5adLock,
) -> dict[str, object]:
    if (
        type(extraction) is not GbmapExtractionResult
        or type(training) is not DevelopmentTrainingResult
    ):
        raise ValueError("GBmap development results are not exact internal types")
    if (
        training.model.production_artifact_permitted is not False
        or training.model.runtime_mount_permitted is not False
    ):
        raise ValueError("GBmap development candidate permits forbidden publication")
    if (
        extraction.receipt.source_sha256 != lock.sha256
        or extraction.receipt.source_bytes != lock.expected_bytes
        or training.split_plan.feature_order_digest != extraction.receipt.feature_order_digest
        or training.summary.feature_order_digest != extraction.receipt.feature_order_digest
    ):
        raise ValueError("GBmap in-memory source and feature bindings do not reconcile")
    body: dict[str, object] = {
        "schema_version": OUTPUT_SCHEMA,
        "bundle_digest_basis": BUNDLE_DIGEST_BASIS,
        "extraction_receipt": _project_extraction(extraction.receipt),
        "validation_split_receipt": _project_split(training.split_plan.receipt),
        "training_summary": _project_training(training.summary),
    }
    payload = {**body, "bundle_digest": _bundle_digest(body)}
    _validate_bundle_raw(payload)
    return payload


def build_development_fit_receipts(
    source: Path,
    reviewed_sha256: str,
    *,
    development_only_acknowledged: bool,
    sha256_independently_reviewed: bool,
) -> dict[str, object]:
    """Extract and fit in-process, returning only approved retained projections."""

    _require_acknowledgements(
        development_only_acknowledged=development_only_acknowledged,
        sha256_independently_reviewed=sha256_independently_reviewed,
    )
    reviewed_digest = _reviewed_sha256(reviewed_sha256)
    before = _capture_source_snapshot(source)
    guard = _open_source_guard(before)
    try:
        lock = _production_lock(reviewed_digest)
        dependencies = _privacy_call(
            "production GBmap extraction dependencies failed closed",
            lambda: (
                production_extraction_recipe(),
                production_donor_crosswalk(),
                production_study_crosswalk(),
                production_label_taxonomy(),
            ),
        )
        recipe, donor_crosswalk, study_crosswalk, taxonomy = dependencies
        extraction = _privacy_call(
            "GBmap source extraction failed closed",
            lambda: extract_pinned_gbmap_reference(
                source,
                lock=lock,
                taxonomy=taxonomy,
                donor_crosswalk=donor_crosswalk,
                study_crosswalk=study_crosswalk,
                recipe=recipe,
            ),
        )
        training = _privacy_call(
            "GBmap development training failed closed",
            lambda: train_development_candidate(extraction.reference),
        )
        after = _capture_source_snapshot(source)
        _require_source_unchanged(before, after, guard)
        return _privacy_call(
            "GBmap retained receipt projection failed closed",
            lambda: _build_bundle(extraction, training, lock),
        )
    finally:
        with suppress(OSError):
            guard.close()


def _canonical_json_bytes(payload: Mapping[str, object]) -> bytes:
    _validate_bundle(payload)
    encoded = _privacy_call(
        "GBmap retained receipts are not canonical JSON",
        lambda: _canonical_fragment(payload) + b"\n",
    )
    if len(encoded) > MAX_OUTPUT_BYTES:
        raise GbmapDevelopmentFitDriverError("GBmap retained receipts exceed the output bound")
    return encoded


def _require_new_destination(destination: Path) -> None:
    if not isinstance(destination, Path):
        raise GbmapDevelopmentFitDriverError("destination must be a pathlib Path")
    exists = False
    failed = False
    try:
        destination.lstat()
        exists = True
    except FileNotFoundError:
        pass
    except OSError:
        failed = True
    if failed:
        raise GbmapDevelopmentFitDriverError(
            "GBmap receipt destination could not be inspected"
        ) from None
    if exists:
        raise GbmapDevelopmentFitDriverError("refusing to overwrite an existing GBmap receipt")


def write_receipts_atomically(destination: Path, payload: Mapping[str, object]) -> int:
    """Publish one new canonical receipt file without overwrite or partial output."""

    _require_new_destination(destination)
    encoded = _canonical_json_bytes(payload)
    temporary_path: Path | None = None
    failure: str | None = None
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            mode="wb",
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary_path, destination)
        except FileExistsError:
            failure = "refusing to overwrite an existing GBmap receipt"
        except OSError:
            failure = "GBmap receipts could not be published atomically"
    except OSError:
        failure = "GBmap receipt output failed closed"
    finally:
        if temporary_path is not None:
            with suppress(OSError):
                temporary_path.unlink(missing_ok=True)
    if failure is not None:
        raise GbmapDevelopmentFitDriverError(failure) from None
    return len(encoded)


def run(
    source: Path,
    reviewed_sha256: str,
    destination: Path,
    *,
    development_only_acknowledged: bool,
    sha256_independently_reviewed: bool,
) -> int:
    """Complete a non-resumable offline fit and atomically publish safe receipts."""

    _require_acknowledgements(
        development_only_acknowledged=development_only_acknowledged,
        sha256_independently_reviewed=sha256_independently_reviewed,
    )
    _require_new_destination(destination)
    payload = build_development_fit_receipts(
        source,
        reviewed_sha256,
        development_only_acknowledged=development_only_acknowledged,
        sha256_independently_reviewed=sha256_independently_reviewed,
    )
    return write_receipts_atomically(destination, payload)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="exact local scarches_core_GBmap.h5ad path")
    parser.add_argument(
        "--reviewed-sha256",
        required=True,
        help="independently reviewed canonical sha256:<64 lowercase hex> lock",
    )
    parser.add_argument("--output", required=True, type=Path, help="new retained receipt JSON path")
    parser.add_argument(
        "--acknowledge-development-only",
        required=True,
        action="store_true",
        help=(
            "acknowledge that the fit is unadmitted development evidence, the model is not "
            "serialized or mounted, and interrupted runs cannot resume"
        ),
    )
    parser.add_argument(
        "--acknowledge-sha256-independently-reviewed",
        required=True,
        action="store_true",
        help="attest that the supplied SHA-256 was recomputed and reviewed independently",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        run(
            cast("Path", args.source),
            cast("str", args.reviewed_sha256),
            cast("Path", args.output),
            development_only_acknowledged=cast("bool", args.acknowledge_development_only),
            sha256_independently_reviewed=cast(
                "bool",
                args.acknowledge_sha256_independently_reviewed,
            ),
        )
    except (GbmapDevelopmentFitDriverError, GbmapDeconvolutionError):
        print("error: GBmap offline development fit failed closed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
