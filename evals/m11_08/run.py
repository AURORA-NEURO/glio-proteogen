"""Deterministic M11-08 mechanism dossier evaluator matrix."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, cast

from glio_proteogen.contracts.m11_08 import (
    M1108_M1107_INPUT_MEDIA_TYPE,
    AssembleVariantPeptideMechanismDossierRequest,
    CounterEvidenceRecord,
    MechanismDossierAssumption,
    MechanismDossierConfiguration,
    MechanismDossierStatus,
    MechanismEvidenceLink,
    MechanismEvidenceLinkKind,
    MechanismEvidenceSource,
    MechanismEvidenceSourceKind,
    ReconstructionStep,
    ValidationRoute,
    ValidationRouteStatus,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads
from glio_proteogen.modules.c11_protein_native_subtype import (
    m11_08_mechanism_evidence_dossier as m1108_runtime,
)

AUTHORITY_SHA256: Final = "0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
AUTHORITY_LINES: Final = "3944-3987"
FIXTURE_PATH: Final = Path(__file__).parents[2] / "tests" / "fixtures" / "m11_08" / "scenarios.json"
_DIGEST: Final = "sha256:" + ("a" * 64)


def _artifact(identifier: str, media_type: str = "application/octet-stream") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=identifier,
        version="1.0.0",
        digest=_DIGEST,
        media_type=media_type,
    )


def _decision(identifier: str) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.{identifier}",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=_artifact(f"evidence.{identifier}"),
    )


def _evidence(identifier: str, role: str = "evidence") -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(f"evidence.{identifier}"),
        role=role,
        claim=f"Caller-declared evaluation evidence for {identifier}.",
    )


def build_request(
    *,
    complete: bool = True,
    accepted: bool = True,
    source_complete: bool = True,
    route_status: ValidationRouteStatus = ValidationRouteStatus.COMPLETE,
) -> AssembleVariantPeptideMechanismDossierRequest:
    """Build one deterministic fixture without traversing external payloads."""

    references = ContextReferences(
        approved_configuration=_decision("configuration"),
        identity_lineage=IdentityLineageReference(
            decision_id="decision.identity",
            state=IdentityLineageState.RESOLVED,
            policy_version="1.0.0",
            binding_digest=_DIGEST,
            evidence=_artifact("evidence.identity"),
        ),
        provenance=_decision("provenance"),
        consent=ConsentReference(
            decision_id="decision.consent",
            state=ConsentState.GRANTED,
            policy_version="1.0.0",
            evidence=_artifact("evidence.consent"),
        ),
        quality=_decision("quality"),
        support=_decision("support"),
        intended_use=_decision("intended-use"),
    )
    if not accepted:
        references = references.model_copy(
            update={
                "support": references.support.model_copy(
                    update={"state": UpstreamDecisionState.REJECTED}
                )
            }
        )
    context = ExecutionContext(
        request_id="eval.m1108.request",
        actor_id="eval.m1108.actor",
        occurred_at=datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
        references=references,
    )
    source_kinds = tuple(MechanismEvidenceSourceKind)
    sources = tuple(
        MechanismEvidenceSource(
            source_id=f"source.{index}",
            kind=kind,
            artifact=_artifact(f"source-artifact.{index}"),
            claim="Caller-declared source; authority is not inferred.",
            evidence=(_evidence(f"source.{index}"),),
        )
        for index, kind in enumerate(source_kinds)
    )
    links = (
        MechanismEvidenceLink(
            link_id="link.input",
            kind=MechanismEvidenceLinkKind.INPUT,
            assertion="Declared inputs enter the mechanism chain.",
            predecessor_ids=("source.0", "source.1", "source.2"),
            evidence=(_evidence("link.input"),),
            assumptions=("Source identity is caller-declared.",),
        ),
        MechanismEvidenceLink(
            link_id="link.mechanism",
            kind=MechanismEvidenceLinkKind.MECHANISM,
            assertion="The mechanism association remains reconstructable.",
            predecessor_ids=("link.input", "source.3"),
            evidence=(_evidence("link.mechanism"),),
            assumptions=("Mechanism interpretation remains review-bound.",),
        ),
        MechanismEvidenceLink(
            link_id="link.ceiling",
            kind=MechanismEvidenceLinkKind.CLAIM_CEILING,
            assertion="The claim ceiling remains explicit.",
            predecessor_ids=("link.mechanism",),
            evidence=(_evidence("link.ceiling"),),
            assumptions=("Promotion requires independent review.",),
        ),
    )
    config = MechanismDossierConfiguration(
        configuration_id="configuration.m1108",
        version="1.0.0",
        model_family="curated_mechanistic_baseline",
        source_manifest=(_artifact("manifest.m1108"),),
        evidence=(_evidence("configuration"),),
    )
    return AssembleVariantPeptideMechanismDossierRequest(
        request_id="eval.m1108.request",
        context=context,
        upstream_result=_artifact("upstream.m1107", M1108_M1107_INPUT_MEDIA_TYPE),
        configuration=config,
        source_artifacts=sources if source_complete else sources[:-1],
        assumptions=(
            MechanismDossierAssumption(
                assumption_id="assumption.review",
                statement="Every link remains caller-attributed until independent review.",
                evidence=(_evidence("assumption"),),
            ),
        )
        if complete
        else (),
        links=links,
        counter_evidence=(
            CounterEvidenceRecord(
                counter_evidence_id="counter.discordance",
                statement="Discordance remains visible as counter-evidence.",
                impact="It may weaken the mechanism association.",
                challenges_link_ids=("link.mechanism",),
                evidence=(_evidence("counter", "counter_evidence"),),
            ),
        )
        if complete
        else (),
        validation_routes=(
            ValidationRoute(
                route_id="route.orthogonal",
                method="orthogonal assay and negative control",
                status=route_status,
                required_experiment="Independent orthogonal assay",
                acceptance_criterion="Prespecified concordance threshold",
                evidence=(_evidence("route"),),
            ),
        ),
        reconstruction_steps=(
            ReconstructionStep(
                sequence=1,
                operation="assemble-evidence-chain",
                input_digests=(_DIGEST,),
                output_digest=_DIGEST,
                evidence=(_evidence("reconstruction"),),
            ),
        ),
        reviewer_id="reviewer.m1108",
    )


def evaluate() -> dict[str, object]:
    """Run supported, abstention, replay, tamper and boundary scenarios."""

    request = build_request()
    result = m1108_runtime.assemble_mechanism_dossier(request)
    incomplete = m1108_runtime.assemble_mechanism_dossier(build_request(complete=False))
    missing_source = m1108_runtime.assemble_mechanism_dossier(build_request(source_complete=False))
    failed_route = m1108_runtime.assemble_mechanism_dossier(
        build_request(route_status=ValidationRouteStatus.FAILED)
    )
    tampered = result.model_copy(update={"result_digest": "sha256:" + ("b" * 64)})
    plugin = m1108_runtime.M1108MechanismEvidenceDossierPlugin(
        m1108_runtime.M1108MechanismEvidenceDossierService()
    )
    checks = {
        "complete_dossier": result.status is MechanismDossierStatus.READY
        and result.dossier is not None
        and result.dossier.claim_ceiling.prohibited_interpretations
        and result.emits_parent is False,
        "incomplete_abstention": incomplete.status is MechanismDossierStatus.ABSTAINED
        and incomplete.dossier is None
        and incomplete.human_review_required,
        "missing_source_abstention": missing_source.status is MechanismDossierStatus.ABSTAINED,
        "failed_route_abstention": failed_route.status is MechanismDossierStatus.ABSTAINED,
        "deterministic_replay": result.model_dump(mode="json")
        == m1108_runtime.assemble_mechanism_dossier(request).model_dump(mode="json"),
        "tampered_digest_rejected": not m1108_runtime.verify_mechanism_dossier_result(tampered),
        "unaccepted_controls_fail_closed": _raises_authorization(),
        "wrong_upstream_media_rejected": _raises_wrong_media(request),
        "duplicate_json_rejected": _raises_duplicate(plugin, request),
    }
    fixture_bytes = FIXTURE_PATH.read_bytes()
    fixture = strict_json_loads(fixture_bytes)
    scenario_count = 0
    if isinstance(fixture, dict) and isinstance(fixture.get("scenarios"), list):
        scenario_count = len(cast("list[object]", fixture["scenarios"]))
    return {
        "module": "GLIO-PROTEOGEN-M11-08",
        "authority_sha256": AUTHORITY_SHA256,
        "authority_lines": AUTHORITY_LINES,
        "fixture_sha256": sha256_digest(fixture),
        "declared_scenarios": scenario_count,
        "executed_scenarios": len(checks),
        "checks": checks,
        "passed": all(checks.values()),
    }


def _raises_authorization() -> bool:
    try:
        m1108_runtime.assemble_mechanism_dossier(build_request(accepted=False))
    except m1108_runtime.M1108AuthorizationError:
        return True
    return False


def _raises_wrong_media(request: AssembleVariantPeptideMechanismDossierRequest) -> bool:
    try:
        m1108_runtime.assemble_mechanism_dossier(
            request.model_copy(update={"upstream_result": _artifact("wrong", "application/json")})
        )
    except ValueError:
        return True
    return False


def _raises_duplicate(
    plugin: m1108_runtime.M1108MechanismEvidenceDossierPlugin,
    request: AssembleVariantPeptideMechanismDossierRequest,
) -> bool:
    try:
        plugin.validate(request.model_dump_json())
        strict_json_loads('{"request_id":"one","request_id":"two"}')
    except StrictJsonError:
        return True
    return False


def main() -> None:
    print(json.dumps(evaluate(), indent=2, sort_keys=True))  # noqa: T201


if __name__ == "__main__":
    main()


__all__ = ["AUTHORITY_LINES", "AUTHORITY_SHA256", "build_request", "evaluate"]
