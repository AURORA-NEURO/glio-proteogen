"""Execute the locked M02-08 identification-release evidence plan."""

from __future__ import annotations

import argparse
import io
import json
import sys
import tarfile
from collections.abc import Iterator, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from evals.m02_01.run import build_scenario_request as build_m0201_request
from evals.m02_02.run import (
    build_scenario_request as build_m0202_request,
)
from evals.m02_02.run import (
    different_scope_control_request,
)
from evals.m02_03.run import build_scenario_submission as build_m0203_submission
from evals.m02_04.run import build_scenario_request as build_m0204_request
from evals.m02_06.run import build_scenario_request as build_m0206_request
from evals.m02_07.run import (
    _base_request as build_m0207_request,
)
from evals.m02_07.run import (
    _genuine_prerequisites as build_m0207_prerequisites,
)
from glio_proteogen.contracts.m02_06 import (
    HarmonizeIdentificationEvidenceRequest,
)
from glio_proteogen.contracts.m02_07 import (
    IdentificationSupportDimension,
)
from glio_proteogen.contracts.m02_08 import (
    M0208_ARCHIVE_MEMBER_COUNT,
    M0208_MANIFEST_PATH,
    M0208_SIGNATURE_RECEIPT_PATH,
    BuildIdentificationQcReleaseRequest,
    ExternalIdentificationSignature,
    IdentificationPackageVerificationReason,
    IdentificationReferenceVersion,
    IdentificationReleaseArtifact,
    IdentificationReleaseArtifactRole,
    IdentificationReleaseDisposition,
    IdentificationReleasePolicy,
    IdentificationReproductionEvidence,
    IdentificationSignatureVerificationReason,
    IdentificationSoftwareVersion,
    manifest_digest,
    normalized_manifest,
    policy_digest,
    signing_statement_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.canonical_ustar import (
    PackageMember,
    inspect_canonical_ustar,
    sha256_bytes,
)
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
from glio_proteogen.modules.c02_identification_qc.m02_01_protocol_metadata import (
    evaluate_conformance,
)
from glio_proteogen.modules.c02_identification_qc.m02_02_identity_lineage import (
    evaluate_identity_bindings,
)
from glio_proteogen.modules.c02_identification_qc.m02_03_raw_ingestion import (
    evaluate_identification_raw_ingestion,
)
from glio_proteogen.modules.c02_identification_qc.m02_04_quality_metrics import (
    compute_identification_quality,
)
from glio_proteogen.modules.c02_identification_qc.m02_06_harmonization import (
    harmonize_identification_evidence,
)
from glio_proteogen.modules.c02_identification_qc.m02_07_support_router import (
    build_identification_support_prerequisites,
    route_identification_support,
)
from glio_proteogen.modules.c02_identification_qc.m02_08_release_packaging import (
    IdentificationReleaseAuthorizationError,
    IdentificationReleaseInputError,
    IdentificationReleaseInputErrorCode,
    build_identification_release,
    build_identification_release_manifest,
    verify_identification_release,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from glio_proteogen.contracts.m02_01 import ConformanceEvaluation
    from glio_proteogen.contracts.m02_02 import IdentityBindingEvaluation
    from glio_proteogen.contracts.m02_03 import IdentificationRawIngestionResult
    from glio_proteogen.contracts.m02_04 import IdentificationQualityProfile
    from glio_proteogen.contracts.m02_05 import IdentificationArtifactDetectionResult
    from glio_proteogen.contracts.m02_06 import IdentificationHarmonizationResult
    from glio_proteogen.contracts.m02_07 import IdentificationSupportRouteResult
    from glio_proteogen.kernel.models import FrozenModel

MODULE_ID: Final = "GLIO-PROTEOGEN-M02-08"
ROOT: Final = Path(__file__).parents[2]
SCENARIO_PATH: Final = ROOT / "tests" / "fixtures" / "m02_08" / "scenarios.json"
EXPECTED_GROUP_IDS: Final = (
    "canonical_release_and_semantic_reorder",
    "seven_stage_disposition_matrix",
    "cross_chain_closure",
    "integrity_and_archive_safety",
    "signature_binding_and_replay",
    "strict_canonical_reconstruction",
    "privacy_and_ownership_closure",
    "authorization_recovery_and_maximum_shape",
)
EXPECTED_CASE_COUNT: Final = 38
EXPECTED_GROUP_CASE_COUNTS: Final = (2, 7, 3, 8, 6, 6, 1, 5)
CROSS_CHAIN_CASE_COUNT: Final = 3
INTEGRITY_CASE_COUNT: Final = 8
SIGNATURE_CASE_COUNT: Final = 6
STRICT_CASE_COUNT: Final = 6
AUTHORIZATION_CASE_COUNT: Final = 5
MAX_METADATA_RECORDS: Final = 64
STAGE_MODULE_IDS: Final = tuple(f"GLIO-PROTEOGEN-M02-{index:02d}" for index in range(1, 8))
NONCRYPTO_ALGORITHM: Final = "eval-noncrypto-v1"
NONCRYPTO_VERIFIER_ID: Final = "verifier.synthetic.m0208.noncrypto"
_PLACEHOLDER_STATEMENT_DIGEST: Final = sha256_digest({"m0208": "statement-placeholder"})
_ARTIFACT_PATHS: Final = {
    IdentificationReleaseArtifactRole.PARENT_PROTEIN_SUBTYPE: (
        "release/parent/protein-subtype.json"
    ),
    IdentificationReleaseArtifactRole.M02_01_CONFORMANCE: "release/stages/m02-01.json",
    IdentificationReleaseArtifactRole.M02_02_IDENTITY_LINEAGE: "release/stages/m02-02.json",
    IdentificationReleaseArtifactRole.M02_03_RAW_INGESTION: "release/stages/m02-03.json",
    IdentificationReleaseArtifactRole.M02_04_QUALITY: "release/stages/m02-04.json",
    IdentificationReleaseArtifactRole.M02_05_ARTIFACT_DETECTION: (
        "release/stages/m02-05.json"
    ),
    IdentificationReleaseArtifactRole.M02_06_HARMONIZATION: "release/stages/m02-06.json",
    IdentificationReleaseArtifactRole.M02_07_SUPPORT_ROUTE: "release/stages/m02-07.json",
}


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


class _InvalidCorpusError(TypeError):
    pass


class _PrematureTraversalError(AssertionError):
    pass


class DeterministicNonCryptographicVerifier:
    """Evaluation seam only; this intentionally provides no cryptographic assurance."""

    __slots__ = ("_accept", "calls")

    def __init__(self, *, accept: bool = True) -> None:
        self._accept = accept
        self.calls: list[tuple[str, ExternalIdentificationSignature]] = []

    @property
    def verifier_id(self) -> str:
        return NONCRYPTO_VERIFIER_ID

    def verify(
        self,
        *,
        statement_digest: str,
        signature: ExternalIdentificationSignature,
    ) -> bool:
        self.calls.append((statement_digest, signature))
        return (
            self._accept
            and statement_digest == signature.claimed_statement_digest
            and signature.signature_value == "NONCRYPTO_EVALUATION_TOKEN"
        )


class _UnreadableMapping(Mapping[str, object]):
    """Hostile mapping proving authorization is checked before caller data."""

    __slots__ = ("_label",)

    def __init__(self, label: str) -> None:
        self._label = label

    def __getitem__(self, key: str) -> object:
        del key
        raise _PrematureTraversalError(self._label)

    def __iter__(self) -> Iterator[str]:
        raise _PrematureTraversalError(self._label)

    def __len__(self) -> int:
        raise _PrematureTraversalError(self._label)


@dataclass(frozen=True, slots=True)
class GenuineIdentificationChain:
    """The exact seven public results supplied to M02-08."""

    conformance: ConformanceEvaluation
    identity: IdentityBindingEvaluation
    ingestion: IdentificationRawIngestionResult
    quality: IdentificationQualityProfile
    artifact_detection: IdentificationArtifactDetectionResult
    harmonization: IdentificationHarmonizationResult
    support_route: IdentificationSupportRouteResult

    def ordered_results(self) -> tuple[FrozenModel, ...]:
        return (
            self.conformance,
            self.identity,
            self.ingestion,
            self.quality,
            self.artifact_detection,
            self.harmonization,
            self.support_route,
        )

    def by_module(self) -> dict[str, FrozenModel]:
        return dict(zip(STAGE_MODULE_IDS, self.ordered_results(), strict=True))


@dataclass(frozen=True, slots=True)
class IdentificationReleaseFixture:
    request: BuildIdentificationQcReleaseRequest
    artifacts: dict[str, bytes]
    stages: dict[str, FrozenModel]


def _evidence(label: str, digest: str | None = None) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.synthetic.m0208.{label}",
        version="1.0.0",
        digest=digest or sha256_digest({"m0208-evidence": label}),
        media_type="application/json",
    )


def _replace_identity_context(
    context: ExecutionContext,
    identity_digest: str,
) -> ExecutionContext:
    identity = context.references.identity_lineage.model_copy(
        update={"binding_digest": identity_digest}
    )
    references = context.references.model_copy(update={"identity_lineage": identity})
    return context.model_copy(update={"references": references})


@lru_cache(maxsize=8)
def build_genuine_chain(
    nonreleasable_stage: str | None = None,
) -> GenuineIdentificationChain:
    """Execute a lineage-coherent C02 chain; never synthesize an upstream result."""

    if nonreleasable_stage not in {None, *STAGE_MODULE_IDS}:
        raise ValueError(nonreleasable_stage)
    harmonization_case = "conformant_eight_factor"
    if nonreleasable_stage == "GLIO-PROTEOGEN-M02-05":
        harmonization_case = "upstream_excluded_target"
    elif nonreleasable_stage == "GLIO-PROTEOGEN-M02-06":
        harmonization_case = "insufficient_controls"
    harmonization_request = build_m0206_request(harmonization_case)
    prerequisites = harmonization_request.prerequisites

    conformance = prerequisites.conformance
    if nonreleasable_stage == "GLIO-PROTEOGEN-M02-01":
        conformance = evaluate_conformance(build_m0201_request("missing_mandatory"))

    identity = prerequisites.identity
    if nonreleasable_stage == "GLIO-PROTEOGEN-M02-02":
        identity = evaluate_identity_bindings(build_m0202_request("swap"))

    ingestion = prerequisites.ingestion
    if nonreleasable_stage == "GLIO-PROTEOGEN-M02-03":
        submission = build_m0203_submission("truncated_mzml")
        ingestion = evaluate_identification_raw_ingestion(
            submission.request,
            submission.sources,
            submission.filenames,
        )

    quality_case = (
        "low_identification_coverage"
        if nonreleasable_stage == "GLIO-PROTEOGEN-M02-04"
        else "none"
    )
    quality_request = build_m0204_request(quality_case)
    quality_request = quality_request.model_copy(
        update={
            "context": _replace_identity_context(
                quality_request.context,
                identity.result_digest,
            )
        }
    )
    quality = compute_identification_quality(quality_request)

    prerequisites = prerequisites.model_copy(
        update={
            "conformance": conformance,
            "identity": identity,
            "ingestion": ingestion,
            "quality": quality,
        }
    )
    harmonization_request = HarmonizeIdentificationEvidenceRequest.model_validate(
        harmonization_request.model_copy(
            update={
                "context": _replace_identity_context(
                    harmonization_request.context,
                    identity.result_digest,
                ),
                "prerequisites": prerequisites,
            }
        ).model_dump(mode="python")
    )
    harmonization = harmonize_identification_evidence(harmonization_request)
    support_prerequisites = build_identification_support_prerequisites(
        quality_request.assay_profile,
        quality,
        harmonization,
    )
    support_request = build_m0207_request(support_prerequisites)
    if nonreleasable_stage == "GLIO-PROTEOGEN-M02-07":
        specimen = next(
            item
            for item in support_request.declared_facts
            if item.dimension is IdentificationSupportDimension.SPECIMEN
        )
        replacement = specimen.model_copy(update={"values": ("specimen.outside",)})
        support_request = support_request.model_copy(
            update={
                "declared_facts": tuple(
                    replacement if item.dimension is specimen.dimension else item
                    for item in support_request.declared_facts
                )
            }
        )
    support_route = route_identification_support(support_request)
    return GenuineIdentificationChain(
        conformance=conformance,
        identity=identity,
        ingestion=ingestion,
        quality=quality,
        artifact_detection=prerequisites.artifact_detection,
        harmonization=harmonization,
        support_route=support_route,
    )


def _policy() -> IdentificationReleasePolicy:
    return IdentificationReleasePolicy(
        policy_id="policy.synthetic.m0208.exact-release",
        version="1.0.0",
        allowed_signature_algorithms=(NONCRYPTO_ALGORITHM,),
        allowed_verifier_ids=(NONCRYPTO_VERIFIER_ID,),
        evidence=_evidence("release-policy"),
    )


def _context(active_policy: IdentificationReleasePolicy, identity_digest: str) -> ExecutionContext:
    def accepted(role: str, digest: str | None = None) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"decision.synthetic.m0208.{role}",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_evidence(f"control.{role}", digest),
        )

    return ExecutionContext(
        request_id="request.synthetic.m0208.identification-release",
        actor_id="actor.synthetic.eval",
        occurred_at=datetime(2026, 8, 13, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=accepted("configuration", policy_digest(active_policy)),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.synthetic.m0208.identity-lineage",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=identity_digest,
                evidence=_evidence("control.identity-lineage"),
            ),
            provenance=accepted("provenance"),
            consent=ConsentReference(
                decision_id="decision.synthetic.m0208.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_evidence("control.consent"),
            ),
            quality=accepted("quality"),
            support=accepted("support"),
            intended_use=accepted("intended-use"),
        ),
    )


