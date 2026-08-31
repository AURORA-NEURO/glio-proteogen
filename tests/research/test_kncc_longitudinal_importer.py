from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import cast

import numpy as np
import pytest

from tools import import_kncc_longitudinal_gbm as importer

ARTIFACT_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "glio_proteogen"
    / "research"
    / "longitudinal_gbm"
    / "data"
    / "kncc_paired_protein_transition.v1.json"
)
WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
RAW_SOURCE_DIR = WORKSPACE_ROOT / ".tmp-longitudinal-gbm-source"
RAW_HGNC_SOURCE = WORKSPACE_ROOT / ".tmp-neftel-source" / "hgnc_complete_set.txt"
EXPECTED_FILE_SHA256 = "cc965d9e9d0f7ab3e1ec7dda151bc3d5b442bbbd8cab12ee4b0f3497e860ae40"
EXPECTED_ARTIFACT_DIGEST = "sha256:5583ee3a1d75bcd3997d12ff2102ec19fd83e49b2ec98f4f2bd9a0b6475d92a3"
EXPECTED_MAPPING_DIGEST = "sha256:d585de04d6da666f03cc66e2d3ae8395e9b9cbb1cf2409a7e0721f8b9e3ea148"
EXPECTED_ENSEMBLE_DIGEST = "sha256:ce51e5a35eeee523283f6b22638afc341b48694ea4beebb28fa95e436db26f36"
EXPECTED_SOURCE_MANIFEST_SHA256 = "03d41fffeb04749296a95bd5cd5dd5829ddedc5f8f791941c011b94d6836a247"


