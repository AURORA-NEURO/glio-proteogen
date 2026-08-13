from __future__ import annotations

from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import pytest
from evals.m03_01.run import build_scenario_request as build_m0301_request
from pydantic import TypeAdapter

from glio_proteogen.contracts.m01_02 import (
    IdentityLineageResolution,
    ReconcileIdentityLineageRequest,
)
from glio_proteogen.contracts.m03_02 import (
    ApprovedCopyNumberMethod,
    ApprovedDerivationMethod,
    ArtifactClaimRole,
    CopyNumberConcordanceReceipt,
    CopyNumberConcordanceState,
    ProteinInferenceArtifactClaim,
    ProteinInferenceArtifactDerivation,
    ProteinInferenceLineagePolicy,
    ReconcileProteinInferenceIdentityLineageRequest,
    ReconciliationDisposition,
    configuration_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage import M0102Service
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.event_store import (
    M0102EventStore,
)
from glio_proteogen.modules.c03_protein_inference.m03_01_protocol_metadata import (
    evaluate_protein_inference_protocol,
)
from glio_proteogen.modules.c03_protein_inference.m03_02_identity_lineage import (
    M0302Plugin,
    M0302ProteinIdentityLineageReconciler,
    M0302Service,
    ProteinIdentityLineageAuthorizationError,
    ValidatedM0302Request,
    preflight_protein_identity_lineage_authorization,
    reconcile_protein_inference_identity_lineage,
)

_ROOT: Final = Path(__file__).parents[3]
_M0102_REQUEST_ADAPTER: Final = TypeAdapter(ReconcileIdentityLineageRequest)
_M0302_REQUEST_ADAPTER: Final = TypeAdapter(ReconcileProteinInferenceIdentityLineageRequest)


def _artifact(label: str, digest: str | None = None) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.synthetic.m0302.{label}",
        version="1.0.0",
        digest=digest or sha256_digest({"m0302": label}),
        media_type="application/json",
    )


def _identity_resolution(tmp_path: Path) -> IdentityLineageResolution:
    corpus = strict_json_loads(
        (_ROOT / "tests" / "fixtures" / "m01_02" / "scenarios.json").read_bytes()
    )
    assert isinstance(corpus, dict)
    scenarios = corpus["scenarios"]
    assert isinstance(scenarios, list)
    canonical = next(
        item
        for item in scenarios
        if isinstance(item, dict) and item.get("case_id") == "complete_ordinary_lineage"
    )
    request = _M0102_REQUEST_ADAPTER.validate_json(
        canonical_json_bytes(canonical["request"]),
        strict=True,
    )
    with M0102EventStore(tmp_path / "m0302-upstream-identity.sqlite3") as store:
        return M0102Service(store).execute(request)


def _protocol_result(identity: IdentityLineageResolution):
    request = build_m0301_request()
    identity_reference = request.context.references.identity_lineage.model_copy(
        update={"binding_digest": identity.resolution_digest}
    )
    references = request.context.references.model_copy(
        update={"identity_lineage": identity_reference}
    )
    bound = request.model_copy(
        update={"context": request.context.model_copy(update={"references": references})}
    )
    return evaluate_protein_inference_protocol(bound)


