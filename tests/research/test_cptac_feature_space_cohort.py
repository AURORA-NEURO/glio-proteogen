"""Synthetic exact-identity and source-only gene-universe assembly oracles."""

from __future__ import annotations

import json
import pickle
from collections import Counter
from dataclasses import asdict, replace
from uuid import UUID

import numpy as np
import pytest

from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.research.cptac_gbm_external_admission.contracts import (
    PANEL,
    GeneIdentity,
    HgncReference,
    SourceLock,
    SourceVerificationError,
)
from glio_proteogen.research.cptac_gbm_external_admission.discovery import (
    PROFILE_ID as DISCOVERY_PROFILE_ID,
)
from glio_proteogen.research.cptac_gbm_external_admission.discovery import (
    DiscoveryProteinAdmission,
)
from glio_proteogen.research.cptac_gbm_external_admission.plan import (
    AssayInputBinding,
    CandidateBinding,
    ExternalAdmissionPlan,
    ExternalAdmissionReceipt,
)
from glio_proteogen.research.cptac_gbm_external_admission.protein import (
    PROFILE_ID as CONFIRMATORY_PROFILE_ID,
)
from glio_proteogen.research.cptac_gbm_external_admission.protein import (
    ConfirmatoryProteinAdmission,
    ProteinAdmissionReceipt,
)
from glio_proteogen.research.cptac_gbm_feature_space import cohort as engine
from glio_proteogen.research.cptac_gbm_feature_space.contracts import (
    CNV_AXIS,
    PROFILE_ID,
    RNA_AXIS,
    FeatureAxis,
    FeatureSpaceError,
    ProjectedAssay,
    ProjectionReceipt,
)

_DIGEST = "sha256:" + "a" * 64
_PRIVATE = "synthetic-private-canary"


def _identity(index, symbol=None):
    return GeneIdentity(
        f"HGNC:{index}", symbol or f"SYNTHETIC{index}", str(index), f"ENSG{index:011}"
    )


def _reference(identities):
    by_ensembl = {}
    for identity in identities:
        if identity.ensembl_gene_id is not None:
            by_ensembl.setdefault(identity.ensembl_gene_id, []).append(identity)
    return HgncReference(
        {identity.hgnc_id: identity for identity in identities},
        {key: tuple(value) for key, value in by_ensembl.items()},
        {identity.symbol: identity for identity in identities},
    )


def _plan(count=72):
    candidates, files = [], {}
    for index in range(count):
        rna_id, cnv_id = str(UUID(int=1_000 + 2 * index)), str(UUID(int=1_001 + 2 * index))
        candidates.append(
            CandidateBinding(
                f"{_PRIVATE}-case-{index}",
                f"{_PRIVATE}-sample-{index}",
                str(UUID(int=10_000 + index)),
                f"{_PRIVATE}-protein-{index}",
                str(UUID(int=20_000 + index)),
                rna_id,
                cnv_id,
            )
        )
        for file_id, workflow in ((rna_id, "STAR - Counts"), (cnv_id, "AscatNGS")):
            files[file_id] = AssayInputBinding(
                file_id + ".bin", SourceLock(100, "b" * 32, "c" * 64), workflow
            )
    receipt = ExternalAdmissionReceipt(
        profile_id="synthetic-plan",
        choices_sha256="d" * 64,
        files_manifest_sha256="e" * 64,
        candidate_count=count,
        rna_file_count=count,
        cnv_file_count=count,
        paired_file_count=2 * count,
        manifest_verified_bytes=200 * count,
        metadata_candidate_not_admitted=True,
        issuer_authentication=False,
        eligibility_admitted=False,
        measurement_bytes_reverified=False,
        limitations=("synthetic metadata only",),
    )
    return ExternalAdmissionPlan(tuple(candidates), files, receipt)


