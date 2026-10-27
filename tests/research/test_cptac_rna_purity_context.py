"""Synthetic context inventories: explicit claims, unknowns, lineage and privacy."""

from __future__ import annotations

import hashlib
import itertools
import json
import pickle
from dataclasses import asdict

import pytest
from pydantic import ValidationError

from glio_proteogen.research.cptac_gbm_rna_purity_admission import context
from glio_proteogen.research.cptac_gbm_rna_purity_admission.contracts import AdmissionError
from glio_proteogen.research.gbm_rna_purity import engine

C = context.ContextComponent
A = context.ContextAssertion
S = context.ContextState
B = context.ReviewBasis
R = context.ContextReason
L = context.LineageScope
SOURCE = "sha256:" + hashlib.sha256(b"synthetic source one").hexdigest()
SOURCE2 = "sha256:" + hashlib.sha256(b"synthetic source two").hexdigest()
BASES = {
    C.ORGANISM: B.ORGANISM,
    C.DISEASE_POPULATION: B.DIAGNOSIS,
    C.PRIMARY_POPULATION_MAPPING: B.POPULATION,
    C.SPECIMEN_MATERIAL: B.MATERIAL,
    C.ASSAY_CONTEXT: B.ASSAY,
    C.RAW_COUNT_COORDINATE: B.PROCESSING,
    C.BATCH_CORRECTION: B.PROCESSING,
    C.COLLECTION_TIMEPOINT: B.TIMEPOINT,
    C.TREATMENT_EXPOSURE: B.TREATMENT,
}


def _target(index=0):
    return context.ContextTarget(
        f"synthetic-private-rna-{index}",
        "sha256:" + hashlib.sha256(f"synthetic-lineage-{index}".encode()).hexdigest(),
    )


def _record(component=C.DISEASE_POPULATION, assertion=A.SUPPORTS_TARGET, **changes):
    baseline = component if isinstance(component, C) else C.DISEASE_POPULATION
    fields = {
        "record_key": "synthetic-" + baseline.value,
        "source_digest": SOURCE,
        "source_location": "synthetic-sheet:R3C8",
        "source_value": "synthetic-private-reviewed-value",
        "component": component,
        "assertion": assertion,
        "review_basis": BASES[baseline],
        "lineage_scope": L.EXACT_SPECIMEN,
    }
    fields.update(changes)
    return context.ReviewedContextRecord(**fields)


def _supported():
    return tuple(_record(component) for component in context.REQUIRED_COMPONENTS)


def _entry(records=(), target=None):
    return context.SpecimenContextEvidence(_target() if target is None else target, tuple(records))


def _assess(records, *, target=None):
    chosen = _target() if target is None else target
    return context.assess_context_inventory(
        (chosen,),
        (_entry(records, chosen),),
        verified_source_digests=(SOURCE, SOURCE2),
    )


def _manual_digest(value):
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def test_unknown_only_inventory_preserves_every_planned_target_and_manual_digests():
    targets = tuple(_target(index) for index in range(7))
    result = context.assess_context_inventory(targets)
    receipt = result.receipt
    assert [item.state for item in result.assessments] == [S.UNKNOWN] * 7
    assert receipt.planned_count == receipt.not_provided_count == receipt.state_counts.unknown == 7
    assert (
        receipt.provided_entry_count
        == receipt.verified_source_count
        == receipt.used_source_count
        == 0
    )
    assert receipt.input_record_count == receipt.distinct_record_count == 0
    assert [(row.reason_code, row.specimen_count) for row in receipt.reason_counts] == [
        (R.NOT_PROVIDED, 7)
    ]
    assert all(
        row.states.unknown == row.states.total == 7 for row in receipt.component_state_counts
    )
    assert dict(receipt.collection_timepoint_counts.values)["unknown"] == 7
    assert dict(receipt.treatment_exposure_counts.values)["unknown"] == 7
    axis = [{"rna_key": t.rna_key, "lineage_digest": t.lineage_digest} for t in targets]
    assert receipt.ordered_axis_digest == _manual_digest(axis)
    assert receipt.evidence_digest == _manual_digest(
        {
            "schema_version": "cptac-gbm-reviewed-context-evidence/1.0.0",
            "entries": [{**target, "provided": False, "records": []} for target in axis],
        }
    )
    assert receipt.verified_source_set_digest == _manual_digest([])


