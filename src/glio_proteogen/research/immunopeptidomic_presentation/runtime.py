"""Caller-owned, allele-aware glioma immunopeptidomic presentation runtime.

The repository does not redistribute NetMHC/processing weights.  Instead this
lane accepts an explicitly digest-bound caller model containing position weight
matrices and processing coefficients, then executes the complete deterministic
scoring, uncertainty, ablation, and replay path.  It is therefore useful for a
licensed local model package while remaining fail-closed for unsupported HLA
alleles and insufficient evidence.
"""

from __future__ import annotations

import math
import re
from typing import Final, Literal, Self

import numpy as np
from pydantic import Field, model_validator

from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import FrozenModel, Identifier, NonEmptyStr, Sha256Digest

PRESENTATION_ALGORITHM_ID: Final = "glioma-immunopeptidomic-presentation"
PRESENTATION_ALGORITHM_VERSION: Final = "0.1.0"
PRESENTATION_PROFILE_ID: Final = (
    f"{PRESENTATION_ALGORITHM_ID}/{PRESENTATION_ALGORITHM_VERSION}"
)
EXPECTED_NUMPY_VERSION: Final = "2.5.2"
AMINO_ACIDS: Final = "ACDEFGHIKLMNPQRSTVWY"
MIN_PEPTIDE_LENGTH: Final = 8
MAX_PEPTIDE_LENGTH: Final = 14
MAX_PEPTIDES: Final = 256
MAX_ALLELES: Final = 16
MAX_BOOTSTRAP_REPLICATES: Final = 256
DEFAULT_BOOTSTRAP_REPLICATES: Final = 64
MAX_REQUEST_BYTES: Final = 2 * 1_024 * 1_024
MAX_RESULT_BYTES: Final = 4 * 1_024 * 1_024
_HLA_PATTERN: Final = re.compile(r"^HLA-[A-Z0-9]+\*[0-9]{2,3}:[0-9]{2,3}$")
_ZERO_DIGEST: Final = "sha256:" + "0" * 64
_PROBABILITY_EPSILON: Final = 1e-12


class ImmunopeptidomicInputError(ValueError):
    """Raised when caller-owned peptide/model evidence cannot be evaluated."""


class PositionWeightMatrix(FrozenModel):
    """Flattened amino-acid log-odds matrix for one peptide length."""

    peptide_length: int = Field(ge=MIN_PEPTIDE_LENGTH, le=MAX_PEPTIDE_LENGTH)
    values: tuple[float, ...] = Field(min_length=MIN_PEPTIDE_LENGTH * 20, max_length=MAX_PEPTIDE_LENGTH * 20)

    @model_validator(mode="after")
    def matrix_is_finite_and_rectangular(self) -> Self:
        if len(self.values) != self.peptide_length * len(AMINO_ACIDS):
            raise ValueError("position matrix must have length * 20 entries")
        if any(not math.isfinite(value) or abs(value) > 50.0 for value in self.values):
            raise ValueError("position matrix values must be finite and bounded")
        return self


class HlaPresentationModel(FrozenModel):
    """A caller-supplied, digest-bound allele model; no weights are bundled."""

    allele: NonEmptyStr
    matrices: tuple[PositionWeightMatrix, ...] = Field(min_length=1, max_length=7)
    processing_weights: tuple[float, ...] = Field(min_length=20, max_length=20)
    intercept: float = Field(ge=-50.0, le=50.0)
    binding_scale: float = Field(ge=0.0, le=20.0)
    processing_scale: float = Field(ge=0.0, le=20.0)
    expression_scale: float = Field(ge=0.0, le=20.0)
    variant_scale: float = Field(ge=0.0, le=20.0)
    temperature: float = Field(gt=0.01, le=20.0)
    source_digest: Sha256Digest
    model_digest: Sha256Digest

    @model_validator(mode="after")
    def model_is_closed(self) -> Self:
        if not _HLA_PATTERN.fullmatch(self.allele):
            raise ValueError("allele must use canonical HLA-*NN:NN notation")
        if any(not math.isfinite(value) or abs(value) > 50.0 for value in self.processing_weights):
            raise ValueError("processing weights must be finite and bounded")
        lengths = [matrix.peptide_length for matrix in self.matrices]
        if len(set(lengths)) != len(lengths):
            raise ValueError("one position matrix per peptide length is required")
        if self.model_digest != model_digest(self):
            raise ValueError("model digest does not match caller-supplied coefficients")
        return self


