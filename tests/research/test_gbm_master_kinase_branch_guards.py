from __future__ import annotations

import hashlib
import io
import json
import sys
from collections import Counter
from dataclasses import replace
from typing import Any, cast

import numpy as np
import pytest
from pydantic import ValidationError

from glio_proteogen.adapters import gbm_master_kinases as adapter_module
from glio_proteogen.research.gbm_master_kinases import (
    AnalysisSupport,
    KinaseEvidence,
    MasterKinaseRequest,
    MasterKinaseResult,
    MethodAgreement,
    MethodEstimate,
    PhosphositeEvidenceState,
    PhosphositeObservation,
    RankEnrichmentEstimate,
    ReplayVerificationRequest,
    ReplayVerificationResult,
    StandardizedContrastReference,
    StateClassification,
    analyze_master_kinases,
    engine,
    synthetic_demo_request,
)
from glio_proteogen.research.gbm_master_kinases import catalog as catalog_module
from glio_proteogen.research.gbm_master_kinases import demo as demo_module
from glio_proteogen.research.gbm_master_kinases import profile as profile_module
from glio_proteogen.research.gbm_master_kinases import service as service_module
from glio_proteogen.research.gbm_master_kinases.canonical import (
    canonical_json_bytes,
    result_payload_digest,
    sha256_digest,
)
from glio_proteogen.research.gbm_master_kinases.errors import CatalogIntegrityError
from glio_proteogen.research.gbm_master_kinases.service import MasterKinaseService
from glio_proteogen.research.proteogenomic_state.cancellation import CancellationContext

PROVENANCE = sha256_digest({"test": "master-kinase-branch-guards"})


@pytest.fixture(scope="module")
def analyzed_demo() -> tuple[MasterKinaseRequest, MasterKinaseResult]:
    request = synthetic_demo_request()
    return request, analyze_master_kinases(request)


def _catalog_document() -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads(catalog_module._resource_bytes()))


def _install_catalog_variant(
    monkeypatch: pytest.MonkeyPatch,
    document: dict[str, Any],
    *,
    master_inventory_changed: bool = False,
    edge_inventory_changed: bool = False,
) -> None:
    source_digests = cast("dict[str, str]", document["source_digests"])
    if master_inventory_changed:
        digest = sha256_digest(document["master_kinases"])
        source_digests["master_kinase_digest"] = digest
        monkeypatch.setattr(catalog_module, "EXPECTED_MASTER_KINASE_DIGEST", digest)
    if edge_inventory_changed:
        digest = sha256_digest(document["signature_edges"])
        source_digests["signature_edge_digest"] = digest
        monkeypatch.setattr(catalog_module, "EXPECTED_SIGNATURE_EDGE_DIGEST", digest)
    raw = canonical_json_bytes(document)
    monkeypatch.setattr(
        catalog_module,
        "EXPECTED_CATALOG_ARTIFACT_DIGEST",
        "sha256:" + hashlib.sha256(raw).hexdigest(),
    )
    monkeypatch.setattr(catalog_module, "EXPECTED_CATALOG_CONTENT_DIGEST", sha256_digest(document))
    monkeypatch.setattr(catalog_module, "_resource_bytes", lambda: raw)
    catalog_module.master_kinase_catalog.cache_clear()


def _assert_catalog_rejected(message: str) -> None:
    try:
        with pytest.raises(CatalogIntegrityError, match=message):
            catalog_module.master_kinase_catalog()
    finally:
        catalog_module.master_kinase_catalog.cache_clear()