def _artifact_bytes(chain: GenuineIdentificationChain) -> dict[str, bytes]:
    parent = canonical_json_bytes(
        {
            "parent_target": "protein_subtype",
            "subject_binding_digest": chain.identity.result_digest,
            "intended_use_evidence_digest": _evidence(
                "control.intended-use"
            ).digest,
        }
    )
    values = (parent, *(canonical_json_bytes(item) for item in chain.ordered_results()))
    return {
        _ARTIFACT_PATHS[role]: value
        for role, value in zip(IdentificationReleaseArtifactRole, values, strict=True)
    }


def _reproduction_evidence() -> IdentificationReproductionEvidence:
    return IdentificationReproductionEvidence(
        environment_lock=_evidence("reproduction.environment-lock"),
        build_recipe=_evidence("reproduction.build-recipe"),
        locked_tests=_evidence("reproduction.locked-tests"),
        benchmark=_evidence("reproduction.benchmark"),
        traceability=_evidence("reproduction.traceability"),
        reviewer_signoff=_evidence("reproduction.reviewer-signoff"),
        rollback=_evidence("reproduction.rollback"),
    )


def build_release_fixture(
    *,
    nonreleasable_stage: str | None = None,
    statement_digest: str = _PLACEHOLDER_STATEMENT_DIGEST,
) -> IdentificationReleaseFixture:
    """Build one strict M02-08 request around genuine immutable public results."""

    chain = build_genuine_chain(nonreleasable_stage)
    payloads = _artifact_bytes(chain)
    artifacts = tuple(
        IdentificationReleaseArtifact(
            path=_ARTIFACT_PATHS[role],
            role=role,
            reference=_evidence(
                f"member.{role.value}",
                sha256_bytes(payloads[_ARTIFACT_PATHS[role]]),
            ),
            declared_size=len(payloads[_ARTIFACT_PATHS[role]]),
        )
        for role in IdentificationReleaseArtifactRole
    )
    active_policy = _policy()
    request = BuildIdentificationQcReleaseRequest(
        context=_context(active_policy, chain.identity.result_digest),
        release_id="release.synthetic.m0208.identification-qc",
        release_version="1.0.0",
        artifacts=artifacts,
        software_versions=(
            IdentificationSoftwareVersion(
                software_id="software.glio-proteogen",
                version="0.1.0",
                build_digest=sha256_digest({"software": "glio-proteogen", "build": 1}),
                evidence=_evidence("software.glio-proteogen"),
            ),
            IdentificationSoftwareVersion(
                software_id="software.python",
                version="3.12.0",
                build_digest=sha256_digest({"software": "python", "build": 1}),
                evidence=_evidence("software.python"),
            ),
        ),
        reference_versions=(
            IdentificationReferenceVersion(
                reference_id="reference.uniprot",
                build_id="build.uniprot.2026-08",
                version="2026_08",
                digest=sha256_digest({"reference": "uniprot", "build": "2026_08"}),
                evidence=_evidence("reference.uniprot"),
            ),
            IdentificationReferenceVersion(
                reference_id="reference.ensembl",
                build_id="build.ensembl.2026-08",
                version="2026_08",
                digest=sha256_digest({"reference": "ensembl", "build": "2026_08"}),
                evidence=_evidence("reference.ensembl"),
            ),
        ),
        reproduction_evidence=_reproduction_evidence(),
        policy=active_policy,
        signature=ExternalIdentificationSignature(
            signer_id="signer.synthetic.external-eval",
            key_id="key.synthetic.noncrypto-eval",
            algorithm=NONCRYPTO_ALGORITHM,
            claimed_statement_digest=statement_digest,
            signature_value="NONCRYPTO_EVALUATION_TOKEN",
            issued_at=datetime(2026, 8, 12, 23, 59, tzinfo=UTC),
            evidence=_evidence("signature.external-noncrypto"),
        ),
    )
    return IdentificationReleaseFixture(
        request=request,
        artifacts=payloads,
        stages=chain.by_module(),
    )


