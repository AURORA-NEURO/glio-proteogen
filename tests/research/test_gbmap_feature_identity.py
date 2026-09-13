from __future__ import annotations

import hashlib
import json

import pytest
from pydantic import ValidationError

from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.research.gbmap_deconvolution.errors import (
    GbmapInputError,
    GbmapSourceAdmissionError,
)
from glio_proteogen.research.gbmap_deconvolution.feature_identity import (
    FeatureIdentityEntry,
    FeatureIdentityMatch,
    HgncIdentityRecord,
    build_feature_identity_crosswalk,
    load_feature_identity_crosswalk_bytes,
    parse_hgnc_complete_set,
    production_feature_identity_crosswalk,
    require_stable_feature_indices,
)

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64


def _records() -> tuple[HgncIdentityRecord, ...]:
    return (
        HgncIdentityRecord(
            hgnc_id="HGNC:1",
            approved_symbol="CURRENT",
            ensembl_gene_id="ENSG00000000001",
            previous_symbols=frozenset({"OLD"}),
            alias_symbols=frozenset({"ALIAS", "COLLISION"}),
        ),
        HgncIdentityRecord(
            hgnc_id="HGNC:2",
            approved_symbol="SECOND",
            ensembl_gene_id=None,
            previous_symbols=frozenset({"COLLISION"}),
            alias_symbols=frozenset({"CURRENT"}),
        ),
    )


def _crosswalk():
    return build_feature_identity_crosswalk(
        ("CURRENT", "OLD", "ALIAS", "COLLISION", "UNKNOWN"),
        _records(),
        gbmap_source_sha256=DIGEST_A,
        hgnc_source_sha256=DIGEST_B,
        hgnc_source_bytes=123,
        hgnc_source_id="fixture-hgnc",
    )


def _artifact_bytes() -> bytes:
    return canonical_json_bytes(_crosswalk().model_dump(mode="json"))


def _artifact_digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def test_exact_current_symbol_wins_and_every_disposition_is_explicit() -> None:
    crosswalk = _crosswalk()
    assert tuple(entry.match_status for entry in crosswalk.entries) == (
        FeatureIdentityMatch.EXACT_APPROVED_SYMBOL,
        FeatureIdentityMatch.UNIQUE_PREVIOUS_OR_ALIAS_SYMBOL,
        FeatureIdentityMatch.UNIQUE_PREVIOUS_OR_ALIAS_SYMBOL,
        FeatureIdentityMatch.AMBIGUOUS_PREVIOUS_OR_ALIAS_SYMBOL,
        FeatureIdentityMatch.UNRESOLVED,
    )
    assert crosswalk.entries[0].hgnc_id == "HGNC:1"
    assert crosswalk.entries[0].ensembl_gene_id == "ENSG00000000001"
    assert crosswalk.entries[3].hgnc_id is None
    assert crosswalk.entries[4].hgnc_id is None
    assert crosswalk.usable_feature_indices == (0,)
    assert crosswalk.counts.model_dump(mode="json") == {
        "source_feature_count": 5,
        "exact_approved_symbol_count": 1,
        "unique_previous_or_alias_symbol_count": 2,
        "ambiguous_previous_or_alias_symbol_count": 1,
        "unresolved_count": 1,
        "stable_hgnc_mapping_count": 3,
        "unique_model_eligible_hgnc_count": 1,
        "duplicate_stable_identity_entry_count": 2,
    }


def test_production_crosswalk_is_digest_locked_and_deduplicates_stable_identity() -> None:
    crosswalk = production_feature_identity_crosswalk()
    assert crosswalk.counts.source_feature_count == 5_000
    assert crosswalk.counts.stable_hgnc_mapping_count == 4_924
    assert crosswalk.counts.unique_model_eligible_hgnc_count == 4_923
    assert crosswalk.counts.duplicate_stable_identity_entry_count == 1
    by_symbol = {entry.input_symbol: index for index, entry in enumerate(crosswalk.entries)}
    assert by_symbol["LINC00632"] in crosswalk.usable_feature_indices
    assert by_symbol["CDR1-AS"] not in crosswalk.usable_feature_indices


def test_crosswalk_artifact_contains_no_hgnc_names_alias_lists_or_model_data() -> None:
    document = json.loads(_artifact_bytes())
    assert set(document["entries"][0]) == {
        "input_symbol",
        "hgnc_id",
        "ensembl_gene_id",
        "match_status",
    }
    flattened = _artifact_bytes().decode("utf-8").lower()
    for forbidden in (
        "patient",
        "gene_counts",
        "signature",
        "previous_symbols",
        "alias_symbols",
    ):
        assert forbidden not in flattened
    assert document["policy"]["donor_data_retained"] is False
    assert document["policy"]["expression_data_retained"] is False
    assert document["policy"]["fitted_model_parameters_retained"] is False
    assert document["policy"]["runtime_mount_permitted"] is False


