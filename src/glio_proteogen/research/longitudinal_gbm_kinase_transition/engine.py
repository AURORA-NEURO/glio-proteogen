"""Deterministic SPHINKS signature-transition concordance runtime."""

from __future__ import annotations

import hashlib
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Literal, cast

import numpy as np
import numpy.typing as npt

from glio_proteogen.research.longitudinal_gbm_phospho.catalog import (
    PhosphositeFeature,
    load_phosphosite_transition_catalog,
)
from glio_proteogen.research.longitudinal_gbm_phospho.contracts import (
    REQUIRED_ASSAY_COMPATIBILITY,
    LongitudinalPhosphoTimePoint,
    PhosphositeEvidenceState,
    PhosphositeObservation,
)
from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    checkpoint,
)

from .canonical import (
    canonical_json_bytes,
    canonical_request_digest,
    computational_request_digest,
    result_payload_digest,
    sha256_digest,
)
from .catalog import (
    KinaseHypothesis,
    KinaseProjection,
    KinaseTransitionCatalog,
    SignatureFamily,
    load_kinase_transition_catalog,
)
from .contracts import (
    MIN_BOOTSTRAPS,
    AnalysisSupport,
    BootstrapInterval,
    BootstrapState,
    KinaseSelectionState,
    KinaseSignatureEvidence,
    LongitudinalGbmKinaseTransitionRequest,
    LongitudinalGbmKinaseTransitionResult,
    ResultProvenance,
    SignatureAblation,
    SignatureDirection,
    SignatureFamilyDriver,
    SourceProvenance,
    SubtypeSignatureEvidence,
    TransitionClassification,
    TransitionEvidence,
)
from .errors import PhosphositeIdentityMismatchError, UnknownPhosphositeError
from .profile import CONSTANTS, algorithm_profile

FloatArray = npt.NDArray[np.float64]
BoolArray = npt.NDArray[np.bool_]

_LIMITED_REASON = "same-assay SPHINKS signature-transition concordance is not independent evidence"
_CALIBRATION_REASON = (
    "patient-bootstrap full-set stability and interval calibration gates are not passed"
)
_COVARIANCE_LIMITATION = (
    "Measurement perturbations assume featurewise-independent Gaussians and combine "
    "from/to standard errors in quadrature; shared-reference, TMT, and batch covariance "
    "cannot be represented by this request contract."
)


@dataclass(frozen=True, slots=True)
class _ExactRow:
    feature: PhosphositeFeature
    from_observation: PhosphositeObservation
    to_observation: PhosphositeObservation
    delta: float
    noise_standard_error: float
    reliability: float


@dataclass(frozen=True, slots=True)
class _FamilyValue:
    family: SignatureFamily
    rows: tuple[_ExactRow, ...]
    delta: float


@dataclass(frozen=True, slots=True)
class _KinaseScore:
    score: float
    coverage: float
    observed_indices: tuple[int, ...]
    ranks: dict[int, float]
    adjusted_weights: dict[int, float]
    contributions: dict[int, float]
    multiplicity: dict[int, int]


@dataclass(frozen=True, slots=True)
class _ScoreBundle:
    consensus: float | None
    equal_kinase: float | None
    kinases: dict[str, _KinaseScore]
    subtypes: dict[str, float]


def _q(value: float) -> float:
    return round(float(value), CONSTANTS.quantization_decimals)


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


def _stratified_ranks(
    standardized: dict[int, float],
    catalog: KinaseTransitionCatalog,
) -> dict[int, float]:
    by_stratum: dict[str, list[tuple[int, float]]] = defaultdict(list)
    family_by_index = catalog.family_by_index
    for index, value in standardized.items():
        by_stratum[family_by_index[index].stratum].append((index, value))
    output: dict[int, float] = {}
    for stratum in sorted(by_stratum):
        members = sorted(by_stratum[stratum])
        if len(members) < 2:
            continue
        values = np.asarray([value for _, value in members], dtype=np.float64)
        ranks = _rank_values(values)
        normalized = 2.0 * (ranks + 0.5) / len(members) - 1.0
        output.update(
            (index, float(rank)) for (index, _), rank in zip(members, normalized, strict=True)
        )
    return output