def _signed_fixture(
    *,
    nonreleasable_stage: str | None = None,
    supersedes_result_digest: str | None = None,
) -> IdentificationReleaseFixture:
    fixture = _with_preserved_stage_encoding(
        build_release_fixture(nonreleasable_stage=nonreleasable_stage)
    )
    request = fixture.request.model_copy(
        update={"supersedes_result_digest": supersedes_result_digest}
    )
    return _sign_fixture(
        IdentificationReleaseFixture(request, fixture.artifacts, fixture.stages)
    )


def _sign_fixture(fixture: IdentificationReleaseFixture) -> IdentificationReleaseFixture:
    request = fixture.request
    manifest = build_identification_release_manifest(
        request,
        fixture.artifacts,
        fixture.stages,
    )
    statement = signing_statement_digest(
        active_manifest_digest=manifest_digest(manifest),
        active_policy_digest=policy_digest(request.policy),
        release_id=request.release_id,
        release_version=request.release_version,
        subject_binding_digest=manifest.subject_binding_digest,
        intended_use_evidence_digest=manifest.intended_use_evidence_digest,
    )
    signature = request.signature.model_copy(update={"claimed_statement_digest": statement})
    request = BuildIdentificationQcReleaseRequest.model_validate(
        request.model_copy(update={"signature": signature}).model_dump(mode="python")
    )
    return IdentificationReleaseFixture(request, fixture.artifacts, fixture.stages)