class PeptideObservation(FrozenModel):
    """A peptide candidate and optional RNA/protein evidence state."""

    peptide_id: Identifier
    sequence: NonEmptyStr
    source_gene: Identifier
    variant_present: bool = False
    state: Literal["observed", "left_censored", "missing", "unsupported"] = "observed"
    expression_effect: float | None = None
    expression_standard_error: float | None = Field(default=None, gt=0.0, le=100.0)
    detection_limit: float | None = None
    quality_weight: float = Field(default=1.0, gt=0.0, le=1.0)

    @model_validator(mode="after")
    def evidence_is_explicit(self) -> Self:
        sequence = self.sequence.upper()
        if sequence != self.sequence or not MIN_PEPTIDE_LENGTH <= len(sequence) <= MAX_PEPTIDE_LENGTH:
            raise ValueError("peptide sequence must be uppercase and 8-14 residues")
        if any(residue not in AMINO_ACIDS for residue in sequence):
            raise ValueError("peptide sequence contains an unsupported amino acid")
        numeric = (self.expression_effect, self.expression_standard_error, self.detection_limit)
        if any(value is not None and not math.isfinite(value) for value in numeric):
            raise ValueError("expression evidence must be finite")
        if self.state == "observed":
            if self.detection_limit is not None:
                raise ValueError("observed evidence cannot carry a detection limit")
        elif self.state == "left_censored":
            if self.detection_limit is None or self.expression_effect is not None:
                raise ValueError("left-censored evidence requires only a detection limit")
        elif self.expression_effect is not None or self.expression_standard_error is not None or self.detection_limit is not None:
            raise ValueError("missing or unsupported evidence cannot carry numeric values")
        return self


class ImmunopeptidomicPresentationRequest(FrozenModel):
    """Strict stateless request for allele-aware glioma peptide scoring."""

    profile_id: Literal["glioma-immunopeptidomic-presentation/0.1.0"] = "glioma-immunopeptidomic-presentation/0.1.0"
    sample_id: Identifier
    hla_alleles: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=MAX_ALLELES)
    peptides: tuple[PeptideObservation, ...] = Field(min_length=1, max_length=MAX_PEPTIDES)
    models: tuple[HlaPresentationModel, ...] = Field(min_length=1, max_length=MAX_ALLELES)
    bootstrap_replicates: int = Field(default=DEFAULT_BOOTSTRAP_REPLICATES, ge=0, le=MAX_BOOTSTRAP_REPLICATES)
    source_digests: tuple[Sha256Digest, ...] = Field(min_length=1, max_length=32)
    provenance_note: NonEmptyStr

    @model_validator(mode="after")
    def request_is_closed(self) -> Self:
        if len(set(self.hla_alleles)) != len(self.hla_alleles):
            raise ValueError("HLA alleles must be unique")
        if any(not _HLA_PATTERN.fullmatch(allele) for allele in self.hla_alleles):
            raise ValueError("HLA alleles must use canonical HLA-*NN:NN notation")
        peptide_ids = [item.peptide_id for item in self.peptides]
        if len(set(peptide_ids)) != len(peptide_ids):
            raise ValueError("peptide identifiers must be unique")
        model_alleles = [item.allele for item in self.models]
        if len(set(model_alleles)) != len(model_alleles):
            raise ValueError("model alleles must be unique")
        if any(allele not in self.hla_alleles for allele in model_alleles):
            raise ValueError("a model cannot be supplied for an unrequested allele")
        return self

    @property
    def request_digest(self) -> Sha256Digest:
        return request_digest(self)


class HlaScore(FrozenModel):
    allele: NonEmptyStr
    binding_score: float
    processing_score: float
    expression_contribution: float
    variant_contribution: float
    logit: float
    probability: float = Field(ge=0.0, le=1.0)