def _validate_identities(request: LongitudinalGbmKinaseTransitionRequest) -> None:
    base = load_phosphosite_transition_catalog()
    for point in request.time_points:
        for observation in point.observations:
            feature = base.feature_by_id.get(observation.phosphosite_id)
            if feature is None:
                raise UnknownPhosphositeError("unknown exact PDC000515 phosphosite identifier")
            if observation.gene_symbol != feature.approved_gene:
                raise PhosphositeIdentityMismatchError(
                    "phosphosite identifier does not match its frozen approved HGNC symbol"
                )


def _paired_families(
    point: LongitudinalPhosphoTimePoint,
    following: LongitudinalPhosphoTimePoint,
    *,
    cancellation: CancellationContext | None,
) -> tuple[dict[int, _FamilyValue], int, int]:
    catalog = load_kinase_transition_catalog()
    base = load_phosphosite_transition_catalog()
    left = {item.phosphosite_id: item for item in point.observations}
    right = {item.phosphosite_id: item for item in following.observations}
    exact: dict[int, _FamilyValue] = {}
    exact_row_count = 0
    censored_family_count = 0
    for offset, family in enumerate(catalog.families):
        if offset % 64 == 0:
            checkpoint(cancellation)
        rows: list[_ExactRow] = []
        saw_censored = False
        for phosphosite_id in family.source_phosphosite_ids:
            before = left.get(phosphosite_id)
            after = right.get(phosphosite_id)
            if before is None or after is None:
                continue
            active = {
                PhosphositeEvidenceState.OBSERVED,
                PhosphositeEvidenceState.LEFT_CENSORED,
            }
            if before.state not in active or after.state not in active:
                continue
            if (
                before.state is PhosphositeEvidenceState.LEFT_CENSORED
                or after.state is PhosphositeEvidenceState.LEFT_CENSORED
            ):
                saw_censored = True
                continue
            before_value = cast("float", before.log_abundance_ratio)
            after_value = cast("float", after.log_abundance_ratio)
            before_se = cast("float", before.standard_error)
            after_se = cast("float", after.standard_error)
            reliability = math.sqrt(before.quality_weight * after.quality_weight)
            rows.append(
                _ExactRow(
                    feature=base.feature_by_id[phosphosite_id],
                    from_observation=before,
                    to_observation=after,
                    delta=after_value - before_value,
                    noise_standard_error=(
                        math.hypot(before_se, after_se) / max(reliability, 1.0e-6)
                    ),
                    reliability=reliability,
                )
            )
        if rows:
            exact[family.family_index] = _FamilyValue(
                family=family,
                rows=tuple(rows),
                delta=float(np.median([row.delta for row in rows])),
            )
            exact_row_count += len(rows)
        elif saw_censored:
            censored_family_count += 1
    return exact, exact_row_count, censored_family_count


def _score(
    values: dict[int, _FamilyValue],
    projections: tuple[KinaseProjection, ...],
    scale_by_family: dict[int, float],
    catalog: KinaseTransitionCatalog,
    *,
    perturbed: dict[int, float] | None = None,
    omit_composites: bool = False,
    inverse_multiplicity: bool = True,
) -> _ScoreBundle:
    standardized = {
        index: (perturbed[index] if perturbed is not None else item.delta) / scale_by_family[index]
        for index, item in values.items()
        if index in scale_by_family
        and (not omit_composites or not item.family.contains_composite_source_group)
    }
    ranks = _stratified_ranks(standardized, catalog)
    multiplicity = Counter(
        index for projection in projections for index in projection.family_indices
    )
    kinase_scores: dict[str, _KinaseScore] = {}
    by_subtype: dict[str, list[float]] = defaultdict(list)
    for projection in projections:
        observed = tuple(index for index in projection.family_indices if index in ranks)
        if len(observed) < CONSTANTS.minimum_kinase_families:
            continue
        source_weights = dict(zip(projection.family_indices, projection.weights, strict=True))
        adjusted = {
            index: source_weights[index] / (multiplicity[index] if inverse_multiplicity else 1)
            for index in projection.family_indices
        }
        full_weight = sum(adjusted.values())
        observed_weight = sum(adjusted[index] for index in observed)
        coverage = observed_weight / full_weight
        if coverage < CONSTANTS.minimum_source_weight_coverage:
            continue
        direction = 1.0 if projection.direction == "source_recurrence_aligned" else -1.0
        contributions = {
            index: direction * adjusted[index] * ranks[index] / observed_weight
            for index in observed
        }
        score = sum(contributions.values())
        kinase_scores[projection.kinase] = _KinaseScore(
            score=score,
            coverage=coverage,
            observed_indices=observed,
            ranks={index: ranks[index] for index in observed},
            adjusted_weights={index: adjusted[index] for index in observed},
            contributions=contributions,
            multiplicity={index: multiplicity[index] for index in observed},
        )
        by_subtype[projection.subtype].append(score)
    subtype_scores = {
        subtype: float(np.mean(scores)) for subtype, scores in by_subtype.items() if scores
    }
    required_subtypes = {item.subtype for item in projections}
    consensus = (
        float(np.mean(list(subtype_scores.values())))
        if required_subtypes and set(subtype_scores) == required_subtypes
        else None
    )
    equal_kinase = (
        float(np.mean([item.score for item in kinase_scores.values()])) if kinase_scores else None
    )
    return _ScoreBundle(
        consensus=consensus,
        equal_kinase=equal_kinase,
        kinases=kinase_scores,
        subtypes=subtype_scores,
    )