def _with_preserved_stage_encoding(
    fixture: IdentificationReleaseFixture,
) -> IdentificationReleaseFixture:
    """Use valid noncanonical JSON so the archive oracle detects reserialization."""

    role = IdentificationReleaseArtifactRole.M02_01_CONFORMANCE
    path = _ARTIFACT_PATHS[role]
    content = b" \r\n" + fixture.artifacts[path] + b"\n"
    declarations = tuple(
        item.model_copy(
            update={
                "reference": item.reference.model_copy(
                    update={"digest": sha256_bytes(content)}
                ),
                "declared_size": len(content),
            }
        )
        if item.role is role
        else item
        for item in fixture.request.artifacts
    )
    request = BuildIdentificationQcReleaseRequest.model_validate(
        fixture.request.model_copy(update={"artifacts": declarations}).model_dump(
            mode="python"
        )
    )
    return IdentificationReleaseFixture(
        request,
        {**fixture.artifacts, path: content},
        fixture.stages,
    )


def build_representative_release_fixture(
) -> tuple[IdentificationReleaseFixture, DeterministicNonCryptographicVerifier]:
    """Return the maximum-metadata signed fixture used by the public benchmark."""

    return _max_metadata_fixture(), DeterministicNonCryptographicVerifier()


def _reordered_fixture(
    fixture: IdentificationReleaseFixture,
) -> IdentificationReleaseFixture:
    policy = fixture.request.policy.model_copy(
        update={
            "allowed_signature_algorithms": tuple(
                reversed(fixture.request.policy.allowed_signature_algorithms)
            ),
            "allowed_verifier_ids": tuple(
                reversed(fixture.request.policy.allowed_verifier_ids)
            ),
        }
    )
    request = BuildIdentificationQcReleaseRequest.model_validate(
        fixture.request.model_copy(
            update={
                "artifacts": tuple(reversed(fixture.request.artifacts)),
                "software_versions": tuple(reversed(fixture.request.software_versions)),
                "reference_versions": tuple(reversed(fixture.request.reference_versions)),
                "policy": policy,
            }
        ).model_dump(mode="python")
    )
    return IdentificationReleaseFixture(
        request,
        dict(reversed(tuple(fixture.artifacts.items()))),
        dict(reversed(tuple(fixture.stages.items()))),
    )


def _replace_stage(
    fixture: IdentificationReleaseFixture,
    module_id: str,
    result: FrozenModel,
) -> IdentificationReleaseFixture:
    ordinal = STAGE_MODULE_IDS.index(module_id) + 1
    role = IdentificationReleaseArtifactRole(f"m02_{ordinal:02d}_{_role_suffix(ordinal)}")
    path = _ARTIFACT_PATHS[role]
    content = canonical_json_bytes(result)
    artifacts_by_path = {**fixture.artifacts, path: content}
    declarations = tuple(
        item.model_copy(
            update={
                "reference": item.reference.model_copy(
                    update={"digest": sha256_bytes(content)}
                ),
                "declared_size": len(content),
            }
        )
        if item.role is role
        else item
        for item in fixture.request.artifacts
    )
    request = BuildIdentificationQcReleaseRequest.model_validate(
        fixture.request.model_copy(update={"artifacts": declarations}).model_dump(mode="python")
    )
    return IdentificationReleaseFixture(
        request,
        artifacts_by_path,
        {**fixture.stages, module_id: result},
    )


def _replace_parent_receipt_field(
    fixture: IdentificationReleaseFixture,
    field: str,
    value: str,
) -> IdentificationReleaseFixture:
    role = IdentificationReleaseArtifactRole.PARENT_PROTEIN_SUBTYPE
    path = _ARTIFACT_PATHS[role]
    decoded = strict_json_loads(fixture.artifacts[path])
    if not isinstance(decoded, dict):
        raise _InvalidCorpusError
    decoded[field] = value
    content = canonical_json_bytes(decoded)
    declarations = tuple(
        item.model_copy(
            update={
                "reference": item.reference.model_copy(
                    update={"digest": sha256_bytes(content)}
                ),
                "declared_size": len(content),
            }
        )
        if item.role is role
        else item
        for item in fixture.request.artifacts
    )
    request = BuildIdentificationQcReleaseRequest.model_validate(
        fixture.request.model_copy(update={"artifacts": declarations}).model_dump(
            mode="python"
        )
    )
    return IdentificationReleaseFixture(
        request,
        {**fixture.artifacts, path: content},
        fixture.stages,
    )


def _role_suffix(ordinal: int) -> str:
    return {
        1: "conformance",
        2: "identity_lineage",
        3: "raw_ingestion",
        4: "quality",
        5: "artifact_detection",
        6: "harmonization",
        7: "support_route",
    }[ordinal]


def _max_metadata_fixture() -> IdentificationReleaseFixture:
    fixture = _with_preserved_stage_encoding(build_release_fixture())
    software = tuple(
        IdentificationSoftwareVersion(
            software_id=f"software.synthetic.m0208.{index:02d}",
            version="1.0.0",
            build_digest=sha256_digest({"m0208-software-build": index}),
            evidence=_evidence(f"maximum.software.{index:02d}"),
        )
        for index in range(MAX_METADATA_RECORDS)
    )
    references = tuple(
        IdentificationReferenceVersion(
            reference_id=f"reference.synthetic.m0208.{index:02d}",
            build_id=f"build.synthetic.m0208.{index:02d}",
            version=f"2026_{index:02d}",
            digest=sha256_digest({"m0208-reference-build": index}),
            evidence=_evidence(f"maximum.reference.{index:02d}"),
        )
        for index in range(MAX_METADATA_RECORDS)
    )
    request = BuildIdentificationQcReleaseRequest.model_validate(
        fixture.request.model_copy(
            update={"software_versions": software, "reference_versions": references}
        ).model_dump(mode="python")
    )
    return _sign_fixture(
        IdentificationReleaseFixture(request, fixture.artifacts, fixture.stages)
    )


