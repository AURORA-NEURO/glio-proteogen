# ruff: noqa: PERF401, PLR0913, PLR0915, PLR0917, PLR2004, T201, TRY003
"""Fit the de-identified PDC000515/SPHINKS signature-transition concordance profile.

The artifact produced here is deliberately not a kinase-activity model.  It freezes
only same-assay longitudinal signature concordance learned from strict paired
PDC000515 phosphosite contrasts.  Patient measurements, identifiers, projections,
and identifier-derived hashes are never serialized.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import warnings
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

import numpy as np
import numpy.typing as npt

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from glio_proteogen.research.gbm_master_kinases.catalog import master_kinase_catalog
from glio_proteogen.research.longitudinal_gbm_phospho.catalog import (
    EXPECTED_CONTENT_DIGEST as PDC_ARTIFACT_CONTENT_DIGEST,
)
from glio_proteogen.research.longitudinal_gbm_phospho.catalog import (
    EXPECTED_CROSSWALK_DIGEST as PDC_CROSSWALK_DIGEST,
)
from glio_proteogen.research.longitudinal_gbm_phospho.catalog import (
    EXPECTED_HGNC_MAPPING_DIGEST as PDC_HGNC_MAPPING_DIGEST,
)
from glio_proteogen.research.longitudinal_gbm_phospho.catalog import (
    EXPECTED_PROFILE_DIGEST as PDC_SOURCE_PROFILE_DIGEST,
)
from tools import import_kncc_longitudinal_phospho as base

MODEL_ID: Final = "kncc-pdc000515-sphinks-signature-transition/1.0.0"
PROFILE_ID: Final = "kncc-gbm-longitudinal-kinase-transition/1.0.0"
SCHEMA_VERSION: Final = "glio-proteogen.kncc-longitudinal-kinase-transition-artifact/1.0.0"
MIN_KINASE_FAMILIES: Final = 3
MIN_RUNTIME_WEIGHT_COVERAGE: Final = 0.25
FDR_THRESHOLD: Final = 0.10
FIXED_HYPOTHESIS_COUNT: Final = 24
OUTER_FOLDS: Final = 5
INNER_FOLDS: Final = 3
FULL_PERMUTATIONS: Final = 2_047
OUTER_PERMUTATIONS: Final = 511
BOOTSTRAP_REPLICATES: Final = 64
BOOTSTRAP_PERMUTATIONS: Final = 255
PHOSPHO_CANDIDATES: Final = (32, 64, 128, 256)
QUANTIZATION_DECIMALS: Final = 10
CORE_STABILITY_THRESHOLD: Final = 0.80

FloatArray = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.int64]
BoolArray = npt.NDArray[np.bool_]
ObjectArray = npt.NDArray[np.object_]


@dataclass(frozen=True, slots=True)
class KinaseSpec:
    symbol: str
    subtype: str
    site_indices: IntArray
    source_weights: FloatArray


@dataclass(frozen=True, slots=True)
class SelectedKinase:
    symbol: str
    subtype: str
    site_indices: IntArray
    weights: FloatArray
    direction: float
    enrichment: float
    p_value: float
    q_value: float


@dataclass(frozen=True, slots=True)
class SignatureFit:
    scale: FloatArray
    support: IntArray
    eligible: BoolArray
    selected: tuple[SelectedKinase, ...]
    all_results: tuple[dict[str, object], ...]
    converged: bool


def _q(value: float) -> float:
    return round(float(value), QUANTIZATION_DECIMALS)


def _require_converged(*, converged: bool, context: str) -> None:
    if not converged:
        raise RuntimeError(f"{context} did not converge")


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _grouped_folds(groups: tuple[str, ...], count: int, salt: str) -> tuple[IntArray, ...]:
    order = sorted(
        range(len(groups)),
        key=lambda index: hashlib.sha256(f"{salt}:{groups[index]}".encode()).digest(),
    )
    buckets: list[list[int]] = [[] for _ in range(count)]
    for offset, index in enumerate(order):
        buckets[offset % count].append(index)
    return tuple(np.asarray(bucket, dtype=np.int64) for bucket in buckets)


def _rank_values(values: FloatArray) -> FloatArray:
    order = np.argsort(values, kind="stable")
    ranks = np.empty(values.size, dtype=np.float64)
    offset = 0
    while offset < values.size:
        stop = offset + 1
        while stop < values.size and values[order[stop]] == values[order[offset]]:
            stop += 1
        ranks[order[offset:stop]] = 0.5 * (offset + stop - 1)
        offset = stop
    return ranks


def _normalized_stratum_ranks(
    values: FloatArray,
    valid: BoolArray,
    strata: ObjectArray,
) -> FloatArray:
    output = np.full(values.size, np.nan, dtype=np.float64)
    for stratum in sorted(set(strata[valid])):
        indices = np.flatnonzero(valid & (strata == stratum))
        if indices.size < 2:
            continue
        ranks = _rank_values(values[indices])
        output[indices] = 2.0 * (ranks + 0.5) / indices.size - 1.0
    return output


def _site_stratum(label: str) -> str:
    tokens = re.findall(r"([STY])\d+[sty]?", label.rsplit("-", 1)[-1])
    if not tokens:
        raise ValueError("crosswalk label has no phospho-residue token")
    return f"{''.join(sorted(set(tokens)))}:{len(tokens)}"


def _bh_fixed_family(p_values: list[float]) -> list[float]:
    count = len(p_values)
    if count != FIXED_HYPOTHESIS_COUNT:
        raise ValueError("the SPHINKS hypothesis family must contain exactly 24 kinases")
    order = np.argsort(np.asarray(p_values, dtype=np.float64), kind="stable")
    output = np.ones(count, dtype=np.float64)
    running = 1.0
    for rank in range(count - 1, -1, -1):
        index = int(order[rank])
        running = min(running, p_values[index] * count / (rank + 1))
        output[index] = running
    return [float(value) for value in output]


def _build_family_matrix(
    cohort: base.PhosphositeCohort,
) -> tuple[tuple[str, ...], FloatArray, tuple[tuple[int, ...], ...], dict[str, object]]:
    labels = tuple(sorted({value for value in cohort.sphinks_labels if value is not None}))
    rows_by_label: dict[str, list[int]] = {label: [] for label in labels}
    for index, label in enumerate(cohort.sphinks_labels):
        if label is not None:
            rows_by_label[label].append(index)
    matrix = np.full((cohort.delta.shape[0], len(labels)), np.nan, dtype=np.float64)
    for column, label in enumerate(labels):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            matrix[:, column] = np.nanmedian(cohort.delta[:, rows_by_label[label]], axis=1)
    signature_rows = [
        index for index, memberships in enumerate(cohort.signature_kinases) if memberships
    ]
    signature_labels = {
        cohort.sphinks_labels[index]
        for index in signature_rows
        if cohort.sphinks_labels[index] is not None
    }
    mapping: dict[str, object] = {
        "exact_crosswalk_pdc_rows": sum(value is not None for value in cohort.sphinks_labels),
        "unique_crosswalk_families": len(labels),
        "duplicate_family_extra_pdc_rows": sum(
            max(0, len(indices) - 1) for indices in rows_by_label.values()
        ),
        "signature_pdc_rows": len(signature_rows),
        "unique_signature_families": len(signature_labels),
        "composite_rows_are_never_split": True,
        "family_collapse": (
            "within-transition median across exact SPHINKS-label collisions after each "
            "PDC composite row remains indivisible"
        ),
    }
    return labels, matrix, tuple(tuple(rows_by_label[label]) for label in labels), mapping


def _build_specs(labels: tuple[str, ...]) -> tuple[KinaseSpec, ...]:
    catalog = master_kinase_catalog()
    label_index = {label: index for index, label in enumerate(labels)}
    output: list[KinaseSpec] = []
    for master in catalog.masters:
        by_site: dict[str, list[float]] = defaultdict(list)
        for edge in catalog.edges_by_kinase[master.hgnc_symbol]:
            if edge.source_site_label in label_index:
                by_site[edge.source_site_label].append(edge.svm_probability * edge.rho_spearman)
        ordered = sorted(by_site)
        output.append(
            KinaseSpec(
                symbol=master.hgnc_symbol,
                subtype=master.subtype,
                site_indices=np.asarray([label_index[value] for value in ordered], dtype=np.int64),
                source_weights=np.asarray(
                    [float(np.mean(by_site[value])) for value in ordered], dtype=np.float64
                ),
            )
        )
    if len(output) != FIXED_HYPOTHESIS_COUNT:
        raise AssertionError("SPHINKS catalog no longer has the fixed 24-kinase family")
    return tuple(output)


def _empirical_enrichment(
    ranks: FloatArray,
    eligible: BoolArray,
    support: IntArray,
    training_count: int,
    strata: ObjectArray,
    spec: KinaseSpec,
    permutations: int,
    seed_component: str,
) -> tuple[float | None, float, IntArray, FloatArray]:
    retained = spec.site_indices[eligible[spec.site_indices]]
    if retained.size < MIN_KINASE_FAMILIES:
        return None, 1.0, retained, np.empty(0, dtype=np.float64)
    source_by_index = {
        int(index): float(weight)
        for index, weight in zip(spec.site_indices, spec.source_weights, strict=True)
    }
    weights = np.asarray([source_by_index[int(index)] for index in retained], dtype=np.float64)
    weights *= np.sqrt(support[retained].astype(np.float64) / training_count)
    observed = float(np.dot(weights, ranks[retained]) / weights.sum())
    rng = np.random.default_rng(
        int.from_bytes(hashlib.sha256(seed_component.encode()).digest()[:8], "big")
    )
    null = np.empty(permutations, dtype=np.float64)
    retained_strata = strata[retained]
    unique_strata = sorted(set(retained_strata))
    pools = {stratum: np.flatnonzero(eligible & (strata == stratum)) for stratum in unique_strata}
    positions = {stratum: np.flatnonzero(retained_strata == stratum) for stratum in unique_strata}
    for replicate in range(permutations):
        numerator = 0.0
        for stratum in unique_strata:
            local = positions[stratum]
            pool = pools[stratum]
            if pool.size < local.size:
                raise ValueError("competitive null stratum is smaller than the signature")
            sampled = rng.choice(pool, size=local.size, replace=False)
            numerator += float(np.dot(weights[local], ranks[sampled]))
        null[replicate] = numerator / weights.sum()
    p_value = (1.0 + float(np.sum(np.abs(null) >= abs(observed)))) / (permutations + 1.0)
    return observed, p_value, retained, weights


def _fit_signature_model(
    matrix: FloatArray,
    labels: tuple[str, ...],
    strata: ObjectArray,
    specs: tuple[KinaseSpec, ...],
    training: IntArray,
    *,
    permutations: int,
    seed_component: str,
    release_eligible: BoolArray | None = None,
) -> SignatureFit:
    source_fit = base._fit_axis(matrix[training], labels)
    eligible = source_fit.eligible.copy()
    if release_eligible is not None:
        eligible &= release_eligible
    ranks = _normalized_stratum_ranks(source_fit.effect, eligible, strata)
    raw: list[tuple[float | None, float, IntArray, FloatArray]] = []
    for spec in specs:
        raw.append(
            _empirical_enrichment(
                ranks,
                eligible,
                source_fit.support,
                training.size,
                strata,
                spec,
                permutations,
                f"{seed_component}:{spec.symbol}",
            )
        )
    q_values = _bh_fixed_family([item[1] for item in raw])
    selected: list[SelectedKinase] = []
    all_results: list[dict[str, object]] = []
    for spec, result, q_value in zip(specs, raw, q_values, strict=True):
        enrichment, p_value, retained, weights = result
        supported = enrichment is not None
        item: dict[str, object] = {
            "kinase": spec.symbol,
            "subtype": spec.subtype,
            "mapped_training_eligible_families": int(retained.size),
            "enrichment": _q(enrichment) if enrichment is not None else None,
            "p_value": _q(p_value),
            "q_value": _q(q_value),
            "selected": bool(supported and q_value <= FDR_THRESHOLD),
        }
        all_results.append(item)
        if supported and q_value <= FDR_THRESHOLD:
            selected.append(
                SelectedKinase(
                    symbol=spec.symbol,
                    subtype=spec.subtype,
                    site_indices=retained,
                    weights=weights,
                    direction=1.0 if cast("float", enrichment) > 0.0 else -1.0,
                    enrichment=cast("float", enrichment),
                    p_value=p_value,
                    q_value=q_value,
                )
            )
    return SignatureFit(
        scale=source_fit.scale,
        support=source_fit.support,
        eligible=eligible,
        selected=tuple(selected),
        all_results=tuple(all_results),
        converged=source_fit.converged,
    )


def _patient_scores(model: SignatureFit, matrix: FloatArray, strata: ObjectArray) -> FloatArray:
    consensus = np.full(matrix.shape[0], np.nan, dtype=np.float64)
    selected_by_subtype: dict[str, list[SelectedKinase]] = defaultdict(list)
    for item in model.selected:
        selected_by_subtype[item.subtype].append(item)
    multiplicity = Counter(int(index) for item in model.selected for index in item.site_indices)
    for patient_index, values in enumerate(matrix):
        valid = model.eligible & np.isfinite(values)
        standardized = np.zeros(values.size, dtype=np.float64)
        standardized[valid] = values[valid] / model.scale[valid]
        ranks = _normalized_stratum_ranks(standardized, valid, strata)
        subtype_scores: list[float] = []
        for subtype in sorted(selected_by_subtype):
            kinase_scores: list[float] = []
            for item in selected_by_subtype[subtype]:
                observed = np.isfinite(ranks[item.site_indices])
                if int(observed.sum()) < MIN_KINASE_FAMILIES:
                    continue
                adjusted = item.weights / np.asarray(
                    [multiplicity[int(index)] for index in item.site_indices],
                    dtype=np.float64,
                )
                coverage = float(adjusted[observed].sum() / adjusted.sum())
                if coverage < MIN_RUNTIME_WEIGHT_COVERAGE:
                    continue
                kinase_scores.append(
                    item.direction
                    * float(
                        np.dot(adjusted[observed], ranks[item.site_indices[observed]])
                        / adjusted[observed].sum()
                    )
                )
            if kinase_scores:
                subtype_scores.append(float(np.mean(kinase_scores)))
        if subtype_scores and len(subtype_scores) == len(selected_by_subtype):
            consensus[patient_index] = float(np.mean(subtype_scores))
    return consensus


def _summarize(scores: FloatArray) -> dict[str, object]:
    values = scores[np.isfinite(scores)]
    count = int(values.size)
    accuracy = float(np.mean(values > 0.0)) if count else 0.0
    z = 1.959963984540054
    if count:
        denominator = 1.0 + z * z / count
        center = (accuracy + z * z / (2.0 * count)) / denominator
        half = (
            z
            * math.sqrt(accuracy * (1.0 - accuracy) / count + z * z / (4.0 * count * count))
            / denominator
        )
        interval = [_q(center - half), _q(center + half)]
    else:
        interval = [0.0, 1.0]
    return {
        "supported_pairs": count,
        "abstained_pairs": int(scores.size - count),
        "direction_accuracy": _q(accuracy),
        "wilson_95_interval": interval,
        "median_sign_margin": _q(float(np.median(2.0 * values)) if count else 0.0),
    }


def _pairwise_jaccard(sets: list[frozenset[str]]) -> dict[str, float]:
    values: list[float] = []
    for left_index, left in enumerate(sets):
        for right in sets[left_index + 1 :]:
            union = left | right
            values.append(len(left & right) / len(union) if union else 1.0)
    return {
        "minimum": _q(float(np.min(values)) if values else 1.0),
        "median": _q(float(np.median(values)) if values else 1.0),
        "maximum": _q(float(np.max(values)) if values else 1.0),
    }


def _kinase_projection(item: SelectedKinase) -> dict[str, object]:
    order = np.argsort(item.site_indices, kind="stable")
    return {
        "kinase": item.symbol,
        "subtype": item.subtype,
        "direction": "source_recurrence_aligned" if item.direction > 0 else "reverse_aligned",
        "family_indices": [int(value) for value in item.site_indices[order]],
        "weights": [_q(value) for value in item.weights[order]],
        "enrichment": _q(item.enrichment),
        "p_value": _q(item.p_value),
        "q_value": _q(item.q_value),
    }


def _bootstrap_projection(index: int, model: SignatureFit) -> dict[str, object]:
    family_indices = sorted({int(value) for item in model.selected for value in item.site_indices})
    content: dict[str, object] = {
        "replicate_index": index,
        "seed_hex": hashlib.sha256(f"pdc000515-sphinks-stability-v1:{index}".encode()).hexdigest()[
            :16
        ],
        "family_indices": family_indices,
        "scales": [_q(model.scale[value]) for value in family_indices],
        "kinases": [_kinase_projection(item) for item in model.selected],
    }
    content["replicate_digest"] = _digest(content)
    return content


def _select_phospho_axis(
    cohort: base.PhosphositeCohort,
    training: IntArray,
    outer_index: int,
) -> int:
    local_groups = tuple(cohort.patient_groups[index] for index in training)
    inner = _grouped_folds(local_groups, INNER_FOLDS, f"mk-baseline-inner-v1:{outer_index}")
    pooled: dict[int, list[float]] = {count: [] for count in PHOSPHO_CANDIDATES}
    totals = dict.fromkeys(PHOSPHO_CANDIDATES, 0)
    for held_local in inner:
        train_local = np.setdiff1d(
            np.arange(training.size, dtype=np.int64), held_local, assume_unique=True
        )
        fit = base._fit_axis(cohort.delta[training[train_local]], cohort.site_groups)
        _require_converged(
            converged=fit.converged,
            context=f"raw phosphosite inner fit in outer fold {outer_index}",
        )
        for count in PHOSPHO_CANDIDATES:
            selected, weights = base._weights(fit, count)
            scores, _, _ = base._project(
                cohort.delta[training[held_local]], fit.scale, selected, weights
            )
            pooled[count].extend(float(value) for value in scores[np.isfinite(scores)])
            totals[count] += int(scores.size)
    summaries = {
        count: base._candidate_summary(
            pooled[count], total_pairs=totals[count], top_feature_count=count
        )
        for count in PHOSPHO_CANDIDATES
    }
    return int(base._one_standard_error_choice(summaries)[0])


def _score_phospho_axis(
    cohort: base.PhosphositeCohort,
    training: IntArray,
    held: IntArray,
    count: int,
) -> FloatArray:
    fit = base._fit_axis(cohort.delta[training], cohort.site_groups)
    _require_converged(converged=fit.converged, context="raw phosphosite outer-comparator fit")
    selected, weights = base._weights(fit, count)
    return base._project(cohort.delta[held], fit.scale, selected, weights)[0]


def build_artifact(source_dir: Path, hgnc_source: Path) -> dict[str, object]:
    """Build an aggregate-only, source-attested signature-transition artifact."""

    cohort = base.load_cohort(source_dir, hgnc_source)
    if cohort.source_attestation is None:
        raise ValueError("naked cohorts cannot produce a canonical artifact")
    if cohort.source_attestation.source_manifest_sha256 != base.PDC_SOURCE_MANIFEST_SHA256:
        raise ValueError("PDC source-manifest attestation drift")
    sphinks_metadata = cast("dict[str, object]", cohort.crosswalk_metadata["sphinks"])
    hgnc_metadata = cast("dict[str, object]", cohort.crosswalk_metadata["hgnc"])
    if sphinks_metadata["crosswalk_digest"] != PDC_CROSSWALK_DIGEST:
        raise ValueError("PDC/SPHINKS exact crosswalk digest drift")
    if hgnc_metadata["mapping_digest"] != PDC_HGNC_MAPPING_DIGEST:
        raise ValueError("PDC/HGNC exact mapping digest drift")

    labels, matrix, rows_by_family, mapping = _build_family_matrix(cohort)
    strata = np.asarray([_site_stratum(label) for label in labels], dtype=object)
    specs = _build_specs(labels)
    all_indices = np.arange(len(cohort.patient_groups), dtype=np.int64)
    full_model = _fit_signature_model(
        matrix,
        labels,
        strata,
        specs,
        all_indices,
        permutations=FULL_PERMUTATIONS,
        seed_component="pdc000515-sphinks-full-v1",
    )
    _require_converged(converged=full_model.converged, context="full PDC000515 family Huber fit")

    outer = _grouped_folds(
        cohort.patient_groups, OUTER_FOLDS, "pdc000515-sphinks-longitudinal-outer-v1"
    )
    signature_scores = np.full(len(cohort.patient_groups), np.nan, dtype=np.float64)
    phospho_scores = np.full(len(cohort.patient_groups), np.nan, dtype=np.float64)
    outer_sets: list[frozenset[str]] = []
    outer_selection: Counter[str] = Counter()
    for outer_index, held in enumerate(outer):
        training = np.setdiff1d(all_indices, held, assume_unique=True)
        model = _fit_signature_model(
            matrix,
            labels,
            strata,
            specs,
            training,
            permutations=OUTER_PERMUTATIONS,
            seed_component=f"pdc000515-sphinks-outer-v1:{outer_index}",
        )
        _require_converged(
            converged=model.converged,
            context=f"signature-transition outer fit {outer_index}",
        )
        signature_scores[held] = _patient_scores(model, matrix[held], strata)
        baseline_count = _select_phospho_axis(cohort, training, outer_index)
        phospho_scores[held] = _score_phospho_axis(cohort, training, held, baseline_count)
        selected = frozenset(item.symbol for item in model.selected)
        outer_sets.append(selected)
        outer_selection.update(selected)

    bootstrap_models: list[SignatureFit] = []
    bootstrap_sets: list[frozenset[str]] = []
    bootstrap_directions: dict[str, list[float]] = defaultdict(list)
    seed_root = int.from_bytes(
        hashlib.sha256(b"pdc000515-sphinks-stability-v1").digest()[:8], "big"
    )
    for replicate in range(BOOTSTRAP_REPLICATES):
        rng = np.random.default_rng(seed_root + replicate)
        sampled = rng.integers(
            0, len(cohort.patient_groups), size=len(cohort.patient_groups)
        ).astype(np.int64)
        model = _fit_signature_model(
            matrix,
            labels,
            strata,
            specs,
            sampled,
            permutations=BOOTSTRAP_PERMUTATIONS,
            seed_component=f"pdc000515-sphinks-stability-v1:{replicate}",
            release_eligible=full_model.eligible,
        )
        _require_converged(converged=model.converged, context=f"patient bootstrap {replicate}")
        bootstrap_models.append(model)
        selected = frozenset(item.symbol for item in model.selected)
        bootstrap_sets.append(selected)
        for item in model.selected:
            bootstrap_directions[item.symbol].append(item.direction)

    catalog = master_kinase_catalog()
    eligible_indices = np.flatnonzero(full_model.eligible)
    families: list[dict[str, object]] = []
    for index in eligible_indices:
        row_indices = rows_by_family[int(index)]
        source_ids = sorted(cohort.site_groups[row] for row in row_indices)
        families.append(
            {
                "family_index": int(index),
                "source_site_label": labels[int(index)],
                "stratum": str(strata[int(index)]),
                "source_phosphosite_ids": source_ids,
                "source_row_count": len(source_ids),
                "contains_composite_source_group": any(
                    len(re.findall(r"[sty]\d+", cohort.site_groups[row])) > 1 for row in row_indices
                ),
                "paired_support": int(full_model.support[int(index)]),
                "paired_coverage": _q(full_model.support[int(index)] / len(cohort.patient_groups)),
                "transition_scale": _q(full_model.scale[int(index)]),
            }
        )

    bootstrap_documents = [
        _bootstrap_projection(index, model) for index, model in enumerate(bootstrap_models)
    ]
    bootstrap_digest = _digest(bootstrap_documents)
    full_symbols = frozenset(item.symbol for item in full_model.selected)
    bootstrap_frequency = {
        spec.symbol: _q(float(np.mean([spec.symbol in selected for selected in bootstrap_sets])))
        for spec in specs
    }
    direction_consistency = {
        symbol: _q(abs(sum(values)) / len(values))
        for symbol, values in sorted(bootstrap_directions.items())
        if values
    }
    common = np.isfinite(signature_scores) & np.isfinite(phospho_scores)
    raw_only = int(np.sum((signature_scores[common] <= 0.0) & (phospho_scores[common] > 0.0)))
    signature_only = int(np.sum((signature_scores[common] > 0.0) & (phospho_scores[common] <= 0.0)))
    discordant = raw_only + signature_only
    if discordant:
        tail = sum(math.comb(discordant, k) for k in range(min(raw_only, signature_only) + 1))
        mcnemar_p = min(1.0, 2.0 * tail / (2**discordant))
    else:
        mcnemar_p = 1.0

    document: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "model_id": MODEL_ID,
        "profile_id": PROFILE_ID,
        "source_attestation_state": "verified_exact_snapshots",
        "privacy": {
            "patient_identifiers_emitted": False,
            "patient_derived_digests_emitted": False,
            "patient_level_matrices_emitted": False,
            "aggregate_and_release_eligible_parameters_only": True,
        },
        "source_bindings": {
            "fitter_source_sha256": (
                "sha256:" + hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
            ),
            "pdc_study_id": base.PDC_STUDY_ID,
            "pdc_study_version_uuid": base.PDC_STUDY_VERSION_UUID,
            "pdc_source_manifest_digest": "sha256:" + base.PDC_SOURCE_MANIFEST_SHA256,
            "pdc_phosphosite_artifact_content_digest": PDC_ARTIFACT_CONTENT_DIGEST,
            "pdc_phosphosite_source_profile_digest": PDC_SOURCE_PROFILE_DIGEST,
            "pdc_hgnc_mapping_digest": PDC_HGNC_MAPPING_DIGEST,
            "pdc_sphinks_crosswalk_digest": PDC_CROSSWALK_DIGEST,
            "sphinks_catalog_artifact_digest": catalog.artifact_digest,
            "sphinks_catalog_content_digest": catalog.content_digest,
            "sphinks_background_tuple_digest": catalog.background_tuple_digest,
            "sphinks_signature_edge_digest": catalog.signature_edge_digest,
            "sphinks_master_kinase_digest": catalog.master_kinase_digest,
            "sphinks_source_sha256": catalog.source_sha256,
        },
        "counts": {
            **mapping,
            "strict_patient_pairs": len(cohort.patient_groups),
            "release_eligible_background_families": int(full_model.eligible.sum()),
            "fixed_master_kinase_hypotheses": len(specs),
            "fixed_subtype_family": dict(Counter(item.subtype for item in specs)),
            "full_fit_selected_kinases": len(full_model.selected),
            "bootstrap_replicates": BOOTSTRAP_REPLICATES,
        },
        "policies": {
            "contrast": "PDC000515 phosphosite T2-minus-T1 only",
            "training_feature_admission": "at_least_60_percent_finite_paired_support",
            "feature_fit": "Huber_location_MAD_and_support_variance_floor_refit",
            "signature_edge_weight": (
                "mean_Table5d_SVM_probability_times_positive_Spearman_rho_then_"
                "sqrt_training_support_fraction"
            ),
            "competitive_null": (
                "two_sided_empirical_permutation_of_release_eligible_Table5a_families_"
                "matched_exact_residue_composition_and_composite_cardinality"
            ),
            "fixed_hypothesis_family": "Benjamini_Hochberg_over_all_24_kinases_abstentions_p1",
            "fdr_threshold": FDR_THRESHOLD,
            "inverse_multiplicity": "global_selected_kinase_family_membership_inverse_count",
            "aggregation": "kinases_equal_within_subtype_then_subtypes_equal",
            "minimum_kinase_families": MIN_KINASE_FAMILIES,
            "minimum_runtime_weight_coverage": MIN_RUNTIME_WEIGHT_COVERAGE,
            "claim_ceiling": "SPHINKS_signature_transition_concordance_only",
        },
        "families": families,
        "full_fit": {
            "all_kinases": list(full_model.all_results),
            "selected_kinases": [_kinase_projection(item) for item in full_model.selected],
        },
        "stability": {
            "bootstrap_inventory_policy": (
                "exact patient-bootstrap refits condition selection on the frozen full-fit "
                "release-eligible family inventory; stability and uncertainty are not validation"
            ),
            "bootstrap_all_refits_converged": True,
            "outer_selected_set_jaccard": _pairwise_jaccard(outer_sets),
            "outer_selection_frequency": {
                spec.symbol: _q(outer_selection[spec.symbol] / OUTER_FOLDS) for spec in specs
            },
            "bootstrap_selected_set_jaccard": _pairwise_jaccard(bootstrap_sets),
            "bootstrap_full_set_recovery_fraction": _q(
                float(np.mean([value == full_symbols for value in bootstrap_sets]))
            ),
            "bootstrap_selection_frequency": bootstrap_frequency,
            "bootstrap_direction_consistency_when_selected": direction_consistency,
            "core_stability_threshold": CORE_STABILITY_THRESHOLD,
        },
        "bootstrap": {
            "replicate_count": BOOTSTRAP_REPLICATES,
            "ensemble_digest": bootstrap_digest,
            "replicates": bootstrap_documents,
        },
        "fit_evaluation": {
            "interpretation": (
                "internal source-cohort transition concordance; repeated held-pair results "
                "are not external validation or independent evidence"
            ),
            "outer_validation_preprocessing": (
                "feature admission, scaling, competitive nulls, signature selection, and weights "
                "are fit only on outer-training pairs without a full-cohort release-inventory gate"
            ),
            "patient_grouped_outer_folds": OUTER_FOLDS,
            "outer_signature_refits_all_converged": True,
            "nested_raw_comparator_refits_all_converged": True,
            "signature_transition": _summarize(signature_scores),
            "raw_phosphosite_axis_same_folds": _summarize(phospho_scores),
            "incremental_comparison": {
                "common_supported_pairs": int(common.sum()),
                "signature_only_correct": signature_only,
                "raw_phosphosite_only_correct": raw_only,
                "mcnemar_exact_two_sided_p_value": _q(mcnemar_p),
                "score_pearson": _q(
                    float(np.corrcoef(signature_scores[common], phospho_scores[common])[0, 1])
                ),
                "sign_agreement": _q(
                    float(
                        np.mean((signature_scores[common] > 0.0) == (phospho_scores[common] > 0.0))
                    )
                ),
                "adds_independent_evidence": False,
            },
        },
        "runtime_quality_gates": {
            "same_assay_independent_evidence_gate_passed": False,
            "patient_bootstrap_full_refit_convergence_gate_passed": True,
            "patient_bootstrap_full_set_stability_gate_passed": False,
            "patient_bootstrap_interval_calibration_gate_passed": False,
            "output_policy": "all_estimable_outputs_limited_otherwise_abstained",
        },
        "provenance": {
            "pdc_article_attribution": (
                "Kim et al., Integrated proteogenomic characterization of glioblastoma "
                "evolution, Cancer Cell 42(3):358-377.e8 (2024), DOI "
                "10.1016/j.ccell.2023.12.015"
            ),
            "pdc_license": "CC-BY-4.0",
            "pdc_license_url": "https://creativecommons.org/licenses/by/4.0/",
            "pdc_transformation_notice": (
                "GLIO-PROTEOGEN transformed exact PDC000515 source snapshots into a "
                "de-identified aggregate signature-transition coefficient artifact; no "
                "raw patient matrices or identifiers are redistributed."
            ),
            "sphinks_article_attribution": (
                f"{catalog.article_authors}, {catalog.article_title}, DOI {catalog.article_doi}"
            ),
            "sphinks_license": catalog.source_license,
            "sphinks_license_url": catalog.source_license_url,
            "sphinks_transformation_notice": catalog.transformation_notice,
        },
    }
    content_digest = _digest(document)
    document["artifact_digest"] = content_digest
    _assert_privacy(document, cohort.private_identifiers)
    return document


def _assert_privacy(document: dict[str, object], private_identifiers: frozenset[str]) -> None:
    payload = _canonical_bytes(document)
    text = payload.decode("utf-8")
    if re.search(r"KNCC_GBM\d+", text, flags=re.IGNORECASE):
        raise ValueError("artifact contains a patient pseudonym")
    for identifier in private_identifiers:
        if identifier and identifier.encode("utf-8") in payload:
            raise ValueError("artifact contains a private source identifier")
        for algorithm in (hashlib.md5, hashlib.sha1, hashlib.sha256):
            digest = algorithm(identifier.encode("utf-8"), usedforsecurity=False).hexdigest()
            if digest in text:
                raise ValueError("artifact contains a reversible low-entropy identifier digest")


def write_artifact(document: dict[str, object], destination: Path) -> None:
    payload = _canonical_bytes(document)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--hgnc-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    document = build_artifact(arguments.source_dir, arguments.hgnc_source)
    write_artifact(document, arguments.output)
    payload = arguments.output.read_bytes()
    print(
        json.dumps(
            {
                "bytes": len(payload),
                "file_sha256": hashlib.sha256(payload).hexdigest(),
                "artifact_digest": document["artifact_digest"],
                "bootstrap_ensemble_digest": cast("dict[str, object]", document["bootstrap"])[
                    "ensemble_digest"
                ],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