def _perturb(
    values: dict[int, _FamilyValue],
    rng: np.random.Generator,
    cancellation: CancellationContext | None,
) -> dict[int, float]:
    output: dict[int, float] = {}
    for offset, (index, family) in enumerate(sorted(values.items())):
        if offset % 32 == 0:
            checkpoint(cancellation)
        draws = [
            row.delta + float(rng.normal(0.0, row.noise_standard_error)) for row in family.rows
        ]
        output[index] = float(np.median(draws))
    return output


def _seed(*parts: object) -> int:
    digest = hashlib.sha256(canonical_json_bytes(parts)).digest()
    return int.from_bytes(digest[:8], "big")


def _classify_interval(lower: float, upper: float) -> TransitionClassification:
    threshold = CONSTANTS.alignment_threshold
    if lower > threshold:
        return TransitionClassification.SOURCE_RECURRENCE_ALIGNED
    if upper < -threshold:
        return TransitionClassification.REVERSE_ALIGNED
    if lower >= -threshold and upper <= threshold:
        return TransitionClassification.STABLE
    return TransitionClassification.INDETERMINATE


def _classify_point(score: float) -> TransitionClassification:
    threshold = CONSTANTS.alignment_threshold
    if score > threshold:
        return TransitionClassification.SOURCE_RECURRENCE_ALIGNED
    if score < -threshold:
        return TransitionClassification.REVERSE_ALIGNED
    return TransitionClassification.STABLE


def _interval(draws: list[float], point: float) -> BootstrapInterval:
    if len(draws) < MIN_BOOTSTRAPS:
        return BootstrapInterval(
            state=BootstrapState.NOT_ESTIMABLE,
            reason="fewer than 32 estimable patient-bootstrap projections",
        )
    values = np.asarray(draws, dtype=np.float64)
    lower = min(point, float(np.quantile(values, 0.05)))
    upper = max(point, float(np.quantile(values, 0.95)))
    return BootstrapInterval(
        state=BootstrapState.ESTIMATED,
        lower_bound=_q(lower),
        upper_bound=_q(upper),
        standard_error=_q(float(np.std(values, ddof=1))),
        bootstrap_replicates_used=len(draws),
    )


def _not_estimable(reason: str) -> BootstrapInterval:
    return BootstrapInterval(state=BootstrapState.NOT_ESTIMABLE, reason=reason)