class AblationEffect(FrozenModel):
    component: Literal["binding", "processing", "expression", "variant"]
    probability_delta: float


class PeptidePresentation(FrozenModel):
    peptide_id: Identifier
    sequence: NonEmptyStr
    source_gene: Identifier
    support: Literal["supported", "unsupported"]
    supported_alleles: tuple[HlaScore, ...] = Field(default=(), max_length=MAX_ALLELES)
    binding_score: float | None = None
    processing_score: float | None = None
    expression_contribution: float | None = None
    presentation_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    interval_low: float | None = Field(default=None, ge=0.0, le=1.0)
    interval_high: float | None = Field(default=None, ge=0.0, le=1.0)
    rank: int | None = Field(default=None, ge=1, le=MAX_PEPTIDES)
    top_drivers: tuple[NonEmptyStr, ...] = Field(default=(), max_length=8)
    ablations: tuple[AblationEffect, ...] = Field(default=(), max_length=4)
    abstention_reason: NonEmptyStr | None = None

    @model_validator(mode="after")
    def interval_is_ordered(self) -> Self:
        if self.support == "supported":
            if not self.supported_alleles or self.presentation_probability is None:
                raise ValueError("supported peptide requires allele scores and probability")
            if self.interval_low is None or self.interval_high is None:
                raise ValueError("supported peptide requires an uncertainty interval")
            if self.interval_low > self.interval_high:
                raise ValueError("presentation interval is reversed")
        elif self.presentation_probability is not None or self.supported_alleles:
            raise ValueError("unsupported peptide cannot carry scores")
        return self


class PresentationProfile(FrozenModel):
    profile_id: Literal["glioma-immunopeptidomic-presentation/0.1.0"] = "glioma-immunopeptidomic-presentation/0.1.0"
    algorithm_id: Literal["glioma-immunopeptidomic-presentation"] = PRESENTATION_ALGORITHM_ID
    algorithm_version: Literal["0.1.0"] = PRESENTATION_ALGORITHM_VERSION
    numpy_version: Literal["2.5.2"] = EXPECTED_NUMPY_VERSION
    execution_scope: Literal["caller_supplied_hla_model_only"] = "caller_supplied_hla_model_only"
    score_model: Literal["allele_pssm_processing_logit"] = "allele_pssm_processing_logit"
    binding_score_policy: Literal["position_log_odds_sum_v1"] = (
        "position_log_odds_sum_v1"
    )
    allele_aggregation_policy: Literal["independent_allele_noisy_or_v1"] = (
        "independent_allele_noisy_or_v1"
    )
    max_peptides: Literal[256] = MAX_PEPTIDES
    max_alleles: Literal[16] = MAX_ALLELES
    default_bootstrap_replicates: Literal[64] = DEFAULT_BOOTSTRAP_REPLICATES
    clinical_use_permitted: Literal[False] = False
    treatment_recommendation_permitted: Literal[False] = False
    profile_digest: Sha256Digest

    @model_validator(mode="after")
    def digest_is_bound(self) -> Self:
        if self.profile_digest != profile_digest(self):
            raise ValueError("presentation profile digest does not match constants")
        return self


class ImmunopeptidomicPresentationResult(FrozenModel):
    result_id: Identifier
    profile_id: Literal["glioma-immunopeptidomic-presentation/0.1.0"] = "glioma-immunopeptidomic-presentation/0.1.0"
    profile_digest: Sha256Digest
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    sample_id: Identifier
    support: Literal["supported", "limited", "abstained"]
    candidates: tuple[PeptidePresentation, ...] = Field(max_length=MAX_PEPTIDES)
    supported_peptide_count: int = Field(ge=0, le=MAX_PEPTIDES)
    supported_allele_count: int = Field(ge=0, le=MAX_ALLELES)
    model_digests: tuple[Sha256Digest, ...] = Field(min_length=1, max_length=MAX_ALLELES)
    bootstrap_replicates: int = Field(ge=0, le=MAX_BOOTSTRAP_REPLICATES)
    abstention_reason: NonEmptyStr | None = None
    limitations: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def result_is_closed(self) -> Self:
        if self.support == "abstained" and self.abstention_reason is None:
            raise ValueError("abstained result requires a reason")
        if self.support != "abstained" and self.abstention_reason is not None:
            raise ValueError("supported result cannot carry an abstention reason")
        if self.supported_peptide_count != sum(item.support == "supported" for item in self.candidates):
            raise ValueError("supported peptide count does not match candidates")
        if self.supported_allele_count > len(self.model_digests):
            raise ValueError("supported allele count exceeds model count")
        return self