def _walk(value: object, path: str = "") -> list[tuple[str, object]]:
    result = [(path, value)]
    if isinstance(value, dict):
        for key, child in value.items():
            result.extend(_walk(child, f"{path}.{key}" if path else str(key)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            result.extend(_walk(child, f"{path}[{index}]"))
    return result


@pytest.fixture(scope="module")
def artifact() -> dict[str, object]:
    return json.loads(ARTIFACT_PATH.read_bytes())


def test_source_file_and_hgnc_authority_locks_are_exact() -> None:
    assert importer.PDC_STUDY_ID == "PDC000514"
    assert importer.PDC_STUDY_VERSION_UUID == "524d5116-b6de-4e36-892a-e35dba7d0170"
    assert (
        importer.SourceFileLock(
            "KNCC_Glioblastoma_Evolution_Proteome.tmt11.tsv",
            "a07f3432-b1e0-4082-91c1-96bad4a4ac38",
            109_341_696,
            "36d0b951c1aaac1c52faf08d1894b1cb",
            "c8430c9a1fcd87dc16d221904d45d639d9372e5e5c5eb49bdcb5c36e0de183c6",
        ),
        importer.SourceFileLock(
            "KNCC_Glioblastoma_Evolution_Proteome.sample.txt",
            "ec09a0de-a5ef-442d-a105-705bb780c734",
            480_961,
            "d8c6d3880dc8a4485ec95ca6fbaf052a",
            "4f0f41c3442ba6fe8dda8c000853bd3c5ded4c191899f08c5ea7c339cf200b71",
        ),
        importer.SourceFileLock(
            "KNCC_Glioblastoma_Evolution_Proteome.summary.tsv",
            "604ce993-b140-4552-81cf-18d7ed598e4e",
            7_042_065,
            "8f785aa0bd7d1f727a38f4b60f65c5f2",
            "fcc12209f69dc1c8e2a3fc24c3c885cd6daed4d165f8afebe16f28fada2c591f",
        ),
    ) == importer.SOURCE_FILES
    assert importer.HGNC_SOURCE_BYTES == 16_948_224
    assert importer.HGNC_SOURCE_SHA256 == (
        "854162118530e929f06249f3349465dd5fe0515fcccf0347f463e833609c1270"
    )
    assert importer.PDC_SOURCE_MANIFEST_FILENAME == "PDC000514.v1.canonical-source-lock.json"
    assert importer.PDC_SOURCE_MANIFEST_BYTES == 1_362_739
    assert importer.PDC_SOURCE_MANIFEST_SHA256 == EXPECTED_SOURCE_MANIFEST_SHA256


@pytest.mark.skipif(
    not RAW_SOURCE_DIR.is_dir() or not RAW_HGNC_SOURCE.is_file(),
    reason="raw digest-locked PDC/HGNC sources are not distributed with the package",
)
def test_local_locked_sources_reproduce_exact_cohort_oracles() -> None:
    cohort = importer.load_cohort(RAW_SOURCE_DIR, RAW_HGNC_SOURCE)
    assert cohort.primary_delta.shape == cohort.ordinary_delta.shape == (104, 11_312)
    assert len(cohort.genes) == len(set(cohort.genes)) == 11_312
    assert cohort.oracles["matrix_unique_row_labels"] == 11_323
    assert cohort.oracles["strict_t1_t2_pairs"] == 104
    assert cohort.oracles["excluded_specimen_labels"] == 6
    assert cohort.oracles["excluded_patient_groups"] == 5
    assert cohort.oracles["official_versioned_biospecimen_records"] == 216
    assert cohort.oracles["official_versioned_file_manifest_records"] == 2_503
    assert cohort.oracles["hgnc_admitted_unique_approved_symbols"] == 11_312
    assert cohort.oracles["hgnc_mapping_digest"] == EXPECTED_MAPPING_DIGEST


def test_checked_in_artifact_is_canonical_digest_locked_and_deidentified(
    artifact: dict[str, object],
) -> None:
    payload = ARTIFACT_PATH.read_bytes()
    assert hashlib.sha256(payload).hexdigest() == EXPECTED_FILE_SHA256
    assert artifact["artifact_digest"] == EXPECTED_ARTIFACT_DIGEST
    content = dict(artifact)
    del content["artifact_digest"]
    assert "sha256:" + hashlib.sha256(importer._canonical_bytes(content)).hexdigest() == (
        EXPECTED_ARTIFACT_DIGEST
    )
    assert b"KNCC_GBM" not in payload
    assert b'"patient_groups"' not in payload
    assert b"metadata_conflict_source_label_digest" not in payload
    assert len(payload) < 6 * 1024 * 1024

    digest_tokens = set(re.findall(rb"(?<![0-9a-f])[0-9a-f]{32,128}(?![0-9a-f])", payload.lower()))
    for number in range(10_000):
        patient = f"KNCC_GBM{number:04d}"
        for identifier in (patient, f"{patient}_T1", f"{patient}_T2"):
            assert identifier.encode() not in payload
            for encoded in (
                identifier.encode(),
                json.dumps(identifier, separators=(",", ":")).encode(),
                identifier.encode() + b"\n",
            ):
                candidates = (
                    hashlib.md5(encoded, usedforsecurity=False).hexdigest().encode(),
                    hashlib.sha1(encoded, usedforsecurity=False).hexdigest().encode(),
                    hashlib.sha256(encoded).hexdigest().encode(),
                    hashlib.sha512(encoded).hexdigest().encode(),
                )
                assert digest_tokens.isdisjoint(candidates)

    artifact_uuids = set(
        re.findall(
            rb"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            payload.lower(),
        )
    )
    assert artifact_uuids == {
        importer.PDC_STUDY_VERSION_UUID.encode(),
        *(lock.uuid.encode() for lock in importer.SOURCE_FILES),
    }


def test_cohort_and_gene_identity_oracles_are_exact(artifact: dict[str, object]) -> None:
    oracles = artifact["cohort_oracles"]
    assert isinstance(oracles, dict)
    assert oracles == {
        "admitted_biological_genes": 11_320,
        "aggregate_rows_excluded_from_fit": ["Mean", "Median", "StdDev"],
        "analytical_samples": 26,
        "biological_specimen_labels": 214,
        "complete_pairs_before_sample_type_exclusion": 105,
        "duplicated_specimen_labels": 7,
        "excluded_patient_groups": 5,
        "excluded_specimen_labels": 6,
        "extra_technical_channels": 7,
        "fractions_per_analytical_sample": 24,
        "hgnc_admitted_unique_approved_symbols": 11_312,
        "hgnc_ambiguous_labels_excluded": 4,
        "hgnc_colliding_approved_symbols_excluded": 0,
        "hgnc_exact_approved_symbols": 11_232,
        "hgnc_mapped_labels_before_collision_exclusion": 11_312,
        "hgnc_mapping_digest": EXPECTED_MAPPING_DIGEST,
        "hgnc_unique_previous_or_alias_mappings": 80,
        "hgnc_unresolved_labels_excluded": 4,
        "incomplete_patient_groups_excluded": 4,
        "matrix_unique_row_labels": 11_323,
        "measurement_channels_per_measure": 260,
        "official_sample_type_mismatch_patient_groups": 1,
        "official_versioned_biological_specimen_labels": 214,
        "official_versioned_biospecimen_records": 216,
        "official_versioned_file_manifest_records": 2_503,
        "ordinary_log_finite_paired_deltas": 1_087_096,
        "primary_finite_paired_deltas": 1_056_603,
        "sample_map_rows": 624,
        "sample_type_mismatch_patient_groups_excluded": 1,
        "source_biological_gene_labels": 11_320,
        "source_biological_specimen_labels": 214,
        "strict_t1_t2_pairs": 104,
        "summary_unique_biological_genes": 11_320,
        "unshared_peptide_support_max": 2058,
        "unshared_peptide_support_median": 23.0,
        "unshared_peptide_support_min": 2,
    }
    assert 214 - oracles["excluded_specimen_labels"] == 2 * oracles["strict_t1_t2_pairs"]
    assert oracles["excluded_specimen_labels"] == 4 + 2
    assert oracles["excluded_patient_groups"] == 4 + 1
    identity = artifact["gene_identity"]
    assert isinstance(identity, dict)
    assert identity["authority_sha256"] == f"sha256:{importer.HGNC_SOURCE_SHA256}"
    assert identity["mapping_digest"] == EXPECTED_MAPPING_DIGEST

    features = artifact["features"]
    assert isinstance(features, list)
    assert len(features) == len({item["gene_symbol"] for item in features}) == 11_312
    mappings = {
        item["source_gene_label"]: (item["gene_symbol"], item["mapping_basis"]) for item in features
    }
    assert mappings["AATK"] == ("LMTK1", "previous_symbol")
    assert mappings["ATP6"] == ("MT-ATP6", "alias_symbol")
    for excluded in ("C18orf21", "COX1", "COX2", "ND1", "IFNAR2-IL10RB", "IQCA1"):
        assert excluded not in mappings


def test_fit_and_ablation_oracles_are_non_proxy_and_locked(artifact: dict[str, object]) -> None:
    fit = artifact["fit"]
    evaluation = artifact["fit_evaluation"]
    ablation = artifact["ordinary_log_ablation"]
    assert isinstance(fit, dict)
    assert isinstance(evaluation, dict)
    assert isinstance(ablation, dict)
    assert fit["selected_top_feature_count"] == 128
    assert fit["eligible_feature_count"] == 10_002
    assert fit["huber_converged"] is True
    assert fit["huber_iterations"] == 17
    assert fit["intensity_variance_floor"] == pytest.approx(0.21792469)
    assert evaluation["protocol"].startswith("patient-grouped nested cross-validation")
    assert evaluation["supported_pairs"] == 104
    assert evaluation["abstained_pairs"] == 0
    assert evaluation["direction_accuracy"] == pytest.approx(0.7884615384615384)
    assert evaluation["balanced_label_swap_accuracy"] == pytest.approx(0.7884615384615384)
    assert evaluation["median_sign_margin"] == pytest.approx(1.4985343285324095)
    assert "derived symmetry oracle" in evaluation["balanced_label_swap_accuracy_role"]
    assert "not independent evidence" in evaluation["balanced_label_swap_accuracy_role"]
    assert evaluation["median_sign_margin_aggregation"].startswith("pooled median")
    outer_folds = evaluation["outer_folds"]
    assert isinstance(outer_folds, list)
    assert len(outer_folds) == 8
    assert all("median_sign_margin" in fold for fold in outer_folds)
    assert ablation["ablation_family"] == "source_processing"
    assert ablation["role"].startswith("source-processing ablation only")
    assert ablation["ablation_kind"] == ("identification_ambiguity_and_shared_peptide_inclusion")
    assert ablation["supported_pair_count"] == 104
    assert 0.0 <= ablation["selected_feature_jaccard"] < 1.0
    projection = ablation["frozen_projection"]
    assert isinstance(projection, dict)
    projection_content = dict(projection)
    projection_digest = projection_content.pop("projection_digest")
    assert projection_digest == (
        "sha256:8a412506a2d946976c7d60f83d6f18a929800177f5702942943ab6ce7edb3368"
    )
    assert projection_digest == importer._canonical_digest(projection_content)
    assert len(projection["feature_indices"]) == 128
    assert projection["feature_indices"] == sorted(set(projection["feature_indices"]))
    assert len(projection["coefficients"]) == len(projection["transition_scales"]) == 128
    assert sum(abs(value) for value in projection["coefficients"]) == pytest.approx(1.0, abs=2e-6)

    features = artifact["features"]
    assert isinstance(features, list)
    coefficients = np.asarray([item["coefficient"] for item in features], dtype=np.float64)
    selected = np.asarray([item["selected"] for item in features], dtype=np.bool_)
    assert int(selected.sum()) == 128
    assert np.abs(coefficients).sum() == pytest.approx(1.0, abs=1e-6)
    assert np.count_nonzero(coefficients) == 128


def test_sparse_bootstrap_ensemble_preserves_coupled_uncertainty(
    artifact: dict[str, object],
) -> None:
    bootstrap = artifact["bootstrap"]
    assert isinstance(bootstrap, dict)
    assert bootstrap["requested_replicates"] == bootstrap["completed_replicates"] == 512
    assert bootstrap["validation_role"] == "none"
    assert "uncertainty approximation" in bootstrap["uncertainty_role"]
    assert "full-cohort" in bootstrap["reference_fit_policy"]
    assert not any("oob" in path.lower() for path, _ in _walk(artifact))
    ensemble = bootstrap["coefficient_ensemble"]
    assert isinstance(ensemble, dict)
    assert ensemble["ensemble_digest"] == EXPECTED_ENSEMBLE_DIGEST
    replicates = ensemble["replicates"]
    assert isinstance(replicates, list)
    assert len(replicates) == 512
    assert importer._canonical_digest(replicates) == EXPECTED_ENSEMBLE_DIGEST
    for expected_index, replicate in enumerate(replicates):
        projection = dict(replicate)
        digest = projection.pop("replicate_digest")
        assert digest == importer._canonical_digest(projection)
        indices = replicate["feature_indices"]
        coefficients = replicate["coefficients"]
        assert replicate["replicate_index"] == expected_index
        assert len(replicate["seed_hex"]) == 16
        assert len(indices) == len(coefficients) == 128
        assert indices == sorted(set(indices))
        assert sum(abs(value) for value in coefficients) == pytest.approx(1.0, abs=2e-6)
    assert replicates[0]["replicate_digest"] == (
        "sha256:4465ee37a5fe677f375633beefd2ea9c5bbb6d8b8756a5625635adc7296c3b0f"
    )
    assert replicates[-1]["replicate_digest"] == (
        "sha256:e4ff15092181d657d72e33d620244296fef555470143b6182c65d68d1afdeded"
    )


def test_technical_channel_median_preserves_missingness() -> None:
    raw = np.asarray(
        [
            [1.0, 3.0],
            [np.nan, 2.0],
            [4.0, np.nan],
            [np.nan, np.nan],
        ]
    )
    collapsed = importer._collapse_columns(raw, [0, 1])
    assert collapsed[:3].tolist() == [2.0, 2.0, 4.0]
    assert np.isnan(collapsed[3])
    assert importer._float_cell("") != importer._float_cell("")
    with pytest.raises(ValueError, match="non-finite"):
        importer._float_cell("nan")


def test_huber_axis_is_outlier_resistant_and_abstains_on_inadequate_overlap() -> None:
    delta = np.asarray(
        [
            [1.0, 0.8, -1.0, 0.5],
            [1.1, 0.9, -1.1, 0.6],
            [0.9, 1.0, -0.9, 0.4],
            [1.0, 0.7, -1.0, 0.5],
            [100.0, 0.8, -1.2, 0.5],
        ],
        dtype=np.float64,
    )
    fit = importer._fit_axis(delta, ("A", "B", "C", "D"))
    assert fit.converged
    assert fit.center[0] < 2.0
    selected, weights = importer._weights(fit, 4)
    sparse = np.full((1, 4), np.nan, dtype=np.float64)
    sparse[0, selected[0]] = 1.0
    scores, coverage, overlap = importer._project(sparse, fit.scale, selected, weights)
    assert np.isnan(scores[0])
    assert coverage[0] < importer.MIN_SCORE_WEIGHT_COVERAGE
    assert overlap[0] == 1


def test_fixed_scale_bootstrap_never_claims_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rng = np.random.default_rng(9102)
    pair_count = 16
    gene_count = 16
    delta = rng.normal(0.4, 0.15, size=(pair_count, gene_count))
    cohort = importer.Cohort(
        genes=tuple(f"G{index:02d}" for index in range(gene_count)),
        hgnc_ids=tuple(f"HGNC:{index + 1}" for index in range(gene_count)),
        source_gene_labels=tuple(f"S{index:02d}" for index in range(gene_count)),
        mapping_basis=("approved_symbol",) * gene_count,
        patient_groups=tuple(f"private-{index:02d}" for index in range(pair_count)),
        primary_delta=delta,
        ordinary_delta=delta.copy(),
        unshared_peptides=np.full(gene_count, 4, dtype=np.int64),
        oracles={"hgnc_mapping_digest": "sha256:" + "0" * 64},
    )
    fit = importer._fit_axis(delta, cohort.genes)

    def fail_if_scored(_scores: importer.FloatArray) -> dict[str, float | int]:
        raise AssertionError

    monkeypatch.setattr(importer, "_score_metrics", fail_if_scored)
    _, _, summary = importer._bootstrap(cohort, fit, top_count=8, replicates=4)
    assert summary["validation_role"] == "none"
    assert not any("oob" in path.lower() for path, _ in _walk(summary))


def test_synthetic_fit_replays_deterministically_without_patient_material() -> None:
    rng = np.random.default_rng(20260829)
    gene_count = 24
    pair_count = 24
    signal = np.linspace(-0.8, 0.9, gene_count)
    primary = signal + rng.normal(0.0, 0.15, size=(pair_count, gene_count))
    primary[0, :18] = np.nan
    cohort = importer.Cohort(
        genes=tuple(f"G{index:03d}" for index in range(gene_count)),
        hgnc_ids=tuple(f"HGNC:{index + 1}" for index in range(gene_count)),
        source_gene_labels=tuple(f"OLD{index:03d}" for index in range(gene_count)),
        mapping_basis=("approved_symbol",) * gene_count,
        patient_groups=tuple(f"group-{index:03d}" for index in range(pair_count)),
        primary_delta=primary,
        ordinary_delta=primary + rng.normal(0.0, 0.03, size=primary.shape),
        unshared_peptides=np.full(gene_count, 5, dtype=np.int64),
        oracles={"hgnc_mapping_digest": "sha256:" + "0" * 64},
    )
    first = importer.build_artifact(cohort, bootstrap_replicates=8)
    second = importer.build_artifact(cohort, bootstrap_replicates=8)
    assert importer._canonical_bytes(first) == importer._canonical_bytes(second)
    payload = importer._canonical_bytes(first)
    assert b"group-" not in payload
    assert first["bootstrap"]["completed_replicates"] == 8


def test_artifact_exposes_only_safe_official_manifest_lock(
    artifact: dict[str, object],
) -> None:
    source_lock = artifact["source_lock"]
    assert isinstance(source_lock, dict)
    manifest_lock = source_lock["versioned_source_manifest"]
    assert manifest_lock == {
        "binding": (
            "exact canonical full responses for the versioned biospecimen and file queries "
            "plus the study-catalog version record"
        ),
        "biospecimen_response_records": 216,
        "bytes": 1_362_739,
        "file_manifest_response_records": 2_503,
        "filename": "PDC000514.v1.canonical-source-lock.json",
        "graphql_api_version": "1.0.0",
        "schema_version": "glio-proteogen.pdc000514-source-manifest/1.0.0",
        "sha256": f"sha256:{EXPECTED_SOURCE_MANIFEST_SHA256}",
    }
    assert "responses" not in source_lock
    assert "sample_submitter_id" not in source_lock


@pytest.mark.skipif(
    not (RAW_SOURCE_DIR / importer.PDC_SOURCE_MANIFEST_FILENAME).is_file(),
    reason="raw versioned PDC metadata source is not distributed with the package",
)
def test_versioned_manifest_fails_on_one_byte_tampering(tmp_path: Path) -> None:
    source = RAW_SOURCE_DIR / importer.PDC_SOURCE_MANIFEST_FILENAME
    payload = source.read_bytes()
    (tmp_path / importer.PDC_SOURCE_MANIFEST_FILENAME).write_bytes(payload[:-1] + b" ")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        importer.verify_versioned_source_manifest(tmp_path)


@pytest.mark.skipif(
    not (RAW_SOURCE_DIR / importer.PDC_SOURCE_MANIFEST_FILENAME).is_file(),
    reason="raw versioned PDC metadata source is not distributed with the package",
)
@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("wrong_version", "provenance changed"),
        ("duplicate_file_uuid", "duplicate file UUID"),
        ("target_file_uuid", "locked file identity differs"),
        ("zero_sample_type_mismatches", "exactly one"),
        ("multiple_sample_type_mismatches", "exactly one"),
    ],
)
def test_versioned_manifest_semantics_fail_closed(
    mutation: str,
    message: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = RAW_SOURCE_DIR / importer.PDC_SOURCE_MANIFEST_FILENAME
    document = cast("dict[str, object]", json.loads(source.read_bytes()))
    responses = cast("dict[str, object]", document["responses"])
    files = cast("list[dict[str, object]]", responses["versioned_files"])
    biospecimens = cast("list[dict[str, object]]", responses["versioned_biospecimens"])

    if mutation == "wrong_version":
        cast("dict[str, object]", document["source"])["pdc_study_version_uuid"] = "0" * 36
    elif mutation == "duplicate_file_uuid":
        files[-1] = dict(files[0])
    elif mutation == "target_file_uuid":
        target_names = {lock.filename for lock in importer.SOURCE_FILES}
        target = next(row for row in files if row["file_name"] in target_names)
        target["file_id"] = "00000000-0000-0000-0000-000000000000"
    else:
        t1_rows = [
            row for row in biospecimens if str(row.get("sample_submitter_id", "")).endswith("_T1")
        ]
        mismatches = [row for row in t1_rows if row.get("sample_type") == "Recurrent Tumor"]
        if mutation == "zero_sample_type_mismatches":
            assert len(mismatches) == 1
            mismatches[0]["sample_type"] = "Primary Tumor"
        else:
            normal = next(row for row in t1_rows if row.get("sample_type") == "Primary Tumor")
            normal["sample_type"] = "Recurrent Tumor"

    payload = importer._canonical_bytes(document)
    destination = tmp_path / importer.PDC_SOURCE_MANIFEST_FILENAME
    destination.write_bytes(payload)
    monkeypatch.setattr(importer, "PDC_SOURCE_MANIFEST_BYTES", len(payload))
    monkeypatch.setattr(importer, "PDC_SOURCE_MANIFEST_SHA256", hashlib.sha256(payload).hexdigest())
    with pytest.raises(ValueError, match=message):
        importer.verify_versioned_source_manifest(tmp_path)


def test_source_verifier_fails_closed_on_tampering(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    payload = b"locked-source"
    filename = "matrix.tsv"
    path = tmp_path / filename
    path.write_bytes(payload)
    lock = importer.SourceFileLock(
        filename,
        "00000000-0000-0000-0000-000000000000",
        len(payload),
        hashlib.md5(payload, usedforsecurity=False).hexdigest(),
        hashlib.sha256(payload).hexdigest(),
    )
    monkeypatch.setattr(importer, "SOURCE_FILES", (lock,))
    assert importer.verify_source_files(tmp_path) == {filename: path}
    path.write_bytes(payload + b"tamper")
    with pytest.raises(ValueError, match="byte-size mismatch"):
        importer.verify_source_files(tmp_path)