def test_catalog_rejects_digest_locked_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = b"{not-json"
    monkeypatch.setattr(
        catalog_module,
        "EXPECTED_CATALOG_ARTIFACT_DIGEST",
        "sha256:" + hashlib.sha256(raw).hexdigest(),
    )
    monkeypatch.setattr(catalog_module, "_resource_bytes", lambda: raw)
    catalog_module.master_kinase_catalog.cache_clear()
    _assert_catalog_rejected("not valid JSON")


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("schema", "unsupported .* schema"),
        ("provenance", "source provenance lock mismatch"),
        ("background_count", "background inventory mismatch"),
        ("background_digest", "background semantic digest mismatch"),
        ("alias_digest", "normalization lock mismatch"),
        ("source_table_digest", "Table 5d/e semantic digest mismatch"),
    ],
)
def test_catalog_rejects_each_metadata_lock(
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    message: str,
) -> None:
    document = _catalog_document()
    if case == "schema":
        document["schema_version"] = "unsupported/9.9.9"
    elif case == "provenance":
        cast("dict[str, Any]", document["source"])["license"] = "unknown"
    elif case == "background_count":
        cast("dict[str, Any]", document["background"])["tuple_count"] = 0
    elif case == "background_digest":
        cast("dict[str, Any]", document["background"])["tuple_digest"] = PROVENANCE
    elif case == "alias_digest":
        cast("dict[str, Any]", document["kinase_label_normalization"])["mapping_digest"] = (
            PROVENANCE
        )
    else:
        cast("dict[str, Any]", document["source_digests"])["master_kinase_digest"] = PROVENANCE
    _install_catalog_variant(monkeypatch, document)
    _assert_catalog_rejected(message)


def test_catalog_rejects_duplicate_background_tuples(monkeypatch: pytest.MonkeyPatch) -> None:
    document = _catalog_document()
    background = cast("dict[str, Any]", document["background"])
    tuples = cast("list[dict[str, Any]]", background["tuples"])
    tuples[1] = dict(tuples[0])
    _install_catalog_variant(monkeypatch, document)
    _assert_catalog_rejected("duplicate source tuples")


def test_catalog_rejects_invalid_master_inventory(monkeypatch: pytest.MonkeyPatch) -> None:
    document = _catalog_document()
    masters = cast("list[dict[str, Any]]", document["master_kinases"])
    masters[0]["subtype"] = "MTC"
    _install_catalog_variant(monkeypatch, document, master_inventory_changed=True)
    _assert_catalog_rejected("master-kinase inventory mismatch")


def test_catalog_rejects_duplicate_source_row_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    document = _catalog_document()
    edges = cast("list[dict[str, Any]]", document["signature_edges"])
    edges[1]["source_row_id"] = edges[0]["source_row_id"]
    _install_catalog_variant(monkeypatch, document, edge_inventory_changed=True)
    _assert_catalog_rejected("source row identities are not unique")


def test_catalog_rejects_invalid_subtype_edge_inventory(monkeypatch: pytest.MonkeyPatch) -> None:
    document = _catalog_document()
    edges = cast("list[dict[str, Any]]", document["signature_edges"])
    edges[0]["subtype"] = "MTC"
    _install_catalog_variant(monkeypatch, document, edge_inventory_changed=True)
    _assert_catalog_rejected("subtype edge inventory mismatch")