class PresentationReplayRequest(FrozenModel):
    """Transport envelope for exact result verification."""

    request: ImmunopeptidomicPresentationRequest
    result: ImmunopeptidomicPresentationResult


class PresentationReplayResult(FrozenModel):
    """Sanitized verification response for the HTTP/CLI boundary."""

    verified: Literal[True] = True
    request_digest: Sha256Digest
    result_digest: Sha256Digest


def _digest_payload(value: FrozenModel, field: str) -> dict[str, object]:
    payload = value.model_dump(mode="json")
    payload[field] = _ZERO_DIGEST
    return payload


def model_digest(model: HlaPresentationModel) -> Sha256Digest:
    return sha256_digest(_digest_payload(model, "model_digest"))


def profile_digest(profile: PresentationProfile) -> Sha256Digest:
    return sha256_digest(_digest_payload(profile, "profile_digest"))


def request_digest(request: ImmunopeptidomicPresentationRequest) -> Sha256Digest:
    return sha256_digest(_canonical_request_payload(request))


def _canonical_request(request: ImmunopeptidomicPresentationRequest) -> ImmunopeptidomicPresentationRequest:
    """Normalize caller ordering before scoring or deriving a seed."""
    return request.model_copy(
        update={
            "hla_alleles": tuple(sorted(request.hla_alleles)),
            "peptides": tuple(sorted(request.peptides, key=lambda item: item.peptide_id)),
            "models": tuple(sorted(request.models, key=lambda item: item.allele)),
            "source_digests": tuple(sorted(request.source_digests)),
        }
    )


def _canonical_request_payload(request: ImmunopeptidomicPresentationRequest) -> dict[str, object]:
    return _canonical_request(request).model_dump(mode="json")


def result_digest(result: ImmunopeptidomicPresentationResult) -> Sha256Digest:
    return sha256_digest(_digest_payload(result, "result_digest"))


def _profile() -> PresentationProfile:
    draft = PresentationProfile.model_construct(profile_digest=_ZERO_DIGEST)
    return draft.model_copy(update={"profile_digest": profile_digest(draft)})


def presentation_profile() -> PresentationProfile:
    return _profile()


def _sigmoid(value: float) -> float:
    if value >= 0.0:
        z = math.exp(-min(value, 700.0))
        return 1.0 / (1.0 + z)
    z = math.exp(max(value, -700.0))
    return z / (1.0 + z)


def _noisy_or(probabilities: tuple[float, ...]) -> float:
    """Return the probability that at least one requested allele presents.

    Allele models are calibrated marginal probabilities.  Combining them as a
    geometric mean of logits (the historical implementation) can lower the
    result when one allele is strongly supportive and has no direct
    probability interpretation.  The noisy-OR is the explicit independence
    approximation for the union event and is monotone in every allele score.
    """

    if not probabilities:
        return 0.0
    complement = math.fsum(
        math.log1p(-min(max(float(probability), _PROBABILITY_EPSILON), 1.0 - _PROBABILITY_EPSILON))
        for probability in probabilities
    )
    return min(1.0 - math.exp(complement), 1.0)


def _aggregate_probabilities(logits: tuple[float, ...]) -> float:
    return _noisy_or(tuple(_sigmoid(logit) for logit in logits))


def _matrix_for(model: HlaPresentationModel, length: int) -> PositionWeightMatrix | None:
    return next((matrix for matrix in model.matrices if matrix.peptide_length == length), None)


