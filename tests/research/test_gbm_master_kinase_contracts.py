from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from glio_proteogen.research.gbm_master_kinases import (
    MAX_COMPUTATIONAL_WORK_UNITS,
    MasterKinaseRequest,
    PhosphositeEvidenceState,
    PhosphositeObservation,
    StandardizedContrastReference,
)
from glio_proteogen.research.gbm_master_kinases.canonical import sha256_digest
from glio_proteogen.research.gbm_master_kinases.catalog import (
    independent_kinase_memberships_by_site,
    master_kinase_catalog,
)

PROVENANCE = sha256_digest({"test": "master-kinase-contracts"})


def _observation(  # noqa: PLR0913
    phosphosite_id: str,
    *,
    identifier: str = "obs.1",
    state: PhosphositeEvidenceState = PhosphositeEvidenceState.OBSERVED,
    effect: float | None = 1.0,
    standard_error: float | None = 0.3,
    quality_weight: float = 1.0,
) -> PhosphositeObservation:
    return PhosphositeObservation(
        observation_id=identifier,
        phosphosite_id=phosphosite_id,
        state=state,
        standardized_effect=effect,
        standard_error=standard_error,
        quality_weight=quality_weight,
        provenance_digest=PROVENANCE,
    )


def _contrast() -> StandardizedContrastReference:
    return StandardizedContrastReference(
        contrast_id="test.contrast",
        numerator_label="case",
        denominator_label="reference",
    )


def test_active_sites_require_exact_pinned_table5a_labels() -> None:
    valid = next(iter(sorted(master_kinase_catalog().background_labels)))
    request = MasterKinaseRequest(
        sample_id="sample.valid",
        observations=(_observation(valid),),
        bootstrap_replicates=16,
        permutation_replicates=64,
        contrast_reference=_contrast(),
    )
    assert request.observations[0].phosphosite_id == valid
    with pytest.raises(ValidationError, match="exactly match the pinned Table 5a"):
        MasterKinaseRequest(
            sample_id="sample.fake",
            observations=(_observation("FAKE-S1s"),),
            bootstrap_replicates=16,
            permutation_replicates=64,
            contrast_reference=_contrast(),
        )
    with pytest.raises(ValidationError, match="exactly match the pinned Table 5a"):
        MasterKinaseRequest(
            sample_id="sample.case",
            observations=(_observation(valid.lower()),),
            bootstrap_replicates=16,
            permutation_replicates=64,
            contrast_reference=_contrast(),
        )


def test_unknown_inactive_site_is_retained_but_cannot_enter_rank_background() -> None:
    request = MasterKinaseRequest(
        sample_id="sample.inactive",
        observations=(
            _observation(
                "FAKE-S1s",
                state=PhosphositeEvidenceState.UNSUPPORTED,
                effect=None,
                standard_error=None,
                quality_weight=0.0,
            ),
        ),
        bootstrap_replicates=16,
        permutation_replicates=64,
        contrast_reference=_contrast(),
    )
    assert request.observations[0].state is PhosphositeEvidenceState.UNSUPPORTED


@pytest.mark.parametrize(
    ("state", "effect", "standard_error", "quality"),
    [
        (PhosphositeEvidenceState.OBSERVED, None, 0.3, 1.0),
        (PhosphositeEvidenceState.LEFT_CENSORED, 0.0, None, 1.0),
        (PhosphositeEvidenceState.OBSERVED, 1.0, 0.3, 0.0),
        (PhosphositeEvidenceState.MISSING, 1.0, 0.3, 0.0),
        (PhosphositeEvidenceState.UNSUPPORTED, None, None, 1.0),
    ],
)
def test_observation_state_machine_rejects_incompatible_values(
    state: PhosphositeEvidenceState,
    effect: float | None,
    standard_error: float | None,
    quality: float,
) -> None:
    site = next(iter(sorted(master_kinase_catalog().background_labels)))
    with pytest.raises(ValidationError):
        _observation(
            site,
            state=state,
            effect=effect,
            standard_error=standard_error,
            quality_weight=quality,
        )


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, 20.1, -20.1])
def test_nonfinite_and_out_of_range_effects_are_rejected(value: float) -> None:
    site = next(iter(sorted(master_kinase_catalog().background_labels)))
    with pytest.raises(ValidationError):
        _observation(site, effect=value)


def test_duplicate_observation_and_exact_site_identifiers_are_rejected() -> None:
    sites = tuple(sorted(master_kinase_catalog().background_labels)[:2])
    with pytest.raises(ValidationError, match="observation identifiers must be unique"):
        MasterKinaseRequest(
            sample_id="sample.duplicate-id",
            observations=(
                _observation(sites[0], identifier="obs.same"),
                _observation(sites[1], identifier="obs.same"),
            ),
            bootstrap_replicates=16,
            permutation_replicates=64,
            contrast_reference=_contrast(),
        )
    with pytest.raises(ValidationError, match="phosphosite identifiers must be unique"):
        MasterKinaseRequest(
            sample_id="sample.duplicate-site",
            observations=(
                _observation(sites[0], identifier="obs.1"),
                _observation(sites[0], identifier="obs.2"),
            ),
            bootstrap_replicates=16,
            permutation_replicates=64,
            contrast_reference=_contrast(),
        )


def test_contrast_reference_is_explicit_and_directional() -> None:
    with pytest.raises(ValidationError, match="must differ"):
        StandardizedContrastReference(
            contrast_id="bad.contrast",
            numerator_label="same",
            denominator_label="same",
        )


def test_composed_work_budget_accepts_max_shape_defaults_and_rejects_maxima() -> None:
    catalog = master_kinase_catalog()
    memberships = independent_kinase_memberships_by_site()
    labels = sorted(
        catalog.background_labels,
        key=lambda site: (-memberships.get(site, 0), site),
    )[:4_096]
    observations = tuple(
        _observation(
            site,
            identifier=f"work.obs.{index:04d}",
            effect=((index % 31) - 15) / 10,
        )
        for index, site in enumerate(labels)
    )
    accepted = MasterKinaseRequest(
        sample_id="work.max-shape-default-replicates",
        observations=observations,
        bootstrap_replicates=64,
        permutation_replicates=256,
        contrast_reference=_contrast(),
    )
    assert accepted.estimated_work_units == 11_879_040
    assert accepted.estimated_work_units <= MAX_COMPUTATIONAL_WORK_UNITS
    with pytest.raises(ValidationError, match="computational work budget"):
        MasterKinaseRequest(
            sample_id="work.composed-maxima",
            observations=observations,
            bootstrap_replicates=256,
            permutation_replicates=2_048,
            contrast_reference=_contrast(),
        )