def test_catalog_rejects_signature_target_outside_background(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _catalog_document()
    edges = cast("list[dict[str, Any]]", document["signature_edges"])
    subtype_site_counts = Counter((edge["subtype"], edge["source_site_label"]) for edge in edges)
    edge = next(
        item
        for item in edges
        if subtype_site_counts[(item["subtype"], item["source_site_label"])] == 1
    )
    edge["source_site_label"] = "FORGED-S1s"
    _install_catalog_variant(monkeypatch, document, edge_inventory_changed=True)
    _assert_catalog_rejected("target is absent")


def test_catalog_rejects_changed_repeated_kinase_site_multiplicity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _catalog_document()
    edges = cast("list[dict[str, Any]]", document["signature_edges"])
    subtype_site_counts = Counter((edge["subtype"], edge["source_site_label"]) for edge in edges)
    pair_counts = Counter((edge["hgnc_symbol"], edge["source_site_label"]) for edge in edges)
    edge_by_pair = {(edge["hgnc_symbol"], edge["source_site_label"]): edge for edge in edges}
    source = next(
        item
        for item in edges
        if subtype_site_counts[(item["subtype"], item["source_site_label"])] > 1
        and pair_counts[(item["hgnc_symbol"], item["source_site_label"])] == 1
        and any(
            candidate["subtype"] == item["subtype"]
            and candidate["hgnc_symbol"] == item["hgnc_symbol"]
            and candidate["source_site_label"] != item["source_site_label"]
            for candidate in edges
        )
    )
    target = next(
        candidate
        for candidate in edges
        if candidate["subtype"] == source["subtype"]
        and candidate["hgnc_symbol"] == source["hgnc_symbol"]
        and candidate["source_site_label"] != source["source_site_label"]
        and (candidate["hgnc_symbol"], candidate["source_site_label"]) in edge_by_pair
    )
    source["source_site_label"] = target["source_site_label"]
    _install_catalog_variant(monkeypatch, document, edge_inventory_changed=True)
    _assert_catalog_rejected("repeated kinase-site source-row inventory mismatch")


def test_catalog_rejects_master_without_signature_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    document = _catalog_document()
    edges = cast("list[dict[str, Any]]", document["signature_edges"])
    for edge in edges:
        if edge["hgnc_symbol"] == "PHKG2":
            edge["hgnc_symbol"] = "UNMODELED"
    _install_catalog_variant(monkeypatch, document, edge_inventory_changed=True)
    _assert_catalog_rejected("master kinase has no .* signature rows")


def _valid_method_payload() -> dict[str, object]:
    return {
        "support": "supported",
        "score": 0.0,
        "lower_bound": -0.1,
        "upper_bound": 0.1,
        "effective_sample_size": 5.0,
        "bootstrap_replicates_requested": 16,
        "bootstrap_replicates_successful": 16,
        "bootstrap_replicates_used": 16,
        "reason": None,
    }


def _valid_rank_payload() -> dict[str, object]:
    return {
        **_valid_method_payload(),
        "mapped_signature_sites": 5,
        "observed_background_sites": 64,
        "permutation_replicates_used": 64,
        "null_standard_deviation": 0.2,
        "p_value": 0.5,
        "q_value": 0.5,
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"support": "abstained", "reason": "no evidence"},
        {
            "support": "abstained",
            "score": None,
            "lower_bound": None,
            "upper_bound": None,
            "reason": "no evidence",
        },
        {"score": None},
        {"reason": "unexpected"},
        {"support": "limited"},
        {"score": 0.5},
        {"bootstrap_replicates_requested": 15},
        {
            "bootstrap_replicates_requested": 0,
            "bootstrap_replicates_successful": 0,
            "bootstrap_replicates_used": 0,
        },
        {"bootstrap_replicates_used": 15},
    ],
)
def test_method_estimate_rejects_every_inconsistent_support_state(
    changes: dict[str, object],
) -> None:
    payload = {**_valid_method_payload(), **changes}
    with pytest.raises(ValidationError):
        MethodEstimate.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize(
    "changes",
    [
        {"support": "abstained", "reason": "no evidence"},
        {
            "support": "abstained",
            "score": None,
            "lower_bound": None,
            "upper_bound": None,
            "null_standard_deviation": None,
            "p_value": None,
            "q_value": None,
            "reason": "no evidence",
        },
        {
            "support": "abstained",
            "score": None,
            "lower_bound": None,
            "upper_bound": None,
            "permutation_replicates_used": 0,
            "null_standard_deviation": None,
            "p_value": None,
            "q_value": None,
            "reason": "no evidence",
        },
        {"score": None},
        {"reason": "unexpected"},
        {"support": "limited"},
        {"score": 0.5},
        {"bootstrap_replicates_requested": 15},
        {
            "bootstrap_replicates_requested": 0,
            "bootstrap_replicates_successful": 0,
            "bootstrap_replicates_used": 0,
        },
        {"bootstrap_replicates_used": 15},
    ],
)
def test_rank_estimate_rejects_every_inconsistent_support_state(
    changes: dict[str, object],
) -> None:
    payload = {**_valid_rank_payload(), **changes}
    with pytest.raises(ValidationError):
        RankEnrichmentEstimate.model_validate_json(json.dumps(payload))