def _drivers(
    score: _KinaseScore,
    values: dict[int, _FamilyValue],
) -> tuple[SignatureFamilyDriver, ...]:
    output: list[SignatureFamilyDriver] = []
    for index in score.observed_indices:
        family_value = values[index]
        rows = family_value.rows
        output.append(
            SignatureFamilyDriver(
                source_site_label=family_value.family.source_site_label,
                source_phosphosite_ids=family_value.family.source_phosphosite_ids,
                stratum=family_value.family.stratum,
                contains_composite_source_group=(
                    family_value.family.contains_composite_source_group
                ),
                standardized_rank=_q(score.ranks[index]),
                inverse_multiplicity=_q(1.0 / score.multiplicity[index]),
                adjusted_source_weight=_q(score.adjusted_weights[index]),
                signed_contribution=_q(score.contributions[index]),
                paired_source_support=family_value.family.paired_support,
                paired_observation_ids=tuple(
                    identifier
                    for row in rows
                    for identifier in (
                        row.from_observation.observation_id,
                        row.to_observation.observation_id,
                    )
                ),
                observation_provenance_digests=tuple(
                    digest
                    for row in rows
                    for digest in (
                        row.from_observation.provenance_digest,
                        row.to_observation.provenance_digest,
                    )
                ),
            )
        )
    output.sort(key=lambda item: (-abs(item.signed_contribution), item.source_site_label))
    return tuple(output[: CONSTANTS.maximum_top_drivers])


def _ablation(
    name: Literal[
        "equal_kinase_instead_of_equal_subtype",
        "omit_composite_source_groups",
        "omit_inverse_multiplicity_correction",
    ],
    point: float,
    score: float | None,
) -> SignatureAblation:
    if score is None:
        return SignatureAblation(
            ablation=name,
            support=AnalysisSupport.ABSTAINED,
            classification=TransitionClassification.NOT_ESTIMABLE,
            reason="ablation lacks enough mapped signature-family support",
        )
    return SignatureAblation(
        ablation=name,
        support=AnalysisSupport.LIMITED,
        score=_q(score),
        score_delta=_q(score - point),
        classification=_classify_point(score),
        reason=_LIMITED_REASON,
    )


def _abstained_kinase(
    hypothesis: KinaseHypothesis,
    selection_state: KinaseSelectionState,
    direction: SignatureDirection,
    reason: str,
) -> KinaseSignatureEvidence:
    return KinaseSignatureEvidence(
        kinase=hypothesis.kinase,
        subtype=cast("Literal['GPM', 'MTC', 'NEU', 'PPR']", hypothesis.subtype),
        selection_state=selection_state,
        support=AnalysisSupport.ABSTAINED,
        source_direction=direction,
        source_enrichment=hypothesis.enrichment,
        source_p_value=hypothesis.p_value,
        source_q_value=hypothesis.q_value,
        mapped_source_family_count=hypothesis.mapped_eligible_families,
        observed_family_count=0,
        source_weight_coverage=0.0,
        outer_selection_frequency=hypothesis.outer_selection_frequency,
        bootstrap_selection_frequency=hypothesis.bootstrap_selection_frequency,
        bootstrap_direction_consistency=hypothesis.bootstrap_direction_consistency,
        classification=TransitionClassification.NOT_ESTIMABLE,
        uncertainty=_not_estimable(reason),
        reasons=(reason,),
    )


def _selection_state(hypothesis: KinaseHypothesis) -> KinaseSelectionState:
    if not hypothesis.selected:
        return KinaseSelectionState.NOT_SELECTED
    if hypothesis.bootstrap_selection_frequency >= CONSTANTS.core_stability_threshold:
        return KinaseSelectionState.SELECTED_CORE
    return KinaseSelectionState.SELECTED_UNSTABLE


def _source_direction(
    hypothesis: KinaseHypothesis,
    catalog: KinaseTransitionCatalog,
) -> SignatureDirection:
    projection = next(
        (item for item in catalog.selected_kinases if item.kinase == hypothesis.kinase),
        None,
    )
    return (
        SignatureDirection(projection.direction)
        if projection is not None
        else SignatureDirection.NOT_ESTABLISHED
    )


