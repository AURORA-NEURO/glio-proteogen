"""M27-08 adversarial closure tests."""

# ruff: noqa: PT011, RUF005

import json
import runpy
import sys
from pathlib import Path

import pytest
from evals.m27_08.fixture import build_request
from typer.testing import CliRunner

from glio_proteogen.contracts.m27_08 import (
    ArchiveStatus,
    ComplexActivityRetirementResult,
    EvidencePreservation,
    LongTermArchive,
    RetirementFinding,
    RetirementFindingCode,
    RetirementPackage,
    RetirementStatus,
)
from glio_proteogen.contracts.m27_08.canonical import normalized_request, result_payload_digest
from glio_proteogen.modules.c27_complex_activity.m27_08_retirement import M2708Service
from glio_proteogen.modules.c27_complex_activity.m27_08_retirement import cli as cli_module
from glio_proteogen.modules.c27_complex_activity.m27_08_retirement.cli import cli


@pytest.mark.parametrize(
    "field", ["criteria", "migrations", "preserved_evidence", "communications", "source_artifacts"]
)
def test_empty_required_collections_reject(field: str) -> None:
    payload = build_request().model_dump(mode="json")
    payload[field] = []
    with pytest.raises(ValueError):
        M2708Service().validate_request(payload)


@pytest.mark.parametrize(
    "field", ["mass_spectrometry_proteome", "genome_transcriptome", "ptm_annotations"]
)
def test_scientific_input_is_opaque_reference_only(field: str) -> None:
    payload = build_request().model_dump(mode="json")
    payload[field]["media_type"] = "application/x-hostile-content"
    request = M2708Service().validate_request(payload)
    assert getattr(request, field).artifact_id.startswith("m2708.artifact")


def test_unsupported_upstream_media_abstains_without_scientific_traversal() -> None:
    request = build_request().model_copy(
        update={
            "source_artifacts": (
                build_request()
                .source_artifacts[0]
                .model_copy(update={"media_type": "application/json"}),
            )
            + build_request().source_artifacts[1:]
        }
    )
    with pytest.raises(ValueError, match="unsupported upstream"):
        M2708Service().execute(request)


def test_result_replay_detects_nested_request_mutation() -> None:
    result = M2708Service().execute(build_request())
    nested = result.model_copy(
        update={"request": result.request.model_copy(update={"request_id": "m2708.changed"})}
    )
    assert not M2708Service().verify(nested)


def test_canonical_dict_projection_is_supported() -> None:
    request = build_request()
    assert normalized_request(request.model_dump(mode="json"))["request_id"] == request.request_id


def test_preservation_and_archive_retrievability_closure() -> None:
    request = build_request()
    evidence = request.preserved_evidence[0].evidence
    with pytest.raises(ValueError):
        EvidencePreservation(
            preservation_id="m2708.invalid",
            artifact=request.preserved_evidence[0].artifact,
            retention_class="long-term",
            retrievable=False,
            evidence=evidence,
        )
    with pytest.raises(ValueError):
        LongTermArchive(
            archive_id="m2708.invalid",
            archive_reference="archive://invalid",
            retention_policy="indefinite",
            manifest=request.archive.manifest,
            status=ArchiveStatus.VERIFIED,
            retrievable=False,
            evidence=evidence,
        )


def test_unretrievable_archive_status_cannot_claim_retrieval() -> None:
    request = build_request()
    with pytest.raises(ValueError):
        LongTermArchive(
            archive_id="m2708.invalid",
            archive_reference="archive://invalid",
            retention_policy="indefinite",
            manifest=request.archive.manifest,
            status=ArchiveStatus.UNRETRIEVABLE,
            retrievable=True,
            evidence=request.archive.evidence,
        )


def test_duplicate_package_ids_are_rejected() -> None:
    request = build_request()
    with pytest.raises(ValueError):
        RetirementPackage(
            package_id="m2708.package.invalid",
            version="1.0.0",
            status=RetirementStatus.PROPOSED,
            criteria=(request.criteria[0], request.criteria[0]),
            migrations=request.migrations,
            preserved_evidence=request.preserved_evidence,
            communications=request.communications,
            archive=request.archive,
            configuration=request.configuration,
            evidence=request.criteria[0].evidence,
        )


def test_executed_result_cannot_carry_findings() -> None:
    result = M2708Service().execute(build_request())
    payload = result.model_dump(mode="json")
    payload["findings"] = [
        RetirementFinding(
            finding_id="m2708.finding.invalid",
            code=RetirementFindingCode.ACTIVE_DEPENDENCY,
            message="Invalid executed finding.",
            evidence=result.evidence[:1],
        ).model_dump(mode="json")
    ]
    payload["result_digest"] = "sha256:" + "0" * 64

    with pytest.raises(ValueError, match="no findings"):
        ComplexActivityRetirementResult.model_validate_json(
            json.dumps(payload), strict=True
        )


def test_abstained_result_requires_findings() -> None:
    result = M2708Service().execute(build_request(incomplete=True))
    payload = result.model_dump(mode="json")
    payload["findings"] = []
    payload["result_digest"] = "sha256:" + "0" * 64

    with pytest.raises(ValueError, match="requires findings"):
        ComplexActivityRetirementResult.model_validate_json(
            json.dumps(payload), strict=True
        )


