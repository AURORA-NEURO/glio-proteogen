"""Admit the 2024 author clinical supplement without upgrading historical pathology.

The private result retains source field names and values. Case-level observations
are distinct from exact selected-specimen observations, and neither is a newly
inferred diagnosis. This adapter never opens files or constructs purity requests.
"""

from __future__ import annotations

import hashlib
import math
from collections import Counter
from typing import Final, Never, SupportsIndex

from glio_proteogen.research.cptac_gbm_external_admission.contracts import SourceLock
from glio_proteogen.research.cptac_gbm_rna_purity_admission.context import ContextState
from glio_proteogen.research.cptac_gbm_rna_purity_execution.clinical import (
    ClinicalAdmission,
    ClinicalAdmissionReceipt,
    ClinicalCase,
    _table,
    _workbook,
)
from glio_proteogen.research.cptac_gbm_rna_purity_execution.contracts import (
    ExecutionError,
    canonical_bytes,
    digest,
)

SOURCE_URL: Final = "https://ars.els-cdn.com/content/image/1-s2.0-S1535610824002290-mmc2.xlsx"
PUBLICATION_DOI: Final = "10.1016/j.ccell.2024.06.004"
SOURCE_LOCK: Final = SourceLock(
    69_098,
    "bdc15f7b77145e8f96cb20492d7f0f43",
    "f91ab4ee136e2a9baf75b72213e63bad2b7b606ead60cd1ef24bf8ae76ed0d27",
)
HEADERS: Final = (
    "preferred_sample_name",
    "case_id",
    "parent_sample_ids",
    "sample_type",
    "tumor_occurrence_sequence",
    "excluded_in_downstream_analysis",
    "exclusion_reason",
    "cohort",
    "path_diagnosis",
    "who_tumor_grade",
    "idh1_r132h_mut_status",
    "mgmt_methyl_status",
    "tumor_site",
    "age",
    "sex",
    "height",
    "weight",
    "bmi",
    "cancer_history",
    "country_of_origin",
    "race",
    "ethnicity",
    "ethnicity_self_identify",
    "smoking_history",
    "smoking_history_detail",
    "secondhand_smoke_exposure",
    "tumor_laterality",
    "tumor_site_curated",
    "tumor_site_curation_notes",
    "follow_up_period",
    "vital_status",
    "path_diag_to_last_contact_days",
    "path_diag_to_death_days",
    "lost_to_follow_up",
    "new_tumor_after_treatment",
    "path_diag_to_new_tumor_days",
    "treatment",
    "alcohol_history",
    "cause_of_death",
    "cause_of_death_detail",
    "Recurrence_status",
    "Recurrence_free_survival_days_from_path_diag",
)
_MISSING: Final = frozenset(("", "NA", "N/A", "Unknown", "Not Performed"))
_IDH: Final = {
    "Negative": "negative",
    "Not Performed": "not_performed",
    "NA": "unknown",
    "": "unknown",
    "Positive": "positive",
}


class SourceReviewError(ExecutionError):
    """Sanitized source integrity, schema or clinical ancestry failure."""


def _require(condition: bool, message: str) -> None:  # noqa: FBT001
    if not condition:
        raise SourceReviewError(message)


class _Private:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"<{type(self).__name__} private>"

    def __setattr__(self, _name: str, _value: object) -> Never:
        raise AttributeError("private source evidence is immutable")

    def __delattr__(self, _name: str) -> Never:
        raise AttributeError("private source evidence is immutable")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> Never:
        raise TypeError("private clinical rows cannot be serialized")

    def __getstate__(self) -> Never:
        raise TypeError("private clinical rows cannot be serialized")