def _protein(identities, plan, values=None):
    count = len(plan.candidates)
    if values is None:
        values = np.full((len(identities), count), -2.0, dtype=np.float64)
    values = np.array(values, dtype=np.float64, copy=True)
    digest = sha256_digest(plan.protein_aliquots)
    receipt = ProteinAdmissionReceipt(
        profile_id=DISCOVERY_PROFILE_ID if count == 72 else CONFIRMATORY_PROFILE_ID,
        protein_sha256="f" * 64,
        sample_map_sha256="a" * 64,
        hgnc_sha256="b" * 64,
        candidate_digest=digest,
        candidate_count=count,
        biological_feature_rows=len(identities),
        identified_feature_rows=sum(identity is not None for identity in identities),
        unavailable_identity_rows=sum(identity is None for identity in identities),
        source_aggregate_rows_excluded=3,
        withdrawn_aliquots_excluded=0,
        pool_targets_excluded=0,
        finite_unshared_cells=int(np.isfinite(values).sum()),
        missing_unshared_cells=int(np.isnan(values).sum()),
        finite_zero_unshared_cells=int((values == 0).sum()),
        finite_all_peptide_cells=values.size,
        missing_all_peptide_cells=0,
        panel_coverage=(),
        limitations=("synthetic fixture",),
    )
    kind = DiscoveryProteinAdmission if count == 72 else ConfirmatoryProteinAdmission
    return kind(digest, values, tuple(identities), receipt)


def _fixture(count=72):
    identities = tuple(_identity(index) for index in (1, 2, 3, 4))
    axis = FeatureAxis(identities[:3])
    hgnc = _reference(identities)
    plan = _plan(count)
    values = np.vstack(
        (
            np.full(count, np.nan),
            np.arange(count, dtype=np.float64) - 2,
            np.full(count, 999.0),
            np.full(count, 888.0),
        )
    )
    # Source order differs from both HGNC order and assay order. The unresolved
    # row and approved external-only row must never populate the absent gene.
    protein = _protein((identities[1], identities[0], None, identities[3]), plan, values)
    return axis, hgnc, plan, protein


def _projection(axis, assay_axis, column, *, data_rows=None):
    states = np.array([(column + row) % 6 for row in range(len(axis.identities))], dtype=np.uint8)
    values = np.full(len(states), np.nan, dtype=np.float64)
    values[states == 0] = column if assay_axis == RNA_AXIS else column * 2
    genes = 10 + column % 2
    summaries = 4 if assay_axis == RNA_AXIS else 0
    receipt = ProjectionReceipt(
        axis=assay_axis,
        workflow="STAR - Counts" if assay_axis == RNA_AXIS else "AscatNGS",
        annotation_release="GENCODE v36" if assay_axis == RNA_AXIS else None,
        input_bytes=100,
        data_rows=genes + summaries if data_rows is None else data_rows,
        gene_rows=genes,
        summary_rows=summaries,
        versioned_gene_rows=genes if assay_axis == RNA_AXIS else 0,
        par_y_gene_rows=1,
        duplicate_gene_symbol_groups=column % 2,
        ambiguous_reference_gene_ids=1,
        missing_gene_rows=column % 2,
        observed_zero_gene_rows=int(column == 0),
        feature_axis_digest=axis.digest,
        feature_count=len(axis.identities),
        state_counts=tuple(int(np.sum(states == code)) for code in range(6)),
    )
    return ProjectedAssay(receipt, values, states)


def _install_readers(monkeypatch, fixture, directory):
    _, _, plan, _ = fixture
    calls, results = [], {}
    lookup = {
        file_id: (column, assay_axis)
        for column, candidate in enumerate(plan.candidates)
        for file_id, assay_axis in (
            (candidate.rna_file_id, RNA_AXIS),
            (candidate.cnv_file_id, CNV_AXIS),
        )
    }

    def read(path, *, lock, hgnc: HgncReference, axis: FeatureAxis):
        assert path.parent == directory
        file_id = path.stem
        assert path.name == file_id + ".bin"
        assert lock is plan.files[file_id].lock
        assert hgnc is fixture[1]
        assert axis is fixture[0]
        calls.append(file_id)
        column, assay_axis = lookup[file_id]
        result = _projection(axis, assay_axis, column)
        results[file_id] = result
        return result

    monkeypatch.setattr(engine.assays, "parse_star_counts_v36", read)
    monkeypatch.setattr(engine.assays, "parse_ascat_gene_cnv", read)
    return calls, results


