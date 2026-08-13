"""Black-box parity, strict ingress, and hostile authorization for M03-04."""

from __future__ import annotations

import copy
import json
from collections.abc import Iterator, Mapping
from typing import TYPE_CHECKING, Any, Final, cast

import pytest
from evals.m03_04.run import build_scenario_request
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters import cli as cli_adapter
from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m03_03 import ProteinInferenceAdmissionDisposition
from glio_proteogen.contracts.m03_04 import (
    M0304_MAX_CANONICAL_REQUEST_BYTES,
    ComputeProteinInferenceQualityRequest,
    ProteinInferenceAssayQualityProfile,
    ProteinInferenceQualityPolicy,
    ProteinInferenceQualityResult,
    ProteinInferenceQualityThreshold,
)
from glio_proteogen.contracts.m03_04.canonical import (
    configuration_digest,
    fact_ledger_digest,
    raw_quality_receipt_digest,
)
from glio_proteogen.kernel.models import SupportStatus
from glio_proteogen.modules.c03_protein_inference.m03_04_quality_metrics import (
    M0304Service,
    ProteinInferenceQualityAuthorizationError,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration
SCHEMA_NAMES: Final = (
    "request",
    "output",
    "policy",
    "profile",
    "threshold",
    "raw-quality-receipt",
    "fact-ledger",
    "metric",
    "finding",
)
HTTP_OK: Final = 200
HTTP_FORBIDDEN: Final = 403
HTTP_UNSUPPORTED_MEDIA_TYPE: Final = 415
HTTP_UNPROCESSABLE_CONTENT: Final = 422
CLI_USAGE_ERROR: Final = 2
PRIVATE_CANARY: Final = "PRIVATE_M0304_INTERFACE_CANARY"
AUTHORIZATION_DENIALS: Final = (
    ("approved_configuration", "rejected"),
    ("identity_lineage", "unresolved"),
    ("provenance", "rejected"),
    ("consent", "withheld"),
    ("quality", "rejected"),
    ("support", "rejected"),
    ("intended_use", "rejected"),
)
SEMANTIC_INGRESS_MUTATIONS: Final = (
    "threshold_direction",
    "threshold_order",
    "profile_duplicate_versions",
    "profile_duplicate_metric",
    "policy_duplicate_identity",
    "policy_overlapping_domain",
    "source_duplicate_diagnostics",
    "source_missing_decoded_digest",
    "source_partial_decode_with_digest",
    "source_decoded_overflow",
    "source_raw_overflow",
    "source_version_without_format",
    "claim_duplicate_findings",
    "duplicate_source_identifier",
    "source_count_mismatch",
    "bound_claim_role_mismatch",
    "missing_spectra_role",
    "duplicate_required_source_role",
    "peptide_claim_count_mismatch",
    "conditional_role_mismatch",
    "duplicate_context_role",
    "claim_role_shape_mismatch",
    "peptide_build_mismatch",
    "ptm_build_mismatch",
    "peptide_partition_mismatch",
    "detection_partition_mismatch",
    "censored_non_detection_state",
    "nonobserved_detection_counts",
    "censored_detection_with_missing",
    "input_postdates_execution",
    "identity_control_binding_mismatch",
    "approved_configuration_binding_mismatch",
    "ledger_presence_mismatch",
    "ledger_time_mismatch",
)


class _HostileRequest(Mapping[str, object]):
    """Expose only authorization context; every governed accessor is hostile."""

    def __init__(self, context: object) -> None:
        self._context = context

    def __getitem__(self, key: str) -> object:
        if key == "context":
            return self._context
        raise AssertionError(PRIVATE_CANARY)

    def __iter__(self) -> Iterator[str]:
        raise AssertionError(PRIVATE_CANARY)

    def __len__(self) -> int:
        raise AssertionError(PRIVATE_CANARY)


def _payload() -> dict[str, Any]:
    return copy.deepcopy(build_scenario_request().model_dump(mode="json"))


def _source(payload: dict[str, Any], role: str) -> dict[str, Any]:
    return cast(
        "dict[str, Any]",
        next(
            item
            for item in payload["raw_quality_receipt"]["sources"]
            if item["role"] == role
        ),
    )


def _mutate_semantic_payload(payload: dict[str, Any], mutation: str) -> None:  # noqa: C901, PLR0912, PLR0915 - explicit ingress matrix.
    receipt = cast("dict[str, Any]", payload["raw_quality_receipt"])
    ledger = cast("dict[str, Any]", payload["fact_ledger"])
    profile = cast("dict[str, Any]", payload["policy"]["profiles"][0])
    thresholds = cast("list[dict[str, Any]]", profile["thresholds"])
    sources = cast("list[dict[str, Any]]", receipt["sources"])
    claims = cast("list[dict[str, Any]]", receipt["claims"])

    if mutation == "threshold_direction":
        thresholds[0]["direction"] = "at_most"
    elif mutation == "threshold_order":
        thresholds[0]["warning_threshold_ppm"] = 700_001
    elif mutation == "profile_duplicate_versions":
        profile["approved_assay_protocol_versions"].append(
            profile["approved_assay_protocol_versions"][0]
        )
    elif mutation == "profile_duplicate_metric":
        thresholds[1]["metric_code"] = thresholds[0]["metric_code"]
    elif mutation == "policy_duplicate_identity":
        payload["policy"]["profiles"].append(copy.deepcopy(profile))
    elif mutation == "policy_overlapping_domain":
        duplicate = copy.deepcopy(profile)
        duplicate["profile_id"] = "profile.synthetic.m0304.overlap"
        payload["policy"]["profiles"].append(duplicate)
    elif mutation == "source_duplicate_diagnostics":
        sources[0]["diagnostic_codes"] = ["decode_failed", "decode_failed"]
    elif mutation == "source_missing_decoded_digest":
        sources[0]["decoded_digest"] = None
    elif mutation == "source_partial_decode_with_digest":
        sources[0]["diagnostic_codes"] = ["decoded_size_limit_exceeded"]
    elif mutation == "source_decoded_overflow":
        sources[0]["decoded_size_bytes"] = 2_147_483_649
    elif mutation == "source_raw_overflow":
        sources[0]["source_size_bytes"] = 536_870_913
    elif mutation == "source_version_without_format":
        sources[0]["detected_format"] = None
    elif mutation == "claim_duplicate_findings":
        claims[0]["finding_codes"] = ["missing_lineage_path", "missing_lineage_path"]
    elif mutation == "duplicate_source_identifier":
        sources[1]["source_id"] = sources[0]["source_id"]
    elif mutation == "source_count_mismatch":
        receipt["source_count"] += 1
    elif mutation == "bound_claim_role_mismatch":
        bundle = _source(payload, "complex_activity_input_bundle")
        peptide = _source(payload, "peptide_evidence")
        bundle["bound_claim_id"], peptide["bound_claim_id"] = (
            peptide["bound_claim_id"],
            bundle["bound_claim_id"],
        )
    elif mutation == "missing_spectra_role":
        sources.remove(_source(payload, "spectra"))
        receipt["source_count"] = len(sources)
    elif mutation == "duplicate_required_source_role":
        duplicate = copy.deepcopy(_source(payload, "canonical_sequences"))
        duplicate["source_id"] = "source.canonical-sequences.duplicate"
        sources.append(duplicate)
        receipt["source_count"] = len(sources)
    elif mutation == "peptide_claim_count_mismatch":
        _source(payload, "peptide_evidence")["role"] = "spectra"
    elif mutation == "conditional_role_mismatch":
        sources.remove(_source(payload, "contaminant_sequences"))
        receipt["source_count"] = len(sources)
    elif mutation == "duplicate_context_role":
        duplicate = copy.deepcopy(_source(payload, "genomic_context"))
        duplicate["source_id"] = "source.genomic-context.duplicate"
        sources.append(duplicate)
        receipt["source_count"] = len(sources)
    elif mutation == "claim_role_shape_mismatch":
        next(item for item in claims if item["claim_role"] == "ambiguity_manifest")[
            "claim_role"
        ] = "complex_activity_input_bundle"
    elif mutation == "peptide_build_mismatch":
        build = _source(payload, "peptide_evidence")["build"]
        build["declared_build_id"] = "search-space.foreign"
        build["expected_build_id"] = "search-space.foreign"
    elif mutation == "ptm_build_mismatch":
        build = _source(payload, "ptm_vocabulary")["build"]
        build["declared_build_id"] = "vocabulary.foreign"
        build["expected_build_id"] = "vocabulary.foreign"
    elif mutation == "peptide_partition_mismatch":
        ledger["counts"]["eligible_peptide_evidence_count"] += 1
    elif mutation == "detection_partition_mismatch":
        ledger["counts"]["detection_eligible_group_count"] += 1
    elif mutation == "censored_non_detection_state":
        ledger["states"]["peptide_assignment"] = "censored"
    elif mutation == "nonobserved_detection_counts":
        ledger["states"]["detection_support"] = "missing"
    elif mutation == "censored_detection_with_missing":
        ledger["states"]["detection_support"] = "censored"
        ledger["counts"]["quantifiable_group_count"] -= 1
        ledger["counts"]["detection_missing_group_count"] = 1
    elif mutation == "input_postdates_execution":
        payload["policy"]["reviewed_at"] = "2026-08-14T00:00:00Z"
    elif mutation == "identity_control_binding_mismatch":
        payload["context"]["references"]["identity_lineage"]["binding_digest"] = (
            "sha256:" + ("0" * 64)
        )
    elif mutation == "approved_configuration_binding_mismatch":
        payload["context"]["references"]["approved_configuration"]["evidence"][
            "digest"
        ] = "sha256:" + ("0" * 64)
    elif mutation == "ledger_presence_mismatch":
        payload["fact_ledger"] = None
    elif mutation == "ledger_time_mismatch":
        ledger["recorded_at"] = "2020-01-01T00:00:00Z"
        ledger["ledger_digest"] = fact_ledger_digest(ledger)
    else:  # pragma: no cover - the parameter inventory is closed above.
        raise AssertionError(mutation)


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_api_and_cli_export_identical_m03_04_schemas(tmp_path: Path, name: str) -> None:
    with TestClient(create_app(tmp_path / f"schema-{name}.sqlite3")) as client:
        response = client.get(f"/v1/contracts/M03-04/{name}/schema")
    cli = CliRunner().invoke(
        cli_app,
        ["protein-inference-quality", "export-schema", name],
    )

    assert response.status_code == HTTP_OK
    assert cli.exit_code == 0, cli.output
    assert response.json() == json.loads(cli.stdout)
    assert response.json()["$id"] == (
        "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M03-04:1.0.0:"
        f"{name}"
    )


def test_library_service_api_and_cli_return_complete_equal_result(tmp_path: Path) -> None:
    request = build_scenario_request()
    payload = request.model_dump_json()
    request_path = tmp_path / "quality-request.json"
    request_path.write_text(payload, encoding="utf-8")
    expected = M0304Service().execute(request)

    with TestClient(create_app(tmp_path / "quality.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M03-04/quality",
            content=payload,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["protein-inference-quality", "compute", str(request_path)],
    )

    assert response.status_code == HTTP_OK, response.text
    assert cli.exit_code == 0, cli.output
    assert (
        ProteinInferenceQualityResult.model_validate_json(response.content, strict=True)
        == expected
    )
    assert ProteinInferenceQualityResult.model_validate_json(cli.stdout, strict=True) == expected


@pytest.mark.parametrize(("role", "denied_state"), AUTHORIZATION_DENIALS)
def test_every_denied_control_precedes_hostile_ledger_traversal(
    tmp_path: Path,
    role: str,
    denied_state: str,
) -> None:
    payload = _payload()
    payload["context"]["references"][role]["state"] = denied_state
    payload["fact_ledger"] = PRIVATE_CANARY
    serialized = json.dumps(payload)
    request_path = tmp_path / f"denied-hostile-{role}.json"
    request_path.write_text(serialized, encoding="utf-8")

    with TestClient(create_app(tmp_path / f"denied-{role}.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M03-04/quality",
            content=serialized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["protein-inference-quality", "compute", str(request_path)],
    )

    assert response.status_code == HTTP_FORBIDDEN
    assert response.json() == {
        "detail": "upstream controls do not authorize protein-inference quality computation"
    }
    assert PRIVATE_CANARY not in response.text
    assert cli.exit_code == CLI_USAGE_ERROR
    assert PRIVATE_CANARY not in cli.output
    assert "Traceback" not in cli.output


def test_service_denial_does_not_traverse_or_disclose_hostile_accessors() -> None:
    context = _payload()["context"]
    context["references"]["support"]["state"] = "rejected"

    with pytest.raises(ProteinInferenceQualityAuthorizationError) as caught:
        M0304Service.validate_request(_HostileRequest(context))

    assert PRIVATE_CANARY not in str(caught.value)


@pytest.mark.parametrize(
    ("mutation", "expected_term"),
    [
        ("duplicate", "duplicate"),
        ("nonfinite", "finite"),
        ("unknown", "extra_forbidden"),
        ("coercion", "int_type"),
    ],
)
def test_api_and_cli_reject_every_non_strict_json_class_without_disclosure(
    tmp_path: Path,
    mutation: str,
    expected_term: str,
) -> None:
    request = build_scenario_request()
    if mutation in {"duplicate", "nonfinite"}:
        serialized = request.model_dump_json()
        operation = '"operation":"compute_protein_inference_quality"'
        if mutation == "duplicate":
            serialized = serialized.replace(operation, f"{operation},{operation}", 1)
        else:
            serialized = f'{serialized[:-1]},"{PRIVATE_CANARY}":NaN}}'
    else:
        payload = _payload()
        if mutation == "unknown":
            payload[PRIVATE_CANARY] = "must-not-be-reflected"
        else:
            payload["policy"]["max_sources"] = "64"
        serialized = json.dumps(payload)
    request_path = tmp_path / f"{mutation}.json"
    request_path.write_text(serialized, encoding="utf-8")

    with TestClient(create_app(tmp_path / f"strict-{mutation}.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M03-04/quality",
            content=serialized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["protein-inference-quality", "compute", str(request_path)],
    )

    assert response.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert cli.exit_code == CLI_USAGE_ERROR
    assert expected_term in cli.output.lower()
    assert PRIVATE_CANARY not in response.text
    assert PRIVATE_CANARY not in cli.output
    assert "Traceback" not in cli.output


def test_api_and_cli_distinguish_exact_two_mib_from_first_byte_past_limit(
    tmp_path: Path,
) -> None:
    exact = b"{" + b" " * (M0304_MAX_CANONICAL_REQUEST_BYTES - 1)
    oversized = exact + b" "
    exact_path = tmp_path / "exact-limit.json"
    oversized_path = tmp_path / "oversized.json"
    exact_path.write_bytes(exact)
    oversized_path.write_bytes(oversized)

    with TestClient(create_app(tmp_path / "size.sqlite3")) as client:
        exact_api = client.post(
            "/v1/modules/M03-04/quality",
            content=exact,
            headers={"content-type": "application/json"},
        )
        oversized_api = client.post(
            "/v1/modules/M03-04/quality",
            content=oversized,
            headers={"content-type": "application/json"},
        )
    exact_cli = CliRunner().invoke(
        cli_app,
        ["protein-inference-quality", "compute", str(exact_path)],
    )
    oversized_cli = CliRunner().invoke(
        cli_app,
        ["protein-inference-quality", "compute", str(oversized_path)],
    )

    assert len(exact) == M0304_MAX_CANONICAL_REQUEST_BYTES
    assert len(oversized) == M0304_MAX_CANONICAL_REQUEST_BYTES + 1
    assert exact_api.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert exact_api.json()["detail"][0]["type"] == "json_invalid_syntax"
    assert oversized_api.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert oversized_api.json()["detail"][0]["type"] == "json_too_large"
    assert exact_cli.exit_code == CLI_USAGE_ERROR
    assert "json_invalid_syntax" in exact_cli.output
    assert oversized_cli.exit_code == CLI_USAGE_ERROR
    assert "byte limit" in oversized_cli.output
    assert "Traceback" not in exact_cli.output + oversized_cli.output


def test_api_content_type_is_exact_but_accepts_json_charset(tmp_path: Path) -> None:
    payload = build_scenario_request().model_dump_json()

    with TestClient(create_app(tmp_path / "media.sqlite3")) as client:
        rejected = client.post(
            "/v1/modules/M03-04/quality",
            content=payload,
            headers={"content-type": "text/plain"},
        )
        accepted = client.post(
            "/v1/modules/M03-04/quality",
            content=payload,
            headers={"content-type": "application/json; charset=utf-8"},
        )

    assert rejected.status_code == HTTP_UNSUPPORTED_MEDIA_TYPE
    assert rejected.json() == {"detail": "content-type must be application/json"}
    assert accepted.status_code == HTTP_OK, accepted.text


def test_invalid_schema_name_is_rejected_by_api_and_cli(tmp_path: Path) -> None:
    invalid_name = "not-a-quality-contract"

    with TestClient(create_app(tmp_path / "schema-invalid.sqlite3")) as client:
        response = client.get(f"/v1/contracts/M03-04/{invalid_name}/schema")
    cli = CliRunner().invoke(
        cli_app,
        ["protein-inference-quality", "export-schema", invalid_name],
    )

    assert response.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert response.json()["detail"][0]["type"] == "literal_error"
    assert cli.exit_code == CLI_USAGE_ERROR
    assert "Invalid value" in cli.output
    assert "Traceback" not in cli.output


def test_cli_sanitizes_a_late_request_read_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_path = tmp_path / "unreadable-after-cli-validation.json"
    request_path.write_text(build_scenario_request().model_dump_json(), encoding="utf-8")

    def fail_read(_path: object, *, max_bytes: int) -> bytes:
        del max_bytes
        raise OSError(PRIVATE_CANARY)

    monkeypatch.setattr(cli_adapter, "read_bounded", fail_read)
    cli = CliRunner().invoke(
        cli_app,
        ["protein-inference-quality", "compute", str(request_path)],
    )

    assert cli.exit_code == CLI_USAGE_ERROR
    assert "unable to read or decode request document" in cli.output
    assert PRIVATE_CANARY not in cli.output
    assert "Traceback" not in cli.output


@pytest.mark.parametrize("mutation", SEMANTIC_INGRESS_MUTATIONS)
def test_api_rejects_semantically_open_or_contradictory_m03_04_requests(
    tmp_path: Path,
    mutation: str,
) -> None:
    payload = _payload()
    _mutate_semantic_payload(payload, mutation)

    with TestClient(create_app(tmp_path / f"semantic-{mutation}.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M03-04/quality",
            content=json.dumps(payload),
            headers={"content-type": "application/json"},
        )

    assert response.status_code == HTTP_UNPROCESSABLE_CONTENT, response.text
    assert response.json()["detail"]
    assert "Traceback" not in response.text


@pytest.mark.parametrize(
    ("upstream_disposition", "support_status", "expected_disposition"),
    [
        ("rejected", "unsupported", "rejected"),
        ("quarantined", "review_required", "quarantined"),
        ("abstained", "unsupported", "abstained"),
    ],
)
def test_service_api_and_cli_preserve_each_typed_upstream_safe_failure(
    tmp_path: Path,
    upstream_disposition: str,
    support_status: str,
    expected_disposition: str,
) -> None:
    canonical = build_scenario_request()
    receipt_payload = canonical.raw_quality_receipt.model_dump(mode="python")
    receipt_payload.update(
        {
            "upstream_disposition": upstream_disposition,
            "upstream_support_status": SupportStatus(support_status),
            "upstream_human_review_required": True,
            "sources": (),
            "claims": (),
        }
    )
    receipt_payload["upstream_disposition"] = ProteinInferenceAdmissionDisposition(
        upstream_disposition
    )
    receipt_payload["receipt_digest"] = raw_quality_receipt_digest(receipt_payload)
    receipt = canonical.raw_quality_receipt.model_validate(receipt_payload, strict=True)
    request = canonical.model_copy(
        update={"raw_quality_receipt": receipt, "fact_ledger": None}
    )
    request = ComputeProteinInferenceQualityRequest.model_validate(
        request,
        strict=True,
    )
    expected = M0304Service().execute(request)
    serialized = request.model_dump_json()
    request_path = tmp_path / f"safe-{upstream_disposition}.json"
    request_path.write_text(serialized, encoding="utf-8")

    with TestClient(create_app(tmp_path / f"safe-{upstream_disposition}.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M03-04/quality",
            content=serialized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["protein-inference-quality", "compute", str(request_path)],
    )

    assert response.status_code == HTTP_OK, response.text
    assert cli.exit_code == 0, cli.output
    assert expected.disposition.value == expected_disposition
    assert ProteinInferenceQualityResult.model_validate_json(
        response.content, strict=True
    ) == expected
    assert ProteinInferenceQualityResult.model_validate_json(cli.stdout, strict=True) == expected


def test_optional_warning_remains_qualified_but_limits_all_public_outputs(
    tmp_path: Path,
) -> None:
    canonical = build_scenario_request()
    threshold = next(
        item
        for item in canonical.policy.profiles[0].thresholds
        if item.metric_code.value == "proteoform_discrimination_coverage"
    )
    changed_threshold = ProteinInferenceQualityThreshold.model_validate(
        threshold.model_copy(
            update={
                "required": False,
                "pass_threshold_ppm": 800_000,
                "warning_threshold_ppm": 700_000,
            }
        ),
        strict=True,
    )
    profile = canonical.policy.profiles[0]
    changed_profile = ProteinInferenceAssayQualityProfile.model_validate(
        profile.model_copy(
            update={
                "thresholds": tuple(
                    changed_threshold if item == threshold else item
                    for item in profile.thresholds
                )
            }
        ),
        strict=True,
    )
    policy = ProteinInferenceQualityPolicy.model_validate(
        canonical.policy.model_copy(update={"profiles": (changed_profile,)}),
        strict=True,
    )
    approved = canonical.context.references.approved_configuration
    references = canonical.context.references.model_copy(
        update={
            "approved_configuration": approved.model_copy(
                update={
                    "evidence": approved.evidence.model_copy(
                        update={"digest": configuration_digest(policy)}
                    )
                }
            )
        }
    )
    request = ComputeProteinInferenceQualityRequest.model_validate(
        canonical.model_copy(
            update={
                "context": canonical.context.model_copy(update={"references": references}),
                "policy": policy,
            }
        ),
        strict=True,
    )
    expected = M0304Service().execute(request)
    serialized = request.model_dump_json()
    request_path = tmp_path / "optional-warning.json"
    request_path.write_text(serialized, encoding="utf-8")

    with TestClient(create_app(tmp_path / "optional-warning.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M03-04/quality",
            content=serialized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["protein-inference-quality", "compute", str(request_path)],
    )

    assert response.status_code == HTTP_OK, response.text
    assert cli.exit_code == 0, cli.output
    assert expected.disposition.value == "qualified"
    assert expected.support.status.value == "limited"
    assert expected.human_review_required is True
    assert ProteinInferenceQualityResult.model_validate_json(
        response.content, strict=True
    ) == expected
    assert ProteinInferenceQualityResult.model_validate_json(cli.stdout, strict=True) == expected