def test_kinase_and_subtype_contracts_reject_support_classification_conflicts(
    analyzed_demo: tuple[MasterKinaseRequest, MasterKinaseResult],
) -> None:
    _request, result = analyzed_demo
    kinase = result.kinase_evidence[0].model_dump(mode="json")
    with pytest.raises(ValidationError, match="abstained kinases must be not_estimable"):
        KinaseEvidence.model_validate_json(json.dumps({**kinase, "support": "abstained"}))
    with pytest.raises(ValidationError, match="abstained kinases require reasons"):
        KinaseEvidence.model_validate_json(
            json.dumps(
                {
                    **kinase,
                    "support": "abstained",
                    "classification": "not_estimable",
                    "abstention_reasons": [],
                }
            )
        )
    with pytest.raises(ValidationError, match="estimated kinases cannot be not_estimable"):
        KinaseEvidence.model_validate_json(
            json.dumps({**kinase, "classification": "not_estimable"})
        )

    subtype_type = type(result.subtype_evidence[0])
    subtype = result.subtype_evidence[0].model_dump(mode="json")
    with pytest.raises(ValidationError, match="abstained subtypes must be not_estimable"):
        subtype_type.model_validate_json(json.dumps({**subtype, "support": "abstained"}))
    with pytest.raises(ValidationError, match="abstained subtypes require reasons"):
        subtype_type.model_validate_json(
            json.dumps(
                {
                    **subtype,
                    "support": "abstained",
                    "classification": "not_estimable",
                    "abstention_reasons": [],
                }
            )
        )
    with pytest.raises(ValidationError, match="estimated subtypes cannot be not_estimable"):
        subtype_type.model_validate_json(json.dumps({**subtype, "classification": "not_estimable"}))


def test_result_receipt_rejects_each_content_binding_failure(
    analyzed_demo: tuple[MasterKinaseRequest, MasterKinaseResult],
) -> None:
    _request, result = analyzed_demo

    profile_mismatch = result.model_dump(mode="json")
    profile_mismatch["profile_digest"] = PROVENANCE
    with pytest.raises(ValidationError, match="profile digest does not match provenance"):
        MasterKinaseResult.model_validate_json(json.dumps(profile_mismatch))

    request_mismatch = result.model_dump(mode="json")
    request_mismatch["request_digest"] = PROVENANCE
    with pytest.raises(ValidationError, match="request digest does not match provenance"):
        MasterKinaseResult.model_validate_json(json.dumps(request_mismatch))

    digest_mismatch = result.model_dump(mode="json")
    digest_mismatch["sample_id"] = "digest-mismatch"
    with pytest.raises(ValidationError, match="result digest does not match"):
        MasterKinaseResult.model_validate_json(json.dumps(digest_mismatch))

    duplicate_kinase = result.model_dump(mode="json")
    duplicate_kinase["kinase_evidence"][1]["kinase_id"] = duplicate_kinase["kinase_evidence"][0][
        "kinase_id"
    ]
    duplicate_kinase["result_digest"] = result_payload_digest(duplicate_kinase)
    with pytest.raises(ValidationError, match="kinase result identifiers must be unique"):
        MasterKinaseResult.model_validate_json(json.dumps(duplicate_kinase))

    duplicate_subtype = result.model_dump(mode="json")
    duplicate_subtype["subtype_evidence"][1]["subtype_id"] = duplicate_subtype["subtype_evidence"][
        0
    ]["subtype_id"]
    duplicate_subtype["result_digest"] = result_payload_digest(duplicate_subtype)
    with pytest.raises(ValidationError, match="subtype result identifiers must be unique"):
        MasterKinaseResult.model_validate_json(json.dumps(duplicate_subtype))