def _build(fixture, path):
    axis, hgnc, plan, protein = fixture
    return engine.build_cohort_matrix(
        axis=axis, protein=protein, plan=plan, files_manifest_path=path, hgnc=hgnc
    )


def test_source_axis_is_approved_source_plus_all_anchors_without_measurement_selection():
    anchors = tuple(_identity(index + 100, symbol) for index, symbol in enumerate(PANEL))
    extras = (_identity(3), _identity(20))
    hgnc = _reference((*anchors, *extras))
    plan = _plan()
    source_identities = (extras[1], *reversed(anchors[2:]), None, extras[0])
    protein = _protein(source_identities, plan)
    universe = engine.derive_source_axis(protein=protein, hgnc=hgnc)
    expected = tuple(sorted((*anchors, *extras), key=lambda identity: identity.hgnc_id))
    assert universe.axis.identities == expected
    assert universe.receipt == engine.SourceUniverseReceipt(
        PROFILE_ID, 17, 16, 1, 2, 18, universe.axis.digest, sha256_digest(asdict(protein.receipt))
    )
    assert not universe.receipt.selection_uses_external_values
    assert not universe.receipt.selection_uses_association_outcomes
    altered = _protein(tuple(reversed(source_identities)), plan, np.full((17, 72), np.nan))
    repeated = engine.derive_source_axis(protein=altered, hgnc=hgnc)
    assert repeated.axis == universe.axis
    assert (
        repeated.receipt.source_protein_receipt_digest
        != universe.receipt.source_protein_receipt_digest
    )
    assert extras[1].symbol not in repr(universe)


def test_axis_can_retain_approved_identities_without_entrez_or_ensembl():
    anchors = tuple(_identity(index + 100, symbol) for index, symbol in enumerate(PANEL))
    partial = GeneIdentity("HGNC:9", "PARTIAL", None, None)
    protein = _protein((partial,), _plan())
    universe = engine.derive_source_axis(protein=protein, hgnc=_reference((*anchors, partial)))
    assert partial in universe.axis.identities
    assert universe.receipt.literature_anchor_only_count == 16