def test_explicit_empty_entry_differs_from_not_provided_without_filtering_axis():
    targets = (_target(), _target(1))
    result = context.assess_context_inventory(targets, (_entry(),))
    assert [a.state for a in result.assessments] == [S.UNKNOWN, S.UNKNOWN]
    assert result.receipt.provided_entry_count == result.receipt.not_provided_count == 1
    assert result.assessments[0].reason_codes == (R.MISSING_COMPONENT, R.NO_RECORDS)
    assert result.assessments[1].reason_codes == (R.NOT_PROVIDED,)


def test_required_source_claims_are_distinct_from_processing_operational_and_inference_context():
    result = _assess(_supported())
    assert result.assessments[0].state is S.SOURCE_SUPPORTED
    assert result.assessments[0].component_states[:5] == (S.SOURCE_SUPPORTED,) * 5
    assert result.assessments[0].component_states[5:] == (S.UNKNOWN,) * 4
    public = result.receipt.model_dump(mode="json")
    for key in (
        "source_assertions_independently_authenticated",
        "source_lineage_independently_reproved",
        "clinical_validation",
        "inference_context_constructed",
        "context_filters_count_preflight",
        "existing_eligibility_flag_overwritten",
        "operational_declarations_inferred",
        "models_executed",
    ):
        assert public[key] is False
    processing = (
        _record(C.RAW_COUNT_COORDINATE, A.OPPOSES_TARGET),
        _record(C.BATCH_CORRECTION, A.OPPOSES_TARGET),
    )
    changed = _assess(_supported() + processing)
    assert changed.assessments[0].state is S.SOURCE_SUPPORTED
    assert changed.assessments[0].component_states[5:7] == (S.OUT_OF_SCOPE,) * 2
    assert changed.receipt.inference_context_constructed is False


@pytest.mark.parametrize(
    ("timepoint", "treatment"),
    [("initial", "unexposed"), ("recurrent", "exposed"), ("other", "other")],
)
def test_collection_and_treatment_are_recorded_without_untreated_or_initial_only_rule(
    timepoint, treatment
):
    records = (
        *_supported(),
        _record(C.COLLECTION_TIMEPOINT, A.DESCRIPTIVE, descriptive_value=timepoint),
        _record(C.TREATMENT_EXPOSURE, A.DESCRIPTIVE, descriptive_value=treatment),
    )
    result = _assess(records)
    assert result.assessments[0].state is S.SOURCE_SUPPORTED
    assert result.assessments[0].collection_timepoint == timepoint
    assert result.assessments[0].treatment_exposure == treatment
    assert dict(result.receipt.collection_timepoint_counts.values)[timepoint] == 1
    assert dict(result.receipt.treatment_exposure_counts.values)[treatment] == 1


def test_conflicting_descriptive_records_remain_visible_without_changing_disease_state():
    records = (
        *_supported(),
        _record(C.COLLECTION_TIMEPOINT, A.DESCRIPTIVE, descriptive_value="initial"),
        _record(
            C.COLLECTION_TIMEPOINT,
            A.DESCRIPTIVE,
            descriptive_value="recurrent",
            record_key="recurrent",
        ),
        _record(C.TREATMENT_EXPOSURE, A.DESCRIPTIVE, descriptive_value="unexposed"),
        _record(
            C.TREATMENT_EXPOSURE, A.DESCRIPTIVE, descriptive_value="exposed", record_key="treated"
        ),
    )
    result = _assess(records)
    assert result.assessments[0].state is S.SOURCE_SUPPORTED
    assert result.assessments[0].component_states[-2:] == (S.CONFLICTING,) * 2
    assert (
        result.assessments[0].collection_timepoint
        == result.assessments[0].treatment_exposure
        == "conflicting"
    )
    assert R.CONTRADICTORY_DESCRIPTIONS in result.assessments[0].reason_codes


def test_four_state_partition_and_precedence_use_required_components_only():
    targets = tuple(_target(index) for index in range(4))
    disease_opposition = _record(assertion=A.OPPOSES_TARGET)
    contradictory = (*_supported(), _record(assertion=A.OPPOSES_TARGET, record_key="contradiction"))
    entries = (
        _entry(_supported(), targets[0]),
        _entry((disease_opposition,), targets[1]),
        _entry((), targets[2]),
        _entry(contradictory, targets[3]),
    )
    result = context.assess_context_inventory(targets, entries, verified_source_digests=(SOURCE,))
    assert tuple(item.state for item in result.assessments) == (
        S.SOURCE_SUPPORTED,
        S.OUT_OF_SCOPE,
        S.UNKNOWN,
        S.CONFLICTING,
    )
    assert result.receipt.state_counts.model_dump() == {
        "source_supported": 1,
        "out_of_scope": 1,
        "unknown": 1,
        "conflicting": 1,
    }
    assert all(row.states.total == 4 for row in result.receipt.component_state_counts)