class ClinicalContextFact(_Private):
    """A parsed source row with a separately recorded specimen ancestry result."""

    __slots__ = ("_binding", "_digest", "_exact", "_row", "_row_number")
    _binding: tuple[str, str, str]
    _row: tuple[str, ...]
    _row_number: int
    _exact: bool
    _digest: str

    def __init__(self, case: ClinicalCase, row: dict[str, str], row_number: int) -> None:
        binding = (case.target.case_key, case.target.sample_key, case.target.lineage_digest)
        values = tuple(row[field] for field in HEADERS)
        parents = row["parent_sample_ids"].split(",")
        _require(
            len(parents) == 1 and all(parent and parent == parent.strip() for parent in parents),
            "author parent specimen identifiers are invalid",
        )
        exact = case.target.sample_key in parents
        object.__setattr__(self, "_binding", binding)
        object.__setattr__(self, "_row", values)
        object.__setattr__(self, "_row_number", row_number)
        object.__setattr__(self, "_exact", exact)
        object.__setattr__(
            self,
            "_digest",
            digest(
                {
                    "binding": binding,
                    "source_row": row_number,
                    "values": values,
                    "exact_selected_specimen": exact,
                    "source_sha256": "sha256:" + SOURCE_LOCK.sha256,
                }
            ),
        )

    @property
    def exact_selected_specimen(self) -> bool:
        return self._exact

    @property
    def evidence_digest(self) -> str:
        return self._digest

    def source_value(self, field: str) -> str:
        """Return parsed source text, retaining explicit missingness tokens."""
        if field not in HEADERS:
            raise SourceReviewError("unrecognized clinical source field")
        return self._row[HEADERS.index(field)]

    def selected_specimen_value(self, field: str) -> str:
        """Require exact ancestry before a row is used as specimen evidence."""
        if not self.exact_selected_specimen:
            raise SourceReviewError("source row does not name the selected specimen")
        return self.source_value(field)


class SourceReview(_Private):
    __slots__ = ("_facts", "_stats")
    _facts: tuple[ClinicalContextFact, ...]
    _stats: bytes

    def __init__(self, facts: tuple[ClinicalContextFact, ...], stats: dict[str, object]) -> None:
        object.__setattr__(self, "_facts", facts)
        object.__setattr__(self, "_stats", canonical_bytes(stats))

    @property
    def facts(self) -> tuple[ClinicalContextFact, ...]:
        return self._facts

    @property
    def aggregate_bytes(self) -> bytes:
        return self._stats


def _source_rows(payload: bytes) -> list[dict[str, str]]:
    _require(
        type(payload) is bytes
        and len(payload) == SOURCE_LOCK.bytes
        and hashlib.sha256(payload).hexdigest() == SOURCE_LOCK.sha256
        and hashlib.md5(payload, usedforsecurity=False).hexdigest() == SOURCE_LOCK.md5,
        "author clinical supplement does not match the reviewed snapshot",
    )
    sheets = _workbook(payload)
    _require(
        tuple(sheets) == ("README", "clinical_data", "longitudinal_genetic_alt")
        and any(
            row.get("B") == "clinical_data"
            and row.get("C") == "Clinical characteristics and survival information"
            for row in sheets["README"]
        ),
        "author clinical supplement description is invalid",
    )
    rows = _table(sheets["clinical_data"], HEADERS)
    _require(
        len(rows) == 264
        and all(tuple(row) == HEADERS for row in rows)
        and len({row["preferred_sample_name"] for row in rows}) == len(rows),
        "author clinical supplement schema or preferred sample axis is invalid",
    )
    return rows


def _baseline_cases(clinical: ClinicalAdmission) -> tuple[ClinicalCase, ...]:
    _require(type(clinical) is ClinicalAdmission, "verified baseline clinical evidence is required")
    receipt = ClinicalAdmissionReceipt.model_validate_json(
        canonical_bytes(clinical.receipt.model_dump(mode="json"))
    )
    cases = clinical.cases
    _require(
        type(cases) is tuple
        and len(cases) == 72
        and all(type(case) is ClinicalCase for case in cases)
        and len({case.target.case_key for case in cases}) == 72
        and len({case.target.sample_key for case in cases}) == 72
        and digest([case.target._document() for case in cases]) == receipt.ordered_axis_digest
        and digest([case.observations_digest for case in cases]) == receipt.evidence_digest,
        "baseline clinical axis or evidence binding is invalid",
    )
    _require(
        all(
            ClinicalCase(
                case.target,
                case.component_states,
                case.observations,
                case.source_hold_reasons,
                case._flags,
            ).observations_digest
            == case.observations_digest
            for case in cases
        ),
        "baseline clinical observations changed after admission",
    )
    _require(
        sum(case.source_hold for case in cases) == 1
        and sum(not case.source_hold and case.state is ContextState.OUT_OF_SCOPE for case in cases)
        == 6
        and sum(not case.source_hold and case.state is ContextState.UNKNOWN for case in cases)
        == 65,
        "baseline clinical partition differs from the reviewed source scope",
    )
    return tuple(
        case for case in cases if not case.source_hold and case.state is ContextState.UNKNOWN
    )