def test_generic_loader_requires_canonical_bytes_and_binds_artifact_digest() -> None:
    raw = _artifact_bytes()
    loaded = load_feature_identity_crosswalk_bytes(
        raw,
        expected_artifact_digest=_artifact_digest(raw),
        require_production_bindings=False,
    )
    assert loaded == _crosswalk()
    with pytest.raises(GbmapSourceAdmissionError, match="artifact digest mismatch"):
        load_feature_identity_crosswalk_bytes(
            raw,
            expected_artifact_digest=DIGEST_A,
            require_production_bindings=False,
        )
    pretty = json.dumps(json.loads(raw), indent=2).encode()
    with pytest.raises(GbmapSourceAdmissionError, match="not canonical JSON"):
        load_feature_identity_crosswalk_bytes(
            pretty,
            expected_artifact_digest=_artifact_digest(pretty),
            require_production_bindings=False,
        )


def test_semantic_tampering_and_duplicate_json_keys_fail_closed() -> None:
    document = json.loads(_artifact_bytes())
    document["entries"][0]["hgnc_id"] = "HGNC:999"
    tampered = canonical_json_bytes(document)
    with pytest.raises(GbmapSourceAdmissionError, match="contract is invalid"):
        load_feature_identity_crosswalk_bytes(
            tampered,
            expected_artifact_digest=_artifact_digest(tampered),
            require_production_bindings=False,
        )
    duplicate = b'{"schema_version":"a","schema_version":"b"}'
    with pytest.raises(GbmapSourceAdmissionError, match="not strict JSON"):
        load_feature_identity_crosswalk_bytes(
            duplicate,
            expected_artifact_digest=_artifact_digest(duplicate),
            require_production_bindings=False,
        )


def test_stable_indices_require_exact_original_feature_order() -> None:
    crosswalk = _crosswalk()
    symbols = tuple(entry.input_symbol for entry in crosswalk.entries)
    assert require_stable_feature_indices(symbols, crosswalk) == (0,)
    with pytest.raises(GbmapInputError, match="locked HGNC crosswalk order"):
        require_stable_feature_indices(tuple(reversed(symbols)), crosswalk)


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"hgnc_id": None}, "mapped identity state"),
        (
            {
                "hgnc_id": None,
                "match_status": FeatureIdentityMatch.UNRESOLVED,
            },
            "Ensembl ID requires",
        ),
        ({"input_symbol": " PADDED "}, "surrounding whitespace"),
    ],
)
def test_entry_state_is_strict(updates: dict[str, object], message: str) -> None:
    payload: dict[str, object] = {
        "input_symbol": "GENE",
        "hgnc_id": "HGNC:1",
        "ensembl_gene_id": "ENSG00000000001",
        "match_status": FeatureIdentityMatch.EXACT_APPROVED_SYMBOL,
    }
    payload.update(updates)
    with pytest.raises(ValidationError, match=message):
        FeatureIdentityEntry.model_validate(payload)


def test_hgnc_complete_set_parser_retains_identity_fields_only() -> None:
    raw = (
        b"hgnc_id\tsymbol\tstatus\talias_symbol\tprev_symbol\tensembl_gene_id\tname\n"
        b'HGNC:1\tCURRENT\tApproved\t"A|B"\tOLD\tENSG00000000001\tprivate name\n'
    )
    records = parse_hgnc_complete_set(raw)
    assert records == (
        HgncIdentityRecord(
            hgnc_id="HGNC:1",
            approved_symbol="CURRENT",
            ensembl_gene_id="ENSG00000000001",
            previous_symbols=frozenset({"OLD"}),
            alias_symbols=frozenset({"A", "B"}),
        ),
    )
    assert "private name" not in repr(records)


@pytest.mark.parametrize(
    "raw",
    [
        b"not\tthe\trequired\theader\n",
        (
            b"hgnc_id\tsymbol\tstatus\talias_symbol\tprev_symbol\tensembl_gene_id\n"
            b"HGNC:1\tA\tEntry Withdrawn\t\t\tENSG00000000001\n"
        ),
        (
            b"hgnc_id\tsymbol\tstatus\talias_symbol\tprev_symbol\tensembl_gene_id\n"
            b"HGNC:1\tA\tApproved\t\t\tENSG00000000001\n"
            b"HGNC:1\tB\tApproved\t\t\tENSG00000000002\n"
        ),
    ],
)
def test_malformed_hgnc_sources_fail_closed(raw: bytes) -> None:
    with pytest.raises(GbmapSourceAdmissionError):
        parse_hgnc_complete_set(raw)


def test_builder_rejects_duplicate_source_symbols_and_duplicate_hgnc_rows() -> None:
    with pytest.raises(GbmapSourceAdmissionError, match="nonempty and unique"):
        build_feature_identity_crosswalk(
            ("A", "A"),
            _records(),
            gbmap_source_sha256=DIGEST_A,
            hgnc_source_sha256=DIGEST_B,
            hgnc_source_bytes=1,
            hgnc_source_id="fixture",
        )
    with pytest.raises(GbmapSourceAdmissionError, match="duplicate identities"):
        build_feature_identity_crosswalk(
            ("A",),
            (_records()[0], _records()[0]),
            gbmap_source_sha256=DIGEST_A,
            hgnc_source_sha256=DIGEST_B,
            hgnc_source_bytes=1,
            hgnc_source_id="fixture",
        )