@pytest.mark.parametrize(
    ("reason", "value"),
    [
        (R.SOURCE_FIELD_ABSENT, ""),
        (R.NOT_REPORTED, "not reported"),
        (R.NOT_TESTED, "not tested"),
        (R.INSUFFICIENT_ASSAY_SCOPE, "isolated negative IDH1 R132H IHC"),
        (R.INSUFFICIENT_ASSAY_SCOPE, "no mutation entry in a synthetic MAF"),
        (R.UNRESOLVED_PRIMARY_MAPPING, "Primary Tumor specimen role"),
        (R.UNRESOLVED_LINEAGE, "unresolved candidate source link"),
        (R.AMBIGUOUS_LINEAGE, "ambiguous candidate source link"),
    ],
)
def test_source_observations_do_not_become_diagnoses_or_age_ihc_rules(reason, value):
    scope = (
        L.AMBIGUOUS
        if reason is R.AMBIGUOUS_LINEAGE
        else L.UNRESOLVED
        if reason is R.UNRESOLVED_LINEAGE
        else L.EXACT_SPECIMEN
    )
    unknown = _record(
        assertion=A.UNKNOWN,
        review_basis=B.UNRESOLVED,
        reason_code=reason,
        source_value=value,
        lineage_scope=scope,
    )
    records = (
        *tuple(record for record in _supported() if record.component is not C.DISEASE_POPULATION),
        unknown,
    )
    result = _assess(records)
    assert result.assessments[0].state is (
        S.CONFLICTING if reason is R.AMBIGUOUS_LINEAGE else S.UNKNOWN
    )
    assert reason in result.assessments[0].reason_codes


def test_conflicts_are_permutation_invariant_and_duplicate_records_never_vote():
    records = (*_supported(), _record(assertion=A.OPPOSES_TARGET, record_key="opposition"))
    first = _assess(records)
    permuted = _assess(tuple(reversed(records)))
    assert first.receipt == permuted.receipt
    repeated = _assess(records + (_record(),) * 8)
    assert repeated.assessments[0].state is S.CONFLICTING
    assert repeated.receipt.distinct_record_count == len(records)
    assert repeated.receipt.duplicate_record_count == 8
    assert repeated.receipt.input_record_count == len(records) + 8


def test_explicit_source_correction_preserves_predecessor_without_latest_row_selection():
    old = _record(assertion=A.OPPOSES_TARGET, record_key="older")
    corrected = _record(
        record_key="corrected",
        source_digest=SOURCE2,
        supersedes=("older",),
        supersession_source_location="synthetic correction notice:R2C4",
    )
    others = tuple(
        record for record in _supported() if record.component is not C.DISEASE_POPULATION
    )
    without_relation = _record(record_key="newer", source_digest=SOURCE2)
    assert _assess((*others, old, without_relation)).assessments[0].state is S.CONFLICTING
    result = _assess((*others, corrected, old))
    assert result.assessments[0].state is S.SOURCE_SUPPORTED
    assert result.receipt.superseded_record_count == 1
    assert result.receipt.distinct_record_count == 6
    assert result.receipt.used_source_count == 2
    assert len(result.assessments[0]._records) == 6
    assert result.receipt == _assess((*others, old, corrected)).receipt


def test_source_correction_chain_is_acyclic_order_independent_and_can_retract_to_unknown():
    oldest = _record(record_key="oldest")
    middle = _record(
        assertion=A.OPPOSES_TARGET,
        record_key="middle",
        supersedes=("oldest",),
        supersession_source_location="synthetic correction one",
    )
    last = _record(
        assertion=A.UNKNOWN,
        review_basis=B.UNRESOLVED,
        reason_code=R.NOT_TESTED,
        record_key="last",
        supersedes=("middle",),
        supersession_source_location="synthetic correction two",
    )
    for permutation in itertools.permutations((oldest, middle, last)):
        result = _assess(permutation)
        assert result.assessments[0].state is S.UNKNOWN
        assert result.receipt.superseded_record_count == 2