def test_result_id_must_bind_request_digest() -> None:
    result = M2708Service().execute(build_request())
    payload = result.model_dump(mode="json")
    payload["result_id"] = "m2708.invalid-result-id"
    payload["result_digest"] = "sha256:" + "0" * 64

    with pytest.raises(ValueError, match="result id"):
        ComplexActivityRetirementResult.model_validate_json(
            json.dumps(payload), strict=True
        )


def test_result_finding_ids_must_be_unique() -> None:
    result = M2708Service().execute(build_request(incomplete=True))
    payload = result.model_dump(mode="json")
    payload["findings"] = [payload["findings"][0], payload["findings"][0]]
    payload["result_digest"] = "sha256:" + "0" * 64

    with pytest.raises(ValueError, match="finding ids"):
        ComplexActivityRetirementResult.model_validate_json(
            json.dumps(payload), strict=True
        )


def test_result_evidence_digests_must_be_unique() -> None:
    result = M2708Service().execute(build_request())
    payload = result.model_dump(mode="json")
    payload["evidence"] = [payload["evidence"][0], payload["evidence"][0]]
    payload["result_digest"] = "sha256:" + "0" * 64

    with pytest.raises(ValueError, match="evidence must be unique"):
        ComplexActivityRetirementResult.model_validate_json(
            json.dumps(payload), strict=True
        )


def _executed_package_payload() -> dict[str, object]:
    result = M2708Service().execute(build_request())
    assert result.package is not None
    return result.package.model_dump(mode="json")


def test_executed_package_rejects_unsatisfied_criteria() -> None:
    payload = _executed_package_payload()
    payload["criteria"][0]["satisfied"] = False  # type: ignore[index]

    with pytest.raises(ValueError, match="unsatisfied criteria"):
        RetirementPackage.model_validate_json(json.dumps(payload), strict=True)


def test_executed_package_requires_completed_migrations() -> None:
    payload = _executed_package_payload()
    payload["migrations"][0]["status"] = "in_progress"  # type: ignore[index]

    with pytest.raises(ValueError, match="completed dependency"):
        RetirementPackage.model_validate_json(json.dumps(payload), strict=True)


def test_executed_package_requires_acknowledged_communications() -> None:
    payload = _executed_package_payload()
    payload["communications"][0]["acknowledged"] = False  # type: ignore[index]

    with pytest.raises(ValueError, match="acknowledged communications"):
        RetirementPackage.model_validate_json(json.dumps(payload), strict=True)


def test_executed_package_requires_retrievable_preserved_evidence() -> None:
    package = M2708Service().execute(build_request()).package
    assert package is not None
    object.__setattr__(package.preserved_evidence[0], "retrievable", False)

    with pytest.raises(ValueError, match="retrievable"):
        package.package_is_closed()


def test_proposed_package_skips_executed_state_requirements() -> None:
    payload = _executed_package_payload()
    payload["status"] = "proposed"
    assert RetirementPackage.model_validate_json(json.dumps(payload), strict=True).status is (
        RetirementStatus.PROPOSED
    )


def test_executed_package_requires_verified_archive() -> None:
    payload = _executed_package_payload()
    payload["archive"]["status"] = "preserved"  # type: ignore[index]

    with pytest.raises(ValueError, match="verified archive"):
        RetirementPackage.model_validate_json(json.dumps(payload), strict=True)


def test_cli_reports_semantic_replay_failure(tmp_path: Path) -> None:
    service = M2708Service()
    result = service.execute(build_request())
    other = service.execute(build_request(request_id="m2708.other"))
    assert other.package is not None
    forged = result.model_copy(update={"package": other.package})
    forged = forged.model_copy(update={"result_digest": result_payload_digest(forged)})
    path = tmp_path / "forged.json"
    path.write_text(forged.model_dump_json(), encoding="utf-8")

    outcome = CliRunner().invoke(cli, ["verify", str(path)])
    assert outcome.exit_code == 1
    assert json.loads(outcome.stdout) == {"verified": False}


def test_cli_file_execution_bootstraps_source_root(monkeypatch: pytest.MonkeyPatch) -> None:
    source = Path(cli_module.__file__).resolve()
    source_root = source.parents[4]
    monkeypatch.setattr(sys, "path", [entry for entry in sys.path if entry != str(source_root)])

    namespace = runpy.run_path(str(source), run_name="m2708_cli_probe")

    assert namespace["_SOURCE_ROOT"] == source_root
    runpy.run_path(str(source), run_name="m2708_cli_probe_again")

    monkeypatch.setattr(sys, "argv", [str(source), "--help"])
    with pytest.raises(SystemExit):
        runpy.run_path(str(source), run_name="__main__")


def test_preflight_control_and_identity_firewalls() -> None:
    service = M2708Service()
    request = build_request()
    with pytest.raises(ValueError, match="context identity"):
        service.execute(request.model_copy(update={"request_id": "m2708.changed"}))
    unresolved = request.context.references.identity_lineage.model_copy(
        update={"state": "unresolved"}
    )
    with pytest.raises(ValueError, match="identity"):
        service.execute(
            request.model_copy(
                update={
                    "context": request.context.model_copy(
                        update={
                            "references": request.context.references.model_copy(
                                update={"identity_lineage": unresolved}
                            )
                        }
                    )
                }
            )
        )
    rejected = request.context.references.support.model_copy(update={"state": "rejected"})
    with pytest.raises(ValueError, match="accepted"):
        service.execute(
            request.model_copy(
                update={
                    "context": request.context.model_copy(
                        update={
                            "references": request.context.references.model_copy(
                                update={"support": rejected}
                            )
                        }
                    )
                }
            )
        )