def _score_allele(model: HlaPresentationModel, peptide: PeptideObservation, expression_shift: float | None = None) -> HlaScore | None:
    matrix = _matrix_for(model, len(peptide.sequence))
    if matrix is None:
        return None
    values = [AMINO_ACIDS.index(residue) for residue in peptide.sequence]
    # Matrix entries are position-specific log-odds.  Summing them is the
    # PSSM likelihood-ratio coordinate; dividing by peptide length would turn
    # a calibrated log-odds model into an arbitrary length-dependent shrinkage
    # proxy because each supported peptide length has its own matrix.
    binding = math.fsum(
        matrix.values[position * 20 + amino_acid]
        for position, amino_acid in enumerate(values)
    )
    processing = model.processing_weights[values[0]] + model.processing_weights[values[-1]]
    expression = 0.0
    if peptide.state == "observed" and peptide.expression_effect is not None:
        expression = peptide.expression_effect if expression_shift is None else expression_shift
    elif peptide.state == "left_censored" and peptide.detection_limit is not None:
        # A censoring limit is an upper bound: only evidence above the limit
        # contributes, never a fabricated negative observation.
        expression = -max(0.0, -peptide.detection_limit)
    variant = model.variant_scale if peptide.variant_present else 0.0
    logit = (
        model.intercept
        + model.binding_scale * binding
        + model.processing_scale * processing
        + model.expression_scale * expression
        + variant
    ) / model.temperature
    return HlaScore(
        allele=model.allele,
        binding_score=binding,
        processing_score=processing,
        expression_contribution=expression,
        variant_contribution=variant,
        logit=logit,
        probability=_sigmoid(logit),
    )


def _aggregate(models: list[HlaPresentationModel], peptide: PeptideObservation, expression_shift: float | None = None) -> tuple[tuple[HlaScore, ...], float] | None:
    scores = tuple(score for model in models if (score := _score_allele(model, peptide, expression_shift)) is not None)
    if not scores:
        return None
    return scores, _aggregate_probabilities(tuple(score.logit for score in scores))


def _drivers(
    scores: tuple[HlaScore, ...],
    models: dict[str, HlaPresentationModel],
) -> tuple[str, ...]:
    score = max(scores, key=lambda item: item.logit)
    model = models[score.allele]
    contributions = {
        f"binding:{score.allele}": model.binding_scale * score.binding_score,
        "processing:terminal-residues": model.processing_scale * score.processing_score,
        "expression:evidence": model.expression_scale * score.expression_contribution,
        "variant:sequence": score.variant_contribution,
    }
    return tuple(key for key, _ in sorted(contributions.items(), key=lambda pair: (-abs(pair[1]), pair[0]))[:4])


def _ablation(
    scores: tuple[HlaScore, ...],
    models: dict[str, HlaPresentationModel],
    full_probability: float,
) -> tuple[AblationEffect, ...]:
    effects: list[AblationEffect] = []
    components: tuple[Literal["binding", "processing", "expression", "variant"], ...] = (
        "binding",
        "processing",
        "expression",
        "variant",
    )
    for component_name in components:
        logits: list[float] = []
        for score in scores:
            model = models[score.allele]
            contribution = {
                "binding": model.binding_scale * score.binding_score,
                "processing": model.processing_scale * score.processing_score,
                "expression": model.expression_scale * score.expression_contribution,
                "variant": score.variant_contribution,
            }[component_name]
            logits.append(score.logit - contribution / model.temperature)
        probability = _aggregate_probabilities(tuple(logits))
        effects.append(AblationEffect(component=component_name, probability_delta=full_probability - probability))
    return tuple(effects)


_LIMITATIONS: Final = (
    "Research use only; this is not a clinical neoantigen, vaccine, or treatment decision model.",
    "Scores require a caller-supplied, licensed HLA/processing model and are not NetMHC predictions unless that model is supplied.",
    "Presentation probability is a calibrated-model coordinate, not proof of cell-surface presentation or T-cell recognition.",
    "HLA typing, peptide generation, proteasomal cleavage, TAP transport, tumor purity, and sampling remain external uncertainties.",
    "Multi-allele probabilities use an explicit independence approximation; correlated HLA presentation is not modeled.",
    "Missing and unsupported expression evidence is ignored; it never becomes a negative peptide observation.",
)


