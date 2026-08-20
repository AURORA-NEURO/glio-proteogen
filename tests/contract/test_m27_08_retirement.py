"""M27-08 contract, schema and strict replay tests."""

# Contract tests intentionally exercise exact numeric/cardinality boundaries.
# ruff: noqa: PLR2004

import pytest
from evals.m27_08.fixture import build_request

from glio_proteogen.contracts.m27_08 import (
    ArchiveStatus,
    contract_json_schemas,
)
from glio_proteogen.contracts.m27_08.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.modules.c27_complex_activity.m27_08_retirement import (
    M2708Service,
    RetirementAuthorizationError,
)


def test_all_ten_schemas_are_strict_and_identified() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == 10
    assert all(value["$schema"].endswith("2020-12/schema") for value in schemas.values())
    assert all(value["x-glio-contract"]["provisionalAbi"] for value in schemas.values())


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


@pytest.mark.parametrize(
    "media_type",
    [
        "application/vnd.attacker.m27-07+json",
        "text/m27-07",
        "application/vnd.glio-proteogen.m27-07+json;profile=attacker",
    ],
)
def test_upstream_media_type_requires_exact_m27_07_contract(media_type: str) -> None:
    request = build_request()
    forged_artifact = request.source_artifacts[0].model_copy(update={"media_type": media_type})
    forged = request.model_copy(update={"source_artifacts": (forged_artifact,)})
    with pytest.raises(RetirementAuthorizationError, match="unsupported upstream artifact"):
        M2708Service().execute(forged)


def test_invalid_archive_status_is_not_executed() -> None:
    result = M2708Service().execute(build_request(incomplete=True, active_dependency=True))
    assert result.status.value == "abstained"
    assert result.findings