def test_demo_fills_less_than_128_background_sites_and_builder_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = catalog_module.master_kinase_catalog()
    signature_sites = frozenset(edge.source_site_label for edge in catalog.edges)
    reduced_catalog = replace(catalog, background_labels=signature_sites)
    demo_module.synthetic_demo_request.cache_clear()
    monkeypatch.setattr(demo_module, "master_kinase_catalog", lambda: reduced_catalog)
    try:
        request = demo_module.synthetic_demo_request()
        assert (
            sum(item.observation_id.startswith("demo.background") for item in request.observations)
            == 0
        )
        assert demo_module.build_demo_request() is request
    finally:
        demo_module.synthetic_demo_request.cache_clear()


def _contrast() -> StandardizedContrastReference:
    return StandardizedContrastReference(
        contrast_id="branch.guard.contrast",
        numerator_label="case",
        denominator_label="reference",
    )


def _observation(
    site: str,
    index: int,
    effect: float,
    state: PhosphositeEvidenceState,
) -> PhosphositeObservation:
    return PhosphositeObservation(
        observation_id=f"branch.obs.{index}",
        phosphosite_id=site,
        state=state,
        standardized_effect=effect,
        standard_error=0.25,
        quality_weight=1.0,
        provenance_digest=PROVENANCE,
    )


def test_location_numeric_guards_and_two_observed_site_limitation() -> None:
    assert engine._effective_sample_size((0.0, -1.0)) == 0.0
    master = next(
        item
        for item in catalog_module.master_kinase_catalog().masters
        if item.hgnc_symbol == "PRKCD"
    )
    specs = engine._site_specs(master)[:3]
    request = MasterKinaseRequest(
        sample_id="two-observed-plus-censor",
        observations=(
            _observation(specs[0].phosphosite_id, 1, 1.0, PhosphositeEvidenceState.OBSERVED),
            _observation(specs[1].phosphosite_id, 2, 1.0, PhosphositeEvidenceState.OBSERVED),
            _observation(
                specs[2].phosphosite_id,
                3,
                0.0,
                PhosphositeEvidenceState.LEFT_CENSORED,
            ),
        ),
        bootstrap_replicates=16,
        permutation_replicates=64,
        contrast_reference=_contrast(),
    )
    raw = engine._robust_location(specs, engine._observation_map(request))
    assert raw.score is not None
    assert raw.support is AnalysisSupport.LIMITED
    assert "fewer than three directly observed" in cast("str", raw.reason)


def test_interval_classification_agreement_and_neutral_discordance_guards() -> None:
    assert engine._interval(0.4, ()) == (0.4, 0.4)
    neutral = MethodEstimate(
        support=AnalysisSupport.SUPPORTED,
        score=0.0,
        lower_bound=-0.1,
        upper_bound=0.1,
        effective_sample_size=5.0,
        bootstrap_replicates_requested=16,
        bootstrap_replicates_successful=16,
        bootstrap_replicates_used=16,
    )
    indeterminate = neutral.model_copy(update={"lower_bound": -0.5, "upper_bound": 0.5})
    assert engine._classification(neutral) is StateClassification.NEUTRAL
    assert engine._classification(indeterminate) is StateClassification.INDETERMINATE

    positive = neutral.model_copy(update={"score": 0.6, "lower_bound": 0.5, "upper_bound": 0.7})
    negative_rank = RankEnrichmentEstimate(
        support=AnalysisSupport.SUPPORTED,
        score=-0.6,
        lower_bound=-0.7,
        upper_bound=-0.5,
        effective_sample_size=5.0,
        bootstrap_replicates_requested=16,
        bootstrap_replicates_successful=16,
        bootstrap_replicates_used=16,
        mapped_signature_sites=5,
        observed_background_sites=64,
        permutation_replicates_used=64,
        null_standard_deviation=0.2,
        p_value=0.01,
        q_value=0.01,
    )
    assert engine._agreement(positive, negative_rank) is MethodAgreement.DISCORDANT
    neutral_rank = negative_rank.model_copy(
        update={"score": 0.0, "lower_bound": -0.1, "upper_bound": 0.1}
    )
    assert engine._agreement(positive, neutral_rank) is MethodAgreement.UNCERTAIN
    assert engine._stability(None, [1.0]) is None

    spec = engine._SiteSpec("A-S1s", (), 1.0, "S")
    supporting = tuple(
        (
            spec,
            engine._Observation(
                f"neutral.{index}",
                f"A-S{index}s",
                PhosphositeEvidenceState.OBSERVED,
                effect,
                0.25,
                1.0,
                PROVENANCE,
                "S",
            ),
            1.0,
        )
        for index, effect in enumerate((-1.0, 0.0, 1.0), start=1)
    )
    raw = engine._RawLocation(
        AnalysisSupport.SUPPORTED,
        0.0,
        3.0,
        None,
        supporting,
        supporting,
    )
    assert engine._discordance(raw) == pytest.approx(2 / 3)