def analyze_immunopeptidomic_presentation(request: ImmunopeptidomicPresentationRequest) -> ImmunopeptidomicPresentationResult:
    """Score supported peptide/allele pairs and seal a deterministic receipt."""
    try:
        validated = _canonical_request(
            ImmunopeptidomicPresentationRequest.model_validate(
                request.model_dump(mode="python"), strict=True
            )
        )
    except (TypeError, ValueError) as error:
        raise ImmunopeptidomicInputError("request does not satisfy the presentation contract") from error
    profile = presentation_profile()
    models = list(validated.models)
    supported_models = [model for model in models if model.allele in validated.hla_alleles]
    model_by_allele = {model.allele: model for model in supported_models}
    informative = [peptide for peptide in validated.peptides if peptide.state in {"observed", "left_censored"}]
    seed = int(validated.request_digest.split(":", 1)[1][:16], 16)
    rng = np.random.default_rng(seed)
    rows: list[PeptidePresentation] = []
    bootstrap_values: dict[str, list[float]] = {peptide.peptide_id: [] for peptide in informative}
    for peptide in validated.peptides:
        if peptide.state not in {"observed", "left_censored"}:
            rows.append(PeptidePresentation(peptide_id=peptide.peptide_id, sequence=peptide.sequence, source_gene=peptide.source_gene, support="unsupported", abstention_reason="expression evidence is missing or unsupported"))
            continue
        aggregate = _aggregate(supported_models, peptide)
        if aggregate is None:
            rows.append(PeptidePresentation(peptide_id=peptide.peptide_id, sequence=peptide.sequence, source_gene=peptide.source_gene, support="unsupported", abstention_reason="no supplied model supports this peptide length or allele"))
            continue
        scores, probability = aggregate
        for _ in range(validated.bootstrap_replicates):
            shift = peptide.expression_effect
            if shift is not None and peptide.expression_standard_error is not None:
                shift += float(rng.normal(0.0, peptide.expression_standard_error / max(peptide.quality_weight, 0.05)))
            perturbed = _aggregate(supported_models, peptide, shift)
            if perturbed is not None:
                bootstrap_values[peptide.peptide_id].append(perturbed[1])
        values = bootstrap_values[peptide.peptide_id]
        if values:
            interval_low, interval_high = (float(value) for value in np.quantile(np.asarray(values), [0.05, 0.95], method="linear"))
        else:
            interval_low = interval_high = probability
        rows.append(PeptidePresentation(
            peptide_id=peptide.peptide_id,
            sequence=peptide.sequence,
            source_gene=peptide.source_gene,
            support="supported",
            supported_alleles=scores,
            binding_score=max(score.binding_score for score in scores),
            processing_score=max(score.processing_score for score in scores),
            expression_contribution=max(score.expression_contribution for score in scores),
            presentation_probability=probability,
            interval_low=interval_low,
            interval_high=interval_high,
            top_drivers=_drivers(scores, model_by_allele),
            ablations=_ablation(scores, model_by_allele, probability),
        ))
    supported_count = sum(row.support == "supported" for row in rows)
    allele_count = len({score.allele for row in rows for score in row.supported_alleles})
    if supported_count < 3:
        support: Literal["supported", "limited", "abstained"] = "abstained"
        reason = "at least three informative peptides must be supported by the supplied HLA models"
    elif allele_count < len(validated.hla_alleles):
        support, reason = "limited", None
    else:
        support, reason = "supported", None
    ranked = sorted(rows, key=lambda row: (-(row.presentation_probability or -1.0), row.peptide_id))
    ranks = {
        row.peptide_id: index
        for index, row in enumerate(
            (item for item in ranked if item.support == "supported"),
            start=1,
        )
    }
    sealed_rows = tuple(row.model_copy(update={"rank": ranks.get(row.peptide_id)}) for row in rows)
    draft = ImmunopeptidomicPresentationResult.model_construct(
        result_id=f"presentation-{validated.sample_id}",
        profile_digest=profile.profile_digest,
        request_digest=validated.request_digest,
        result_digest=_ZERO_DIGEST,
        sample_id=validated.sample_id,
        support=support,
        candidates=sealed_rows,
        supported_peptide_count=supported_count,
        supported_allele_count=allele_count,
        model_digests=tuple(model.model_digest for model in models),
        bootstrap_replicates=validated.bootstrap_replicates,
        abstention_reason=reason,
        limitations=_LIMITATIONS,
    )
    return draft.model_copy(update={"result_digest": result_digest(draft)})


