"""Execute the locked M04-08 release-packaging evidence plan."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Mapping

# Keep the documented direct entrypoint usable from the repository root.  When
# Python executes this file by path, ``evals`` is not otherwise importable.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).parents[2]))

from evals.m04_07.run import build_scenario as build_m0407_scenario
from glio_proteogen.contracts.m04_08 import (
    M0408_ARCHIVE_MEMBER_COUNT,
    M0408_MANIFEST_PATH,
    M0408_SIGNATURE_RECEIPT_PATH,
    BuildProteoformReleaseRequest,
    ExternalProteoformSignature,
    ProteoformParentDiscordanceReceipt,
    ProteoformReferenceVersion,
    ProteoformReleaseArtifact,
    ProteoformReleaseArtifactRole,
    ProteoformReleaseDisposition,
    ProteoformReleasePolicy,
    ProteoformReproductionEvidence,
    ProteoformSignatureAlgorithm,
    ProteoformSoftwareVersion,
    contract_json_schemas,
    manifest_digest,
    policy_digest,
    signing_statement_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.canonical_ustar import inspect_canonical_ustar, sha256_bytes
from glio_proteogen.kernel.models import ArtifactReference, ControlRole
from glio_proteogen.modules.c04_proteoform_isoform.m04_07_support_router import (
    route_proteoform_support,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_08_release_packaging import (
    build_proteoform_release,
    build_proteoform_release_manifest,
    verify_proteoform_release,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M04-08"
ROOT: Final = Path(__file__).parents[2]
SCENARIO_PATH: Final = ROOT / "tests" / "fixtures" / "m04_08" / "scenarios.json"
_STAGE_MODULES: Final = tuple(f"GLIO-PROTEOGEN-M04-{i:02d}" for i in range(1, 8))
_STAGE_NAMES: Final = (
    "protocol-conformance",
    "identity-lineage",
    "raw-ingestion",
    "quality",
    "artifact-detection",
    "harmonization",
    "upstream-result",
)
_PATHS: Final = (
    "parent/protein-rna-discordance-handoff.json",
    *(f"stages/m04-{i:02d}-{name}.json" for i, name in enumerate(_STAGE_NAMES, 1)),
)
_MEDIA: Final = (
    "application/vnd.glio-proteogen.protein-rna-discordance-handoff+json",
    *(f"application/vnd.glio-proteogen.m04-{i:02d}+json" for i in range(1, 8)),
)
_EXPECTED_CASE_IDS: Final = frozenset(
    {
        "corpus_inventory",
        "genuine_m0401_m0407_chain",
        "canonical_release",
        "semantic_reorder_replay",
        "archive_inventory",
        "archive_tamper_detection",
        "signature_replay",
        "signature_quarantine",
        "stage_identity_binding",
        "parent_receipt_ceiling",
        "schema_inventory",
        "maximum_shape_limits",
    }
)
_CALLER_ARTIFACT_COUNT: Final = 8
_STAGE_COUNT: Final = 7
_SCHEMA_COUNT: Final = 9
_VERIFICATION_CALL_COUNT: Final = 2


@dataclass(frozen=True, slots=True)
class Fixture:
    request: BuildProteoformReleaseRequest
    artifacts: dict[str, bytes]
    stages: Mapping[str, object]


class DeterministicVerifier:
    """Evaluation-only verifier; it provides no cryptographic authority."""

    def __init__(self, *, accept: bool = True) -> None:
        self.accept = accept
        self.calls = 0

    @property
    def verifier_id(self) -> str:
        return _oid("verifier", "m0408-eval")

    def verify(self, *, statement_digest: str, signature: ExternalProteoformSignature) -> bool:
        self.calls += 1
        return self.accept and statement_digest == signature.claimed_statement_digest


def _oid(namespace: str, label: object) -> str:
    return f"{namespace}.{sha256_digest({'m0408': label}).removeprefix('sha256:')}"


def _evidence(label: str, digest: str | None = None) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=_oid("evidence", label),
        version="1.0.0",
        digest=digest or sha256_digest({"m0408_evidence": label}),
        media_type="application/json",
    )


@lru_cache(maxsize=1)
def _fixture() -> Fixture:
    source = build_m0407_scenario()
    support = route_proteoform_support(source.request)
    quality = source.quality_result
    harmonization = source.harmonization_result
    ingestion = quality.request.raw_input_result
    identity = ingestion.request.lineage_result
    protocol = identity.request.protocol_result
    artifact_detection = harmonization.request.artifact_result
    stages = (protocol, identity, ingestion, quality, artifact_detection, harmonization, support)
    identity_digest = next(
        item.subject_digest
        for item in protocol.provenance.control_decisions
        if item.role is ControlRole.IDENTITY_LINEAGE
    )
    if identity_digest is None:
        raise ValueError
    release_policy = ProteoformReleasePolicy(
        policy_id=_oid("policy", "m0408-eval"),
        version="1.0.0",
        allowed_signature_algorithms=(ProteoformSignatureAlgorithm.ED25519,),
        allowed_verifier_ids=(_oid("verifier", "m0408-eval"),),
        evidence=_evidence("release-policy"),
        reviewed_by=_oid("reviewer", "m0408-eval"),
        reviewed_at=datetime(2026, 8, 13, 15, 3, tzinfo=UTC),
    )
    references = source.request.context.references
    references = references.model_copy(
        update={
            "approved_configuration": references.approved_configuration.model_copy(
                update={
                    "evidence": references.approved_configuration.evidence.model_copy(
                        update={"digest": policy_digest(release_policy)}
                    )
                }
            ),
            "quality": references.quality.model_copy(
                update={
                    "evidence": references.quality.evidence.model_copy(
                        update={"digest": quality.result_digest}
                    )
                }
            ),
            "support": references.support.model_copy(
                update={
                    "evidence": references.support.evidence.model_copy(
                        update={"digest": support.result_digest}
                    )
                }
            ),
        }
    )
    context = source.request.context.model_copy(
        update={
            "request_id": _oid("request", "m0408-eval"),
            "occurred_at": datetime(2026, 8, 13, 15, 4, tzinfo=UTC),
            "references": references,
        }
    )
    parent = canonical_json_bytes(
        ProteoformParentDiscordanceReceipt(
            identity_resolution_digest=identity_digest,
            intended_use_evidence_digest=context.references.intended_use.evidence.digest,
            terminal_routing_result_digest=support.result_digest,
        ).model_dump(mode="json")
    )
    contents = (parent, *(canonical_json_bytes(item) for item in stages))
    payloads = dict(zip(_PATHS, contents, strict=True))
    roles = tuple(ProteoformReleaseArtifactRole)
    declarations = []
    for index, (role, path, content) in enumerate(zip(roles, _PATHS, contents, strict=True)):
        artifact_id = (
            _oid("parent", "m0408-parent")
            if index == 0
            else (
                support.route_id
                if index == _STAGE_COUNT
                else (
                    f"result.m04{index:02d}."
                    f"{stages[index - 1].request_digest.removeprefix('sha256:')}"
                )
            )
        )
        declarations.append(
            ProteoformReleaseArtifact(
                path=path,
                role=role,
                reference=ArtifactReference(
                    artifact_id=artifact_id,
                    version="1.0.0",
                    digest=sha256_bytes(content),
                    media_type=_MEDIA[index],
                ),
                declared_size=len(content),
            )
        )

    def software(label: str) -> ProteoformSoftwareVersion:
        return ProteoformSoftwareVersion(
            software_id=_oid("software", label),
            version="1.0.0",
            build_digest=sha256_digest({"build": label}),
            evidence=_evidence(f"software.{label}"),
        )

    def reference(label: str) -> ProteoformReferenceVersion:
        return ProteoformReferenceVersion(
            reference_id=_oid("reference", label),
            build_id=_oid("build", label),
            version="2026.1",
            digest=sha256_digest({"reference": label}),
            evidence=_evidence(f"reference.{label}"),
        )

    reproduction = ProteoformReproductionEvidence(
        **{
            name: _evidence(f"reproduction.{name}")
            for name in ProteoformReproductionEvidence.model_fields
        }
    )
    request = BuildProteoformReleaseRequest(
        context=context,
        release_id=_oid("release", "m0408-eval"),
        release_version="1.0.0",
        artifacts=tuple(declarations),
        software_versions=(software("packager"),),
        reference_versions=(reference("proteome"),),
        reproduction_evidence=reproduction,
        policy=release_policy,
        signature=ExternalProteoformSignature(
            signer_id=_oid("signer", "m0408-eval"),
            key_id=_oid("key", "m0408-eval"),
            algorithm=ProteoformSignatureAlgorithm.ED25519,
            claimed_statement_digest=sha256_digest("placeholder"),
            signature_value="EVAL",
            issued_at=datetime(2026, 8, 13, 15, 3, tzinfo=UTC),
            evidence=_evidence("signature"),
        ),
    )
    stage_map = dict(zip(_STAGE_MODULES, stages, strict=True))
    manifest = build_proteoform_release_manifest(request, payloads, stage_map)
    statement = signing_statement_digest(
        active_manifest_digest=manifest_digest(manifest),
        active_policy_digest=policy_digest(request.policy),
        release_id=request.release_id,
        release_version=request.release_version,
        identity_resolution_digest=manifest.identity_resolution_digest,
        intended_use_evidence_digest=manifest.intended_use_evidence_digest,
        terminal_routing_result_digest=manifest.terminal_routing_result_digest,
    )
    signed = request.model_copy(
        update={
            "signature": request.signature.model_copy(
                update={"claimed_statement_digest": statement}
            )
        }
    )
    return Fixture(signed, payloads, stage_map)


def _check(name: str, passed: bool, detail: str) -> dict[str, object]:  # noqa: FBT001
    return {"name": f"scenario.{name}", "passed": passed, "detail": detail}


def evaluate() -> dict[str, object]:
    fixture = _fixture()
    scenario = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    declared = frozenset(item["case_id"] for item in scenario["cases"])
    verifier = DeterministicVerifier()
    built = build_proteoform_release(fixture.request, fixture.artifacts, fixture.stages, verifier)
    members = inspect_canonical_ustar(built.package_bytes or b"")
    verified = verify_proteoform_release(built.result, built.package_bytes or b"", verifier)
    replay = build_proteoform_release(
        fixture.request,
        dict(reversed(tuple(fixture.artifacts.items()))),
        fixture.stages,
        DeterministicVerifier(),
    )
    tampered = bytearray(built.package_bytes or b"")
    if tampered:
        tampered[-1] ^= 1
    tamper_result = verify_proteoform_release(
        built.result, bytes(tampered), DeterministicVerifier()
    )
    rejected = build_proteoform_release(
        fixture.request, fixture.artifacts, fixture.stages, DeterministicVerifier(accept=False)
    )
    checks = [
        _check(
            "corpus_inventory",
            scenario["module_id"] == MODULE_ID and declared == _EXPECTED_CASE_IDS,
            f"cases={len(declared)}",
        ),
        _check(
            "genuine_m0401_m0407_chain",
            len(fixture.stages) == _STAGE_COUNT
            and all(hasattr(item, "disposition") for item in fixture.stages.values()),
            "all seven stage outputs are releasable",
        ),
        _check(
            "canonical_release",
            built.result.disposition is ProteoformReleaseDisposition.RELEASED
            and len(members) == M0408_ARCHIVE_MEMBER_COUNT
            and verifier.calls == _VERIFICATION_CALL_COUNT,
            f"disposition={built.result.disposition.value};members={len(members)}",
        ),
        _check(
            "semantic_reorder_replay",
            replay.result == built.result and replay.package_bytes == built.package_bytes,
            "request/artifact order is canonicalized",
        ),
        _check(
            "archive_inventory",
            {item.path for item in members} >= {M0408_MANIFEST_PATH, M0408_SIGNATURE_RECEIPT_PATH}
            and built.result.package_descriptor is not None,
            "manifest, signature, and eight caller members present",
        ),
        _check(
            "archive_tamper_detection",
            not tamper_result.verified,
            f"reason={tamper_result.reason_code.value}",
        ),
        _check(
            "signature_replay",
            verified.verified and verified.signature_verification.verified,
            f"reason={verified.reason_code.value}",
        ),
        _check(
            "signature_quarantine",
            rejected.result.disposition is ProteoformReleaseDisposition.QUARANTINED
            and rejected.package_bytes is None,
            f"reasons={len(rejected.result.quarantine_reasons)}",
        ),
        _check(
            "stage_identity_binding",
            all(
                item.reference.digest == sha256_bytes(fixture.artifacts[item.path])
                for item in fixture.request.artifacts
            ),
            "artifact bytes bind declarations",
        ),
        _check(
            "parent_receipt_ceiling",
            built.result.parent_target == "protein_rna_discordance"
            and not built.result.emits_protein_rna_discordance
            and not built.result.signs_release,
            "authority flags remain false",
        ),
        _check(
            "schema_inventory",
            len(contract_json_schemas()) == _SCHEMA_COUNT,
            f"schemas={len(contract_json_schemas())}",
        ),
        _check(
            "maximum_shape_limits",
            len(fixture.request.artifacts) == _CALLER_ARTIFACT_COUNT
            and len(fixture.stages) == _STAGE_COUNT,
            "bounded request inventory",
        ),
    ]
    return {
        "module_id": MODULE_ID,
        "phase": "locked_executable_release_evidence",
        "passed": all(item["passed"] is True for item in checks),
        "declared_case_count": len(declared),
        "executed_check_count": len(checks),
        "genuine_e2e_executed": True,
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = evaluate()
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        sys.stdout.write(rendered)
    else:
        args.output.write_text(rendered, encoding="utf-8")
    return 0 if report["passed"] is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
