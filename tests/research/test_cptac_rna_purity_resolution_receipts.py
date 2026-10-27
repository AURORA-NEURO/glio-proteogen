"""Synthetic source-review contracts; no clinical rows, RNA or models are accessed."""

import json

import pytest
from pydantic import ValidationError

from glio_proteogen.research.cptac_gbm_rna_purity_resolution.contracts import (
    MAX_RECEIPT_BYTES,
    ResolutionError,
    canonical_bytes,
    checked_receipt_document,
    digest,
    parse_receipt,
    seal_document,
    validate_digest,
)
from glio_proteogen.research.cptac_gbm_rna_purity_resolution.receipts import (
    ClinicalResolutionReceipt,
    ClinicalSourceReceipt,
    FieldAvailability,
    Idh1Counts,
    SpecimenCounts,
)

_ZERO = "sha256:" + "0" * 64


def _source_document():
    provisional = ClinicalSourceReceipt(
        idh1_r132h=Idh1Counts(negative=40, not_performed=15, unknown=10, positive=0),
        specimen=SpecimenCounts(exact_specimen=64, specimen_mismatch=1, unresolved=0),
        field_availability=FieldAvailability(
            reported_age=65,
            sex=65,
            mgmt_status=42,
            vital_status=55,
            survival_days=50,
            treatment_history=48,
        ),
        source_receipt_digest=_ZERO,
    ).model_dump(mode="json")
    return seal_document(provisional, "source_receipt_digest")


def _review_document():
    provisional = ClinicalResolutionReceipt(
        baseline_clinical_receipt_digest=digest("synthetic-baseline"),
        ordered_case_axis_digest=digest("synthetic-complete-axis"),
        ordered_target_bindings_digest=digest("synthetic-targeted-bindings"),
        source_receipt_digest=_source_document()["source_receipt_digest"],
        resolution_evidence_digest=digest("synthetic-private-evidence"),
        receipt_digest=_ZERO,
    ).model_dump(mode="json")
    return seal_document(provisional, "receipt_digest")


def _checked_source(document):
    return checked_receipt_document(
        document, ClinicalSourceReceipt, digest_field="source_receipt_digest"
    )


def _checked_review(document):
    return checked_receipt_document(
        document, ClinicalResolutionReceipt, digest_field="receipt_digest"
    )


def test_sealed_review_preserves_axis_and_independent_evidence_dimensions():
    source = _checked_source(_source_document())
    review = _checked_review(_review_document())
    assert source.idh1_r132h.negative == 40
    assert source.specimen.specimen_mismatch == 1
    assert source.field_availability.mgmt_status == 42
    assert source.explicit_idh_wildtype_cases == source.explicit_idh2_scope_cases == 0
    assert review.source_receipt_digest == source.source_receipt_digest
    assert (
        review.targeted_unknown_cases
        + review.preserved_out_of_scope_cases
        + review.preserved_source_hold_cases
        == review.planned_cases
    )
    assert source.source_qualified_cases == review.source_qualified_cases == 0
    assert review.eligibility_admitted is review.rna_read is review.model_executed is False


def test_even_complete_negative_idh1_and_exact_specimen_do_not_qualify_wildtype():
    document = _source_document()
    document["idh1_r132h"] = {"negative": 65, "not_performed": 0, "unknown": 0, "positive": 0}
    document["specimen"] = {"exact_specimen": 65, "specimen_mismatch": 0, "unresolved": 0}
    source = _checked_source(seal_document(document, "source_receipt_digest"))
    assert source.source_qualified_cases == 0
    document["source_qualified_cases"] = 65
    with pytest.raises(ResolutionError):
        _checked_source(seal_document(document, "source_receipt_digest"))