def _request(tmp_path: Path) -> ReconcileProteinInferenceIdentityLineageRequest:
    identity = _identity_resolution(tmp_path)
    protocol = _protocol_result(identity)
    policy = ProteinInferenceLineagePolicy(
        policy_id="policy.synthetic.m0302",
        version="1.0.0",
        approved_derivation_methods=(
            ApprovedDerivationMethod(
                method_id="method.synthetic.m0302.derivation",
                version="1.0.0",
                evidence=_artifact("approved-derivation-method"),
            ),
        ),
        approved_cn_methods=(
            ApprovedCopyNumberMethod(
                method_id="method.synthetic.m0302.cn",
                version="1.0.0",
                evidence=_artifact("approved-cn-method"),
            ),
        ),
        evidence=_artifact("policy"),
        reviewed_by="reviewer.synthetic.m0302",
        reviewed_at=datetime(2026, 8, 12, 12, tzinfo=UTC),
    )

    def decision(role: str, digest: str | None = None) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"decision.synthetic.m0302.{role}",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact(f"control-{role}", digest),
        )

    context = ExecutionContext(
        request_id="request.synthetic.m0302",
        actor_id="actor.synthetic.m0302",
        occurred_at=datetime(2026, 8, 12, 13, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision(
                "configuration",
                configuration_digest(policy),
            ),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.synthetic.m0302.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=identity.resolution_digest,
                evidence=_artifact("control-identity"),
            ),
            provenance=decision("provenance"),
            consent=ConsentReference(
                decision_id="decision.synthetic.m0302.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("control-consent"),
            ),
            quality=decision("quality"),
            support=decision("support"),
            intended_use=decision("intended-use"),
        ),
    )
    anchor = next(node for node in identity.graph.nodes if node.entity_id == "obj-a")
    common_claim = {
        "identity_entity_id": anchor.entity_id,
        "declared_subject_component_ids": anchor.subject_component_ids,
        "producer_identity_resolution_digest": identity.resolution_digest,
        "producer_protocol_result_digest": protocol.result_digest,
        "producer_search_space_digest": protocol.receipt.search_space_digest,
        "evidence_state": "observed",
    }
    claims = tuple(
        ProteinInferenceArtifactClaim(
            claim_id=claim_id,
            role=role,
            artifact=_artifact(claim_id),
            **common_claim,
        )
        for claim_id, role in (
            ("claim.synthetic.peptide-a", ArtifactClaimRole.PEPTIDE_EVIDENCE_MANIFEST),
            ("claim.synthetic.peptide-b", ArtifactClaimRole.PEPTIDE_EVIDENCE_MANIFEST),
            ("claim.synthetic.group", ArtifactClaimRole.PROTEIN_GROUP_MANIFEST),
            ("claim.synthetic.ambiguity", ArtifactClaimRole.AMBIGUITY_MANIFEST),
            ("claim.synthetic.bundle", ArtifactClaimRole.COMPLEX_ACTIVITY_INPUT_BUNDLE),
        )
    )

    def derivation(
        derivation_id: str,
        source_claim_ids: tuple[str, ...],
        target_claim_id: str,
    ) -> ProteinInferenceArtifactDerivation:
        return ProteinInferenceArtifactDerivation(
            derivation_id=derivation_id,
            source_claim_ids=source_claim_ids,
            target_claim_id=target_claim_id,
            method_id="method.synthetic.m0302.derivation",
            method_version="1.0.0",
            evidence=_artifact(derivation_id),
        )

    return ReconcileProteinInferenceIdentityLineageRequest(
        context=context,
        identity_resolution=identity,
        protocol_result=protocol,
        policy=policy,
        artifact_claims=claims,
        derivations=(
            derivation(
                "derivation.synthetic.group",
                ("claim.synthetic.peptide-a", "claim.synthetic.peptide-b"),
                "claim.synthetic.group",
            ),
            derivation(
                "derivation.synthetic.ambiguity",
                ("claim.synthetic.group",),
                "claim.synthetic.ambiguity",
            ),
            derivation(
                "derivation.synthetic.bundle",
                ("claim.synthetic.group", "claim.synthetic.ambiguity"),
                "claim.synthetic.bundle",
            ),
        ),
        cn_receipts=(
            CopyNumberConcordanceReceipt(
                receipt_id="receipt.synthetic.m0302.cn",
                claim_id="claim.synthetic.group",
                identity_entity_id=anchor.entity_id,
                state=CopyNumberConcordanceState.CONCORDANT,
                method_id="method.synthetic.m0302.cn",
                method_version="1.0.0",
                informative_feature_count=11,
                concordant_feature_count=11,
                discordant_feature_count=0,
                evidence=_artifact("cn-receipt"),
            ),
        ),
    )


class _ProtectedTraversal(BaseException):
    pass


class _HostileDeniedRequest(Mapping[str, object]):
    def __init__(self, context: object) -> None:
        self._context = context

    def __getitem__(self, key: str) -> object:
        if key == "context":
            return self._context
        raise _ProtectedTraversal

    def __iter__(self) -> Iterator[str]:
        raise _ProtectedTraversal

    def __len__(self) -> int:
        raise _ProtectedTraversal

    def get(self, key: str, default: object = None) -> object:
        del default
        return self[key]


