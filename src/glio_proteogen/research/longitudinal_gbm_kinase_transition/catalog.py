"""Fail-closed catalog for the de-identified PDC000515/SPHINKS fitted profile."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from functools import cached_property, lru_cache
from importlib.resources import files
from typing import Final, cast

from glio_proteogen.research.gbm_master_kinases.catalog import master_kinase_catalog
from glio_proteogen.research.longitudinal_gbm_phospho.catalog import (
    EXPECTED_CONTENT_DIGEST as EXPECTED_PDC_ARTIFACT_DIGEST,
)
from glio_proteogen.research.longitudinal_gbm_phospho.catalog import (
    EXPECTED_CROSSWALK_DIGEST as EXPECTED_PDC_CROSSWALK_DIGEST,
)
from glio_proteogen.research.longitudinal_gbm_phospho.catalog import (
    EXPECTED_HGNC_MAPPING_DIGEST as EXPECTED_PDC_HGNC_MAPPING_DIGEST,
)
from glio_proteogen.research.longitudinal_gbm_phospho.catalog import (
    EXPECTED_PROFILE_DIGEST as EXPECTED_PDC_PROFILE_DIGEST,
)
from glio_proteogen.research.longitudinal_gbm_phospho.catalog import (
    load_phosphosite_transition_catalog,
)

from .errors import SourceProfileIntegrityError

ARTIFACT_RESOURCE: Final = "data/kncc_sphinks_signature_transition.v1.json"
MODEL_ID: Final = "kncc-pdc000515-sphinks-signature-transition/1.0.0"
PROFILE_ID: Final = "kncc-gbm-longitudinal-kinase-transition/1.0.0"
SCHEMA_VERSION: Final = "glio-proteogen.kncc-longitudinal-kinase-transition-artifact/1.0.0"
EXPECTED_ARTIFACT_BYTES: Final = 1_271_736
EXPECTED_ARTIFACT_SHA256: Final = "5e14278cca4d179bc6585abcc698704bf213fb81885a8a6876a5f1741ac4c82d"
EXPECTED_CONTENT_DIGEST: Final = (
    "sha256:416a5f814378ed141fc89d3dd4bf497489c472cef2db1c16e97ec9ede080c822"
)
EXPECTED_FITTER_SOURCE_SHA256: Final = (
    "sha256:ccddb71c2bc92a853d4c0ccdf55b88a50d8f223adf89310d4cacc2c1dff38ab8"
)
EXPECTED_BOOTSTRAP_DIGEST: Final = (
    "sha256:c5756048bce4074efe9b1914c325b0cbb5f312e7840efe92d8b926edbb5df38c"
)
EXPECTED_FAMILY_COUNT: Final = 2_457
EXPECTED_SELECTED_COUNT: Final = 12
EXPECTED_BOOTSTRAPS: Final = 64
EXPECTED_STRICT_PAIRS: Final = 88
EXPECTED_HYPOTHESES: Final = 24
EXPECTED_CORE_KINASES: Final = frozenset(
    {
        "BRAF",
        "CDK1",
        "CDK2",
        "CSNK2A1",
        "GSK3B",
        "MAPK10",
        "PAK1",
        "PAK3",
        "PRKCE",
        "PRKDC",
        "TTBK2",
    }
)


@dataclass(frozen=True, slots=True)
class SignatureFamily:
    family_index: int
    source_site_label: str
    stratum: str
    source_phosphosite_ids: tuple[str, ...]
    contains_composite_source_group: bool
    paired_support: int
    paired_coverage: float
    transition_scale: float


@dataclass(frozen=True, slots=True)
class KinaseProjection:
    kinase: str
    subtype: str
    direction: str
    family_indices: tuple[int, ...]
    weights: tuple[float, ...]
    enrichment: float
    p_value: float
    q_value: float


@dataclass(frozen=True, slots=True)
class KinaseHypothesis:
    kinase: str
    subtype: str
    mapped_eligible_families: int
    enrichment: float | None
    p_value: float
    q_value: float
    selected: bool
    outer_selection_frequency: float
    bootstrap_selection_frequency: float
    bootstrap_direction_consistency: float | None


@dataclass(frozen=True, slots=True)
class BootstrapProjection:
    replicate_index: int
    seed_hex: str
    family_indices: tuple[int, ...]
    scales: tuple[float, ...]
    kinases: tuple[KinaseProjection, ...]
    replicate_digest: str

    @property
    def scale_by_family(self) -> dict[int, float]:
        return dict(zip(self.family_indices, self.scales, strict=True))


@dataclass(frozen=True)
class KinaseTransitionCatalog:
    artifact_sha256: str
    artifact_digest: str
    bootstrap_digest: str
    families: tuple[SignatureFamily, ...]
    hypotheses: tuple[KinaseHypothesis, ...]
    selected_kinases: tuple[KinaseProjection, ...]
    bootstrap_projections: tuple[BootstrapProjection, ...]
    counts: dict[str, object]
    fit_evaluation: dict[str, object]
    source_bindings: dict[str, str]
    pdc_attribution: str
    pdc_license: str
    pdc_license_url: str
    pdc_transformation_notice: str
    sphinks_attribution: str
    sphinks_license: str
    sphinks_license_url: str
    sphinks_transformation_notice: str

    @cached_property
    def family_by_index(self) -> dict[int, SignatureFamily]:
        return {item.family_index: item for item in self.families}

    @cached_property
    def family_by_phosphosite_id(self) -> dict[str, SignatureFamily]:
        return {
            phosphosite_id: family
            for family in self.families
            for phosphosite_id in family.source_phosphosite_ids
        }

    @cached_property
    def hypothesis_by_kinase(self) -> dict[str, KinaseHypothesis]:
        return {item.kinase: item for item in self.hypotheses}


def _fail(message: str) -> None:
    raise SourceProfileIntegrityError(message)


def _artifact_digest(value: object) -> str:
    payload = (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _object(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        _fail(f"artifact field {name!r} is not an object")
    return cast("dict[str, object]", value)


def _list(value: object, name: str) -> list[object]:
    if not isinstance(value, list):
        _fail(f"artifact field {name!r} is not an array")
    return cast("list[object]", value)


def _finite(value: object, name: str) -> float:
    parsed = float(cast("float | int", value))
    if not math.isfinite(parsed):
        _fail(f"artifact field {name!r} is non-finite")
    return parsed


def _projection(value: object, name: str) -> KinaseProjection:
    item = _object(value, name)
    indices = tuple(
        int(cast("int", entry))
        for entry in _list(item.get("family_indices"), f"{name}.family_indices")
    )
    weights = tuple(
        _finite(entry, f"{name}.weights") for entry in _list(item.get("weights"), f"{name}.weights")
    )
    if len(indices) < 3 or len(indices) != len(weights):
        _fail("kinase projection dimensions are inconsistent")
    if tuple(sorted(indices)) != indices or len(set(indices)) != len(indices):
        _fail("kinase projection family indices are not sorted and unique")
    if any(weight <= 0.0 for weight in weights):
        _fail("kinase projection has a non-positive source weight")
    direction = str(item.get("direction"))
    if direction not in {"source_recurrence_aligned", "reverse_aligned"}:
        _fail("kinase projection direction is invalid")
    return KinaseProjection(
        kinase=str(item.get("kinase")),
        subtype=str(item.get("subtype")),
        direction=direction,
        family_indices=indices,
        weights=weights,
        enrichment=_finite(item.get("enrichment"), f"{name}.enrichment"),
        p_value=_finite(item.get("p_value"), f"{name}.p_value"),
        q_value=_finite(item.get("q_value"), f"{name}.q_value"),
    )


def _bootstrap(value: object, index: int, family_indices: frozenset[int]) -> BootstrapProjection:
    item = _object(value, f"bootstrap[{index}]")
    supplied = str(item.get("replicate_digest"))
    content = dict(item)
    content.pop("replicate_digest", None)
    if _artifact_digest(content) != supplied:
        _fail("bootstrap replicate digest mismatch")
    indices = tuple(
        int(cast("int", entry)) for entry in _list(item.get("family_indices"), "indices")
    )
    scales = tuple(_finite(entry, "scale") for entry in _list(item.get("scales"), "scales"))
    if int(cast("int", item.get("replicate_index"))) != index:
        _fail("bootstrap replicate indices are not consecutive")
    if len(indices) != len(scales) or tuple(sorted(indices)) != indices:
        _fail("bootstrap scale dimensions are inconsistent")
    if not set(indices).issubset(family_indices) or any(scale <= 0.0 for scale in scales):
        _fail("bootstrap references an unreleased family scale")
    kinases = tuple(
        _projection(entry, f"bootstrap[{index}].kinases")
        for entry in _list(item.get("kinases"), "kinases")
    )
    if len({item.kinase for item in kinases}) != len(kinases):
        _fail("bootstrap kinase projections are duplicated")
    if any(not set(item.family_indices).issubset(set(indices)) for item in kinases):
        _fail("bootstrap kinase references a family without a replicate scale")
    return BootstrapProjection(
        replicate_index=index,
        seed_hex=str(item.get("seed_hex")),
        family_indices=indices,
        scales=scales,
        kinases=kinases,
        replicate_digest=supplied,
    )


def _bh(p_values: tuple[float, ...]) -> tuple[float, ...]:
    count = len(p_values)
    order = sorted(range(count), key=lambda index: (p_values[index], index))
    output = [1.0] * count
    running = 1.0
    for rank in range(count - 1, -1, -1):
        index = order[rank]
        running = min(running, p_values[index] * count / (rank + 1))
        output[index] = running
    return tuple(output)


@lru_cache(maxsize=1)
def load_kinase_transition_catalog() -> KinaseTransitionCatalog:  # noqa: PLR0915
    payload = files(__package__).joinpath(ARTIFACT_RESOURCE).read_bytes()
    if len(payload) != EXPECTED_ARTIFACT_BYTES:
        _fail("signature-transition artifact byte size mismatch")
    observed_sha = hashlib.sha256(payload).hexdigest()
    if observed_sha != EXPECTED_ARTIFACT_SHA256:
        _fail("signature-transition artifact byte digest mismatch")
    try:
        root = _object(json.loads(payload), "root")
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SourceProfileIntegrityError(
            "signature-transition artifact is invalid JSON"
        ) from error
    canonical = (
        json.dumps(root, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode()
    if canonical != payload:
        _fail("signature-transition artifact is not canonical JSON")
    if root.get("schema_version") != SCHEMA_VERSION or root.get("model_id") != MODEL_ID:
        _fail("signature-transition artifact identity changed")
    if root.get("profile_id") != PROFILE_ID:
        _fail("signature-transition artifact profile changed")
    content = dict(root)
    supplied_digest = content.pop("artifact_digest", None)
    if supplied_digest != EXPECTED_CONTENT_DIGEST or _artifact_digest(content) != supplied_digest:
        _fail("signature-transition artifact content digest mismatch")

    privacy = _object(root.get("privacy"), "privacy")
    if privacy != {
        "aggregate_and_release_eligible_parameters_only": True,
        "patient_derived_digests_emitted": False,
        "patient_identifiers_emitted": False,
        "patient_level_matrices_emitted": False,
    }:
        _fail("signature-transition artifact privacy declaration changed")
    bindings = {
        key: str(value)
        for key, value in _object(root.get("source_bindings"), "source_bindings").items()
    }
    pdc = load_phosphosite_transition_catalog()
    sphinks = master_kinase_catalog()
    expected_bindings = {
        "fitter_source_sha256": EXPECTED_FITTER_SOURCE_SHA256,
        "pdc_study_id": "PDC000515",
        "pdc_study_version_uuid": "e5e0dd84-f982-46e3-b78a-5cb19eef31a8",
        "pdc_source_manifest_digest": pdc.source_manifest_digest,
        "pdc_phosphosite_artifact_content_digest": EXPECTED_PDC_ARTIFACT_DIGEST,
        "pdc_phosphosite_source_profile_digest": EXPECTED_PDC_PROFILE_DIGEST,
        "pdc_hgnc_mapping_digest": EXPECTED_PDC_HGNC_MAPPING_DIGEST,
        "pdc_sphinks_crosswalk_digest": EXPECTED_PDC_CROSSWALK_DIGEST,
        "sphinks_catalog_artifact_digest": sphinks.artifact_digest,
        "sphinks_catalog_content_digest": sphinks.content_digest,
        "sphinks_background_tuple_digest": sphinks.background_tuple_digest,
        "sphinks_signature_edge_digest": sphinks.signature_edge_digest,
        "sphinks_master_kinase_digest": sphinks.master_kinase_digest,
        "sphinks_source_sha256": sphinks.source_sha256,
    }
    if bindings != expected_bindings:
        _fail("signature-transition upstream source bindings changed")

    raw_families = _list(root.get("families"), "families")
    families: list[SignatureFamily] = []
    for raw in raw_families:
        item = _object(raw, "family")
        ids = tuple(str(value) for value in _list(item.get("source_phosphosite_ids"), "ids"))
        family = SignatureFamily(
            family_index=int(cast("int", item.get("family_index"))),
            source_site_label=str(item.get("source_site_label")),
            stratum=str(item.get("stratum")),
            source_phosphosite_ids=ids,
            contains_composite_source_group=bool(item.get("contains_composite_source_group")),
            paired_support=int(cast("int", item.get("paired_support"))),
            paired_coverage=_finite(item.get("paired_coverage"), "paired_coverage"),
            transition_scale=_finite(item.get("transition_scale"), "transition_scale"),
        )
        if (
            not ids
            or tuple(sorted(ids)) != ids
            or int(cast("int", item.get("source_row_count"))) != len(ids)
            or family.paired_support < 53
            or family.transition_scale <= 0.0
            or not math.isclose(family.paired_coverage, family.paired_support / 88, abs_tol=1e-9)
        ):
            _fail("release-eligible family invariant failed")
        families.append(family)
    if len(families) != EXPECTED_FAMILY_COUNT:
        _fail("release-eligible family count changed")
    indices = tuple(item.family_index for item in families)
    labels = tuple(item.source_site_label for item in families)
    all_ids = tuple(value for item in families for value in item.source_phosphosite_ids)
    if indices != tuple(sorted(set(indices))) or len(labels) != len(set(labels)):
        _fail("release-eligible family identity is not ordered and unique")
    if len(all_ids) != len(set(all_ids)):
        _fail("a PDC source phosphosite appears in more than one SPHINKS family")
    base_by_id = pdc.feature_by_id
    if any(value not in base_by_id for value in all_ids):
        _fail("signature-transition artifact references an unknown PDC phosphosite")

    full_fit = _object(root.get("full_fit"), "full_fit")
    raw_hypotheses = _list(full_fit.get("all_kinases"), "all_kinases")
    stability = _object(root.get("stability"), "stability")
    outer_frequency = _object(stability.get("outer_selection_frequency"), "outer_frequency")
    bootstrap_frequency = _object(
        stability.get("bootstrap_selection_frequency"), "bootstrap_frequency"
    )
    direction_consistency = _object(
        stability.get("bootstrap_direction_consistency_when_selected"),
        "direction_consistency",
    )
    hypotheses = tuple(
        KinaseHypothesis(
            kinase=str(item.get("kinase")),
            subtype=str(item.get("subtype")),
            mapped_eligible_families=int(
                cast("int", item.get("mapped_training_eligible_families"))
            ),
            enrichment=(
                _finite(item.get("enrichment"), "enrichment")
                if item.get("enrichment") is not None
                else None
            ),
            p_value=_finite(item.get("p_value"), "p_value"),
            q_value=_finite(item.get("q_value"), "q_value"),
            selected=bool(item.get("selected")),
            outer_selection_frequency=_finite(
                outer_frequency.get(str(item.get("kinase"))), "outer_frequency"
            ),
            bootstrap_selection_frequency=_finite(
                bootstrap_frequency.get(str(item.get("kinase"))), "bootstrap_frequency"
            ),
            bootstrap_direction_consistency=(
                _finite(
                    direction_consistency.get(str(item.get("kinase"))),
                    "direction_consistency",
                )
                if str(item.get("kinase")) in direction_consistency
                else None
            ),
        )
        for raw in raw_hypotheses
        for item in (_object(raw, "hypothesis"),)
    )
    master_symbols = tuple(item.hgnc_symbol for item in sphinks.masters)
    if (
        len(hypotheses) != EXPECTED_HYPOTHESES
        or tuple(item.kinase for item in hypotheses) != master_symbols
    ):
        _fail("fixed 24-kinase hypothesis identity changed")
    expected_q = _bh(tuple(item.p_value for item in hypotheses))
    if any(
        not math.isclose(item.q_value, q, abs_tol=2e-9)
        for item, q in zip(hypotheses, expected_q, strict=True)
    ):
        _fail("fixed-family BH q-values do not replay")
    if any(
        item.selected is not (item.enrichment is not None and item.q_value <= 0.10)
        for item in hypotheses
    ):
        _fail("fixed-family selection rule changed")

    selected = tuple(
        _projection(raw, "selected_kinases")
        for raw in _list(full_fit.get("selected_kinases"), "selected_kinases")
    )
    if len(selected) != EXPECTED_SELECTED_COUNT:
        _fail("full-fit selected kinase count changed")
    if {item.kinase for item in selected} != {item.kinase for item in hypotheses if item.selected}:
        _fail("selected kinase projections disagree with fixed-family results")
    family_index_set = frozenset(indices)
    if any(not set(item.family_indices).issubset(family_index_set) for item in selected):
        _fail("full-fit kinase projection references an unreleased family")
    core = {
        item.kinase
        for item in hypotheses
        if item.selected and item.bootstrap_selection_frequency >= 0.80
    }
    if core != EXPECTED_CORE_KINASES:
        _fail("core stable kinase inventory changed")
    if (
        hypotheses[
            tuple(item.kinase for item in hypotheses).index("CHEK2")
        ].bootstrap_selection_frequency
        >= 0.80
    ):
        _fail("CHEK2 must remain below the frozen stability threshold")

    bootstrap = _object(root.get("bootstrap"), "bootstrap")
    raw_bootstraps = _list(bootstrap.get("replicates"), "replicates")
    if len(raw_bootstraps) != EXPECTED_BOOTSTRAPS:
        _fail("patient bootstrap count changed")
    if (
        bootstrap.get("ensemble_digest") != EXPECTED_BOOTSTRAP_DIGEST
        or _artifact_digest(raw_bootstraps) != EXPECTED_BOOTSTRAP_DIGEST
    ):
        _fail("patient bootstrap ensemble digest mismatch")
    bootstraps = tuple(
        _bootstrap(raw, index, family_index_set) for index, raw in enumerate(raw_bootstraps)
    )

    gates = _object(root.get("runtime_quality_gates"), "runtime_quality_gates")
    if gates != {
        "output_policy": "all_estimable_outputs_limited_otherwise_abstained",
        "patient_bootstrap_full_refit_convergence_gate_passed": True,
        "patient_bootstrap_full_set_stability_gate_passed": False,
        "patient_bootstrap_interval_calibration_gate_passed": False,
        "same_assay_independent_evidence_gate_passed": False,
    }:
        _fail("runtime quality gates changed")
    counts = _object(root.get("counts"), "counts")
    if (
        counts.get("strict_patient_pairs") != EXPECTED_STRICT_PAIRS
        or counts.get("release_eligible_background_families") != EXPECTED_FAMILY_COUNT
        or counts.get("fixed_master_kinase_hypotheses") != EXPECTED_HYPOTHESES
    ):
        _fail("source/cohort count oracle changed")
    provenance = _object(root.get("provenance"), "provenance")
    return KinaseTransitionCatalog(
        artifact_sha256="sha256:" + observed_sha,
        artifact_digest=EXPECTED_CONTENT_DIGEST,
        bootstrap_digest=EXPECTED_BOOTSTRAP_DIGEST,
        families=tuple(families),
        hypotheses=hypotheses,
        selected_kinases=selected,
        bootstrap_projections=bootstraps,
        counts=counts,
        fit_evaluation=_object(root.get("fit_evaluation"), "fit_evaluation"),
        source_bindings=bindings,
        pdc_attribution=str(provenance.get("pdc_article_attribution")),
        pdc_license=str(provenance.get("pdc_license")),
        pdc_license_url=str(provenance.get("pdc_license_url")),
        pdc_transformation_notice=str(provenance.get("pdc_transformation_notice")),
        sphinks_attribution=str(provenance.get("sphinks_article_attribution")),
        sphinks_license=str(provenance.get("sphinks_license")),
        sphinks_license_url=str(provenance.get("sphinks_license_url")),
        sphinks_transformation_notice=str(provenance.get("sphinks_transformation_notice")),
    )


__all__ = [
    "ARTIFACT_RESOURCE",
    "EXPECTED_ARTIFACT_BYTES",
    "EXPECTED_ARTIFACT_SHA256",
    "EXPECTED_BOOTSTRAP_DIGEST",
    "EXPECTED_CONTENT_DIGEST",
    "EXPECTED_FITTER_SOURCE_SHA256",
    "MODEL_ID",
    "PROFILE_ID",
    "BootstrapProjection",
    "KinaseHypothesis",
    "KinaseProjection",
    "KinaseTransitionCatalog",
    "SignatureFamily",
    "load_kinase_transition_catalog",
]