@pytest.mark.parametrize(
    ("model_type", "values"),
    [
        (Idh1Counts, {"negative": 64, "not_performed": 0, "unknown": 0, "positive": 0}),
        (Idh1Counts, {"negative": 65, "not_performed": 1, "unknown": 0, "positive": 0}),
        (SpecimenCounts, {"exact_specimen": 63, "specimen_mismatch": 1, "unresolved": 0}),
        (SpecimenCounts, {"exact_specimen": 64, "specimen_mismatch": 1, "unresolved": 1}),
    ],
)
def test_observation_partitions_cannot_drop_or_duplicate_targets(model_type, values):
    with pytest.raises(ValidationError):
        model_type.model_validate(values)


@pytest.mark.parametrize("invalid", [-1, 66, True, 1.0, "1"])
def test_descriptive_availability_is_a_strict_bounded_count(invalid):
    fields = dict.fromkeys(FieldAvailability.model_fields, 0)
    fields["reported_age"] = invalid
    with pytest.raises(ValidationError):
        FieldAvailability.model_validate(fields)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_url", "https://ars.els-cdn.com/content/image/other.xlsx?token=PRIVATE"),
        ("source_sha256", "sha256:" + "1" * 64),
        ("source_bytes", 69_099),
        ("source_bytes", 69_098.0),
        ("publication_doi", "10.1016/other"),
        ("reviewed_cases", 64),
        ("historical_pathology_cases", 64),
        ("explicit_idh_wildtype_cases", 1),
        ("explicit_idh2_scope_cases", 1),
        ("explicit_integrated_diagnosis_cases", 1),
        ("source_qualified_cases", 1),
        ("source_qualified_cases", False),
    ],
)
def test_resealing_cannot_change_locked_source_or_invent_clinical_support(field, value):
    document = {**_source_document(), field: value}
    with pytest.raises(ResolutionError):
        _checked_source(seal_document(document, "source_receipt_digest"))


@pytest.mark.parametrize(
    "field",
    [
        "clinical_diagnosis_inferred",
        "research_population_inferred",
        "eligibility_admitted",
        "rna_read",
        "model_executed",
        "individual_results_exported",
        "research_use_only",
    ],
)
@pytest.mark.parametrize("invalid", [0, 1, "false", None])
def test_review_declarations_reject_scalar_aliases_even_after_resealing(field, invalid):
    document = {**_review_document(), field: invalid}
    with pytest.raises(ResolutionError):
        _checked_review(seal_document(document, "receipt_digest"))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("planned_cases", 71),
        ("targeted_unknown_cases", 64),
        ("preserved_out_of_scope_cases", 5),
        ("preserved_source_hold_cases", 0),
        ("source_qualified_cases", 1),
        ("planned_cases", 72.0),
        ("source_qualified_cases", False),
        ("research_use_only", False),
        ("clinical_diagnosis_inferred", True),
    ],
)
def test_review_cannot_rewrite_baseline_partition_or_claim_new_actions(field, value):
    document = {**_review_document(), field: value}
    with pytest.raises(ResolutionError):
        _checked_review(seal_document(document, "receipt_digest"))


def test_changed_evidence_binding_invalidates_seal_and_requires_new_review_digest():
    original = _review_document()
    changed = {**original, "resolution_evidence_digest": digest("different-evidence")}
    with pytest.raises(ResolutionError, match="seal"):
        _checked_review(changed)
    resealed = seal_document(changed, "receipt_digest")
    assert _checked_review(resealed).receipt_digest != _checked_review(original).receipt_digest


def test_closed_receipt_rejects_private_rows_without_echoing_them():
    private_value = "PRIVATE-SAMPLE-DO-NOT-DISCLOSE"
    document = {**_review_document(), "individual_rows": [private_value]}
    with pytest.raises(ResolutionError) as error:
        _checked_review(seal_document(document, "receipt_digest"))
    assert private_value not in str(error.value)


def test_saved_review_requires_all_materialized_defaults():
    document = _review_document()
    del document["clinical_diagnosis_inferred"]
    with pytest.raises(ResolutionError, match="complete"):
        _checked_review(seal_document(document, "receipt_digest"))


