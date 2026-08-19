"""M27-08 contract, schema and strict replay tests."""

# Contract tests intentionally exercise exact numeric/cardinality boundaries.
# ruff: noqa: PLR2004

from typing import Any, cast

import pytest
from evals.m27_08.fixture import build_request

from glio_proteogen.contracts.m27_08 import (
    ArchiveStatus,
    ComplexActivityRetirementResult,
    contract_json_schemas,
)
from glio_proteogen.contracts.m27_08.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.modules.c27_complex_activity.m27_08_retirement import M2708Service


def test_all_ten_schemas_are_strict_and_identified() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == 10
    for value in schemas.values():
        schema = cast("dict[str, Any]", value)
        assert str(schema["$schema"]).endswith("2020-12/schema")
        metadata = cast("dict[str, Any]", schema["x-glio-contract"])
        assert metadata["provisionalAbi"]


def test_request_digest_is_order_sensitive_for_controlled_sequences() -> None:
    request = build_request()
    swapped = request.model_copy(
        update={"source_artifacts": tuple(reversed(request.source_artifacts))}
    )
    assert canonical_request_digest(request) != canonical_request_digest(swapped)


def test_unverified_archive_forces_abstention() -> None:
    request = build_request()
    bad = request.model_copy(
        update={"archive": request.archive.model_copy(update={"status": ArchiveStatus.PRESERVED})}
    )
    assert M2708Service().execute(bad).status.value == "abstained"


def test_result_replay_rejects_forged_digest() -> None:
    result = M2708Service().execute(build_request())
    forged = result.model_copy(update={"result_digest": "sha256:" + "0" * 64})
    assert not M2708Service().verify(forged)


def test_result_replay_rejects_self_rehashed_forged_package() -> None:
    result = M2708Service().execute(build_request())
    assert result.package is not None
    forged_package = result.package.model_copy(update={"version": "9.9.9"})
    forged = result.model_copy(update={"package": forged_package})
    rehashed = forged.model_copy(update={"result_digest": result_payload_digest(forged)})
    assert not M2708Service().verify(rehashed)


@pytest.mark.parametrize(
    "field",
    [
        "criteria",
        "migrations",
        "preserved_evidence",
        "communications",
        "archive",
        "configuration",
        "evidence",
    ],
)
def test_result_contract_rejects_self_rehashed_package_payload_forgery(field: str) -> None:
    result = M2708Service().execute(build_request())
    assert result.package is not None
    package = result.package
    if field == "criteria":
        forged_package = package.model_copy(
            update={
                "criteria": (
                    package.criteria[0].model_copy(update={"statement": "forged"}),
                    *package.criteria[1:],
                )
            }
        )
    elif field == "migrations":
        forged_package = package.model_copy(
            update={
                "migrations": (
                    package.migrations[0].model_copy(
                        update={"target_reference": "target://forged"}
                    ),
                    *package.migrations[1:],
                )
            }
        )
    elif field == "preserved_evidence":
        forged_package = package.model_copy(
            update={
                "preserved_evidence": (
                    package.preserved_evidence[0].model_copy(update={"retention_class": "forged"}),
                    *package.preserved_evidence[1:],
                )
            }
        )
    elif field == "communications":
        forged_package = package.model_copy(
            update={
                "communications": (
                    package.communications[0].model_copy(update={"message": "forged"}),
                    *package.communications[1:],
                )
            }
        )
    elif field == "archive":
        forged_package = package.model_copy(
            update={
                "archive": package.archive.model_copy(
                    update={"archive_reference": "archive://forged"}
                )
            }
        )
    elif field == "configuration":
        forged_package = package.model_copy(
            update={"configuration": package.configuration.model_copy(update={"version": "9.9.9"})}
        )
    else:
        forged_package = package.model_copy(
            update={"evidence": (package.evidence[0].model_copy(update={"claim": "forged"}),)}
        )
    forged = result.model_copy(update={"package": forged_package})
    rehashed = forged.model_copy(update={"result_digest": result_payload_digest(forged)})
    with pytest.raises(ValueError, match=f"executed result package {field.replace('_', ' ')}"):
        ComplexActivityRetirementResult.model_validate(
            rehashed.model_dump(mode="python"), strict=True
        )


def test_result_contract_binds_deterministic_result_and_package_ids() -> None:
    result = M2708Service().execute(build_request())
    assert result.package is not None
    forged_result = result.model_copy(update={"result_id": "result.m2708.forged"})
    with pytest.raises(ValueError, match="result id must be derived"):
        ComplexActivityRetirementResult.model_validate(
            forged_result.model_dump(mode="python"), strict=True
        )
    forged_package = result.package.model_copy(update={"package_id": "package.m2708.forged"})
    forged_result = result.model_copy(update={"package": forged_package})
    with pytest.raises(ValueError, match="package id must be derived"):
        ComplexActivityRetirementResult.model_validate(
            forged_result.model_dump(mode="python"), strict=True
        )


def test_abstention_has_no_package_and_requires_review() -> None:
    result = M2708Service().execute(build_request(incomplete=True))
    assert result.status.value == "abstained"
    assert result.package is None
    assert result.human_review_required


def test_unknown_request_member_is_rejected() -> None:
    payload = build_request().model_dump(mode="json")
    payload["unknown_member"] = True
    with pytest.raises(ValueError, match="validation failed"):
        M2708Service().validate_request(payload)


def test_duplicate_source_artifacts_are_rejected_before_retirement() -> None:
    request = build_request()
    duplicate = request.model_copy(
        update={"source_artifacts": (request.source_artifacts[0], request.source_artifacts[0])}
    )
    with pytest.raises(ValueError, match="source artifact ids"):
        M2708Service().execute(duplicate)


def test_invalid_archive_status_is_not_executed() -> None:
    result = M2708Service().execute(build_request(incomplete=True, active_dependency=True))
    assert result.status.value == "abstained"
    assert result.findings