def test_competing_source_corrections_do_not_resolve_their_new_contradiction_by_order():
    old = _record(record_key="old")
    one = _record(
        record_key="correction-one",
        supersedes=("old",),
        supersession_source_location="synthetic correction notice one",
    )
    two = _record(
        assertion=A.OPPOSES_TARGET,
        record_key="correction-two",
        supersedes=("old",),
        supersession_source_location="synthetic correction notice two",
    )
    for records in itertools.permutations((old, one, two)):
        result = _assess(records)
        assert result.assessments[0].state is S.CONFLICTING
        assert result.receipt.superseded_record_count == 1


def test_private_evidence_entry_rejects_nonrecord_payloads_before_classification():
    with pytest.raises(AdmissionError):
        context.SpecimenContextEvidence(_target(), (False,))
    with pytest.raises(AdmissionError):
        context.SpecimenContextEvidence(target=False, records=())
    with pytest.raises(AdmissionError):
        context.SpecimenContextEvidence(_target(), [])


@pytest.mark.parametrize(
    "records",
    [
        lambda: (
            _record(
                record_key="a", supersedes=("missing",), supersession_source_location="correction"
            ),
        ),
        lambda: (
            _record(record_key="a", supersedes=("b",), supersession_source_location="correction"),
            _record(record_key="b", supersedes=("a",), supersession_source_location="correction"),
        ),
        lambda: (
            _record(record_key="a", supersedes=("b",), supersession_source_location="correction"),
            _record(C.ORGANISM, record_key="b"),
        ),
        lambda: (
            _record(record_key="a"),
            _record(record_key="a", source_value="different private original"),
        ),
    ],
)
def test_invalid_correction_graph_and_conflicting_record_keys_fail_closed(records):
    with pytest.raises(AdmissionError):
        _assess(records())


@pytest.mark.parametrize(
    "changes",
    [
        {
            "supersedes": ("self",),
            "record_key": "self",
            "supersession_source_location": "correction",
        },
        {"supersedes": ("a", "a"), "supersession_source_location": "correction"},
        {"supersedes": ["a"], "supersession_source_location": "correction"},
        {"supersedes": ("a",)},
        {"supersession_source_location": "unsolicited correction location"},
        {
            "supersedes": tuple(f"r{x}" for x in range(65)),
            "supersession_source_location": "correction",
        },
    ],
)
def test_source_corrections_require_bounded_distinct_predecessors_and_explicit_location(changes):
    with pytest.raises(AdmissionError):
        _record(**changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"source_digest": "private-invalid-digest"},
        {"component": "disease_population"},
        {"assertion": "supports_target"},
        {"review_basis": B.PROCESSING},
        {"review_basis": B.UNRESOLVED},
        {"lineage_scope": "exact_specimen"},
        {"reason_code": "not_tested"},
        {"reason_code": R.NOT_TESTED},
        {"source_value": ""},
        {"source_value": "   "},
        {"source_location": "private\nlocation"},
        {"record_key": "private key"},
        {"descriptive_value": "initial"},
        {"lineage_scope": L.UNRESOLVED},
    ],
)
def test_record_strict_semantics_and_sanitized_failures(changes):
    with pytest.raises(AdmissionError) as error:
        _record(**changes)
    assert "private" not in str(error.value)
    assert error.value.__cause__ is None


@pytest.mark.parametrize(
    "changes",
    [
        {"assertion": A.UNKNOWN},
        {"assertion": A.UNKNOWN, "reason_code": R.EXPLICIT_OPPOSITION},
        {"assertion": A.UNKNOWN, "reason_code": R.NOT_TESTED, "lineage_scope": L.AMBIGUOUS},
    ],
)
def test_unknown_claims_require_valid_specific_reason_and_matching_lineage_reason(changes):
    with pytest.raises(AdmissionError):
        _record(**changes)


@pytest.mark.parametrize("descriptor", ["conflicting", "anything", True, 1])
def test_descriptive_input_cannot_assert_conflict_or_a_nonpolicy_value(descriptor):
    with pytest.raises(AdmissionError):
        _record(C.COLLECTION_TIMEPOINT, A.DESCRIPTIVE, descriptive_value=descriptor)


def test_descriptive_unknown_and_reviewed_case_scope_are_retained():
    record = _record(
        C.COLLECTION_TIMEPOINT,
        A.DESCRIPTIVE,
        descriptive_value="unknown",
        reason_code=R.NOT_REPORTED,
        lineage_scope=L.REVIEWED_CASE_TO_SPECIMEN,
    )
    result = _assess((*_supported(), record))
    assert result.assessments[0].state is S.SOURCE_SUPPORTED
    assert result.assessments[0].collection_timepoint == "unknown"
    assert R.NOT_REPORTED in result.assessments[0].reason_codes