def _nonnegative_number(value: str) -> bool:
    if value in _MISSING:
        return False
    try:
        number = float(value)
    except ValueError:
        return False
    return math.isfinite(number) and number >= 0


def _availability(facts: tuple[ClinicalContextFact, ...]) -> dict[str, int]:
    return {
        "reported_age": sum(_nonnegative_number(fact.source_value("age")) for fact in facts),
        "sex": sum(fact.source_value("sex") not in _MISSING for fact in facts),
        "mgmt_status": sum(
            fact.source_value("mgmt_methyl_status") not in _MISSING for fact in facts
        ),
        "vital_status": sum(
            fact.source_value("vital_status") in ("Living", "Deceased") for fact in facts
        ),
        "survival_days": sum(
            any(
                _nonnegative_number(fact.source_value(field))
                for field in ("path_diag_to_last_contact_days", "path_diag_to_death_days")
            )
            for fact in facts
        ),
        "treatment_history": sum(fact.source_value("treatment") not in _MISSING for fact in facts),
    }


def review_source(clinical: ClinicalAdmission, payload: bytes) -> SourceReview:
    """Review exactly the 65 unknown cases, preserving prior exclusions and holds."""
    try:
        targets = _baseline_cases(clinical)
        rows = _source_rows(payload)
        sample_owners = {case.target.sample_key: case.target.case_key for case in clinical.cases}
        facts = []
        for case in targets:
            matches = [
                (index, row)
                for index, row in enumerate(rows, 2)
                if row["case_id"] == case.target.case_key
                and row["preferred_sample_name"] == case.target.case_key
            ]
            _require(len(matches) == 1, "author clinical case join is absent or ambiguous")
            row_number, row = matches[0]
            _require(
                all(
                    sample_owners.get(parent, case.target.case_key) == case.target.case_key
                    for parent in row["parent_sample_ids"].split(",")
                ),
                "author clinical parent specimen belongs to a different selected case",
            )
            _require(
                row["sample_type"] == "CPTAC Pro. Primary Tumor"
                and row["cohort"] == "Discovery"
                and row["path_diagnosis"] == "Glioblastoma"
                and row["who_tumor_grade"] == "IV"
                and row["excluded_in_downstream_analysis"] in ("0", "False")
                and row["idh1_r132h_mut_status"] in _IDH,
                "author target clinical schema differs from the reviewed snapshot",
            )
            facts.append(ClinicalContextFact(case, row, row_number))
        ordered = tuple(facts)
        counts = Counter(_IDH[fact.source_value("idh1_r132h_mut_status")] for fact in ordered)
        exact = sum(fact.exact_selected_specimen for fact in ordered)
        return SourceReview(
            ordered,
            {
                "publication_doi": PUBLICATION_DOI,
                "source_url": SOURCE_URL,
                "source_sha256": "sha256:" + SOURCE_LOCK.sha256,
                "source_bytes": SOURCE_LOCK.bytes,
                "reviewed_cases": len(ordered),
                "historical_pathology_cases": len(ordered),
                "explicit_idh_wildtype_cases": 0,
                "explicit_idh2_scope_cases": 0,
                "explicit_integrated_diagnosis_cases": 0,
                "idh1_r132h": {name: counts[name] for name in _IDH.values()},
                "specimen": {
                    "exact_specimen": exact,
                    "specimen_mismatch": len(ordered) - exact,
                    "unresolved": 0,
                },
                "field_availability": _availability(ordered),
                "source_qualified_cases": 0,
                "resolution_evidence_digest": digest([fact.evidence_digest for fact in ordered]),
                "ordered_target_bindings_digest": digest(
                    [
                        (case.target.case_key, case.target.sample_key, case.target.lineage_digest)
                        for case in targets
                    ]
                ),
            },
        )
    except ExecutionError:
        raise
    except (TypeError, ValueError, KeyError, AttributeError, OverflowError):
        raise SourceReviewError("author clinical source review failed") from None


__all__ = [
    "HEADERS",
    "PUBLICATION_DOI",
    "SOURCE_LOCK",
    "SOURCE_URL",
    "ClinicalContextFact",
    "SourceReview",
    "SourceReviewError",
    "review_source",
]
