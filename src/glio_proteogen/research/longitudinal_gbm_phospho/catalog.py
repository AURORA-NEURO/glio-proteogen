"""Integrity-checked numerical catalog for the de-identified PDC000515 model."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from functools import cached_property, lru_cache
from importlib.resources import files
from typing import Final, cast

ARTIFACT_RESOURCE: Final = "data/kncc_paired_phosphosite_transition.v1.json"
MODEL_ID: Final = "kncc-paired-phosphosite-transition/1.0.0"
SOURCE_PROFILE_ID: Final = "kncc-pdc000515-tmt11-phosphosite-log2-transition/1.0.0"
PROFILE_ID: Final = SOURCE_PROFILE_ID
SCHEMA_VERSION: Final = "glio-proteogen.kncc-paired-phosphosite-transition-artifact/1.0.0"
EXPECTED_ARTIFACT_BYTES: Final = 14_712_589
EXPECTED_ARTIFACT_SHA256: Final = "5060d34d214582395f55ef66f9026303f781019230e91cd01d51d60c4fd6255e"
EXPECTED_CONTENT_DIGEST: Final = (
    "sha256:d31635cc2c9f634679ebd913cf2e0911b0bdff1fb66d53533239e870d4b8624a"
)
EXPECTED_PROFILE_DIGEST: Final = (
    "sha256:81901f97d258f500dfc0aa31bf533e5bf45fa7d0e611820a58756e7ed8b64216"
)
EXPECTED_CROSSWALK_DIGEST: Final = (
    "sha256:4d9d62c63361f285b45fff380588b37174663bfc702cef0587b705aaadebe8c4"
)
EXPECTED_BOOTSTRAP_DIGEST: Final = (
    "sha256:75238c55a615d01301d96f4240933aab2c283f72892d48ac8d1c6521195de488"
)
EXPECTED_SOURCE_MANIFEST_DIGEST: Final = (
    "sha256:1b248983791886a9b4522de07d96abb517c416d793b789d435544745dbe6ed34"
)
EXPECTED_HGNC_MAPPING_DIGEST: Final = (
    "sha256:07245f3fe73129607856b1a92671cce13932a53c95a19f16894daf4971449aa4"
)
EXPECTED_FEATURES: Final = 24_015
EXPECTED_STRICT_PAIRS: Final = 88
EXPECTED_ELIGIBLE: Final = 4_225
EXPECTED_BOOTSTRAPS: Final = 64
EXPECTED_GATE_OUTPUT_POLICY: Final = (
    "uncalibrated bootstrap intervals force runtime output to LIMITED or ABSTAINED even "
    "when selection stability and every exact refit pass"
)


@dataclass(frozen=True, slots=True)
class PhosphositeFeature:
    """One exact, indivisible PDC phosphosite source group."""

    index: int
    phosphosite_id: str
    source_gene: str
    approved_gene: str
    hgnc_id: str
    site_cardinality: int
    composite_site_group: bool
    numerical_release_state: str
    transition_center: float | None
    transition_scale: float | None
    paired_support: int
    paired_coverage: float
    eligible: bool
    selected: bool
    coefficient: float
    bootstrap_selection_stability: float
    sphinks_source_site_label: str | None
    sphinks_signature_kinases: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SparseBootstrapProjection:
    """One frozen sparse coefficient draw; it is uncertainty, not validation."""

    replicate_index: int
    seed_hex: str
    feature_indices: tuple[int, ...]
    coefficients: tuple[float, ...]
    scales: tuple[float, ...]
    replicate_digest: str


@dataclass(frozen=True)
class PhosphositeTransitionCatalog:
    """Safe immutable numerical catalog for the packaged source artifact."""

    artifact_sha256: str
    artifact_digest: str
    source_profile_digest: str
    source_manifest_digest: str
    crosswalk_digest: str
    hgnc_mapping_digest: str
    bootstrap_digest: str
    source_attestation_state: str
    feature_count: int
    strict_pair_count: int
    selected_feature_count: int
    eligible_feature_count: int
    features: tuple[PhosphositeFeature, ...]
    bootstrap_projections: tuple[SparseBootstrapProjection, ...]
    selection_stability_gate_passed: bool
    bootstrap_full_refit_gate_passed: bool
    bootstrap_feature_selection_stability_gate_passed: bool
    bootstrap_calibration_gate_passed: bool
    source_attribution: str
    source_license: str
    source_license_url: str
    source_transformation_notice: str
    sphinks_source_attribution: str
    sphinks_source_license: str
    sphinks_source_license_url: str
    sphinks_transformation_notice: str

    @property
    def profile_digest(self) -> str:
        return self.source_profile_digest

    @cached_property
    def feature_by_id(self) -> dict[str, PhosphositeFeature]:
        return {feature.phosphosite_id: feature for feature in self.features}

    @cached_property
    def selected_features(self) -> tuple[PhosphositeFeature, ...]:
        return tuple(feature for feature in self.features if feature.selected)


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


def _object(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError(f"PDC000515 artifact field {name!r} is not an object")
    return cast("dict[str, object]", value)


def _list(value: object, name: str) -> list[object]:
    if not isinstance(value, list):
        raise TypeError(f"PDC000515 artifact field {name!r} is not an array")
    return cast("list[object]", value)


def _finite_float(value: object, name: str) -> float:
    parsed = float(cast("float | int", value))
    if not math.isfinite(parsed):
        raise RuntimeError(f"PDC000515 artifact field {name!r} is non-finite")
    return parsed


def _parse_feature(index: int, value: object) -> PhosphositeFeature:
    item = _object(value, f"features[{index}]")
    kinases = tuple(str(value) for value in _list(item["sphinks_signature_kinases"], "kinases"))
    eligible = bool(item["eligible"])
    center = (
        _finite_float(item["transition_center"], "transition_center")
        if item["transition_center"] is not None
        else None
    )
    scale = (
        _finite_float(item["transition_scale"], "transition_scale")
        if item["transition_scale"] is not None
        else None
    )
    release_state = str(item["numerical_release_state"])
    feature = PhosphositeFeature(
        index=index,
        phosphosite_id=str(item["source_site_group"]),
        source_gene=str(item["source_gene"]),
        approved_gene=str(item["approved_gene"]),
        hgnc_id=str(item["hgnc_id"]),
        site_cardinality=int(cast("int", item["site_cardinality"])),
        composite_site_group=bool(item["composite_site_group"]),
        numerical_release_state=release_state,
        transition_center=center,
        transition_scale=scale,
        paired_support=int(cast("int", item["paired_support"])),
        paired_coverage=_finite_float(item["paired_coverage"], "paired_coverage"),
        eligible=eligible,
        selected=bool(item["selected"]),
        coefficient=_finite_float(item["coefficient"], "coefficient"),
        bootstrap_selection_stability=_finite_float(
            item["bootstrap_selection_stability"], "bootstrap_selection_stability"
        ),
        sphinks_source_site_label=(
            str(item["sphinks_source_site_label"])
            if item["sphinks_source_site_label"] is not None
            else None
        ),
        sphinks_signature_kinases=kinases,
    )
    if feature.site_cardinality < 1:
        raise RuntimeError("PDC000515 feature cardinality is invalid")
    if feature.eligible:
        if (
            feature.numerical_release_state != "released_minimum_support"
            or feature.transition_center is None
            or feature.transition_scale is None
            or feature.transition_scale <= 0.0
        ):
            raise RuntimeError("PDC000515 eligible feature lacks its released fitted scale")
    elif (
        feature.numerical_release_state != "suppressed_insufficient_support"
        or feature.transition_center is not None
        or feature.transition_scale is not None
    ):
        raise RuntimeError("PDC000515 ineligible numerical fields are not fully suppressed")
    if feature.composite_site_group is not (feature.site_cardinality > 1):
        raise RuntimeError("PDC000515 composite-site declaration is inconsistent")
    if feature.selected and (not feature.eligible or feature.coefficient == 0.0):
        raise RuntimeError("PDC000515 selected feature is not numerically fitted")
    if not feature.selected and feature.coefficient != 0.0:
        raise RuntimeError("PDC000515 unselected feature carries a coefficient")
    return feature


def _parse_bootstrap(index: int, value: object, feature_count: int) -> SparseBootstrapProjection:
    item = _object(value, f"bootstrap.replicates[{index}]")
    supplied_digest = str(item["replicate_digest"])
    content = dict(item)
    content.pop("replicate_digest")
    if _digest(content) != supplied_digest:
        raise RuntimeError("PDC000515 bootstrap replicate digest mismatch")
    indices = tuple(int(cast("int", value)) for value in _list(item["feature_indices"], "indices"))
    coefficients = tuple(
        _finite_float(value, "bootstrap coefficient")
        for value in _list(item["coefficients"], "coefficients")
    )
    scales = tuple(
        _finite_float(value, "bootstrap scale") for value in _list(item["scales"], "scales")
    )
    if int(cast("int", item["replicate_index"])) != index:
        raise RuntimeError("PDC000515 bootstrap indices are not consecutive")
    if not indices or len(coefficients) != len(indices) or len(scales) != len(indices):
        raise RuntimeError("PDC000515 sparse bootstrap dimensions changed")
    if tuple(sorted(indices)) != indices or len(set(indices)) != len(indices):
        raise RuntimeError("PDC000515 sparse bootstrap indices are not sorted and unique")
    if any(feature_index < 0 or feature_index >= feature_count for feature_index in indices):
        raise RuntimeError("PDC000515 sparse bootstrap index is out of range")
    if not math.isclose(sum(abs(value) for value in coefficients), 1.0, abs_tol=1e-6):
        raise RuntimeError("PDC000515 sparse bootstrap coefficients are not L1 normalized")
    if any(value <= 0.0 for value in scales):
        raise RuntimeError("PDC000515 sparse bootstrap contains a non-positive scale")
    return SparseBootstrapProjection(
        replicate_index=index,
        seed_hex=str(item["seed_hex"]),
        feature_indices=indices,
        coefficients=coefficients,
        scales=scales,
        replicate_digest=supplied_digest,
    )


@lru_cache(maxsize=1)
def load_phosphosite_transition_catalog() -> PhosphositeTransitionCatalog:  # noqa: PLR0915
    """Load every frozen coefficient and fail closed on content or invariant drift."""

    payload = files(__package__).joinpath(ARTIFACT_RESOURCE).read_bytes()
    if len(payload) != EXPECTED_ARTIFACT_BYTES:
        raise RuntimeError("PDC000515 artifact byte-size mismatch")
    observed_sha = hashlib.sha256(payload).hexdigest()
    if observed_sha != EXPECTED_ARTIFACT_SHA256:
        raise RuntimeError("PDC000515 artifact SHA-256 mismatch")
    try:
        document = cast("object", json.loads(payload))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("PDC000515 artifact is not valid JSON") from error
    root = _object(document, "root")
    if _canonical_bytes(root) != payload:
        raise RuntimeError("PDC000515 artifact is not canonical JSON")
    if root.get("schema_version") != SCHEMA_VERSION or root.get("model_id") != MODEL_ID:
        raise RuntimeError("PDC000515 artifact identity changed")
    if root.get("profile_id") != SOURCE_PROFILE_ID:
        raise RuntimeError("PDC000515 source profile identity changed")
    if root.get("profile_digest") != EXPECTED_PROFILE_DIGEST:
        raise RuntimeError("PDC000515 source profile digest changed")
    if root.get("source_attestation_state") != "verified_exact_snapshots":
        raise RuntimeError("PDC000515 production source snapshots are not exactly attested")
    content = dict(root)
    artifact_digest = content.pop("artifact_digest", None)
    if artifact_digest != EXPECTED_CONTENT_DIGEST or _digest(content) != EXPECTED_CONTENT_DIGEST:
        raise RuntimeError("PDC000515 canonical content digest mismatch")

    raw_features = _list(root.get("features"), "features")
    if len(raw_features) != EXPECTED_FEATURES:
        raise RuntimeError("PDC000515 feature inventory changed")
    parsed_features = tuple(_parse_feature(index, item) for index, item in enumerate(raw_features))
    feature_ids = tuple(feature.phosphosite_id for feature in parsed_features)
    if len(feature_ids) != len(set(feature_ids)):
        raise RuntimeError("PDC000515 phosphosite identifiers are not unique")

    cohort = _object(root.get("cohort_oracles"), "cohort_oracles")
    if cohort.get("strict_t1_t2_pairs") != EXPECTED_STRICT_PAIRS:
        raise RuntimeError("PDC000515 strict-pair oracle changed")
    crosswalk = _object(root.get("crosswalk"), "crosswalk")
    hgnc = _object(crosswalk.get("hgnc"), "hgnc")
    sphinks = _object(crosswalk.get("sphinks"), "sphinks")
    if sphinks.get("crosswalk_digest") != EXPECTED_CROSSWALK_DIGEST:
        raise RuntimeError("PDC000515 SPHINKS crosswalk digest changed")
    if (
        sphinks.get("source_article_doi") != "10.1038/s43018-022-00510-x"
        or sphinks.get("source_license") != "CC-BY-4.0"
        or sphinks.get("source_license_url") != "https://creativecommons.org/licenses/by/4.0/"
    ):
        raise RuntimeError("PDC000515 SPHINKS source attribution changed")
    if hgnc.get("mapping_digest") != EXPECTED_HGNC_MAPPING_DIGEST:
        raise RuntimeError("PDC000515 HGNC mapping digest changed")
    fit = _object(root.get("fit"), "fit")
    selected = int(cast("int", fit.get("selected_top_feature_count")))
    eligible = int(cast("int", fit.get("eligible_feature_count")))
    if not 1 <= selected <= eligible or eligible != EXPECTED_ELIGIBLE:
        raise RuntimeError("PDC000515 fitted feature dimensions are inconsistent")
    if sum(feature.selected for feature in parsed_features) != selected:
        raise RuntimeError("PDC000515 selected feature inventory changed")
    if not math.isclose(
        sum(abs(feature.coefficient) for feature in parsed_features), 1.0, abs_tol=1e-6
    ):
        raise RuntimeError("PDC000515 frozen coefficients are not L1 normalized")

    bootstrap = _object(root.get("bootstrap"), "bootstrap")
    raw_replicates = _list(bootstrap.get("replicates"), "bootstrap.replicates")
    if len(raw_replicates) != EXPECTED_BOOTSTRAPS:
        raise RuntimeError("PDC000515 bootstrap replicate count changed")
    if (
        bootstrap.get("ensemble_digest") != EXPECTED_BOOTSTRAP_DIGEST
        or _digest(raw_replicates) != EXPECTED_BOOTSTRAP_DIGEST
    ):
        raise RuntimeError("PDC000515 bootstrap ensemble digest mismatch")
    replicates = tuple(
        _parse_bootstrap(index, item, len(parsed_features))
        for index, item in enumerate(raw_replicates)
    )
    if any(len(projection.feature_indices) != selected for projection in replicates):
        raise RuntimeError("PDC000515 bootstrap width does not match selected feature count")
    if any(
        not parsed_features[index].eligible
        or parsed_features[index].numerical_release_state != "released_minimum_support"
        or parsed_features[index].transition_scale is None
        for projection in replicates
        for index in projection.feature_indices
    ):
        raise RuntimeError("PDC000515 bootstrap references a suppressed feature")

    source_lock = _object(root.get("source_lock"), "source_lock")
    manifest = _object(source_lock.get("versioned_source_manifest"), "manifest")
    if manifest.get("sha256") != EXPECTED_SOURCE_MANIFEST_DIGEST:
        raise RuntimeError("PDC000515 versioned source manifest digest changed")
    provenance = _object(root.get("provenance"), "provenance")
    quality_gates = _object(root.get("runtime_quality_gates"), "runtime_quality_gates")
    gate_names = (
        "selection_stability_passed",
        "bootstrap_full_refit_passed",
        "bootstrap_feature_selection_stability_passed",
        "bootstrap_calibration_passed",
    )
    if any(type(quality_gates.get(name)) is not bool for name in gate_names):
        raise RuntimeError("PDC000515 runtime quality gates are not explicit booleans")
    if quality_gates.get("output_policy") != EXPECTED_GATE_OUTPUT_POLICY:
        raise RuntimeError("PDC000515 runtime quality-gate output policy changed")
    expected_gate_values = {
        "selection_stability_passed": True,
        "bootstrap_full_refit_passed": True,
        "bootstrap_feature_selection_stability_passed": False,
        "bootstrap_calibration_passed": False,
    }
    if any(quality_gates[name] is not expected for name, expected in expected_gate_values.items()):
        raise RuntimeError("PDC000515 frozen runtime quality-gate result changed")
    evaluation = _object(root.get("fit_evaluation"), "fit_evaluation")
    partition_stability = _object(
        evaluation.get("selection_partition_stability"), "selection_partition_stability"
    )
    if quality_gates["selection_stability_passed"] is not partition_stability.get("passed"):
        raise RuntimeError("PDC000515 selection-stability gate disagrees with its oracle")
    if quality_gates["bootstrap_full_refit_passed"] is not bootstrap.get("all_refits_converged"):
        raise RuntimeError("PDC000515 full-refit gate disagrees with its oracle")
    if quality_gates["bootstrap_feature_selection_stability_passed"] is not bootstrap.get(
        "feature_selection_stability_passed"
    ):
        raise RuntimeError("PDC000515 bootstrap-stability gate disagrees with its oracle")
    attribution = (
        f"{provenance['article_authors']}, {provenance['article_title']}, "
        f"{provenance['article_journal']}, DOI {provenance['article_doi']}"
    )
    sphinks_attribution = (
        f"{sphinks['source_article_authors']}, {sphinks['source_article_title']}, "
        f"DOI {sphinks['source_article_doi']}"
    )
    return PhosphositeTransitionCatalog(
        artifact_sha256="sha256:" + observed_sha,
        artifact_digest=artifact_digest,
        source_profile_digest=EXPECTED_PROFILE_DIGEST,
        source_manifest_digest=EXPECTED_SOURCE_MANIFEST_DIGEST,
        crosswalk_digest=EXPECTED_CROSSWALK_DIGEST,
        hgnc_mapping_digest=EXPECTED_HGNC_MAPPING_DIGEST,
        bootstrap_digest=EXPECTED_BOOTSTRAP_DIGEST,
        source_attestation_state="verified_exact_snapshots",
        feature_count=len(parsed_features),
        strict_pair_count=EXPECTED_STRICT_PAIRS,
        selected_feature_count=selected,
        eligible_feature_count=eligible,
        features=parsed_features,
        bootstrap_projections=replicates,
        selection_stability_gate_passed=(quality_gates.get("selection_stability_passed") is True),
        bootstrap_full_refit_gate_passed=(quality_gates.get("bootstrap_full_refit_passed") is True),
        bootstrap_feature_selection_stability_gate_passed=(
            quality_gates.get("bootstrap_feature_selection_stability_passed") is True
        ),
        bootstrap_calibration_gate_passed=(
            quality_gates.get("bootstrap_calibration_passed") is True
        ),
        source_attribution=attribution,
        source_license=str(provenance["license"]),
        source_license_url=str(provenance["license_url"]),
        source_transformation_notice=str(provenance["transformation_notice"]),
        sphinks_source_attribution=sphinks_attribution,
        sphinks_source_license=str(sphinks["source_license"]),
        sphinks_source_license_url=str(sphinks["source_license_url"]),
        sphinks_transformation_notice=str(sphinks["source_transformation_notice"]),
    )


__all__ = [
    "ARTIFACT_RESOURCE",
    "EXPECTED_ARTIFACT_BYTES",
    "EXPECTED_ARTIFACT_SHA256",
    "EXPECTED_BOOTSTRAP_DIGEST",
    "EXPECTED_CONTENT_DIGEST",
    "EXPECTED_CROSSWALK_DIGEST",
    "EXPECTED_PROFILE_DIGEST",
    "EXPECTED_SOURCE_MANIFEST_DIGEST",
    "MODEL_ID",
    "PROFILE_ID",
    "SCHEMA_VERSION",
    "SOURCE_PROFILE_ID",
    "PhosphositeFeature",
    "PhosphositeTransitionCatalog",
    "SparseBootstrapProjection",
    "load_phosphosite_transition_catalog",
]