def _load_corpus() -> dict[str, object]:
    value = strict_json_loads(SCENARIO_PATH.read_bytes())
    if not isinstance(value, dict):
        raise _InvalidCorpusError
    return cast("dict[str, object]", value)


def _corpus_check(corpus: dict[str, object]) -> EvalCheck:
    groups = corpus.get("scenario_groups")
    if not isinstance(groups, list) or not all(isinstance(item, dict) for item in groups):
        return EvalCheck(
            name="corpus.locked_release_plan",
            passed=False,
            detail="invalid scenario_groups",
        )
    locked_groups = cast("list[dict[str, object]]", groups)
    identifiers = tuple(item.get("group_id") for item in locked_groups)
    case_counts = tuple(item.get("case_count") for item in locked_groups)
    case_count = sum(item for item in case_counts if isinstance(item, int))
    passed = (
        corpus.get("module_id") == MODULE_ID
        and corpus.get("schema_version") == "1.0.0"
        and corpus.get("data_classification") == "synthetic_nonclinical"
        and corpus.get("caller_artifact_count") == len(IdentificationReleaseArtifactRole)
        and corpus.get("archive_member_count") == M0208_ARCHIVE_MEMBER_COUNT
        and identifiers == EXPECTED_GROUP_IDS
        and case_counts == EXPECTED_GROUP_CASE_COUNTS
        and case_count == EXPECTED_CASE_COUNT
    )
    return EvalCheck(
        "corpus.locked_release_plan",
        passed,
        f"groups={len(identifiers)};cases={case_count};members={M0208_ARCHIVE_MEMBER_COUNT}",
    )


def _canonical_release_check() -> tuple[EvalCheck, dict[str, object]]:
    fixture = _signed_fixture()
    first_verifier = DeterministicNonCryptographicVerifier()
    first = build_identification_release(
        fixture.request,
        fixture.artifacts,
        fixture.stages,
        first_verifier,
    )
    reordered = _reordered_fixture(fixture)
    second_verifier = DeterministicNonCryptographicVerifier()
    second = build_identification_release(
        reordered.request,
        reordered.artifacts,
        reordered.stages,
        second_verifier,
    )
    package = first.package_bytes
    members = inspect_canonical_ustar(package) if package is not None else ()
    member_bytes = {item.path: item.content for item in members}
    verification_verifier = DeterministicNonCryptographicVerifier()
    package_verification = (
        verify_identification_release(first.result, package, verification_verifier)
        if package is not None
        else None
    )
    expected_manifest_bytes = canonical_json_bytes(normalized_manifest(first.result.manifest))
    expected_receipt_bytes = canonical_json_bytes(
        first.result.signature_verification.model_dump(
            mode="python",
            by_alias=True,
            exclude_none=False,
        )
    )
    preserved_path = _ARTIFACT_PATHS[
        IdentificationReleaseArtifactRole.M02_01_CONFORMANCE
    ]
    passed = (
        first.result.disposition is IdentificationReleaseDisposition.RELEASED
        and first.result == second.result
        and package is not None
        and package == second.package_bytes
        and len(members) == M0208_ARCHIVE_MEMBER_COUNT
        and all(member_bytes.get(path) == content for path, content in fixture.artifacts.items())
        and member_bytes.get(preserved_path, b"").startswith(b" \r\n{")
        and member_bytes.get(M0208_MANIFEST_PATH) == expected_manifest_bytes
        and member_bytes.get(M0208_SIGNATURE_RECEIPT_PATH) == expected_receipt_bytes
        and package_verification is not None
        and package_verification.verified
        and package_verification.content_verified
        and package_verification.authenticity_verified
        and package_verification.member_count == M0208_ARCHIVE_MEMBER_COUNT
        and len(first_verifier.calls) == len(second_verifier.calls) == 1
        and len(verification_verifier.calls) == 1
    )
    return (
        EvalCheck(
            "scenario.canonical_release_and_semantic_reorder",
            passed,
            f"members={len(members)};byte_equal={package == second.package_bytes};"
            f"verified={package_verification.verified if package_verification else False}",
        ),
        first.result.model_dump(mode="json"),
    )


def _stage_disposition_check() -> EvalCheck:
    observed: list[str] = []
    exact = True
    for module_id in STAGE_MODULE_IDS:
        fixture = _signed_fixture(nonreleasable_stage=module_id)
        verifier = DeterministicNonCryptographicVerifier()
        built = build_identification_release(
            fixture.request,
            fixture.artifacts,
            fixture.stages,
            verifier,
        )
        reason_modules = {
            item.stage_module_id
            for item in built.result.quarantine_reasons
            if item.stage_module_id is not None
        }
        exact = exact and (
            built.result.disposition is IdentificationReleaseDisposition.QUARANTINED
            and built.package_bytes is None
            and module_id in reason_modules
            and not verifier.calls
        )
        observed.append(module_id)
    return EvalCheck(
        "scenario.seven_stage_disposition_matrix",
        exact and tuple(observed) == STAGE_MODULE_IDS,
        f"isolated={','.join(observed)}",
    )


def _input_error_code(
    operation: Callable[[], object],
) -> IdentificationReleaseInputErrorCode | None:
    try:
        operation()
    except IdentificationReleaseInputError as error:
        return error.code
    return None


def _manifest_input_error_code(
    candidate: IdentificationReleaseFixture,
) -> IdentificationReleaseInputErrorCode | None:
    try:
        build_identification_release_manifest(
            candidate.request,
            candidate.artifacts,
            candidate.stages,
        )
    except IdentificationReleaseInputError as error:
        return error.code
    return None