def test_bootstrap_tracks_enforce_identity_and_profile_success_gate() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        engine._bootstrap_support(AnalysisSupport.SUPPORTED, None, [], 0)
    with pytest.raises(ValueError, match="track length"):
        engine._bootstrap_support(AnalysisSupport.SUPPORTED, None, [1.0], 2)

    support, reason, successful = engine._bootstrap_support(
        AnalysisSupport.SUPPORTED,
        None,
        [1.0, 1.1, 0.9, 1.05, None],
        5,
    )
    assert support is AnalysisSupport.LIMITED
    assert reason == "bootstrap success fraction 4/5 is incomplete"
    assert successful == (1.0, 1.1, 0.9, 1.05)

    raw_location = engine._RawLocation(
        AnalysisSupport.SUPPORTED,
        1.0,
        4.0,
        None,
        (),
        (),
    )
    with pytest.raises(ValueError, match="location bootstrap track length"):
        engine._method_estimate(raw_location, [1.0], 2)
    location = engine._method_estimate(raw_location, [1.0, None], 2)
    assert location.support is AnalysisSupport.ABSTAINED
    assert location.bootstrap_replicates_requested == 2
    assert location.bootstrap_replicates_successful == 1
    assert location.bootstrap_replicates_used == 0

    raw_rank = engine._RawRank(
        AnalysisSupport.SUPPORTED,
        0.5,
        4.0,
        None,
        (),
        64,
    )
    with pytest.raises(ValueError, match="rank bootstrap track length"):
        engine._rank_estimate(
            raw_rank,
            [0.5],
            requested=2,
            nulls=[0.0],
            q_value=0.1,
        )
    rank = engine._rank_estimate(
        raw_rank,
        [0.5, None],
        requested=2,
        nulls=[0.0],
        q_value=0.1,
    )
    assert rank.support is AnalysisSupport.ABSTAINED
    assert rank.bootstrap_replicates_requested == 2
    assert rank.bootstrap_replicates_successful == 1
    assert rank.bootstrap_replicates_used == 0


def test_subtype_pooling_rejects_malformed_and_preserves_incomplete_track_identity(
    analyzed_demo: tuple[MasterKinaseRequest, MasterKinaseResult],
) -> None:
    _request, result = analyzed_demo
    samples = {
        item.kinase_id: [item.location.score] if item.location.score is not None else []
        for item in result.kinase_evidence
    }
    first_gpm = next(item for item in result.kinase_evidence if item.source_subtype.value == "GPM")
    samples[first_gpm.kinase_id] = []
    with pytest.raises(ValueError, match="bootstrap track does not match"):
        engine._subtype_outputs(
            catalog_module.master_kinase_catalog().masters,
            result.kinase_evidence,
            samples,
            2,
        )

    samples = {
        item.kinase_id: [cast("float", item.location.score)] * 2
        if item.location.score is not None
        else [None, None]
        for item in result.kinase_evidence
    }
    samples[first_gpm.kinase_id] = [None, cast("float", first_gpm.location.score)]
    outputs = engine._subtype_outputs(
        catalog_module.master_kinase_catalog().masters,
        result.kinase_evidence,
        samples,
        2,
    )
    gpm = next(item for item in outputs if item.subtype_id.value == "GPM")
    assert gpm.support is AnalysisSupport.ABSTAINED
    assert gpm.aggregate.bootstrap_replicates_requested == 2
    assert gpm.aggregate.bootstrap_replicates_successful == 1
    assert gpm.aggregate.bootstrap_replicates_used == 0