def test_evidence_requires_exact_target_key_lineage_and_verified_source_bytes():
    target = _target()
    for evidence, verified in (
        ((_entry(_supported(), _target(1)),), (SOURCE,)),
        (
            (_entry(_supported(), context.ContextTarget(target.rna_key, "sha256:" + "f" * 64)),),
            (SOURCE,),
        ),
        ((_entry(_supported(), target),), ()),
    ):
        with pytest.raises(AdmissionError):
            context.assess_context_inventory((target,), evidence, verified_source_digests=verified)
    with pytest.raises(AdmissionError):
        context.assess_context_inventory(
            (target, _target(1)), (_entry(), _entry()), verified_source_digests=(SOURCE,)
        )
    with pytest.raises(AdmissionError):
        context.assess_context_inventory((target, target))
    with pytest.raises(AdmissionError):
        context.assess_context_inventory((target,), verified_source_digests=(SOURCE, SOURCE))


@pytest.mark.parametrize(
    ("targets", "evidence", "sources"),
    [
        ((), (), ()),
        ([], (), ()),
        ((True,), (), ()),
        ((_target(),), [], ()),
        ((_target(),), (True,), ()),
        ((_target(),), (), []),
        ((_target(),), (), ("bad",)),
        (tuple(_target(i) for i in range(context.MAX_CASES + 1)), (), ()),
        (
            (_target(),),
            (),
            tuple("sha256:" + f"{i:064x}" for i in range(context.MAX_CONTEXT_SOURCES + 1)),
        ),
    ],
)
def test_inventory_has_closed_axis_and_source_bounds_without_type_coercion(
    targets, evidence, sources
):
    with pytest.raises(AdmissionError):
        context.assess_context_inventory(targets, evidence, verified_source_digests=sources)


def _document(records=None):
    return {
        "schema_version": context.EVIDENCE_SCHEMA,
        "entries": [
            {
                "rna_key": _target().rna_key,
                "lineage_digest": _target().lineage_digest,
                "records": [
                    record._document() for record in (_supported() if records is None else records)
                ],
            }
        ],
    }


def test_closed_json_replays_typed_claims_and_absent_context_document_is_not_fabricated():
    document = _document()
    result = context.parse_context_evidence(
        json.dumps(document).encode(),
        targets=(_target(),),
        verified_source_digests=(SOURCE, SOURCE2),
    )
    assert result.receipt == _assess(_supported()).receipt
    empty = {"schema_version": context.EVIDENCE_SCHEMA, "entries": []}
    unknown = context.parse_context_evidence(json.dumps(empty).encode(), targets=(_target(),))
    assert unknown.receipt == context.assess_context_inventory((_target(),)).receipt


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"\xff",
        b"[]",
        b"null",
        b"{}",
        b'{"entries":{},"schema_version":"wrong"}',
        b'{"schema_version":"x","schema_version":"y","entries":[]}',
        b'{"schema_version":"cptac-gbm-reviewed-context-evidence/1.0.0","entries":[{}]}',
        b'{"schema_version":"cptac-gbm-reviewed-context-evidence/1.0.0","entries":[],"research_use_only":true}',
    ],
)
def test_json_rejects_malformed_extra_duplicate_or_operational_fields(payload):
    with pytest.raises(AdmissionError):
        context.parse_context_evidence(payload, targets=(_target(),))


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d["entries"][0]["records"][0].update(component="invalid"),
        lambda d: d["entries"][0]["records"][0].update(assertion=True),
        lambda d: d["entries"][0]["records"][0].update(record_key="private\nid"),
        lambda d: d["entries"][0]["records"][0].update(extra="private"),
        lambda d: d["entries"][0]["records"][0].update(supersedes="private"),
        lambda d: d["entries"][0]["records"].append(True),
        lambda d: d["entries"][0].update(records={}),
        lambda d: d.update(entries={}),
    ],
)
def test_json_record_schema_and_types_fail_without_echoing_private_values(change):
    document = _document()
    change(document)
    with pytest.raises(AdmissionError) as error:
        context.parse_context_evidence(
            json.dumps(document).encode(), targets=(_target(),), verified_source_digests=(SOURCE,)
        )
    assert "private" not in str(error.value)