def _releasable_cross_chain_results() -> tuple[FrozenModel, FrozenModel, FrozenModel]:
    canonical = build_genuine_chain()
    alternate_identity = evaluate_identity_bindings(different_scope_control_request())

    alternate_quality_request = build_m0204_request("optional_censored_or_not_applicable")
    alternate_quality_request = alternate_quality_request.model_copy(
        update={
            "context": _replace_identity_context(
                alternate_quality_request.context,
                canonical.identity.result_digest,
            )
        }
    )
    alternate_quality = compute_identification_quality(alternate_quality_request)

    support_prerequisites = build_m0207_prerequisites(
        "none",
        "upstream_excluded_target",
    )
    support_request = build_m0207_request(support_prerequisites)
    alternate_support_context = support_request.context.model_copy(
        update={
            "request_id": "request.synthetic.m0208.cross-chain-support",
        }
    )
    alternate_support_request = support_request.model_copy(
        update={"context": alternate_support_context}
    )
    alternate_support = route_identification_support(alternate_support_request)
    return alternate_identity, alternate_quality, alternate_support


def _cross_chain_check() -> EvalCheck:
    fixture = build_release_fixture()
    alternate_identity_raw, alternate_quality_raw, alternate_support_raw = (
        _releasable_cross_chain_results()
    )
    alternate_identity = cast("IdentityBindingEvaluation", alternate_identity_raw)
    alternate_quality = cast("IdentificationQualityProfile", alternate_quality_raw)
    alternate_support = cast("IdentificationSupportRouteResult", alternate_support_raw)
    substitutions = (
        ("GLIO-PROTEOGEN-M02-02", alternate_identity),
        ("GLIO-PROTEOGEN-M02-04", alternate_quality),
        ("GLIO-PROTEOGEN-M02-07", alternate_support),
    )
    error_codes = []
    for module_id, result in substitutions:
        candidate = _replace_stage(fixture, module_id, result)
        error_codes.append(_manifest_input_error_code(candidate))
    independently_releasable = (
        alternate_identity.disposition.value == "conformant"
        and not alternate_identity.human_review_required
        and alternate_quality.disposition.value == "accepted"
        and not alternate_quality.human_review_required
        and alternate_support.disposition.value == "supported"
        and not alternate_support.human_review_required
    )
    return EvalCheck(
        "scenario.cross_chain_closure",
        independently_releasable
        and error_codes
        == [IdentificationReleaseInputErrorCode.CHAIN_MISMATCH] * CROSS_CHAIN_CASE_COUNT,
        f"chain_mismatch={error_codes.count(IdentificationReleaseInputErrorCode.CHAIN_MISMATCH)}"
        f"/{CROSS_CHAIN_CASE_COUNT};alternates_releasable={independently_releasable}",
    )


def _parent_receipt_binding_check() -> EvalCheck:
    fixture = build_release_fixture()
    variants = (
        _replace_parent_receipt_field(
            fixture,
            "parent_target",
            "kinase_activity",
        ),
        _replace_parent_receipt_field(
            fixture,
            "subject_binding_digest",
            sha256_digest({"m0208": "wrong-parent-subject"}),
        ),
        _replace_parent_receipt_field(
            fixture,
            "intended_use_evidence_digest",
            sha256_digest({"m0208": "wrong-parent-intended-use"}),
        ),
    )
    codes = tuple(_manifest_input_error_code(item) for item in variants)
    expected = (
        IdentificationReleaseInputErrorCode.PARENT_JSON_INVALID,
        IdentificationReleaseInputErrorCode.CHAIN_MISMATCH,
        IdentificationReleaseInputErrorCode.CHAIN_MISMATCH,
    )
    return EvalCheck(
        "boundary.parent_protein_subtype_receipt",
        codes == expected,
        f"codes={','.join(item.value if item is not None else 'none' for item in codes)}",
    )