def _transition(  # noqa: PLR0915
    request: LongitudinalGbmKinaseTransitionRequest,
    index: int,
    *,
    numerical_digest: str,
    cancellation: CancellationContext | None,
) -> TransitionEvidence:
    catalog = load_kinase_transition_catalog()
    point = request.time_points[index]
    following = request.time_points[index + 1]
    values, exact_rows, censored = _paired_families(point, following, cancellation=cancellation)
    full_scales = {item.family_index: item.transition_scale for item in catalog.families}
    main = _score(
        values,
        catalog.selected_kinases,
        full_scales,
        catalog,
    )
    if main.consensus is None:
        reason = "every source-selected SPHINKS subtype family requires mapped observations"
        kinases = tuple(
            sorted(
                (
                    _abstained_kinase(
                        hypothesis,
                        _selection_state(hypothesis),
                        _source_direction(hypothesis, catalog),
                        reason,
                    )
                    for hypothesis in catalog.hypotheses
                ),
                key=lambda item: item.kinase,
            )
        )
        abstained_subtypes = tuple(
            SubtypeSignatureEvidence(
                subtype=subtype,
                selected_kinase_count=sum(
                    item.subtype == subtype for item in catalog.selected_kinases
                ),
                estimable_kinase_count=0,
                support=AnalysisSupport.ABSTAINED,
                classification=TransitionClassification.NOT_ESTIMABLE,
                uncertainty=_not_estimable(reason),
                reasons=(reason,),
            )
            for subtype in ("GPM", "MTC", "NEU", "PPR")
        )
        ablations = tuple(
            _ablation(name, 0.0, None)
            for name in (
                "equal_kinase_instead_of_equal_subtype",
                "omit_composite_source_groups",
                "omit_inverse_multiplicity_correction",
            )
        )
        return TransitionEvidence(
            transition_id=f"transition-{index}",
            transition_index=index,
            from_time_point_id=point.time_point_id,
            to_time_point_id=following.time_point_id,
            support=AnalysisSupport.ABSTAINED,
            classification=TransitionClassification.NOT_ESTIMABLE,
            uncertainty=_not_estimable(reason),
            exact_source_row_count=exact_rows,
            exact_family_count=len(values),
            censored_family_count=censored,
            selected_kinase_count=len(catalog.selected_kinases),
            estimable_kinase_count=len(main.kinases),
            kinase_signatures=kinases,
            subtype_signatures=abstained_subtypes,
            ablations=cast(
                "tuple[SignatureAblation, SignatureAblation, SignatureAblation]", ablations
            ),
            reasons=(reason,),
        )

    ordered = sorted(
        catalog.bootstrap_projections,
        key=lambda item: sha256_digest(
            {"request": numerical_digest, "replicate": item.replicate_digest}
        ),
    )[: request.bootstrap_replicates]
    overall_draws: list[float] = []
    kinase_draws: dict[str, list[float]] = defaultdict(list)
    subtype_draws: dict[str, list[float]] = defaultdict(list)
    point_selected = {item.kinase for item in catalog.selected_kinases}
    for bootstrap_model in ordered:
        checkpoint(cancellation)
        rng = np.random.default_rng(
            _seed(numerical_digest, index, bootstrap_model.replicate_digest)
        )
        perturbed = _perturb(values, rng, cancellation)
        combined = _score(
            values,
            bootstrap_model.kinases,
            bootstrap_model.scale_by_family,
            catalog,
            perturbed=perturbed,
        )
        if combined.consensus is not None:
            overall_draws.append(combined.consensus)
        for symbol in point_selected:
            if symbol not in {item.kinase for item in bootstrap_model.kinases}:
                kinase_draws[symbol].append(0.0)
            elif symbol in combined.kinases:
                kinase_draws[symbol].append(combined.kinases[symbol].score)
        for subtype in {item.subtype for item in catalog.selected_kinases}:
            subtype_draws[subtype].append(combined.subtypes.get(subtype, 0.0))

    overall_interval = _interval(overall_draws, main.consensus)
    if overall_interval.state is BootstrapState.NOT_ESTIMABLE:
        reason = cast("str", overall_interval.reason)
        return TransitionEvidence(
            transition_id=f"transition-{index}",
            transition_index=index,
            from_time_point_id=point.time_point_id,
            to_time_point_id=following.time_point_id,
            support=AnalysisSupport.ABSTAINED,
            classification=TransitionClassification.NOT_ESTIMABLE,
            uncertainty=overall_interval,
            exact_source_row_count=exact_rows,
            exact_family_count=len(values),
            censored_family_count=censored,
            selected_kinase_count=len(catalog.selected_kinases),
            estimable_kinase_count=len(main.kinases),
            kinase_signatures=tuple(
                sorted(
                    (
                        _abstained_kinase(
                            item,
                            _selection_state(item),
                            _source_direction(item, catalog),
                            reason,
                        )
                        for item in catalog.hypotheses
                    ),
                    key=lambda item: item.kinase,
                )
            ),
            subtype_signatures=tuple(
                SubtypeSignatureEvidence(
                    subtype=subtype,
                    selected_kinase_count=sum(
                        item.subtype == subtype for item in catalog.selected_kinases
                    ),
                    estimable_kinase_count=0,
                    support=AnalysisSupport.ABSTAINED,
                    classification=TransitionClassification.NOT_ESTIMABLE,
                    uncertainty=_not_estimable(reason),
                    reasons=(reason,),
                )
                for subtype in ("GPM", "MTC", "NEU", "PPR")
            ),
            ablations=cast(
                "tuple[SignatureAblation, SignatureAblation, SignatureAblation]",
                tuple(
                    _ablation(name, main.consensus, None)
                    for name in (
                        "equal_kinase_instead_of_equal_subtype",
                        "omit_composite_source_groups",
                        "omit_inverse_multiplicity_correction",
                    )
                ),
            ),
            reasons=(reason,),
        )

    selected_projection = {item.kinase: item for item in catalog.selected_kinases}
    kinase_evidence: list[KinaseSignatureEvidence] = []
    for hypothesis in catalog.hypotheses:
        selected_model = selected_projection.get(hypothesis.kinase)
        if selected_model is None:
            kinase_evidence.append(
                _abstained_kinase(
                    hypothesis,
                    KinaseSelectionState.NOT_SELECTED,
                    SignatureDirection.NOT_ESTABLISHED,
                    "not selected by the fixed 24-hypothesis source-cohort BH procedure",
                )
            )
            continue
        selection_state = _selection_state(hypothesis)
        source_direction = SignatureDirection(selected_model.direction)
        point_score = main.kinases.get(hypothesis.kinase)
        if point_score is None:
            kinase_evidence.append(
                _abstained_kinase(
                    hypothesis,
                    selection_state,
                    source_direction,
                    "fewer than three observed mapped families or less than 25% source weight coverage",
                )
            )
            continue
        uncertainty = _interval(kinase_draws[hypothesis.kinase], point_score.score)
        if uncertainty.state is BootstrapState.NOT_ESTIMABLE:
            kinase_evidence.append(
                _abstained_kinase(
                    hypothesis,
                    selection_state,
                    source_direction,
                    cast("str", uncertainty.reason),
                )
            )
            continue
        lower = cast("float", uncertainty.lower_bound)
        upper = cast("float", uncertainty.upper_bound)
        reasons = [_LIMITED_REASON, _CALIBRATION_REASON]
        if selection_state is KinaseSelectionState.SELECTED_UNSTABLE:
            reasons.append(
                "bootstrap selection frequency is below the frozen 0.80 core-stability threshold"
            )
        kinase_evidence.append(
            KinaseSignatureEvidence(
                kinase=hypothesis.kinase,
                subtype=cast("Literal['GPM', 'MTC', 'NEU', 'PPR']", hypothesis.subtype),
                selection_state=selection_state,
                support=AnalysisSupport.LIMITED,
                source_direction=source_direction,
                source_enrichment=hypothesis.enrichment,
                source_p_value=hypothesis.p_value,
                source_q_value=hypothesis.q_value,
                mapped_source_family_count=hypothesis.mapped_eligible_families,
                observed_family_count=len(point_score.observed_indices),
                source_weight_coverage=_q(point_score.coverage),
                outer_selection_frequency=hypothesis.outer_selection_frequency,
                bootstrap_selection_frequency=hypothesis.bootstrap_selection_frequency,
                bootstrap_direction_consistency=hypothesis.bootstrap_direction_consistency,
                score=_q(point_score.score),
                classification=_classify_interval(lower, upper),
                uncertainty=uncertainty,
                top_family_drivers=_drivers(point_score, values),
                reasons=tuple(reasons),
            )
        )
    kinase_evidence.sort(key=lambda item: item.kinase)

    subtype_evidence: list[SubtypeSignatureEvidence] = []
    for subtype in ("GPM", "MTC", "NEU", "PPR"):
        selected_count = sum(item.subtype == subtype for item in catalog.selected_kinases)
        estimable_count = sum(
            item.subtype == subtype and item.kinase in main.kinases
            for item in catalog.selected_kinases
        )
        subtype_score = main.subtypes.get(subtype)
        if selected_count == 0:
            reason = "no kinase in this subtype passed the fixed source-cohort BH procedure"
            subtype_evidence.append(
                SubtypeSignatureEvidence(
                    subtype=cast("Literal['GPM', 'MTC', 'NEU', 'PPR']", subtype),
                    selected_kinase_count=0,
                    estimable_kinase_count=0,
                    support=AnalysisSupport.ABSTAINED,
                    classification=TransitionClassification.NOT_ESTIMABLE,
                    uncertainty=_not_estimable(reason),
                    reasons=(reason,),
                )
            )
            continue
        if subtype_score is None:
            reason = "selected subtype lacks enough mapped runtime families"
            subtype_evidence.append(
                SubtypeSignatureEvidence(
                    subtype=cast("Literal['GPM', 'MTC', 'NEU', 'PPR']", subtype),
                    selected_kinase_count=selected_count,
                    estimable_kinase_count=estimable_count,
                    support=AnalysisSupport.ABSTAINED,
                    classification=TransitionClassification.NOT_ESTIMABLE,
                    uncertainty=_not_estimable(reason),
                    reasons=(reason,),
                )
            )
            continue
        uncertainty = _interval(subtype_draws[subtype], subtype_score)
        if uncertainty.state is BootstrapState.NOT_ESTIMABLE:
            reason = cast("str", uncertainty.reason)
            subtype_evidence.append(
                SubtypeSignatureEvidence(
                    subtype=cast("Literal['GPM', 'MTC', 'NEU', 'PPR']", subtype),
                    selected_kinase_count=selected_count,
                    estimable_kinase_count=estimable_count,
                    support=AnalysisSupport.ABSTAINED,
                    classification=TransitionClassification.NOT_ESTIMABLE,
                    uncertainty=uncertainty,
                    reasons=(reason,),
                )
            )
            continue
        subtype_evidence.append(
            SubtypeSignatureEvidence(
                subtype=cast("Literal['GPM', 'MTC', 'NEU', 'PPR']", subtype),
                selected_kinase_count=selected_count,
                estimable_kinase_count=estimable_count,
                support=AnalysisSupport.LIMITED,
                score=_q(subtype_score),
                classification=_classify_interval(
                    cast("float", uncertainty.lower_bound),
                    cast("float", uncertainty.upper_bound),
                ),
                uncertainty=uncertainty,
                reasons=(_LIMITED_REASON, _CALIBRATION_REASON),
            )
        )

    omit_composite = _score(
        values,
        catalog.selected_kinases,
        full_scales,
        catalog,
        omit_composites=True,
    )
    no_inverse = _score(
        values,
        catalog.selected_kinases,
        full_scales,
        catalog,
        inverse_multiplicity=False,
    )
    ablations = (
        _ablation(
            "equal_kinase_instead_of_equal_subtype",
            main.consensus,
            main.equal_kinase,
        ),
        _ablation(
            "omit_composite_source_groups",
            main.consensus,
            omit_composite.consensus,
        ),
        _ablation(
            "omit_inverse_multiplicity_correction",
            main.consensus,
            no_inverse.consensus,
        ),
    )
    return TransitionEvidence(
        transition_id=f"transition-{index}",
        transition_index=index,
        from_time_point_id=point.time_point_id,
        to_time_point_id=following.time_point_id,
        support=AnalysisSupport.LIMITED,
        score=_q(main.consensus),
        classification=_classify_interval(
            cast("float", overall_interval.lower_bound),
            cast("float", overall_interval.upper_bound),
        ),
        uncertainty=overall_interval,
        exact_source_row_count=exact_rows,
        exact_family_count=len(values),
        censored_family_count=censored,
        selected_kinase_count=len(catalog.selected_kinases),
        estimable_kinase_count=len(main.kinases),
        kinase_signatures=tuple(kinase_evidence),
        subtype_signatures=tuple(subtype_evidence),
        ablations=ablations,
        reasons=(_LIMITED_REASON, _CALIBRATION_REASON),
    )