def test_subtype_pooling_marks_less_than_half_coverage_limited(
    analyzed_demo: tuple[MasterKinaseRequest, MasterKinaseResult],
) -> None:
    _request, result = analyzed_demo
    gpm_ids = [
        item.kinase_id for item in result.kinase_evidence if item.source_subtype.value == "GPM"
    ]
    retained = gpm_ids[0]
    abstained_location = MethodEstimate(
        support=AnalysisSupport.ABSTAINED,
        effective_sample_size=0.0,
        bootstrap_replicates_requested=1,
        bootstrap_replicates_successful=0,
        bootstrap_replicates_used=0,
        reason="no evidence in branch-guard fixture",
    )
    kinase_outputs = tuple(
        item
        if item.kinase_id not in set(gpm_ids[1:])
        else item.model_copy(
            update={
                "support": AnalysisSupport.ABSTAINED,
                "classification": StateClassification.NOT_ESTIMABLE,
                "location": abstained_location,
                "abstention_reasons": ("no evidence in branch-guard fixture",),
            }
        )
        for item in result.kinase_evidence
    )
    samples = {
        item.kinase_id: [item.location.score] if item.location.score is not None else []
        for item in kinase_outputs
    }
    outputs = engine._subtype_outputs(
        catalog_module.master_kinase_catalog().masters,
        kinase_outputs,
        samples,
        1,
    )
    gpm = next(item for item in outputs if item.subtype_id.value == "GPM")
    assert gpm.estimated_member_count == 1
    assert gpm.top_kinases[0].kinase_id == retained
    assert "fewer than half" in cast("str", gpm.aggregate.reason)


def test_profile_rejects_unbound_numpy_version(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(np, "__version__", "0.0.0")
    with pytest.raises(RuntimeError, match=r"requires NumPy 2\.5\.2"):
        profile_module.algorithm_profile()


def test_service_object_delegates_analysis_and_verification(
    monkeypatch: pytest.MonkeyPatch,
    analyzed_demo: tuple[MasterKinaseRequest, MasterKinaseResult],
) -> None:
    request, result = analyzed_demo
    cancellation = CancellationContext()
    analyze_calls: list[tuple[MasterKinaseRequest, CancellationContext | None]] = []

    def fake_analyze(
        value: MasterKinaseRequest,
        *,
        cancellation: CancellationContext | None = None,
    ) -> MasterKinaseResult:
        analyze_calls.append((value, cancellation))
        return result

    monkeypatch.setattr(service_module, "infer_master_kinases", fake_analyze)
    assert MasterKinaseService().analyze(request, cancellation=cancellation) is result
    assert analyze_calls == [(request, cancellation)]

    verification = ReplayVerificationRequest(request=request, result=result)
    expected = ReplayVerificationResult(
        verified=True,
        request_digest_match=True,
        profile_digest_match=True,
        result_digest_match=True,
        semantic_match=True,
        recomputed_request_digest=request.request_digest,
        recomputed_result_digest=result.result_digest,
        message="delegated",
    )
    verify_calls: list[tuple[ReplayVerificationRequest, CancellationContext | None]] = []

    def fake_verify(
        value: ReplayVerificationRequest,
        *,
        cancellation: CancellationContext | None = None,
    ) -> ReplayVerificationResult:
        verify_calls.append((value, cancellation))
        return expected

    monkeypatch.setattr(service_module, "verify_replay", fake_verify)
    assert MasterKinaseService().verify(verification, cancellation=cancellation) is expected
    assert verify_calls == [(verification, cancellation)]


def test_cli_emitter_preserves_unicode_without_a_binary_stdout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream = io.StringIO()
    monkeypatch.setattr(sys, "stdout", stream)
    adapter_module._emit({"kinase": "PKCδ"})
    assert json.loads(stream.getvalue()) == {"kinase": "PKCδ"}