def _raw_ustar(members: tuple[PackageMember, ...]) -> bytes:
    target = io.BytesIO()
    with tarfile.open(fileobj=target, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for member in members:
            info = tarfile.TarInfo(member.path)
            info.size = len(member.content)
            info.mtime = 0
            info.mode = 0o644
            info.uid = 0
            info.gid = 0
            archive.addfile(info, io.BytesIO(member.content))
    return target.getvalue()


def _integrity_archive_check() -> EvalCheck:
    fixture = _signed_fixture()
    verifier = DeterministicNonCryptographicVerifier()
    canonical = build_identification_release(
        fixture.request,
        fixture.artifacts,
        fixture.stages,
        verifier,
    )
    if canonical.package_bytes is None:
        return EvalCheck(
            name="scenario.integrity_and_archive_safety",
            passed=False,
            detail="canonical package unavailable",
        )
    first_path = next(iter(fixture.artifacts))
    original = fixture.artifacts[first_path]
    changed = bytes([original[0] ^ 1]) + original[1:]
    byte_verifier = DeterministicNonCryptographicVerifier()
    byte_mismatch = _input_error_code(
        lambda: build_identification_release(
            fixture.request,
            {**fixture.artifacts, first_path: changed},
            fixture.stages,
            byte_verifier,
        )
    )
    declaration = fixture.request.artifacts[0]
    wrong_digest = declaration.reference.model_copy(
        update={"digest": sha256_digest({"wrong": "declared-digest"})}
    )
    digest_request = fixture.request.model_copy(
        update={
            "artifacts": (
                declaration.model_copy(update={"reference": wrong_digest}),
                *fixture.request.artifacts[1:],
            )
        }
    )
    declaration_verifier = DeterministicNonCryptographicVerifier()
    declared_mismatch = _input_error_code(
        lambda: build_identification_release(
            digest_request,
            fixture.artifacts,
            fixture.stages,
            declaration_verifier,
        )
    )
    size_request = fixture.request.model_copy(
        update={
            "artifacts": (
                declaration.model_copy(update={"declared_size": declaration.declared_size + 1}),
                *fixture.request.artifacts[1:],
            )
        }
    )
    size_verifier = DeterministicNonCryptographicVerifier()
    size_mismatch = _input_error_code(
        lambda: build_identification_release(
            size_request,
            fixture.artifacts,
            fixture.stages,
            size_verifier,
        )
    )
    missing = dict(fixture.artifacts)
    missing.pop(first_path)
    missing_verifier = DeterministicNonCryptographicVerifier()
    missing_member = _input_error_code(
        lambda: build_identification_release(
            fixture.request,
            missing,
            fixture.stages,
            missing_verifier,
        )
    )
    extra_verifier = DeterministicNonCryptographicVerifier()
    undeclared_member = _input_error_code(
        lambda: build_identification_release(
            fixture.request,
            {**fixture.artifacts, "release/undeclared.json": b"{}"},
            fixture.stages,
            extra_verifier,
        )
    )
    canonical_members = inspect_canonical_ustar(canonical.package_bytes)
    archive_variants = (
        _raw_ustar((*canonical_members, canonical_members[0])),
        _raw_ustar(
            (
                PackageMember("../unsafe.json", b"{}"),
                *canonical_members[1:],
            )
        ),
        _raw_ustar(
            (
                *canonical_members,
                PackageMember(canonical_members[0].path.upper(), b"{}"),
            )
        ),
    )
    archive_results = []
    archive_call_counts = []
    for package in archive_variants:
        archive_verifier = DeterministicNonCryptographicVerifier()
        archive_results.append(
            verify_identification_release(
                canonical.result,
                package,
                archive_verifier,
            )
        )
        archive_call_counts.append(len(archive_verifier.calls))
    actual_input_codes = (
        byte_mismatch,
        declared_mismatch,
        size_mismatch,
        missing_member,
        undeclared_member,
    )
    expected_input_codes = (
        IdentificationReleaseInputErrorCode.ARTIFACT_DIGEST_MISMATCH,
        IdentificationReleaseInputErrorCode.ARTIFACT_DIGEST_MISMATCH,
        IdentificationReleaseInputErrorCode.ARTIFACT_SIZE_MISMATCH,
        IdentificationReleaseInputErrorCode.ARTIFACT_MAPPING_MISMATCH,
        IdentificationReleaseInputErrorCode.ARTIFACT_MAPPING_MISMATCH,
    )
    input_call_counts = tuple(
        len(item.calls)
        for item in (
            byte_verifier,
            declaration_verifier,
            size_verifier,
            missing_verifier,
            extra_verifier,
        )
    )
    archive_rejected = all(
        not item.verified
        and not item.content_verified
        and item.reason_code is IdentificationPackageVerificationReason.DESCRIPTOR_MISMATCH
        for item in archive_results
    )
    return EvalCheck(
        "scenario.integrity_and_archive_safety",
        actual_input_codes == expected_input_codes
        and not any(input_call_counts)
        and archive_rejected
        and not any(archive_call_counts)
        and len((*actual_input_codes, *archive_results)) == INTEGRITY_CASE_COUNT,
        f"input_codes={sum(code is not None for code in actual_input_codes)}/5;"
        f"archive_rejected={sum(not item.verified for item in archive_results)}/3;"
        f"verifier_calls={sum(input_call_counts) + sum(archive_call_counts)}",
    )


def _signature_binding_check() -> EvalCheck:
    fixture = _signed_fixture()
    accepted_verifier = DeterministicNonCryptographicVerifier()
    accepted = build_identification_release(
        fixture.request,
        fixture.artifacts,
        fixture.stages,
        accepted_verifier,
    )
    rejected_verifier = DeterministicNonCryptographicVerifier(accept=False)
    rejected = build_identification_release(
        fixture.request,
        fixture.artifacts,
        fixture.stages,
        rejected_verifier,
    )
    unavailable = build_identification_release(
        fixture.request,
        fixture.artifacts,
        fixture.stages,
        None,
    )
    mismatch_fixture = build_release_fixture()
    mismatch_verifier = DeterministicNonCryptographicVerifier()
    mismatch = build_identification_release(
        mismatch_fixture.request,
        mismatch_fixture.artifacts,
        mismatch_fixture.stages,
        mismatch_verifier,
    )
    unsupported_payload = fixture.request.model_dump(mode="python")
    unsupported_payload["signature"]["algorithm"] = "unsupported-eval-algorithm"
    try:
        BuildIdentificationQcReleaseRequest.model_validate(unsupported_payload)
        unsupported_rejected = False
    except ValueError:
        unsupported_rejected = True
    replay_verifier = DeterministicNonCryptographicVerifier()
    replay = build_identification_release(
        fixture.request,
        fixture.artifacts,
        fixture.stages,
        replay_verifier,
    )
    cases = (
        accepted.result.disposition is IdentificationReleaseDisposition.RELEASED
        and len(accepted_verifier.calls) == 1,
        rejected.result.signature_verification.reason_code
        is IdentificationSignatureVerificationReason.VERIFIER_REJECTED
        and rejected.package_bytes is None
        and len(rejected_verifier.calls) == 1,
        unavailable.result.signature_verification.reason_code
        is IdentificationSignatureVerificationReason.VERIFIER_UNAVAILABLE
        and unavailable.package_bytes is None,
        mismatch.result.signature_verification.reason_code
        is IdentificationSignatureVerificationReason.STATEMENT_MISMATCH
        and not mismatch_verifier.calls,
        unsupported_rejected,
        replay.result == accepted.result
        and replay.package_bytes == accepted.package_bytes
        and len(replay_verifier.calls) == 1,
    )
    return EvalCheck(
        "scenario.signature_binding_and_replay",
        all(cases) and len(cases) == SIGNATURE_CASE_COUNT,
        f"passed={sum(cases)}/{SIGNATURE_CASE_COUNT};"
        f"accepted_calls={len(accepted_verifier.calls)}",
    )


def _strict_reconstruction_check() -> EvalCheck:
    fixture = _signed_fixture()
    base = fixture.request.model_dump(mode="python")
    payloads: list[dict[str, object]] = []
    coerced_integer = fixture.request.model_dump(mode="python")
    coerced_integer["artifacts"][0]["declared_size"] = str(
        fixture.request.artifacts[0].declared_size
    )
    payloads.append(coerced_integer)
    coerced_boolean = fixture.request.model_dump(mode="python")
    coerced_boolean["artifacts"][0]["declared_size"] = True
    payloads.append(coerced_boolean)
    unknown = fixture.request.model_dump(mode="python")
    unknown["unknown_release_field"] = "forbidden"
    payloads.append(unknown)
    invalid_enum = fixture.request.model_dump(mode="python")
    invalid_enum["artifacts"][0]["role"] = "kinase_activity"
    payloads.append(invalid_enum)
    stale = fixture.request.model_dump(mode="python")
    stale["context"]["references"]["approved_configuration"]["evidence"]["digest"] = (
        sha256_digest({"stale": "policy"})
    )
    payloads.append(stale)
    duplicate = fixture.request.model_dump(mode="python")
    duplicate["artifacts"][1]["path"] = str(base["artifacts"][0]["path"]).upper()
    payloads.append(duplicate)
    rejected = []
    for payload in payloads:
        try:
            BuildIdentificationQcReleaseRequest.model_validate(payload)
            rejected.append(False)
        except ValueError:
            rejected.append(True)
    return EvalCheck(
        "scenario.strict_canonical_reconstruction",
        all(rejected) and len(rejected) == STRICT_CASE_COUNT,
        f"rejected={sum(rejected)}/{STRICT_CASE_COUNT}",
    )


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in _all_keys(item)}
    if isinstance(value, list | tuple):
        return {key for item in value for key in _all_keys(item)}
    return set()