def infer_longitudinal_gbm_kinase_transition(
    request: LongitudinalGbmKinaseTransitionRequest,
    *,
    cancellation: CancellationContext | None = None,
) -> LongitudinalGbmKinaseTransitionResult:
    """Apply the source-fitted signature-transition model without retaining evidence."""

    checkpoint(cancellation)
    if request.assay_compatibility != REQUIRED_ASSAY_COMPATIBILITY:
        raise ValueError("request assay compatibility does not match PDC000515")
    _validate_identities(request)
    profile = algorithm_profile()
    catalog = load_kinase_transition_catalog()
    request_digest = canonical_request_digest(request)
    computational_digest = computational_request_digest(
        request, profile_digest=profile.profile_digest
    )
    numerical_digest = sha256_digest(
        {
            "computational_digest": computational_digest,
            "artifact": catalog.artifact_digest,
            "bootstrap": catalog.bootstrap_digest,
        }
    )
    transitions = tuple(
        _transition(
            request,
            index,
            numerical_digest=numerical_digest,
            cancellation=cancellation,
        )
        for index in range(len(request.time_points) - 1)
    )
    provenance_digests = tuple(
        sorted(
            {item.provenance_digest for point in request.time_points for item in point.observations}
        )
    )
    source = SourceProvenance(
        pdc_article_attribution=catalog.pdc_attribution,
        pdc_license="CC-BY-4.0",
        pdc_license_url="https://creativecommons.org/licenses/by/4.0/",
        pdc_transformation_notice=catalog.pdc_transformation_notice,
        sphinks_article_attribution=catalog.sphinks_attribution,
        sphinks_license="CC-BY-4.0",
        sphinks_license_url="https://creativecommons.org/licenses/by/4.0/",
        sphinks_transformation_notice=catalog.sphinks_transformation_notice,
    )
    provenance = ResultProvenance(
        request_digest=request_digest,
        profile_digest=profile.profile_digest,
        fitted_artifact_content_digest=catalog.artifact_digest,
        fitted_artifact_byte_digest=catalog.artifact_sha256,
        bootstrap_ensemble_digest=catalog.bootstrap_digest,
        engine_semantic_digest=profile.digests.engine_semantic_digest,
        assay_compatibility_digest=sha256_digest(
            request.assay_compatibility.model_dump(mode="json")
        ),
        normalization_reference_digest=request.normalization_reference.binding_digest,
        computational_digest=computational_digest,
        numerical_seed_digest=numerical_digest,
        observation_source_digests=provenance_digests,
        source_attestation_state="verified_exact_snapshots",
        source_provenance=source,
        numpy_version=np.__version__,
    )
    payload: dict[str, object] = {
        "algorithm_id": "kncc-gbm-longitudinal-kinase-transition",
        "algorithm_version": "1.0.0",
        "profile_id": "kncc-gbm-longitudinal-kinase-transition/1.0.0",
        "profile_digest": profile.profile_digest,
        "request_digest": request_digest,
        "series_id": request.series_id,
        "assay_compatibility": request.assay_compatibility.model_dump(mode="json"),
        "normalization_reference": request.normalization_reference.model_dump(mode="json"),
        "time_point_ids": [item.time_point_id for item in request.time_points],
        "transitions": [item.model_dump(mode="json") for item in transitions],
        "provenance": provenance.model_dump(mode="json"),
        "output_semantics": "SPHINKS_signature_transition_concordance_only",
        "limitations": [
            "Research use only; not diagnostic, prognostic, prescriptive, or clinically validated.",
            "The result is same-assay PDC000515 signature-transition concordance, not independent evidence.",
            "Kinase labels index SPHINKS signatures; no biochemical activity or causal regulation is inferred.",
            "Held-pair evaluation is internal source-cohort concordance, not external validation.",
            "Composite source site groups remain indivisible; independent residue localization is not inferred.",
            "Missing and unsupported values are ignored and never converted to negative evidence.",
            "Left-censored evidence is counted but excluded from point scores rather than imputed.",
            _COVARIANCE_LIMITATION,
            "Patient-bootstrap full-set stability and interval calibration gates remain unpassed.",
        ],
        "research_use_only": True,
        "non_prescriptive": True,
        "infers_kinase_activity": False,
        "infers_biochemical_activity": False,
        "makes_causal_claim": False,
        "independent_evidence": False,
    }
    payload["result_digest"] = result_payload_digest(payload)
    checkpoint(cancellation)
    return LongitudinalGbmKinaseTransitionResult.model_validate_json(canonical_json_bytes(payload))


__all__ = ["infer_longitudinal_gbm_kinase_transition"]
