from __future__ import annotations

import hashlib
import json
import re
from dataclasses import replace
from pathlib import Path
from typing import cast

import numpy as np
import pytest

from glio_proteogen.research.longitudinal_gbm_phospho import (
    load_phosphosite_transition_catalog,
)
from tools import import_kncc_longitudinal_phospho as importer

WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
RAW_SOURCE_DIR = (
    WORKSPACE_ROOT
    / ".tmp-longitudinal-gbm-phospho-source"
    / "PDC000515-v1-e5e0dd84-f982-46e3-b78a-5cb19eef31a8"
)
RAW_HGNC_SOURCE = WORKSPACE_ROOT / ".tmp-neftel-source" / "hgnc_complete_set.txt"
ARTIFACT_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "glio_proteogen"
    / "research"
    / "longitudinal_gbm_phospho"
    / "data"
    / "kncc_paired_phosphosite_transition.v1.json"
)


def _walk(value: object, path: str = "") -> list[tuple[str, object]]:
    result = [(path, value)]
    if isinstance(value, dict):
        for key, child in value.items():
            result.extend(_walk(child, f"{path}.{key}" if path else str(key)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            result.extend(_walk(child, f"{path}[{index}]"))
    return result


def _synthetic_cohort() -> importer.PhosphositeCohort:
    rng = np.random.default_rng(20260829)
    pair_count = 20
    site_count = 40
    signal = np.linspace(-0.8, 1.0, site_count)
    delta = signal + rng.normal(0.0, 0.15, size=(pair_count, site_count))
    delta[0, :12] = np.nan
    delta[:, 0] = np.nan
    delta[0, 0] = -0.75
    return importer.PhosphositeCohort(
        site_groups=tuple(f"ENSP{index:011d}.1:s1" for index in range(site_count)),
        source_genes=tuple(f"G{index:03d}" for index in range(site_count)),
        approved_genes=tuple(f"G{index:03d}" for index in range(site_count)),
        hgnc_ids=tuple(f"HGNC:{index + 1}" for index in range(site_count)),
        gene_mapping_basis=("approved_symbol",) * site_count,
        modified_peptides=(("S*AAA",),) * site_count,
        sphinks_labels=(None,) * site_count,
        signature_kinases=((),) * site_count,
        patient_groups=tuple(f"private-group-{index:03d}" for index in range(pair_count)),
        delta=delta,
        private_identifiers=frozenset(f"private-group-{index:03d}" for index in range(pair_count)),
        crosswalk_metadata={
            "hgnc": {"mapping_digest": "sha256:" + "1" * 64},
            "sphinks": {
                "crosswalk_digest": "sha256:" + "2" * 64,
                "source_article_authors": "Synthetic test fixture",
                "source_article_title": "Synthetic test fixture",
                "source_article_doi": "10.0000/synthetic-test-fixture",
                "source_license": "CC-BY-4.0",
                "source_license_url": "https://creativecommons.org/licenses/by/4.0/",
                "source_transformation_notice": "Synthetic test-only crosswalk.",
            },
        },
        oracles={"strict_t1_t2_pairs": pair_count},
    )


def test_exact_study_and_six_file_source_locks() -> None:
    assert importer.PDC_STUDY_ID == "PDC000515"
    assert importer.PDC_STUDY_VERSION_UUID == "e5e0dd84-f982-46e3-b78a-5cb19eef31a8"
    assert importer.PDC_SOURCE_MANIFEST_BYTES == 708_545
    assert importer.PDC_SOURCE_MANIFEST_SHA256 == (
        "1b248983791886a9b4522de07d96abb517c416d793b789d435544745dbe6ed34"
    )
    assert (
        importer.SourceFileLock(
            "KNCC_Glioblastoma_Evolution_Phosphoproteome.label.txt",
            "ee9b645e-092e-4d94-9fb6-0b936e125039",
            522,
            "4e6cc0cb78f8e9143abd078694c2e610",
            "83f55a385bcc88d8780a75a8535c1e319e1c30633ff700e15ad87df5ae3792f4",
        ),
        importer.SourceFileLock(
            "KNCC_Glioblastoma_Evolution_Phosphoproteome.peptides.tsv",
            "61f74ed4-77b0-40b9-aa7b-b6eadc0673cd",
            63_695_733,
            "e17edd5ac8b045dae10ee900c5f18bbb",
            "c8c419582bf4a1e3c011f9c35cf7cbe453bda566f4e18364e9bb6d92e32a206e",
        ),
        importer.SourceFileLock(
            "KNCC_Glioblastoma_Evolution_Phosphoproteome.phosphopeptide.tmt11.tsv",
            "0bfd4904-153a-4eb0-ae99-7e9667fe79e4",
            39_476_036,
            "53fc6e9689d48dcc0875947787b40faf",
            "d513fe4ca28b70f873d28ecab563c758a1ffd3fb903fd5ebe7eba2f97b43eba8",
        ),
        importer.SourceFileLock(
            "KNCC_Glioblastoma_Evolution_Phosphoproteome.phosphosite.tmt11.tsv",
            "dd668a70-2c1d-413e-b439-50d7aa47fd74",
            35_462_701,
            "367c076701733fd37b1965f3cb65bd18",
            "0bae05b8b80ea68d62acd25d89d2fef4b33d06a747dc8d89399ead62780c29fe",
        ),
        importer.SourceFileLock(
            "KNCC_Glioblastoma_Evolution_Phosphoproteome.sample.txt",
            "355422f5-e199-4f02-a37e-17e9791bc49e",
            203_737,
            "0768c7087da1c0b354ea6208b1ff5c77",
            "71e6b8e88cb1920b6792c3c7c712fe740516d838b9c7fa8fe5d1c9ccbb82bef1",
        ),
        importer.SourceFileLock(
            "KNCC_Glioblastoma_Evolution_Phosphoproteome.summary.tsv",
            "73e6eb70-7489-4469-ac7f-20ac095fa63d",
            3_160_731,
            "e5f6e2dea921a9560a5e63b03ce5b345",
            "e79c8220875713eee3d9ab7956329e1d54b748a0382f0c40abddc6e21f628c3c",
        ),
    ) == importer.SOURCE_FILES
    assert sum(lock.bytes for lock in importer.SOURCE_FILES) == 141_999_460


@pytest.mark.skipif(
    not RAW_SOURCE_DIR.is_dir() or not RAW_HGNC_SOURCE.is_file(),
    reason="raw source-locked PDC000515/HGNC inputs are external",
)
def test_local_source_manifest_and_streaming_cohort_oracles_are_exact() -> None:
    metadata = importer.verify_versioned_source_manifest(RAW_SOURCE_DIR)
    cohort = importer.load_cohort(RAW_SOURCE_DIR, RAW_HGNC_SOURCE)
    assert len(metadata.private_identifiers) > 180
    assert cohort.delta.shape == (88, 24_015)
    assert cohort.oracles == {
        "analytical_samples": 22,
        "biological_measurement_channels": 185,
        "duplicated_specimens": 7,
        "extra_technical_channels": 7,
        "finite_paired_deltas": 588_984,
        "fractions_per_analytical_sample": 12,
        "matrix_columns": 224,
        "matrix_rows": 24_015,
        "measurement_channels": 220,
        "multi_peptide_rows": 5_221,
        "nominal_complete_pairs": 89,
        "non_biological_measurement_channels": 35,
        "official_experimental_design_rows": 22,
        "official_protein_assembly_bytes": 141_999_460,
        "official_protocol_records": 1,
        "official_sample_type_mismatch_patient_groups": 1,
        "official_total_file_bytes": 1_272_495_437_200,
        "official_versioned_biological_specimens": 178,
        "official_versioned_biospecimen_records": 180,
        "official_versioned_file_records": 1_064,
        "paired_support_max": 88,
        "paired_support_median": 12.0,
        "paired_support_min": 0,
        "sample_map_rows": 264,
        "sample_type_mismatch_pairs_excluded": 1,
        "single_site_rows": 21_475,
        "sites_with_at_least_half_pairs": 5_206,
        "sites_with_at_least_sixty_percent_pairs": 4_225,
        "sites_with_at_least_three_pairs": 21_990,
        "source_biological_specimens": 178,
        "strict_t1_t2_pairs": 88,
        "three_site_composite_rows": 250,
        "two_site_composite_rows": 2_290,
    }
    hgnc = cast("dict[str, object]", cohort.crosswalk_metadata["hgnc"])
    sphinks = cast("dict[str, object]", cohort.crosswalk_metadata["sphinks"])
    assert hgnc["mapping_digest"] == (
        "sha256:07245f3fe73129607856b1a92671cce13932a53c95a19f16894daf4971449aa4"
    )
    assert hgnc["mapping_counts"] == {"approved_symbol": 23_864, "previous_symbol": 151}
    assert hgnc["authority_url"] == (
        "https://storage.googleapis.com/public-download-files/hgnc/tsv/tsv/hgnc_complete_set.txt"
    )
    assert hgnc["authority_license"] == "CC0-1.0"
    assert hgnc["authority_release_identifier"] is None
    assert hgnc["authority_retrieval_date"] is None
    assert sphinks["crosswalk_digest"] == (
        "sha256:4d9d62c63361f285b45fff380588b37174663bfc702cef0587b705aaadebe8c4"
    )
    assert sphinks["exact_site_peptide_rows"] == 8_779
    assert sphinks["signature_rows"] == 608
    assert cohort.source_attestation == importer._expected_source_attestation()
    assert cohort.source_attestation.cohort_semantic_digest == (
        importer.EXPECTED_COHORT_SEMANTIC_DIGEST
    )
    assert cohort.delta.flags.writeable is False
    with pytest.raises(ValueError, match="read-only"):
        cohort.delta[0, 0] = 0.0

    tampered_delta = cohort.delta.copy()
    tampered_delta[0, 0] = 0.0
    tampered_delta.setflags(write=False)
    with pytest.raises(ValueError, match="semantic digest changed"):
        importer.build_artifact(replace(cohort, delta=tampered_delta), bootstrap_replicates=1)


def test_missing_and_technical_repeat_collapse_never_create_zero_observations() -> None:
    raw = np.asarray(
        [[1.0, 3.0], [np.nan, 2.0], [4.0, np.nan], [np.nan, np.nan]],
        dtype=np.float64,
    )
    collapsed = importer._collapse_columns(raw, [0, 1])
    assert collapsed[:3].tolist() == [2.0, 2.0, 4.0]
    assert np.isnan(collapsed[3])
    assert np.isnan(importer._float_cell(""))
    with pytest.raises(ValueError, match="non-finite"):
        importer._float_cell("nan")


def test_composite_site_and_modified_peptide_crosswalk_is_lossless() -> None:
    assert importer._site_cardinality("ENSP00000000001.1:s12t15y18") == 3
    assert importer._direct_sphinks_label("GENE", "ENSP00000000001.1:s12t15y18") == (
        "GENE-S12sT15tY18y"
    )
    assert importer._convert_modified_peptide("AAsBTtYy") == "AAS*BTT*YY*"
    with pytest.raises(ValueError, match="lowercase"):
        importer._convert_modified_peptide("AaS")


def test_synthetic_nested_fit_is_deterministic_and_never_silently_fuses() -> None:
    cohort = _synthetic_cohort()
    first = importer._build_unattested_artifact_for_tests(cohort, bootstrap_replicates=4)
    second = importer._build_unattested_artifact_for_tests(cohort, bootstrap_replicates=4)
    reversed_cohort = replace(
        cohort,
        patient_groups=cohort.patient_groups[::-1],
        delta=cohort.delta[::-1].copy(),
    )
    reordered = importer._build_unattested_artifact_for_tests(
        reversed_cohort, bootstrap_replicates=4
    )
    assert importer._canonical_bytes(first) == importer._canonical_bytes(second)
    assert importer._canonical_bytes(first) == importer._canonical_bytes(reordered)
    assert first["occupancy_like_view"] == {
        "reason": (
            "cognate-protein adjustment is deliberately deferred until its own "
            "training-fold-only implementation and outer-CV tests are complete"
        ),
        "silent_fusion": False,
        "support": "not_fitted",
    }
    evaluation = cast("dict[str, object]", first["fit_evaluation"])
    assert evaluation["supported_pairs"] == 20
    assert "not clinical prediction" in str(evaluation["interpretation"])
    assert not any("oob" in path.lower() for path, _ in _walk(first))
    assert b"private-group" not in importer._canonical_bytes(first)
    bootstrap = cast("dict[str, object]", first["bootstrap"])
    assert "exact per-replicate Huber" in str(bootstrap["method"])
    quality_gates = cast("dict[str, object]", first["runtime_quality_gates"])
    assert quality_gates["bootstrap_full_refit_passed"] is True
    assert quality_gates["bootstrap_calibration_passed"] is False
    first_feature = cast("list[dict[str, object]]", first["features"])[0]
    assert first_feature["paired_support"] == 1
    assert first_feature["numerical_release_state"] == "suppressed_insufficient_support"
    assert first_feature["transition_center"] is None
    assert first_feature["transition_scale"] is None


def test_production_builder_and_writer_reject_unattested_cohorts(
    tmp_path: Path,
) -> None:
    cohort = _synthetic_cohort()
    with pytest.raises(ValueError, match="must be immutable"):
        importer.build_artifact(cohort, bootstrap_replicates=1)

    forged_delta = cohort.delta.copy()
    forged_delta.setflags(write=False)
    forged = replace(
        cohort,
        delta=forged_delta,
        source_attestation=importer._expected_source_attestation(),
    )
    with pytest.raises(ValueError, match="semantic digest changed"):
        importer.build_artifact(forged, bootstrap_replicates=1)

    test_only = importer._build_unattested_artifact_for_tests(cohort, bootstrap_replicates=1)
    assert test_only["source_attestation_state"] == "unattested_test_only"
    with pytest.raises(ValueError, match="refusing to write"):
        importer.write_artifact(test_only, tmp_path / "forged.json")
    assert not (tmp_path / "forged.json").exists()


def test_nested_cv_fit_spy_never_sees_an_outer_held_patient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cohort = _synthetic_cohort()
    marked_delta = cohort.delta.copy()
    marked_delta[:, 0] = np.arange(len(cohort.patient_groups), dtype=np.float64)
    cohort = replace(cohort, delta=marked_delta)
    original_fit = importer._fit_axis
    fit_patient_markers: list[set[int]] = []

    def spy(delta: importer.FloatArray, labels: tuple[str, ...]) -> importer.AxisFit:
        fit_patient_markers.append({int(value) for value in delta[:, 0]})
        return original_fit(delta, labels)

    monkeypatch.setattr(importer, "_fit_axis", spy)
    importer._nested_cross_validation(cohort)
    nested_calls = importer.OUTER_FOLDS * (importer.INNER_FOLDS + 1)
    stability_calls = importer.SELECTION_STABILITY_REPEATS * importer.SELECTION_STABILITY_FOLDS
    expected_calls = nested_calls + stability_calls
    assert len(fit_patient_markers) == expected_calls
    outer = importer._folds(cohort.patient_groups, importer.OUTER_FOLDS, "pdc000515-outer-v2")
    all_markers = set(range(len(cohort.patient_groups)))
    for outer_index, held in enumerate(outer):
        held_markers = {int(value) for value in held}
        start = outer_index * (importer.INNER_FOLDS + 1)
        block = fit_patient_markers[start : start + importer.INNER_FOLDS + 1]
        assert all(markers.isdisjoint(held_markers) for markers in block)
        assert block[-1] == all_markers - held_markers
        assert all(markers < all_markers - held_markers for markers in block[:-1])

    offset = nested_calls
    for repeat in range(importer.SELECTION_STABILITY_REPEATS):
        folds = importer._folds(
            cohort.patient_groups,
            importer.SELECTION_STABILITY_FOLDS,
            f"pdc000515-selection-stability-v2:{repeat}",
        )
        for held in folds:
            assert fit_patient_markers[offset] == all_markers - {int(value) for value in held}
            offset += 1
    assert offset == expected_calls


def test_one_standard_error_selection_prefers_the_smallest_coverage_matched_model() -> None:
    summaries = {
        32: importer._candidate_summary(
            [1.0] * 74 + [-1.0] * 14, total_pairs=88, top_feature_count=32
        ),
        64: importer._candidate_summary(
            [1.0] * 75 + [-1.0] * 13, total_pairs=88, top_feature_count=64
        ),
        128: importer._candidate_summary(
            [1.0] * 76 + [-1.0] * 12, total_pairs=88, top_feature_count=128
        ),
        256: importer._candidate_summary(
            [1.0] * 77 + [-1.0] * 11, total_pairs=88, top_feature_count=256
        ),
    }

    selected, decision = importer._one_standard_error_choice(summaries)

    assert selected == 32
    assert decision["best_accuracy_candidate"] == 256
    assert decision["admissible_feature_counts"] == [32, 64, 128, 256]


def test_partition_stability_uses_modal_repeats_without_pseudoreplication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cohort = _synthetic_cohort()
    summaries = {
        count: importer._candidate_summary(
            [1.0] * 68 + [-1.0] * 20,
            total_pairs=88,
            top_feature_count=count,
        )
        for count in importer.TOP_FEATURE_CANDIDATES
    }
    choices = iter([32] * 17 + [64] * 3)

    monkeypatch.setattr(
        importer,
        "_cross_validated_candidate_summaries",
        lambda _cohort, *, fold_count, salt: summaries,
    )
    monkeypatch.setattr(
        importer,
        "_one_standard_error_choice",
        lambda _summaries: (next(choices), {"rule": "controlled test choice"}),
    )

    selected, stability = importer._selection_partition_stability(cohort)

    assert selected == 32
    assert stability["selection_counts"] == {"32": 17, "64": 3, "128": 0, "256": 0}
    assert stability["modal_fraction"] == 0.85
    interval = cast("list[float]", stability["modal_fraction_wilson_95_interval"])
    assert interval[0] > importer.SELECTION_STABILITY_WILSON_LOWER_MINIMUM
    assert stability["passed"] is True
    assert "never used as a binomial sample size" in str(stability["independence_guard"])
    assert "aggregate_decision" not in stability


def test_bootstrap_exactly_refits_each_patient_resample(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cohort = _synthetic_cohort()
    fit = importer._fit_axis(cohort.delta, cohort.site_groups)
    original_fit = importer._fit_axis
    refit_rows: list[int] = []

    def spy(delta: importer.FloatArray, labels: tuple[str, ...]) -> importer.AxisFit:
        refit_rows.append(delta.shape[0])
        return original_fit(delta, labels)

    monkeypatch.setattr(importer, "_fit_axis", spy)
    _stability, _intervals, bootstrap = importer._bootstrap(cohort, fit, 32, 4)

    assert refit_rows == [len(cohort.patient_groups)] * 4
    assert bootstrap["all_refits_converged"] is True
    assert "exact per-replicate Huber" in str(bootstrap["method"])
    assert "not coverage-calibrated" in str(bootstrap["interval"])
    replicates = cast("list[dict[str, object]]", bootstrap["replicates"])
    assert len(replicates) == 4
    assert all(item["fit_converged"] is True for item in replicates)
    assert all(len(cast("list[float]", item["scales"])) == 32 for item in replicates)
    assert all(
        all(value > 0.0 for value in cast("list[float]", item["scales"])) for item in replicates
    )


def test_cli_main_reads_the_sealed_receipt_document(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cohort = _synthetic_cohort()
    destination = tmp_path / "artifact.json"
    document: dict[str, object] = {
        "artifact_digest": "sha256:" + "a" * 64,
        "profile_digest": "sha256:" + "b" * 64,
    }
    receipt = importer.AttestedArtifact(
        document=document,
        canonical_payload=b"sealed\n",
        private_identifiers=frozenset(),
        capability=object(),
    )

    monkeypatch.setattr(importer, "load_cohort", lambda _source, _hgnc: cohort)
    monkeypatch.setattr(
        importer,
        "build_artifact",
        lambda _cohort, *, bootstrap_replicates: receipt,
    )

    def fake_write(_receipt: object, output: Path) -> None:
        output.write_bytes(b"sealed\n")

    monkeypatch.setattr(importer, "write_artifact", fake_write)
    monkeypatch.setattr(
        "sys.argv",
        [
            "import_kncc_longitudinal_phospho.py",
            "--source-dir",
            str(tmp_path),
            "--hgnc-source",
            str(tmp_path / "hgnc.tsv"),
            "--output",
            str(destination),
            "--bootstrap-replicates",
            "7",
        ],
    )

    assert importer.main() == 0
    output = cast("dict[str, object]", json.loads(capsys.readouterr().out))
    assert output["artifact_digest"] == document["artifact_digest"]
    assert output["profile_digest"] == document["profile_digest"]
    assert output["bootstrap_replicates"] == 7


@pytest.mark.skipif(
    not (RAW_SOURCE_DIR / importer.PDC_SOURCE_MANIFEST_FILENAME).is_file(),
    reason="external canonical source manifest is absent",
)
def test_saved_manifest_has_exact_queries_oracles_and_no_signed_urls() -> None:
    path = RAW_SOURCE_DIR / importer.PDC_SOURCE_MANIFEST_FILENAME
    payload = path.read_bytes()
    assert len(payload) == importer.PDC_SOURCE_MANIFEST_BYTES
    assert hashlib.sha256(payload).hexdigest() == importer.PDC_SOURCE_MANIFEST_SHA256
    document = cast("dict[str, object]", json.loads(payload))
    assert importer._canonical_bytes(document) == payload
    queries = cast("dict[str, object]", document["query_provenance"])
    assert queries == {
        "experimental_design": importer.PDC_EXPERIMENTAL_DESIGN_QUERY,
        "study_catalog": importer.PDC_STUDY_CATALOG_QUERY,
        "versioned_biospecimens": importer.PDC_VERSIONED_BIOSPECIMEN_QUERY,
        "versioned_files": importer.PDC_VERSIONED_FILES_QUERY,
        "versioned_protocol": importer.PDC_VERSIONED_PROTOCOL_QUERY,
        "versioned_study": importer.PDC_VERSIONED_STUDY_QUERY,
    }
    responses = cast("dict[str, object]", document["responses"])
    assert len(cast("list[object]", responses["study_catalog"])) == 1
    assert len(cast("list[object]", responses["versioned_study"])) == 1
    assert len(cast("list[object]", responses["versioned_biospecimens"])) == 180
    assert len(cast("list[object]", responses["versioned_files"])) == 1_064
    assert len(cast("list[object]", responses["versioned_protocol"])) == 1
    assert len(cast("list[object]", responses["experimental_design"])) == 22
    assert not any(path.endswith("signedUrl") for path, _ in _walk(document))
    assert b'"signedUrl"' not in payload


@pytest.mark.skipif(not ARTIFACT_PATH.is_file(), reason="fitted artifact has not been built")
def test_packaged_artifact_is_canonical_digest_locked_and_exhaustively_private() -> None:
    payload = ARTIFACT_PATH.read_bytes()
    artifact = cast("dict[str, object]", json.loads(payload))
    assert len(payload) == 14_712_589
    assert hashlib.sha256(payload).hexdigest() == (
        "5060d34d214582395f55ef66f9026303f781019230e91cd01d51d60c4fd6255e"
    )
    assert artifact["profile_digest"] == (
        "sha256:81901f97d258f500dfc0aa31bf533e5bf45fa7d0e611820a58756e7ed8b64216"
    )
    assert importer._canonical_bytes(artifact) == payload
    content = dict(artifact)
    digest = content.pop("artifact_digest")
    assert digest == importer._canonical_digest(content)
    assert b"KNCC_GBM" not in payload
    assert b'"patient_groups"' not in payload
    assert b"sample_submitter_id" not in payload
    assert b"aliquot_submitter_id" not in payload
    assert b"case_submitter_id" not in payload

    digest_tokens = set(re.findall(rb"(?<![0-9a-f])[0-9a-f]{32,128}(?![0-9a-f])", payload.lower()))
    for number in range(10_000):
        patient = f"KNCC_GBM{number:04d}"
        for identifier in (patient, f"{patient}_T1", f"{patient}_T2"):
            encoded = identifier.encode()
            for source_form in (encoded, encoded + b"\n", json.dumps(identifier).encode()):
                candidates = {
                    hashlib.md5(source_form, usedforsecurity=False).hexdigest().encode(),
                    hashlib.sha1(source_form, usedforsecurity=False).hexdigest().encode(),
                    hashlib.sha256(source_form).hexdigest().encode(),
                    hashlib.sha512(source_form).hexdigest().encode(),
                }
                assert digest_tokens.isdisjoint(candidates)

    allowed_uuids = {
        importer.PDC_STUDY_VERSION_UUID.encode(),
        *(lock.uuid.encode() for lock in importer.SOURCE_FILES),
    }
    assert set(importer._UUID_PATTERN_BYTES.findall(payload.lower())) == allowed_uuids


@pytest.mark.skipif(not ARTIFACT_PATH.is_file(), reason="fitted artifact has not been built")
def test_packaged_artifact_suppresses_small_cells_and_locks_runtime_gates() -> None:
    artifact = cast("dict[str, object]", json.loads(ARTIFACT_PATH.read_bytes()))
    assert artifact["source_attestation_state"] == "verified_exact_snapshots"
    gates = cast("dict[str, object]", artifact["runtime_quality_gates"])
    assert gates["selection_stability_passed"] is True
    assert gates["bootstrap_full_refit_passed"] is True
    assert gates["bootstrap_feature_selection_stability_passed"] is False
    assert gates["bootstrap_calibration_passed"] is False

    features = cast("list[dict[str, object]]", artifact["features"])
    supports = [cast("int", feature["paired_support"]) for feature in features]
    assert sum(support == 0 for support in supports) == 5
    assert sum(support == 1 for support in supports) == 342
    assert sum(support == 2 for support in supports) == 1_678
    assert sum(support < 53 for support in supports) == 19_790
    for feature in features:
        if feature["eligible"] is True:
            assert feature["numerical_release_state"] == "released_minimum_support"
            assert isinstance(feature["transition_center"], float)
            assert isinstance(feature["transition_scale"], float)
            assert float(feature["transition_scale"]) > 0.0
        else:
            assert feature["numerical_release_state"] == "suppressed_insufficient_support"
            assert feature["transition_center"] is None
            assert feature["transition_scale"] is None

    bootstrap = cast("dict[str, object]", artifact["bootstrap"])
    replicates = cast("list[dict[str, object]]", bootstrap["replicates"])
    for replicate in replicates:
        indices = cast("list[int]", replicate["feature_indices"])
        coefficients = cast("list[float]", replicate["coefficients"])
        scales = cast("list[float]", replicate["scales"])
        assert len(indices) == len(coefficients) == len(scales)
        assert all(features[index]["eligible"] is True for index in indices)
        assert all(scale > 0.0 for scale in scales)


@pytest.mark.skipif(not ARTIFACT_PATH.is_file(), reason="fitted artifact has not been built")
def test_packaged_artifact_carries_standalone_sphinks_attribution() -> None:
    artifact = cast("dict[str, object]", json.loads(ARTIFACT_PATH.read_bytes()))
    provenance = cast("dict[str, object]", artifact["provenance"])
    third_party = cast("list[dict[str, object]]", provenance["third_party_sources"])
    assert len(third_party) == 1
    sphinks_provenance = third_party[0]
    assert sphinks_provenance["article_authors"] == "Migliozzi et al."
    assert sphinks_provenance["article_doi"] == "10.1038/s43018-022-00510-x"
    assert sphinks_provenance["license"] == "CC-BY-4.0"
    assert sphinks_provenance["license_url"] == ("https://creativecommons.org/licenses/by/4.0/")
    assert sphinks_provenance["role"] == (
        "exact modified-peptide/site crosswalk and frozen kinase-signature memberships for "
        "matched rows"
    )
    assert "Supplementary Tables 5a, 5d, and 5e" in str(sphinks_provenance["transformation_notice"])


@pytest.mark.skipif(
    not ARTIFACT_PATH.is_file()
    or not (RAW_SOURCE_DIR / importer.PDC_SOURCE_MANIFEST_FILENAME).is_file(),
    reason="fitted artifact and external canonical source manifest are required",
)
def test_packaged_artifact_omits_every_exact_source_biospecimen_identifier() -> None:
    payload = ARTIFACT_PATH.read_bytes()
    digest_tokens = set(re.findall(rb"(?<![0-9a-f])[0-9a-f]{32,128}(?![0-9a-f])", payload.lower()))
    manifest = cast(
        "dict[str, object]",
        json.loads((RAW_SOURCE_DIR / importer.PDC_SOURCE_MANIFEST_FILENAME).read_bytes()),
    )
    responses = cast("dict[str, object]", manifest["responses"])
    biospecimens = cast("list[dict[str, object]]", responses["versioned_biospecimens"])
    for row in biospecimens:
        for field in (
            "aliquot_id",
            "sample_id",
            "case_id",
            "aliquot_submitter_id",
            "sample_submitter_id",
            "case_submitter_id",
        ):
            identifier = str(row[field]).encode()
            if not (
                identifier.startswith(b"KNCC_GBM")
                or importer._UUID_PATTERN_BYTES.fullmatch(identifier) is not None
            ):
                continue
            assert identifier not in payload
            source_forms = (
                identifier,
                identifier + b"\n",
                json.dumps(identifier.decode()).encode(),
            )
            for source_form in source_forms:
                candidates = {
                    hashlib.md5(source_form, usedforsecurity=False).hexdigest().encode(),
                    hashlib.sha1(source_form, usedforsecurity=False).hexdigest().encode(),
                    hashlib.sha256(source_form).hexdigest().encode(),
                    hashlib.sha512(source_form).hexdigest().encode(),
                }
                assert digest_tokens.isdisjoint(candidates)


@pytest.mark.skipif(not ARTIFACT_PATH.is_file(), reason="fitted artifact has not been built")
def test_runtime_catalog_loader_rechecks_all_frozen_identities() -> None:
    load_phosphosite_transition_catalog.cache_clear()
    catalog = load_phosphosite_transition_catalog()
    assert catalog.artifact_sha256 == (
        "sha256:5060d34d214582395f55ef66f9026303f781019230e91cd01d51d60c4fd6255e"
    )
    assert catalog.artifact_digest == (
        "sha256:d31635cc2c9f634679ebd913cf2e0911b0bdff1fb66d53533239e870d4b8624a"
    )
    assert catalog.profile_digest == (
        "sha256:81901f97d258f500dfc0aa31bf533e5bf45fa7d0e611820a58756e7ed8b64216"
    )
    assert catalog.crosswalk_digest == (
        "sha256:4d9d62c63361f285b45fff380588b37174663bfc702cef0587b705aaadebe8c4"
    )
    assert catalog.feature_count == 24_015
    assert catalog.strict_pair_count == 88
    assert catalog.selected_feature_count == 32
    assert catalog.eligible_feature_count == 4_225


@pytest.mark.skipif(
    not ARTIFACT_PATH.is_file() or not RAW_SOURCE_DIR.is_dir() or not RAW_HGNC_SOURCE.is_file(),
    reason="exact external source and fitted artifact are required",
)
def test_full_source_rebuild_is_byte_identical() -> None:
    cohort = importer.load_cohort(RAW_SOURCE_DIR, RAW_HGNC_SOURCE)
    rebuilt = importer.build_artifact(cohort)
    assert rebuilt.canonical_payload == ARTIFACT_PATH.read_bytes()


def test_source_verifier_fails_closed_on_tampering(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    payload = b"source-lock"
    path = tmp_path / "matrix.tsv"
    path.write_bytes(payload)
    lock = importer.SourceFileLock(
        path.name,
        "00000000-0000-0000-0000-000000000000",
        len(payload),
        hashlib.md5(payload, usedforsecurity=False).hexdigest(),
        hashlib.sha256(payload).hexdigest(),
    )
    monkeypatch.setattr(importer, "SOURCE_FILES", (lock,))
    assert importer.verify_source_files(tmp_path) == {path.name: path}
    path.write_bytes(payload + b"tamper")
    with pytest.raises(ValueError, match="byte-size mismatch"):
        importer.verify_source_files(tmp_path)


def test_source_verifier_rejects_same_byte_digest_tampering(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    payload = b"source-lock"
    path = tmp_path / "matrix.tsv"
    path.write_bytes(payload)
    lock = importer.SourceFileLock(
        path.name,
        "00000000-0000-0000-0000-000000000000",
        len(payload),
        hashlib.md5(payload, usedforsecurity=False).hexdigest(),
        hashlib.sha256(payload).hexdigest(),
    )
    monkeypatch.setattr(importer, "SOURCE_FILES", (lock,))
    path.write_bytes(b"source-Lock")
    assert path.stat().st_size == len(payload)
    with pytest.raises(ValueError, match="digest mismatch"):
        importer.verify_source_files(tmp_path)


def test_locked_parser_snapshot_is_the_exact_verified_payload(tmp_path: Path) -> None:
    payload = b"immutable-parser-input"
    path = tmp_path / "matrix.tsv"
    path.write_bytes(payload)
    lock = importer.SourceFileLock(
        path.name,
        "00000000-0000-0000-0000-000000000000",
        len(payload),
        hashlib.md5(payload, usedforsecurity=False).hexdigest(),
        hashlib.sha256(payload).hexdigest(),
    )

    snapshot = importer._read_locked_payload(path, lock)
    path.write_bytes(b"mutated-after-verification")

    assert snapshot == payload
    with pytest.raises(ValueError, match="byte-size mismatch"):
        importer._read_locked_payload(path, lock)


@pytest.mark.skipif(
    not (RAW_SOURCE_DIR / importer.PDC_SOURCE_MANIFEST_FILENAME).is_file(),
    reason="external canonical source manifest is absent",
)
def test_manifest_one_byte_tampering_fails_closed(tmp_path: Path) -> None:
    source = RAW_SOURCE_DIR / importer.PDC_SOURCE_MANIFEST_FILENAME
    payload = source.read_bytes()
    (tmp_path / importer.PDC_SOURCE_MANIFEST_FILENAME).write_bytes(payload[:-1] + b" ")
    for lock in importer.SOURCE_FILES:
        (tmp_path / lock.filename).write_bytes(b"")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        importer.verify_versioned_source_manifest(tmp_path)