def test_constructed_or_mutated_model_cannot_bypass_saved_review_checks():
    source = _checked_source(_source_document())
    with pytest.raises(ValidationError):
        source.source_qualified_cases = 1
    corrupted = ClinicalSourceReceipt.model_construct(
        **{name: getattr(source, name) for name in ClinicalSourceReceipt.model_fields}
    )
    object.__setattr__(corrupted, "source_qualified_cases", 1)
    with pytest.raises(ResolutionError):
        _checked_source(seal_document(corrupted.model_dump(mode="json"), "source_receipt_digest"))


def test_receipt_parser_accepts_whitespace_but_not_nested_duplicate_keys():
    document = _source_document()
    payload = json.dumps(document, indent=2).encode()
    parsed = parse_receipt(payload, ClinicalSourceReceipt, digest_field="source_receipt_digest")
    assert parsed == _checked_source(document)
    duplicate = canonical_bytes(document).replace(b'"negative":40', b'"negative":40,"negative":40')
    with pytest.raises(ResolutionError, match="JSON"):
        parse_receipt(duplicate, ClinicalSourceReceipt, digest_field="source_receipt_digest")


@pytest.mark.parametrize("payload", [b"", b"\xff", b"{", b"[]", b"null", "{}"])
def test_receipt_parser_rejects_invalid_or_wrong_kind_payloads(payload):
    with pytest.raises(ResolutionError):
        parse_receipt(payload, ClinicalResolutionReceipt, digest_field="receipt_digest")


def test_receipt_byte_limits_apply_before_json_and_typed_admission():
    with pytest.raises(ResolutionError, match="byte bound"):
        parse_receipt(
            b" " * (MAX_RECEIPT_BYTES + 1),
            ClinicalResolutionReceipt,
            digest_field="receipt_digest",
        )
    document = {**_review_document(), "padding": "x" * MAX_RECEIPT_BYTES}
    with pytest.raises(ResolutionError, match="byte bound"):
        _checked_review(seal_document(document, "receipt_digest"))


@pytest.mark.parametrize("value", [None, b"sha256:" + b"a" * 64, "sha256:" + "A" * 64, "bad"])
def test_digest_validation_is_exact(value):
    with pytest.raises(ResolutionError):
        validate_digest(value)
    assert validate_digest(_ZERO) == _ZERO


@pytest.mark.parametrize("value", [float("nan"), object(), "\ud800"])
def test_unencodable_values_fail_without_echoing_input(value):
    with pytest.raises(ResolutionError, match="cannot be encoded"):
        canonical_bytes(value)


def test_canonical_binding_ignores_mapping_insertion_order():
    assert canonical_bytes({"b": 2, "a": 1}) == b'{"a":1,"b":2}'
    assert digest({"b": 2, "a": 1}) == digest({"a": 1, "b": 2})


@pytest.mark.parametrize("document", [[], None, {1: "invalid-key"}])
def test_sealing_requires_a_closed_object_kind(document):
    with pytest.raises(ResolutionError):
        seal_document(document, "receipt_digest")


def test_invalid_seal_role_and_untyped_model_are_rejected():
    with pytest.raises(ResolutionError, match="seal field"):
        seal_document({}, "other_digest")
    with pytest.raises(ResolutionError, match="typed"):
        checked_receipt_document(_review_document(), object, digest_field="receipt_digest")
    with pytest.raises(ResolutionError, match="typed"):
        checked_receipt_document(
            _review_document(), FieldAvailability, digest_field="receipt_digest"
        )


def test_missing_or_malformed_seal_is_rejected():
    document = _review_document()
    del document["receipt_digest"]
    with pytest.raises(ResolutionError, match="digest"):
        _checked_review(document)


def test_cross_document_binding_cannot_be_used_as_the_review_self_seal():
    wrong_seal = seal_document(_review_document(), "source_receipt_digest")
    with pytest.raises(ResolutionError, match="typed"):
        checked_receipt_document(
            wrong_seal, ClinicalResolutionReceipt, digest_field="source_receipt_digest"
        )