def test_record_and_byte_bounds_cover_both_typed_and_json_entry_points(monkeypatch):
    monkeypatch.setattr(context, "MAX_CONTEXT_RECORDS", 2)
    with pytest.raises(AdmissionError):
        _entry(_supported())
    entries = (_entry((_record(),), _target()), _entry((_record(), _record()), _target(1)))
    with pytest.raises(AdmissionError):
        context.assess_context_inventory(
            (_target(), _target(1)), entries, verified_source_digests=(SOURCE,)
        )
    with pytest.raises(AdmissionError):
        context.parse_context_evidence(
            json.dumps(_document()).encode(),
            targets=(_target(),),
            verified_source_digests=(SOURCE,),
        )
    monkeypatch.setattr(context, "MAX_CONTEXT_BYTES", 10)
    with pytest.raises(AdmissionError):
        context.assess_context_inventory((_target(),))
    with pytest.raises(AdmissionError):
        context.parse_context_evidence(b"x" * 11, targets=(_target(),))


def test_private_wrappers_are_immutable_non_dataclass_nonpickleable_and_non_json():
    record = _record()
    inventory = _assess(_supported())
    objects = (_target(), record, _entry(), inventory.assessments[0], inventory)
    for value in objects:
        assert "synthetic" not in repr(value)
        assert not hasattr(value, "__dict__")
        with pytest.raises((AttributeError, TypeError)):
            value.private = "private"
        with pytest.raises((AttributeError, TypeError)):
            del value._rna_key
        with pytest.raises(TypeError):
            pickle.dumps(value)
        with pytest.raises(TypeError):
            json.dumps(value)
        with pytest.raises(TypeError):
            asdict(value)
    public = inventory.receipt.model_dump_json()
    for secret in (
        _target().rna_key,
        _target().lineage_digest,
        SOURCE,
        "synthetic-sheet",
        "synthetic-private-reviewed-value",
    ):
        assert secret not in public
    with pytest.raises(ValidationError):
        inventory.receipt.planned_count = 3


def test_context_inventory_cannot_invoke_the_existing_model_or_preprocessing(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("context admission invoked model preprocessing or inference")

    for name in ("_input_vector", "_forward", "analyze_gbm_rna_purity"):
        monkeypatch.setattr(engine, name, forbidden)
    assert _assess(_supported()).assessments[0].state is S.SOURCE_SUPPORTED
    assert context.assess_context_inventory((_target(),)).assessments[0].state is S.UNKNOWN


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d.update(verified_source_count=1, used_source_count=1),
        lambda d: d.update(input_record_count=1, distinct_record_count=1),
        lambda d: d.update(
            verified_source_count=1,
            used_source_count=1,
            input_record_count=1,
            distinct_record_count=1,
        ),
        lambda d: d.update(reason_counts=[]),
        lambda d: d["component_state_counts"][0]["states"].update(
            unknown=0,
            source_supported=1,
        ),
        lambda d: d["collection_timepoint_counts"].update(
            values=[
                ["initial", 1],
                ["recurrent", 0],
                ["other", 0],
                ["unknown", 0],
                ["conflicting", 0],
            ],
        ),
        lambda d: d["component_state_counts"][-1]["states"].update(
            unknown=0,
            out_of_scope=1,
        ),
        lambda d: d.update(profile_id="a-different-context-policy/1.0.0"),
    ],
)
def test_public_receipt_rejects_impossible_source_absence_and_descriptor_partitions(change):
    document = context.assess_context_inventory((_target(),)).receipt.model_dump(mode="json")
    change(document)
    with pytest.raises(ValidationError):
        context.ContextInventoryReceipt.model_validate_json(json.dumps(document))


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d.update(planned_count=True),
        lambda d: d.update(provided_entry_count=1),
        lambda d: d.update(used_source_count=1),
        lambda d: d.update(duplicate_record_count=1),
        lambda d: d.update(superseded_record_count=1),
        lambda d: d["state_counts"].update(unknown=0),
        lambda d: d.update(component_state_counts=list(reversed(d["component_state_counts"]))),
        lambda d: d["component_state_counts"][0]["states"].update(unknown=0),
        lambda d: d["collection_timepoint_counts"]["values"].reverse(),
        lambda d: d["treatment_exposure_counts"]["values"][0].__setitem__(1, 2),
        lambda d: d.update(inference_context_constructed=True),
        lambda d: d.update(clinical_validation=True),
        lambda d: d.update(extra="private"),
    ],
)
def test_public_receipt_rejects_unconserved_counts_coercion_and_false_claims(change):
    document = context.assess_context_inventory((_target(),)).receipt.model_dump(mode="json")
    change(document)
    with pytest.raises(ValidationError):
        context.ContextInventoryReceipt.model_validate_json(json.dumps(document))