@pytest.mark.parametrize(
    ("role", "denied_state"),
    [
        ("approved_configuration", UpstreamDecisionState.REJECTED),
        ("identity_lineage", IdentityLineageState.CONFLICTED),
        ("provenance", UpstreamDecisionState.REJECTED),
        ("consent", ConsentState.REVOKED),
        ("quality", UpstreamDecisionState.REJECTED),
        ("support", UpstreamDecisionState.REJECTED),
        ("intended_use", UpstreamDecisionState.REJECTED),
    ],
)
def test_authorization_precedes_protected_traversal_for_all_boundaries(
    tmp_path: Path,
    role: str,
    denied_state: object,
) -> None:
    request = _request(tmp_path)
    payload = request.model_dump(mode="python")
    references = payload["context"]["references"]
    references[role]["state"] = denied_state
    hostile = _HostileDeniedRequest(payload["context"])
    plugin = M0302Plugin(M0302Service())

    with pytest.raises(ProteinIdentityLineageAuthorizationError):
        reconcile_protein_inference_identity_lineage(hostile)
    with pytest.raises(ProteinIdentityLineageAuthorizationError):
        M0302Service.validate_request(hostile)
    with pytest.raises(ProteinIdentityLineageAuthorizationError):
        plugin.validate(hostile)


def test_preflight_catches_exception_but_never_base_exception() -> None:
    class ExceptionBoundary(Mapping[str, object]):
        def __getitem__(self, _key: str) -> object:
            raise RuntimeError

        def __iter__(self) -> Iterator[str]:
            return iter(())

        def __len__(self) -> int:
            return 0

    class BaseExceptionBoundary(ExceptionBoundary):
        def __getitem__(self, _key: str) -> object:
            raise _ProtectedTraversal

    with pytest.raises(ProteinIdentityLineageAuthorizationError):
        preflight_protein_identity_lineage_authorization(ExceptionBoundary())
    with pytest.raises(_ProtectedTraversal):
        preflight_protein_identity_lineage_authorization(BaseExceptionBoundary())


def test_direct_service_and_plugin_are_exactly_identical(tmp_path: Path) -> None:
    request = _request(tmp_path)
    direct = reconcile_protein_inference_identity_lineage(request)
    reconciler = M0302ProteinIdentityLineageReconciler().reconcile(request)
    service = M0302Service().execute(request)
    plugin = M0302Plugin(M0302Service())
    typed_plugin = plugin.run(plugin.validate(request))
    json_plugin = plugin.run(plugin.validate(canonical_json_bytes(request.model_dump(mode="json"))))

    assert direct == reconciler == service == typed_plugin == json_plugin
    assert direct.disposition is ReconciliationDisposition.RECONCILED
    assert direct.findings == ()
    assert direct.result_digest != "sha256:" + ("0" * 64)
    assert direct.receipt.emits_complex_activity is False
    assert direct.receipt.infers_identity is False


def test_semantic_reordering_produces_full_exact_result_parity(tmp_path: Path) -> None:
    request = _request(tmp_path)
    payload = request.model_dump(mode="json")
    payload["artifact_claims"].reverse()
    payload["derivations"].reverse()
    for derivation in payload["derivations"]:
        derivation["source_claim_ids"].reverse()
    reordered = _M0302_REQUEST_ADAPTER.validate_json(
        canonical_json_bytes(payload),
        strict=True,
    )

    assert reconcile_protein_inference_identity_lineage(request) == (
        reconcile_protein_inference_identity_lineage(reordered)
    )


def test_plugin_descriptor_and_execution_token_preserve_authority(tmp_path: Path) -> None:
    plugin = M0302Plugin(M0302Service())
    descriptor = plugin.descriptor()

    assert descriptor.module_id == "GLIO-PROTEOGEN-M03-02"
    assert descriptor.owner == "ML engineering"
    assert descriptor.safety_class == "S2"
    assert descriptor.gate == "G0"
    assert any("raw peptide" in item for item in descriptor.prohibited_outputs)
    assert any("identity" in item for item in descriptor.prohibited_outputs)
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(_request(tmp_path))  # type: ignore[arg-type]
    assert isinstance(plugin.validate(_request(tmp_path)), ValidatedM0302Request)