def synthetic_presentation_request() -> ImmunopeptidomicPresentationRequest:
    """Return a deterministic, synthetic glioma-like HLA-I workbench request."""
    def matrix(length: int, favored: str) -> PositionWeightMatrix:
        values = [0.0] * (length * 20)
        for position, residue in ((1, favored), (length - 1, favored)):
            values[position * 20 + AMINO_ACIDS.index(residue)] = 2.0
        return PositionWeightMatrix(peptide_length=length, values=tuple(values))

    def model(allele: str, favored: str) -> HlaPresentationModel:
        draft = HlaPresentationModel.model_construct(
            allele=allele,
            matrices=(matrix(9, favored), matrix(10, favored)),
            processing_weights=tuple(0.1 if residue in "LMIFVW" else 0.0 for residue in AMINO_ACIDS),
            intercept=-2.0,
            binding_scale=1.2,
            processing_scale=0.4,
            expression_scale=0.5,
            variant_scale=0.6,
            temperature=1.0,
            source_digest=sha256_digest({"synthetic": allele}),
            model_digest=_ZERO_DIGEST,
        )
        return draft.model_copy(update={"model_digest": model_digest(draft)})

    peptides = tuple(
        PeptideObservation(peptide_id=f"pep-{index}", sequence=sequence, source_gene=gene, variant_present=index < 3, state="observed", expression_effect=effect, expression_standard_error=0.15, quality_weight=0.9)
        for index, (sequence, gene, effect) in enumerate(
            (("SLYNTVATL", "EGFR", 1.3), ("LLGRNSFEV", "PDGFRA", 0.8), ("GILGFVFTL", "IDH1", 0.5), ("KLGVEAKKL", "TP53", -0.1), ("NLVPMVATV", "SOX2", 0.2)),
            start=1,
        )
    )
    return ImmunopeptidomicPresentationRequest(
        sample_id="synthetic-glioma",
        hla_alleles=("HLA-A*02:01", "HLA-B*07:02"),
        peptides=peptides,
        models=(model("HLA-A*02:01", "L"), model("HLA-B*07:02", "V")),
        source_digests=(sha256_digest({"demo": "synthetic-glioma-immunopeptidome"}),),
        provenance_note="Synthetic sequences and caller-model coefficients for research workbench tests.",
    )


def verify_presentation_replay(request: ImmunopeptidomicPresentationRequest, result: ImmunopeptidomicPresentationResult) -> bool:
    """Recompute and compare a presentation receipt exactly."""
    recomputed = analyze_immunopeptidomic_presentation(request)
    if result.request_digest != request.request_digest or result.result_digest != recomputed.result_digest or result != recomputed:
        raise ValueError("presentation replay does not match")
    return True


__all__ = [
    "AMINO_ACIDS",
    "DEFAULT_BOOTSTRAP_REPLICATES",
    "PRESENTATION_ALGORITHM_ID",
    "PRESENTATION_ALGORITHM_VERSION",
    "PRESENTATION_PROFILE_ID",
    "HlaPresentationModel",
    "HlaScore",
    "ImmunopeptidomicInputError",
    "ImmunopeptidomicPresentationRequest",
    "ImmunopeptidomicPresentationResult",
    "PeptideObservation",
    "PeptidePresentation",
    "PositionWeightMatrix",
    "PresentationProfile",
    "PresentationReplayRequest",
    "PresentationReplayResult",
    "analyze_immunopeptidomic_presentation",
    "model_digest",
    "presentation_profile",
    "profile_digest",
    "request_digest",
    "result_digest",
    "synthetic_presentation_request",
    "verify_presentation_replay",
]