@pytest.mark.parametrize("count", [72, 56])
def test_cohort_keeps_exact_order_all_six_states_and_one_verified_read_per_file(
    monkeypatch, tmp_path, count
):
    fixture = _fixture(count)
    axis, _, plan, protein = fixture
    calls, projections = _install_readers(monkeypatch, fixture, tmp_path)
    admission = _build(fixture, tmp_path / "manifest.private.json")
    matrix, receipt = admission.matrix, admission.receipt
    assert matrix.case_count == count
    assert matrix.axis is axis
    assert matrix.candidate_digest == protein.candidate_digest
    assert Counter(calls) == Counter(dict.fromkeys(plan.files, 1))
    for column, candidate in enumerate(plan.candidates):
        for name, file_id in (("rna", candidate.rna_file_id), ("cnv", candidate.cnv_file_id)):
            np.testing.assert_array_equal(
                getattr(matrix, name)[:, column], projections[file_id].values
            )
            np.testing.assert_array_equal(
                getattr(matrix, name + "_states")[:, column], projections[file_id].states
            )
    np.testing.assert_array_equal(matrix.protein[0], np.arange(count) - 2)
    assert matrix.protein[0, 2] == 0
    assert matrix.protein_states[0, 2] == 0
    assert np.all(np.isnan(matrix.protein[1:]))
    assert np.all(matrix.protein_states[1] == 5)
    assert np.all(matrix.protein_states[2] == 1)
    assert receipt.protein_rows_outside_source_axis == 1
    assert receipt.source_protein_receipt is protein.receipt
    assert receipt.verified_rna_files == receipt.verified_cnv_files == count
    assert tuple(summary.axis for summary in receipt.schema_summaries) == (CNV_AXIS, RNA_AXIS)
    for summary in receipt.schema_summaries:
        assert summary.verified_input_bytes == count * 100
        expected_counts = Counter((column + row) % 6 for column in range(count) for row in range(3))
        assert summary.state_totals == tuple(expected_counts[code] for code in range(6))
        assert summary.feature_count == 3
        assert summary.verified_files == count
        histograms = {histogram.field: histogram.bins for histogram in summary.histograms}
        assert histograms["gene_rows"] == (
            engine.SchemaHistogramBin(10, (count + 1) // 2),
            engine.SchemaHistogramBin(11, count // 2),
        )
        assert all(sum(item.files for item in bins) == count for bins in histograms.values())
    serialized = json.dumps(asdict(receipt), allow_nan=False)
    for secret in (*plan.protein_aliquots, *plan.files, _PRIVATE):
        assert secret not in serialized
        assert secret not in repr(admission)
    assert matrix.measurement_bytes == 3 * 3 * count * 8
    for values in (
        matrix.cnv,
        matrix.rna,
        matrix.protein,
        matrix.cnv_states,
        matrix.rna_states,
        matrix.protein_states,
    ):
        with pytest.raises(ValueError):
            values.flags.writeable = True
    with pytest.raises(TypeError, match="cannot be serialized"):
        pickle.dumps(admission)
    with pytest.raises(TypeError, match="cannot be serialized"):
        admission.__getstate__()
    with pytest.raises(TypeError, match="dataclass"):
        asdict(admission)
    with pytest.raises(AttributeError, match="immutable"):
        admission.matrix = matrix
    protein.values[:] = 500
    assert matrix.protein[0, 2] == 0


def test_external_only_protein_gene_does_not_expand_source_axis(monkeypatch, tmp_path):
    fixture = _fixture(56)
    _install_readers(monkeypatch, fixture, tmp_path)
    admission = _build(fixture, tmp_path / "manifest.private.json")
    assert admission.matrix.axis.hgnc_ids == ("HGNC:1", "HGNC:2", "HGNC:3")
    with pytest.raises(FeatureSpaceError, match="outside the frozen feature axis"):
        admission.matrix.gene("HGNC:4")
    assert admission.receipt.protein_rows_outside_source_axis == 1


@pytest.mark.parametrize(
    "defect",
    [
        "wrong_source",
        "missing_anchor",
        "unknown_identity",
        "stale_reference",
        "duplicate_identity",
        "duplicate_symbol",
    ],
)
def test_source_universe_rejects_unresolved_or_conflicting_identity_claims(defect):
    anchors = tuple(_identity(index + 100, symbol) for index, symbol in enumerate(PANEL))
    hgnc = _reference(anchors)
    plan = _plan(56 if defect == "wrong_source" else 72)
    protein = _protein(anchors, plan)
    if defect == "missing_anchor":
        hgnc = _reference(anchors[1:])
        protein = _protein(anchors[1:], plan)
    elif defect == "unknown_identity":
        protein = _protein((*anchors, _identity(9, _PRIVATE)), plan)
    elif defect == "stale_reference":
        protein = _protein((replace(anchors[0], entrez_id="99999"), *anchors[1:]), plan)
    elif defect in {"duplicate_identity", "duplicate_symbol"}:
        protein = _protein((*anchors, anchors[0]), plan)
    with pytest.raises(FeatureSpaceError) as error:
        engine.derive_source_axis(protein=protein, hgnc=hgnc)
    assert _PRIVATE not in str(error.value)


@pytest.mark.parametrize(
    "defect",
    [
        "type",
        "hgnc_type",
        "digest",
        "receipt_type",
        "profile",
        "candidate_count",
        "receipt_digest",
        "values_type",
        "dtype",
        "ndim",
        "columns",
        "identity_container",
        "empty",
        "identity_rows",
        "receipt_rows",
        "infinite",
        "identified",
        "unresolved",
        "finite",
        "missing",
        "zero",
    ],
)
def test_invalid_protein_is_rejected_before_any_assay_access(  # noqa: C901, PLR0912 - explicit adversarial input matrix.
    monkeypatch, tmp_path, defect
):
    axis, hgnc, plan, protein = _fixture()
    if defect == "type":
        protein = object()
    elif defect == "hgnc_type":
        hgnc = object()
    elif defect == "digest":
        protein = replace(protein, candidate_digest=_PRIVATE)
    elif defect == "receipt_type":
        protein = replace(protein, receipt=object())
    elif defect == "profile":
        protein = replace(
            protein, receipt=replace(protein.receipt, profile_id=CONFIRMATORY_PROFILE_ID)
        )
    elif defect == "candidate_count":
        protein = replace(protein, receipt=replace(protein.receipt, candidate_count=56))
    elif defect == "receipt_digest":
        protein = replace(protein, receipt=replace(protein.receipt, candidate_digest=_DIGEST))
    elif defect == "values_type":
        protein = replace(protein, values=protein.values.tolist())
    elif defect == "dtype":
        protein = replace(protein, values=protein.values.astype(np.float32))
    elif defect == "ndim":
        protein = replace(protein, values=protein.values.flatten())
    elif defect == "columns":
        protein = replace(protein, values=protein.values[:, :-1])
    elif defect == "identity_container":
        protein = replace(protein, identities=list(protein.identities))
    elif defect == "empty":
        protein = _protein((), plan)
    elif defect == "identity_rows":
        protein = replace(protein, identities=protein.identities[:-1])
    elif defect == "receipt_rows":
        protein = replace(protein, receipt=replace(protein.receipt, biological_feature_rows=99))
    elif defect == "infinite":
        protein.values[0, 0] = np.inf
    else:
        field = {
            "identified": "identified_feature_rows",
            "unresolved": "unavailable_identity_rows",
            "finite": "finite_unshared_cells",
            "missing": "missing_unshared_cells",
            "zero": "finite_zero_unshared_cells",
        }[defect]
        protein = replace(
            protein,
            receipt=replace(protein.receipt, **{field: getattr(protein.receipt, field) + 1}),
        )

    def forbidden(*_args, **_kwargs):
        pytest.fail("invalid protein reached measurement access")

    monkeypatch.setattr(engine.assays, "parse_star_counts_v36", forbidden)
    with pytest.raises(FeatureSpaceError) as error:
        engine.build_cohort_matrix(
            axis=axis,
            protein=protein,
            plan=plan,
            files_manifest_path=tmp_path / _PRIVATE,
            hgnc=hgnc,
        )
    assert _PRIVATE not in str(error.value)


@pytest.mark.parametrize(
    "defect",
    [
        "axis",
        "path",
        "axis_reference",
        "plan",
        "receipt",
        "count",
        "receipt_count",
        "rna_count",
        "cnv_count",
        "paired_count",
        "files_count",
        "candidate_type",
        "label",
        "sample_uuid",
        "duplicate_case",
        "file_uuid",
        "unhashable_file",
        "duplicate_file",
        "missing_file",
        "binding_type",
        "lock",
        "traversal",
        "workflow",
        "order",
    ],
)
def test_invalid_bundle_binding_is_rejected_before_file_reads(  # noqa: C901, PLR0912, PLR0915 - explicit adversarial binding matrix.
    monkeypatch, tmp_path, defect
):
    axis, hgnc, plan, protein = _fixture()
    path = tmp_path / "manifest.private.json"
    first = plan.candidates[0]
    if defect == "axis":
        axis = object()
    elif defect == "path":
        path = _PRIVATE
    elif defect == "axis_reference":
        axis = FeatureAxis((replace(axis.identities[0], entrez_id="9999"), *axis.identities[1:]))
    elif defect == "plan":
        plan = object()
    elif defect == "receipt":
        plan = replace(plan, receipt=object())
    elif defect == "count":
        plan = replace(plan, candidates=plan.candidates[:-1])
    elif defect in {"receipt_count", "rna_count", "cnv_count", "paired_count"}:
        field = {
            "receipt_count": "candidate_count",
            "rna_count": "rna_file_count",
            "cnv_count": "cnv_file_count",
            "paired_count": "paired_file_count",
        }[defect]
        plan = replace(plan, receipt=replace(plan.receipt, **{field: 0}))
    elif defect == "files_count":
        plan = replace(
            plan,
            files={key: value for key, value in plan.files.items() if key != first.rna_file_id},
        )
    elif defect == "candidate_type":
        plan = replace(plan, candidates=(object(), *plan.candidates[1:]))
    elif defect == "label":
        plan = replace(
            plan,
            candidates=(replace(first, protein_aliquot_submitter_id="POOL"), *plan.candidates[1:]),
        )
    elif defect == "sample_uuid":
        plan = replace(
            plan, candidates=(replace(first, gdc_sample_uuid=_PRIVATE), *plan.candidates[1:])
        )
    elif defect == "duplicate_case":
        second = replace(plan.candidates[1], case_submitter_id=first.case_submitter_id)
        plan = replace(plan, candidates=(first, second, *plan.candidates[2:]))
    elif defect in {"file_uuid", "unhashable_file"}:
        value = _PRIVATE if defect == "file_uuid" else []
        plan = replace(plan, candidates=(replace(first, rna_file_id=value), *plan.candidates[1:]))
    elif defect == "duplicate_file":
        plan = replace(
            plan, candidates=(replace(first, cnv_file_id=first.rna_file_id), *plan.candidates[1:])
        )
    elif defect == "order":
        plan = replace(plan, candidates=tuple(reversed(plan.candidates)))
    else:
        files = dict(plan.files)
        original = files[first.rna_file_id]
        if defect == "missing_file":
            del files[first.rna_file_id]
            files[str(UUID(int=999_999))] = original
        elif defect == "binding_type":
            files[first.rna_file_id] = object()
        elif defect == "lock":
            files[first.rna_file_id] = replace(original, lock=object())
        elif defect == "traversal":
            files[first.rna_file_id] = replace(original, relative_path="../" + _PRIVATE)
        elif defect == "workflow":
            files[first.rna_file_id] = replace(original, workflow="AscatNGS")
        plan = replace(plan, files=files)

    def forbidden(*_args, **_kwargs):
        pytest.fail("invalid binding reached measurement access")

    monkeypatch.setattr(engine.assays, "parse_star_counts_v36", forbidden)
    with pytest.raises(FeatureSpaceError) as error:
        engine.build_cohort_matrix(
            axis=axis, protein=protein, plan=plan, files_manifest_path=path, hgnc=hgnc
        )
    assert _PRIVATE not in str(error.value)


@pytest.mark.parametrize("defect", ["type", "axis", "digest", "feature_count", "bytes"])
def test_projection_is_bound_to_exact_source_axis_and_lock(monkeypatch, tmp_path, defect):
    fixture = _fixture()
    axis = fixture[0]
    projected = _projection(axis, RNA_AXIS, 0)
    if defect == "type":
        projected = object()
    elif defect == "axis":
        projected = _projection(axis, CNV_AXIS, 0)
    elif defect == "digest":
        projected = replace(
            projected, receipt=replace(projected.receipt, feature_axis_digest=_DIGEST)
        )
    elif defect == "feature_count":
        other = FeatureAxis(axis.identities[:2])
        projected = _projection(other, RNA_AXIS, 0)
        projected = replace(
            projected, receipt=replace(projected.receipt, feature_axis_digest=axis.digest)
        )
    elif defect == "bytes":
        projected = replace(projected, receipt=replace(projected.receipt, input_bytes=101))
    monkeypatch.setattr(engine.assays, "parse_star_counts_v36", lambda *args, **kwargs: projected)
    with pytest.raises(FeatureSpaceError, match="projection"):
        _build(fixture, tmp_path / "manifest.private.json")


def test_verification_failure_propagates_without_partial_matrix(monkeypatch, tmp_path):
    fixture = _fixture()
    calls, _ = _install_readers(monkeypatch, fixture, tmp_path)

    failure = SourceVerificationError("source checksums did not match its lock")

    def corrupt(*_args, **_kwargs):
        raise failure

    monkeypatch.setattr(engine.assays, "parse_ascat_gene_cnv", corrupt)
    with pytest.raises(SourceVerificationError, match="checksums"):
        _build(fixture, tmp_path / "manifest.private.json")
    assert len(calls) == 1


def test_matrix_size_is_checked_before_assay_reads(monkeypatch, tmp_path):
    fixture = _fixture()
    monkeypatch.setattr(engine, "MAX_CELLS", 1)
    with pytest.raises(FeatureSpaceError, match="bounded feature matrix"):
        _build(fixture, tmp_path / "manifest.private.json")