def _privacy_ownership_check(result: dict[str, object]) -> EvalCheck:
    forbidden = {
        "artifact_bytes",
        "raw_spectra",
        "peptide_rows",
        "protein_subtype_score",
        "proteotype",
        "kinase_activity",
        "omics_fusion",
        "treatment_recommendation",
        "private_key",
        "signing_secret",
        "upstream_mutations",
    }
    leaked = sorted(_all_keys(result) & forbidden)
    rendered = canonical_json_bytes(result).decode("utf-8")
    leaked_values = [
        value
        for value in ("NONCRYPTO_EVALUATION_TOKEN", "synthetic-spectrum", "MPEPTIDE")
        if value in rendered and value != "NONCRYPTO_EVALUATION_TOKEN"
    ]
    return EvalCheck(
        "scenario.privacy_and_ownership_closure",
        not leaked and not leaked_values,
        "closed release metadata only" if not leaked else f"keys={leaked}",
    )


def _authorization_recovery_limit_check() -> EvalCheck:
    fixture = _signed_fixture()
    denied_consent = fixture.request.context.references.consent.model_copy(
        update={"state": ConsentState.WITHHELD}
    )
    denied_references = fixture.request.context.references.model_copy(
        update={"consent": denied_consent}
    )
    denied = fixture.request.model_copy(
        update={
            "context": fixture.request.context.model_copy(
                update={"references": denied_references}
            )
        }
    )
    try:
        build_identification_release(
            denied,
            fixture.artifacts,
            _UnreadableMapping("stage results"),
            DeterministicNonCryptographicVerifier(),
        )
        hostile_chain = False
    except IdentificationReleaseAuthorizationError:
        hostile_chain = True
    try:
        build_identification_release(
            denied,
            _UnreadableMapping("artifact bytes"),
            fixture.stages,
            DeterministicNonCryptographicVerifier(),
        )
        hostile_artifacts = False
    except IdentificationReleaseAuthorizationError:
        hostile_artifacts = True

    rejected = build_identification_release(
        fixture.request,
        fixture.artifacts,
        fixture.stages,
        DeterministicNonCryptographicVerifier(accept=False),
    )
    rejected_snapshot = rejected.result.model_dump_json()
    recovery_fixture = _signed_fixture(
        supersedes_result_digest=rejected.result.result_digest
    )
    recovered = build_identification_release(
        recovery_fixture.request,
        recovery_fixture.artifacts,
        recovery_fixture.stages,
        DeterministicNonCryptographicVerifier(),
    )
    recovery = (
        rejected.result.disposition is IdentificationReleaseDisposition.QUARANTINED
        and recovered.result.disposition is IdentificationReleaseDisposition.RELEASED
        and recovered.result.supersedes_result_digest == rejected.result.result_digest
        and rejected.result.model_dump_json() == rejected_snapshot
    )

    maximum = _max_metadata_fixture()
    maximum_built = build_identification_release(
        maximum.request,
        maximum.artifacts,
        maximum.stages,
        DeterministicNonCryptographicVerifier(),
    )
    maximum_accepted = (
        maximum_built.result.disposition is IdentificationReleaseDisposition.RELEASED
        and len(maximum.request.software_versions) == MAX_METADATA_RECORDS
        and len(maximum.request.reference_versions) == MAX_METADATA_RECORDS
    )
    excess_payload = maximum.request.model_dump(mode="python")
    excess_software = IdentificationSoftwareVersion(
        software_id="software.synthetic.m0208.excess",
        version="1.0.0",
        build_digest=sha256_digest({"m0208-software-build": "excess"}),
        evidence=_evidence("maximum.software.excess"),
    ).model_dump(mode="python")
    excess_payload["software_versions"] = (
        *excess_payload["software_versions"],
        excess_software,
    )
    try:
        BuildIdentificationQcReleaseRequest.model_validate(excess_payload)
        first_excess_rejected = False
    except ValueError:
        first_excess_rejected = True
    cases = (
        hostile_chain,
        hostile_artifacts,
        recovery,
        maximum_accepted,
        first_excess_rejected,
    )
    return EvalCheck(
        "scenario.authorization_recovery_and_maximum_shape",
        all(cases) and len(cases) == AUTHORIZATION_CASE_COUNT,
        f"passed={sum(cases)}/{AUTHORIZATION_CASE_COUNT}",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    corpus = _load_corpus()
    checks = [_corpus_check(corpus)]
    canonical_check, canonical_result = _canonical_release_check()
    checks.extend(
        (
            canonical_check,
            _stage_disposition_check(),
            _cross_chain_check(),
            _parent_receipt_binding_check(),
            _integrity_archive_check(),
            _signature_binding_check(),
            _strict_reconstruction_check(),
            _privacy_ownership_check(canonical_result),
            _authorization_recovery_limit_check(),
        )
    )
    passed = all(item.passed for item in checks)
    report = {
        "module_id": MODULE_ID,
        "passed": passed,
        "scenario_group_count": len(EXPECTED_GROUP_IDS),
        "scenario_case_count": EXPECTED_CASE_COUNT,
        "corpus_digest": sha256_digest(corpus),
        "checks": [asdict(item) for item in checks],
    }
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        sys.stdout.write(rendered)
    else:
        args.output.write_text(rendered, encoding="utf-8")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
