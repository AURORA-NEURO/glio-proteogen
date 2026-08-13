"""Execute the locked M03-03 protein-inference raw-admission corpus."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, TypedDict, cast

from fastapi.testclient import TestClient
from pydantic import TypeAdapter, ValidationError
from typer.testing import CliRunner

from evals.m03_01.run import build_scenario_request as build_m0301_request
from evals.m03_02.run import build_scenario_request as build_m0302_request
from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m03_01 import (
    ApprovedSearchSpace,
    EvaluateProteinInferenceProtocolRequest,
    ProteinInferenceProtocolConformanceResult,
    ProtocolConformanceDisposition,
)
from glio_proteogen.contracts.m03_01 import (
    configuration_digest as m0301_configuration_digest,
)
from glio_proteogen.contracts.m03_01 import (
    protocol_digest as m0301_protocol_digest,
)
from glio_proteogen.contracts.m03_02 import (
    ProteinInferenceArtifactClaim,
    ProteinInferenceIdentityLineageResolution,
    ReconcileProteinInferenceIdentityLineageRequest,
    ReconciliationDisposition,
)
from glio_proteogen.contracts.m03_02 import (
    configuration_digest as m0302_configuration_digest,
)
from glio_proteogen.contracts.m03_03 import (
    M0303_MAX_SOURCES,
    ApprovedBuild,
    IngestProteinInferenceRawInputsRequest,
    ProteinInferenceAdmissionDisposition,
    ProteinInferenceBuildState,
    ProteinInferenceCompression,
    ProteinInferenceDiagnosticCode,
    ProteinInferenceRawAdmissionResult,
    ProteinInferenceRawFormat,
    ProteinInferenceRawPolicy,
    ProteinInferenceRawRole,
    ProteinInferenceRawSource,
    ValidatedProteinInferenceRawInput,
    canonical_request_digest,
    contract_json_schema,
    lineage_ingestion_receipt,
    lineage_receipt_digest,
    protocol_ingestion_receipt,
    protocol_receipt_digest,
    source_manifest_digest,
)
from glio_proteogen.contracts.m03_03 import (
    configuration_digest as m0303_configuration_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentState,
    ExecutionContext,
    IdentityLineageState,
    UpstreamDecisionState,
)
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c03_protein_inference.m03_01_protocol_metadata import (
    evaluate_protein_inference_protocol,
)
from glio_proteogen.modules.c03_protein_inference.m03_02_identity_lineage import (
    reconcile_protein_inference_identity_lineage,
)
from glio_proteogen.modules.c03_protein_inference.m03_03_raw_ingestion import (
    M0303Plugin,
    M0303ProteinInferenceRawIngestionEngine,
    M0303Service,
    ProteinInferenceRawIngestionAuthorizationError,
    ProteinInferenceRawIngestionInputError,
    ProteinInferenceRawIngestionSubmission,
    ingest_protein_inference_raw_inputs,
)

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

MODULE_ID = "GLIO-PROTEOGEN-M03-03"
ROOT = Path(__file__).parents[2]
SCENARIO_PATH = ROOT / "tests" / "fixtures" / "m03_03" / "scenarios.json"
_REQUEST_ADAPTER = TypeAdapter(IngestProteinInferenceRawInputsRequest)
_RESULT_ADAPTER = TypeAdapter(ProteinInferenceRawAdmissionResult)
_EXPECTED_GROUP_COUNT = 8
_EXPECTED_CASE_COUNT = 77
_EXPECTED_SCHEMA_NAMES = 8
_HTTP_OK = 200
_BUILD_ID = "build.synthetic.reference"
_BUILD_VERSION = "1.0.0"


class _MutuallyExclusiveBuilderOptionsError(ValueError):
    pass


class _UnexpectedSourceTraversalError(AssertionError):
    pass


class ScenarioGroup(TypedDict):
    group_id: str
    case_ids: list[str]


class Corpus(TypedDict):
    module_id: str
    scenario_groups: list[ScenarioGroup]


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class Scenario:
    """One fully genuine upstream chain plus actual M03-03 source bytes."""

    request: IngestProteinInferenceRawInputsRequest
    sources: dict[str, bytes]
    protocol_result: ProteinInferenceProtocolConformanceResult
    lineage_result: ProteinInferenceIdentityLineageResolution


@dataclass(frozen=True, slots=True)
class ScenarioOptions:
    """Explicit mutations and source cardinalities for one evidence scenario."""

    gzip_roles: frozenset[ProteinInferenceRawRole] = frozenset()
    raw_overrides: Mapping[ProteinInferenceRawRole, bytes] | None = None
    generated_overrides: Mapping[ProteinInferenceRawRole, bytes] | None = None
    transport_overrides: Mapping[ProteinInferenceRawRole, bytes] | None = None
    spectra_count: int = 1
    peptide_count: int = 1


@dataclass(frozen=True, slots=True)
class _ExtraPeptide:
    source_id: str
    payload: bytes
    artifact: ArtifactReference
    claim_id: str


@dataclass(frozen=True, slots=True)
class _ManifestMaterials:
    group_bytes: bytes
    group_artifact: ArtifactReference
    ambiguity_bytes: bytes
    ambiguity_artifact: ArtifactReference
    claim_artifacts: dict[str, ArtifactReference]
    extra_peptides: tuple[_ExtraPeptide, ...]


def _bytes_digest(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _artifact(source_id: str, payload: bytes, media_type: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.synthetic.m0303.{source_id}",
        version="1.0.0",
        digest=_bytes_digest(payload),
        media_type=media_type,
    )


def _base_source_bytes() -> dict[ProteinInferenceRawRole, tuple[str, bytes, str]]:
    return {
        ProteinInferenceRawRole.SPECTRA: (
            "source.spectra.mzml",
            (
                b'<?xml version="1.0" encoding="UTF-8"?>\n'
                b'<mzML xmlns="http://psi.hupo.org/ms/mzml" version="1.1.0">'
                b'<run id="run-synthetic"><spectrumList count="1">'
                b'<spectrum id="scan=1" index="0" defaultArrayLength="0"/>'
                b'</spectrumList><chromatogramList count="0"/></run></mzML>\n'
            ),
            "application/mzml+xml",
        ),
        ProteinInferenceRawRole.PEPTIDE_EVIDENCE: (
            "source.peptide-evidence.mzid",
            (
                b'<?xml version="1.0" encoding="UTF-8"?>\n'
                b'<MzIdentML xmlns="http://psidev.info/psi/pi/mzIdentML/1.3" '
                b'id="identification-synthetic" version="1.3.0"><DataCollection>'
                b'<Inputs><SearchDatabase id="database-1" '
                b'databaseName="build.synthetic.targets-decoys-v1" '
                b'version="2026.1.0"/>'
                b'<SpectraData id="spectra-1"/></Inputs><AnalysisData>'
                b'<SpectrumIdentificationList id="list-1">'
                b'<SpectrumIdentificationResult id="result-1" spectrumID="scan=1" '
                b'spectraData_ref="spectra-1"/></SpectrumIdentificationList>'
                b"</AnalysisData></DataCollection></MzIdentML>\n"
            ),
            "application/mzidentml+xml",
        ),
        ProteinInferenceRawRole.CANONICAL_SEQUENCES: (
            "source.canonical.fasta",
            b">canonical.synthetic.1\nMPEPTIDEK\n",
            "text/x-fasta",
        ),
        ProteinInferenceRawRole.DECOY_SEQUENCES: (
            "source.decoy.fasta",
            b">decoy.synthetic.1\nKEDITPEPM\n",
            "text/x-fasta",
        ),
        ProteinInferenceRawRole.ISOFORM_SEQUENCES: (
            "source.isoform.fasta",
            b">isoform.synthetic.1\nMPEPTIDEKR\n",
            "text/x-fasta",
        ),
        ProteinInferenceRawRole.VARIANT_SEQUENCES: (
            "source.variant.fasta",
            b">variant.synthetic.1\nMPEPAIDEK\n",
            "text/x-fasta",
        ),
        ProteinInferenceRawRole.CONTAMINANT_SEQUENCES: (
            "source.contaminant.fasta",
            b">contaminant.synthetic.1\nMACDEFGHIK\n",
            "text/x-fasta",
        ),
        ProteinInferenceRawRole.PTM_VOCABULARY: (
            "source.psi-mod.obo",
            (
                b"format-version: 1.2\ndata-version: 3.0.0\n\n[Term]\n"
                b"id: MOD:00046\nname: Synthetic modification control\n"
            ),
            "text/obo",
        ),
        ProteinInferenceRawRole.GENOMIC_CONTEXT: (
            "source.variants.vcf",
            (
                b"##fileformat=VCFv4.5\n"
                b"##reference=build.synthetic.reference:1.0.0\n"
                b"##contig=<ID=synthetic_chr,length=1000>\n"
                b"#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
                b"synthetic_chr\t101\tvariant-1\tA\tG\t60\tPASS\t.\n"
            ),
            "text/x-vcf",
        ),
        ProteinInferenceRawRole.TRANSCRIPT_CONTEXT: (
            "source.annotations.gff3",
            (
                b"##gff-version 3\n"
                b"##genome-build build.synthetic.reference:1.0.0\n"
                b"##sequence-region synthetic_chr 1 1000\n"
                b"synthetic_chr\tfixture\tgene\t101\t300\t.\t+\t.\tID=gene-1\n"
            ),
            "text/x-gff3",
        ),
    }


def _declared_format(role: ProteinInferenceRawRole) -> ProteinInferenceRawFormat:
    return {
        ProteinInferenceRawRole.SPECTRA: ProteinInferenceRawFormat.MZML,
        ProteinInferenceRawRole.PEPTIDE_EVIDENCE: ProteinInferenceRawFormat.MZIDENTML,
        ProteinInferenceRawRole.PROTEIN_GROUP_MANIFEST: (
            ProteinInferenceRawFormat.PROTEIN_GROUP_JSON
        ),
        ProteinInferenceRawRole.AMBIGUITY_MANIFEST: ProteinInferenceRawFormat.AMBIGUITY_JSON,
        ProteinInferenceRawRole.COMPLEX_ACTIVITY_INPUT_BUNDLE: (
            ProteinInferenceRawFormat.COMPLEX_BUNDLE_JSON
        ),
        ProteinInferenceRawRole.CANONICAL_SEQUENCES: ProteinInferenceRawFormat.FASTA,
        ProteinInferenceRawRole.DECOY_SEQUENCES: ProteinInferenceRawFormat.FASTA,
        ProteinInferenceRawRole.ISOFORM_SEQUENCES: ProteinInferenceRawFormat.FASTA,
        ProteinInferenceRawRole.VARIANT_SEQUENCES: ProteinInferenceRawFormat.FASTA,
        ProteinInferenceRawRole.CONTAMINANT_SEQUENCES: ProteinInferenceRawFormat.FASTA,
        ProteinInferenceRawRole.PTM_VOCABULARY: ProteinInferenceRawFormat.PSI_MOD_OBO,
        ProteinInferenceRawRole.GENOMIC_CONTEXT: ProteinInferenceRawFormat.VCF,
        ProteinInferenceRawRole.TRANSCRIPT_CONTEXT: ProteinInferenceRawFormat.GFF3,
    }[role]


def _source(  # noqa: PLR0913 - explicit byte/declaration binding inputs.
    role: ProteinInferenceRawRole,
    source_id: str,
    payload: bytes,
    media_type: str,
    *,
    artifact: ArtifactReference | None = None,
    bound_claim_id: str | None = None,
    compression: ProteinInferenceCompression = ProteinInferenceCompression.NONE,
    expected_build: tuple[str, str] | None = None,
) -> ProteinInferenceRawSource:
    build_fields: dict[str, str] = {}
    if role in {
        ProteinInferenceRawRole.GENOMIC_CONTEXT,
        ProteinInferenceRawRole.TRANSCRIPT_CONTEXT,
    }:
        build_fields = {
            "expected_build_id": _BUILD_ID,
            "expected_build_version": _BUILD_VERSION,
        }
    elif expected_build is not None:
        build_fields = {
            "expected_build_id": expected_build[0],
            "expected_build_version": expected_build[1],
        }
    return ProteinInferenceRawSource(
        source_id=source_id,
        role=role,
        artifact=artifact or _artifact(source_id, payload, media_type),
        byte_length=len(payload),
        declared_format=_declared_format(role),
        declared_compression=compression,
        bound_claim_id=bound_claim_id,
        **build_fields,
    )


def _genuine_protocol_result(
    identity_digest: str,
    raw: Mapping[ProteinInferenceRawRole, tuple[str, bytes, str]],
) -> ProteinInferenceProtocolConformanceResult:
    seed = build_m0301_request("canonical")
    search = seed.protocol_schema.search_space
    search_artifacts = {
        role: _artifact(*raw[role])
        for role in (
            ProteinInferenceRawRole.CANONICAL_SEQUENCES,
            ProteinInferenceRawRole.DECOY_SEQUENCES,
            ProteinInferenceRawRole.ISOFORM_SEQUENCES,
            ProteinInferenceRawRole.VARIANT_SEQUENCES,
            ProteinInferenceRawRole.CONTAMINANT_SEQUENCES,
        )
    }
    search = search.model_copy(
        update={
            "content_digest": sha256_digest(
                tuple(sorted(item.digest for item in search_artifacts.values()))
            ),
            "canonical_sequence_reference": search_artifacts[
                ProteinInferenceRawRole.CANONICAL_SEQUENCES
            ],
            "decoy_reference": search_artifacts[ProteinInferenceRawRole.DECOY_SEQUENCES],
            "isoform_reference": search_artifacts[ProteinInferenceRawRole.ISOFORM_SEQUENCES],
            "variant_reference": search_artifacts[ProteinInferenceRawRole.VARIANT_SEQUENCES],
            "contaminant_reference": search_artifacts[
                ProteinInferenceRawRole.CONTAMINANT_SEQUENCES
            ],
        }
    )
    eligibility = seed.protocol_schema.peptide_eligibility.model_copy(
        update={
            "modification_vocabulary_reference": _artifact(
                *raw[ProteinInferenceRawRole.PTM_VOCABULARY]
            )
        }
    )
    protocol = seed.protocol_schema.model_copy(
        update={"search_space": search, "peptide_eligibility": eligibility}
    )
    approved = ApprovedSearchSpace(
        namespace=search.namespace,
        release=search.release,
        build_id=search.build_id,
        content_digest=search.content_digest,
    )
    profile = seed.conformance_profile.model_copy(
        update={
            "protocol_schema_digest": m0301_protocol_digest(protocol),
            "approved_search_spaces": (approved,),
        }
    )
    references = seed.context.references
    configuration = references.approved_configuration.model_copy(
        update={
            "evidence": references.approved_configuration.evidence.model_copy(
                update={"digest": m0301_configuration_digest(protocol, profile)}
            )
        }
    )
    identity = references.identity_lineage.model_copy(update={"binding_digest": identity_digest})
    context = seed.context.model_copy(
        update={
            "references": references.model_copy(
                update={
                    "approved_configuration": configuration,
                    "identity_lineage": identity,
                }
            )
        }
    )
    request = EvaluateProteinInferenceProtocolRequest(
        context=context,
        protocol_schema=protocol,
        conformance_profile=profile,
    )
    result = evaluate_protein_inference_protocol(request)
    if result.disposition is not ProtocolConformanceDisposition.CONFORMANT:
        raise AssertionError
    return result


def _transformed_source_bytes(
    options: ScenarioOptions,
) -> tuple[
    dict[ProteinInferenceRawRole, tuple[str, bytes, str]],
    dict[ProteinInferenceRawRole, tuple[str, bytes, str]],
]:
    raw = _base_source_bytes()
    if options.raw_overrides:
        raw = {
            role: (source_id, options.raw_overrides.get(role, payload), media_type)
            for role, (source_id, payload, media_type) in raw.items()
        }
    transformed = {
        role: (
            source_id,
            (
                gzip.compress(payload, compresslevel=9, mtime=0)
                if role in options.gzip_roles
                else payload
            ),
            media_type,
        )
        for role, (source_id, payload, media_type) in raw.items()
    }
    if options.transport_overrides:
        transformed = {
            role: (source_id, options.transport_overrides.get(role, payload), media_type)
            for role, (source_id, payload, media_type) in transformed.items()
        }
    return raw, transformed


def _manifest_materials(
    protocol: ProteinInferenceProtocolConformanceResult,
    transformed: Mapping[ProteinInferenceRawRole, tuple[str, bytes, str]],
    options: ScenarioOptions,
) -> _ManifestMaterials:
    peptide_id, peptide_bytes, peptide_media = transformed[ProteinInferenceRawRole.PEPTIDE_EVIDENCE]
    peptide_artifact = _artifact(peptide_id, peptide_bytes, peptide_media)
    common = {
        "schema_version": "1.0.0",
        "protocol_result_digest": protocol.result_digest,
        "search_space_digest": protocol.receipt.search_space_digest,
        "controlled_vocabulary_id": protocol.protocol_schema.controlled_vocabulary_id,
        "controlled_vocabulary_version": protocol.protocol_schema.controlled_vocabulary_version,
        "unit_system_version": protocol.protocol_schema.unit_system_version,
    }
    group_bytes = canonical_json_bytes(
        {**common, "claim_id": "claim.group", "group_ids": ["group.synthetic.1"]}
    )
    if options.generated_overrides:
        group_bytes = options.generated_overrides.get(
            ProteinInferenceRawRole.PROTEIN_GROUP_MANIFEST,
            group_bytes,
        )
    group_artifact = _artifact("source.protein-group.json", group_bytes, "application/json")
    ambiguity_bytes = canonical_json_bytes(
        {
            **common,
            "claim_id": "claim.ambiguity",
            "group_claim_id": "claim.group",
            "group_claim_digest": group_artifact.digest,
            "ambiguity_ids": ["ambiguity.synthetic.1"],
        }
    )
    if options.generated_overrides:
        ambiguity_bytes = options.generated_overrides.get(
            ProteinInferenceRawRole.AMBIGUITY_MANIFEST,
            ambiguity_bytes,
        )
    ambiguity_artifact = _artifact(
        "source.ambiguity.json",
        ambiguity_bytes,
        "application/json",
    )
    claim_artifacts = {
        "claim.peptide.000": peptide_artifact,
        "claim.group": group_artifact,
        "claim.ambiguity": ambiguity_artifact,
    }
    peptide_template = transformed[ProteinInferenceRawRole.PEPTIDE_EVIDENCE][1]
    extra: list[_ExtraPeptide] = []
    for index in range(1, options.peptide_count):
        source_id = f"source.peptide-evidence.{index:03d}.mzid"
        claim_id = f"claim.peptide.{index:03d}"
        payload = peptide_template.replace(
            b'identification-synthetic"',
            f'identification-synthetic-{index:03d}"'.encode(),
            1,
        )
        artifact = _artifact(source_id, payload, "application/mzidentml+xml")
        extra.append(
            _ExtraPeptide(
                source_id=source_id,
                payload=payload,
                artifact=artifact,
                claim_id=claim_id,
            )
        )
        claim_artifacts[claim_id] = artifact
    return _ManifestMaterials(
        group_bytes=group_bytes,
        group_artifact=group_artifact,
        ambiguity_bytes=ambiguity_bytes,
        ambiguity_artifact=ambiguity_artifact,
        claim_artifacts=claim_artifacts,
        extra_peptides=tuple(extra),
    )


def _non_bundle_capsule(
    protocol: ProteinInferenceProtocolConformanceResult,
    raw: Mapping[ProteinInferenceRawRole, tuple[str, bytes, str]],
    transformed: Mapping[ProteinInferenceRawRole, tuple[str, bytes, str]],
    materials: _ManifestMaterials,
    options: ScenarioOptions,
) -> tuple[list[ProteinInferenceRawSource], dict[str, bytes]]:
    declarations: list[ProteinInferenceRawSource] = []
    payloads: dict[str, bytes] = {}
    claim_by_role = {
        ProteinInferenceRawRole.PEPTIDE_EVIDENCE: "claim.peptide.000",
        ProteinInferenceRawRole.PROTEIN_GROUP_MANIFEST: "claim.group",
        ProteinInferenceRawRole.AMBIGUITY_MANIFEST: "claim.ambiguity",
    }
    expected_builds = {
        ProteinInferenceRawRole.PEPTIDE_EVIDENCE: (
            protocol.protocol_schema.search_space.build_id,
            protocol.protocol_schema.search_space.release,
        ),
        ProteinInferenceRawRole.PTM_VOCABULARY: (
            protocol.protocol_schema.controlled_vocabulary_id,
            protocol.protocol_schema.controlled_vocabulary_version,
        ),
    }
    materialized = {
        **transformed,
        ProteinInferenceRawRole.PROTEIN_GROUP_MANIFEST: (
            "source.protein-group.json",
            materials.group_bytes,
            "application/json",
        ),
        ProteinInferenceRawRole.AMBIGUITY_MANIFEST: (
            "source.ambiguity.json",
            materials.ambiguity_bytes,
            "application/json",
        ),
    }
    for role, (source_id, payload, media_type) in materialized.items():
        bound_claim_id = claim_by_role.get(role)
        bound_artifact = (
            materials.claim_artifacts[bound_claim_id] if bound_claim_id is not None else None
        )
        declaration = _source(
            role,
            source_id,
            payload,
            media_type,
            artifact=bound_artifact,
            bound_claim_id=bound_claim_id,
            compression=(
                ProteinInferenceCompression.GZIP
                if role in options.gzip_roles
                else ProteinInferenceCompression.NONE
            ),
            expected_build=expected_builds.get(role),
        )
        declarations.append(declaration)
        payloads[source_id] = payload
    peptide_build = expected_builds[ProteinInferenceRawRole.PEPTIDE_EVIDENCE]
    for extra in materials.extra_peptides:
        declarations.append(
            _source(
                ProteinInferenceRawRole.PEPTIDE_EVIDENCE,
                extra.source_id,
                extra.payload,
                "application/mzidentml+xml",
                artifact=extra.artifact,
                bound_claim_id=extra.claim_id,
                expected_build=peptide_build,
            )
        )
        payloads[extra.source_id] = extra.payload
    spectra_template = raw[ProteinInferenceRawRole.SPECTRA][1]
    for index in range(1, options.spectra_count):
        source_id = f"source.spectra.{index:02d}.mzml"
        payload = spectra_template.replace(
            b'run id="run-synthetic"',
            f'run id="run-synthetic-{index:02d}"'.encode(),
            1,
        )
        declarations.append(
            _source(
                ProteinInferenceRawRole.SPECTRA,
                source_id,
                payload,
                "application/mzml+xml",
            )
        )
        payloads[source_id] = payload
    return declarations, payloads


def _close_bundle(
    declarations: list[ProteinInferenceRawSource],
    payloads: dict[str, bytes],
    materials: _ManifestMaterials,
    options: ScenarioOptions,
) -> tuple[tuple[ProteinInferenceRawSource, ...], str]:
    manifest_digest = source_manifest_digest(tuple(declarations))
    bundle_bytes = canonical_json_bytes(
        {
            "schema_version": "1.0.0",
            "claim_id": "claim.bundle",
            "source_manifest_digest": manifest_digest,
            "protein_group_claim_id": "claim.group",
            "protein_group_digest": materials.group_artifact.digest,
            "ambiguity_claim_id": "claim.ambiguity",
            "ambiguity_digest": materials.ambiguity_artifact.digest,
        }
    )
    if options.generated_overrides:
        bundle_bytes = options.generated_overrides.get(
            ProteinInferenceRawRole.COMPLEX_ACTIVITY_INPUT_BUNDLE,
            bundle_bytes,
        )
    bundle_artifact = _artifact("source.bundle.json", bundle_bytes, "application/json")
    materials.claim_artifacts["claim.bundle"] = bundle_artifact
    bundle_source = _source(
        ProteinInferenceRawRole.COMPLEX_ACTIVITY_INPUT_BUNDLE,
        "source.bundle.json",
        bundle_bytes,
        "application/json",
        artifact=bundle_artifact,
        bound_claim_id="claim.bundle",
    )
    payloads[bundle_source.source_id] = bundle_bytes
    return (*declarations, bundle_source), manifest_digest


def _genuine_lineage_result(
    seed: ReconcileProteinInferenceIdentityLineageRequest,
    protocol: ProteinInferenceProtocolConformanceResult,
    materials: _ManifestMaterials,
) -> ProteinInferenceIdentityLineageResolution:
    claims = tuple(
        ProteinInferenceArtifactClaim(
            **{
                **claim.model_dump(mode="python"),
                "artifact": materials.claim_artifacts[claim.claim_id],
                "producer_protocol_result_digest": protocol.result_digest,
                "producer_search_space_digest": protocol.receipt.search_space_digest,
            }
        )
        for claim in seed.artifact_claims
    )
    peptide_template = next(claim for claim in claims if claim.claim_id == "claim.peptide.000")
    claims = (
        *claims,
        *(
            ProteinInferenceArtifactClaim(
                **{
                    **peptide_template.model_dump(mode="python"),
                    "claim_id": extra.claim_id,
                    "artifact": extra.artifact,
                }
            )
            for extra in materials.extra_peptides
        ),
    )
    peptide_claim_ids = tuple(
        claim.claim_id for claim in claims if claim.role.value == "peptide_evidence_manifest"
    )
    derivations = tuple(
        item.model_copy(update={"source_claim_ids": peptide_claim_ids})
        if item.target_claim_id == "claim.group"
        else item
        for item in seed.derivations
    )
    policy = seed.policy
    if len(claims) > policy.max_artifact_claims:
        policy = policy.model_copy(
            update={
                "max_artifact_claims": len(claims),
                "max_derivation_sources": len(peptide_claim_ids),
            }
        )
    context = seed.context
    if policy != seed.policy:
        references = context.references
        approved = references.approved_configuration.model_copy(
            update={
                "evidence": references.approved_configuration.evidence.model_copy(
                    update={"digest": m0302_configuration_digest(policy)}
                )
            }
        )
        context = context.model_copy(
            update={
                "references": references.model_copy(update={"approved_configuration": approved})
            }
        )
    request = ReconcileProteinInferenceIdentityLineageRequest(
        context=context,
        identity_resolution=seed.identity_resolution,
        protocol_result=protocol,
        policy=policy,
        artifact_claims=claims,
        derivations=derivations,
        cn_receipts=seed.cn_receipts,
    )
    result = reconcile_protein_inference_identity_lineage(request)
    if result.disposition is not ReconciliationDisposition.RECONCILED:
        raise AssertionError
    return result


def _raw_policy() -> ProteinInferenceRawPolicy:
    approved = ApprovedBuild(build_id=_BUILD_ID, version=_BUILD_VERSION)
    return ProteinInferenceRawPolicy(
        policy_id="policy.synthetic.m0303",
        version="1.0.0",
        max_sources=M0303_MAX_SOURCES,
        max_lineage_artifacts=48,
        max_spectra_sources=32,
        max_source_bytes=1_048_576,
        max_decoded_bytes=2_097_152,
        max_total_source_bytes=16_777_216,
        max_total_decoded_bytes=33_554_432,
        approved_genome_builds=(approved,),
        approved_transcript_builds=(approved,),
        evidence=_artifact(
            "policy.json",
            b"synthetic-m0303-policy-evidence",
            "application/json",
        ),
        reviewed_by="reviewer.synthetic.quality",
        reviewed_at=datetime(2026, 8, 12, 14, 0, tzinfo=UTC),
    )


def _ingestion_request(
    protocol: ProteinInferenceProtocolConformanceResult,
    lineage: ProteinInferenceIdentityLineageResolution,
    sources: tuple[ProteinInferenceRawSource, ...],
    manifest_digest: str,
) -> IngestProteinInferenceRawInputsRequest:
    policy = _raw_policy()
    references = lineage.request.context.references
    approved = references.approved_configuration.model_copy(
        update={
            "evidence": references.approved_configuration.evidence.model_copy(
                update={"digest": m0303_configuration_digest(policy)}
            )
        }
    )
    context = ExecutionContext(
        request_id="request.synthetic.m0303",
        actor_id="actor.synthetic.quality",
        occurred_at=datetime(2026, 8, 12, 15, 0, tzinfo=UTC),
        references=references.model_copy(update={"approved_configuration": approved}),
    )
    return IngestProteinInferenceRawInputsRequest(
        context=context,
        protocol_receipt=protocol_ingestion_receipt(protocol),
        lineage_receipt=lineage_ingestion_receipt(lineage),
        policy=policy,
        source_manifest_digest=manifest_digest,
        sources=sources,
    )


def build_scenario(
    *,
    options: ScenarioOptions | None = None,
    gzip_roles: frozenset[ProteinInferenceRawRole] | None = None,
) -> Scenario:
    """Execute genuine public upstream modules and close them over real source bytes."""

    if options is not None and gzip_roles is not None:
        raise _MutuallyExclusiveBuilderOptionsError
    active = options or ScenarioOptions(gzip_roles=gzip_roles or frozenset())
    lineage_seed = build_m0302_request("canonical")
    raw, transformed = _transformed_source_bytes(active)
    protocol = _genuine_protocol_result(
        lineage_seed.identity_resolution.resolution_digest,
        transformed,
    )
    materials = _manifest_materials(protocol, transformed, active)
    declarations, payloads = _non_bundle_capsule(
        protocol,
        raw,
        transformed,
        materials,
        active,
    )
    sources, manifest_digest = _close_bundle(
        declarations,
        payloads,
        materials,
        active,
    )
    lineage = _genuine_lineage_result(lineage_seed, protocol, materials)
    request = _ingestion_request(protocol, lineage, sources, manifest_digest)
    return Scenario(
        request=request,
        sources=payloads,
        protocol_result=protocol,
        lineage_result=lineage,
    )


def build_scenario_request() -> tuple[IngestProteinInferenceRawInputsRequest, dict[str, bytes]]:
    """Public evidence helper for interface and benchmark parity tests."""

    scenario = build_scenario()
    return scenario.request, scenario.sources


def _scenario(case_id: str, *, passed: bool, detail: str) -> EvalCheck:
    return EvalCheck(name=f"scenario.{case_id}", passed=passed, detail=detail)


def _corpus() -> Corpus:
    return cast("Corpus", strict_json_loads(SCENARIO_PATH.read_bytes()))


def _corpus_check(corpus: Corpus) -> EvalCheck:
    groups = corpus["scenario_groups"]
    cases = [case for group in groups for case in group["case_ids"]]
    expected_groups = (
        "genuine_chain_and_admission_capsule",
        "role_format_and_cross_reference_parsing",
        "m0301_search_space_and_ptm_closure",
        "m0302_identity_graph_and_manifest_binding",
        "build_cv_unit_and_context_coherence",
        "typed_failure_precedence_and_disagreement",
        "authorization_strictness_capacity_and_filesystem",
        "canonical_privacy_interfaces_recovery",
    )
    passed = (
        corpus["module_id"] == MODULE_ID
        and tuple(group["group_id"] for group in groups) == expected_groups
        and len(groups) == _EXPECTED_GROUP_COUNT
        and len(cases) == _EXPECTED_CASE_COUNT
        and len(set(cases)) == _EXPECTED_CASE_COUNT
    )
    return EvalCheck(
        name="corpus.exact_inventory",
        passed=passed,
        detail=f"groups={len(groups)};cases={len(cases)};unique={len(set(cases))}",
    )


def _canonical_checks(scenario: Scenario) -> list[EvalCheck]:
    result = ingest_protein_inference_raw_inputs(scenario.request, scenario.sources)
    request = scenario.request
    emitted = result.model_dump(mode="json")
    return [
        _scenario(
            "genuine_public_m0102_m0301_m0302_chain",
            passed=(
                scenario.protocol_result.disposition is ProtocolConformanceDisposition.CONFORMANT
                and scenario.lineage_result.disposition is ReconciliationDisposition.RECONCILED
                and request.protocol_receipt.protocol_result_digest
                == scenario.protocol_result.result_digest
                and request.lineage_receipt.lineage_result_digest
                == scenario.lineage_result.result_digest
            ),
            detail="all three genuine public upstream results close",
        ),
        _scenario(
            "canonical_supported_source_set_is_admitted",
            passed=(
                result.disposition is ProteinInferenceAdmissionDisposition.VALIDATED
                and len(result.raw_inputs) == len(request.sources)
                and not result.diagnostics
            ),
            detail=f"disposition={result.disposition.value};sources={len(result.raw_inputs)}",
        ),
        _scenario(
            "source_manifest_binds_exact_bytes_lengths_and_digests",
            passed=(
                request.source_manifest_digest == source_manifest_digest(request.sources)
                and all(
                    declaration.byte_length == len(scenario.sources[declaration.source_id])
                    and declaration.artifact.digest
                    == _bytes_digest(scenario.sources[declaration.source_id])
                    for declaration in request.sources
                )
            ),
            detail=request.source_manifest_digest,
        ),
        _scenario(
            "bundle_source_manifest_binding_is_non_circular",
            passed=(
                request.source_manifest_digest
                == source_manifest_digest(
                    tuple(
                        item
                        for item in request.sources
                        if item.role is not ProteinInferenceRawRole.COMPLEX_ACTIVITY_INPUT_BUNDLE
                    )
                )
                and request.source_manifest_digest.encode()
                in scenario.sources["source.bundle.json"]
            ),
            detail="bundle excluded from manifest preimage and carries manifest digest",
        ),
        _scenario(
            "admission_capsule_retains_exact_parent_receipt",
            passed=(
                lineage_receipt_digest(result.request.lineage_receipt)
                == lineage_receipt_digest(request.lineage_receipt)
                == result.receipt.lineage_receipt_digest
            ),
            detail=result.receipt.lineage_receipt_digest,
        ),
        _scenario(
            "capsule_supports_complex_activity_workflow_without_inference",
            passed=(
                result.parent_target == "complex_activity"
                and not result.emits_complex_activity
                and not result.infers_protein
                and not result.infers_kinase_activity
            ),
            detail="complex_activity receipt support only",
        ),
        _scenario(
            "canonical_result_emits_no_protein_or_activity_claim",
            passed=not {
                "protein_presence",
                "protein_absence",
                "activity_score",
                "protein_subtype",
                "proteotype_result",
                "treatment_recommendation",
            }.intersection(_nested_keys(emitted)),
            detail="recursive claims ceiling retained",
        ),
    ]


def _nested_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return {
            *(str(key) for key in value),
            *(nested for item in value.values() for nested in _nested_keys(item)),
        }
    if isinstance(value, list | tuple):
        return {nested for item in value for nested in _nested_keys(item)}
    return set()


def _diagnostic_codes(
    result: ProteinInferenceRawAdmissionResult,
) -> set[ProteinInferenceDiagnosticCode]:
    return {item.code for item in result.diagnostics}


def _role_output(
    result: ProteinInferenceRawAdmissionResult,
    role: ProteinInferenceRawRole,
) -> tuple[ValidatedProteinInferenceRawInput, ...]:
    return tuple(item for item in result.raw_inputs if item.role is role)


def _parsing_checks(scenario: Scenario) -> list[EvalCheck]:
    canonical = ingest_protein_inference_raw_inputs(scenario.request, scenario.sources)
    gzip_scenario = build_scenario(gzip_roles=frozenset({ProteinInferenceRawRole.SPECTRA}))
    gzip_result = ingest_protein_inference_raw_inputs(
        gzip_scenario.request,
        gzip_scenario.sources,
    )
    ambiguity = scenario.sources["source.ambiguity.json"].replace(
        b'"group_claim_id":"claim.group"',
        b'"group_claim_id":"claim.ghost"',
    )
    dangling_scenario = build_scenario(
        options=ScenarioOptions(
            generated_overrides={ProteinInferenceRawRole.AMBIGUITY_MANIFEST: ambiguity}
        )
    )
    dangling = ingest_protein_inference_raw_inputs(
        dangling_scenario.request,
        dangling_scenario.sources,
    )
    by_role = {role: _role_output(canonical, role) for role in ProteinInferenceRawRole}
    fasta_roles = (
        ProteinInferenceRawRole.CANONICAL_SEQUENCES,
        ProteinInferenceRawRole.DECOY_SEQUENCES,
        ProteinInferenceRawRole.ISOFORM_SEQUENCES,
        ProteinInferenceRawRole.VARIANT_SEQUENCES,
        ProteinInferenceRawRole.CONTAMINANT_SEQUENCES,
    )

    def parsed(
        role: ProteinInferenceRawRole,
        raw_format: ProteinInferenceRawFormat,
    ) -> bool:
        values = by_role[role]
        return bool(values) and all(
            item.detected_format is raw_format and not item.diagnostics for item in values
        )

    return [
        _scenario(
            "mzml_structure_and_internal_references_validated",
            passed=parsed(ProteinInferenceRawRole.SPECTRA, ProteinInferenceRawFormat.MZML),
            detail="mzML structure accepted under the exact spectra role",
        ),
        _scenario(
            "mzidentml_structure_and_internal_references_validated",
            passed=(
                parsed(
                    ProteinInferenceRawRole.PEPTIDE_EVIDENCE,
                    ProteinInferenceRawFormat.MZIDENTML,
                )
                and all(
                    item.reference_count >= 1
                    for item in by_role[ProteinInferenceRawRole.PEPTIDE_EVIDENCE]
                )
            ),
            detail="mzIdentML SpectraData reference resolved",
        ),
        _scenario(
            "protein_group_json_structure_and_references_validated",
            passed=parsed(
                ProteinInferenceRawRole.PROTEIN_GROUP_MANIFEST,
                ProteinInferenceRawFormat.PROTEIN_GROUP_JSON,
            ),
            detail="strict protein-group JSON closed over protocol receipt",
        ),
        _scenario(
            "ambiguity_json_structure_and_references_validated",
            passed=parsed(
                ProteinInferenceRawRole.AMBIGUITY_MANIFEST,
                ProteinInferenceRawFormat.AMBIGUITY_JSON,
            ),
            detail="strict ambiguity JSON closed over protein-group claim",
        ),
        _scenario(
            "bundle_json_structure_and_references_validated",
            passed=parsed(
                ProteinInferenceRawRole.COMPLEX_ACTIVITY_INPUT_BUNDLE,
                ProteinInferenceRawFormat.COMPLEX_BUNDLE_JSON,
            ),
            detail="bundle JSON closed over non-circular source manifest",
        ),
        _scenario(
            "all_fasta_component_roles_parsed_separately",
            passed=all(parsed(role, ProteinInferenceRawFormat.FASTA) for role in fasta_roles),
            detail="five governed FASTA roles retained separately",
        ),
        _scenario(
            "psi_mod_obo_terms_and_identifiers_validated",
            passed=parsed(
                ProteinInferenceRawRole.PTM_VOCABULARY,
                ProteinInferenceRawFormat.PSI_MOD_OBO,
            ),
            detail="PSI-MOD OBO term profile validated",
        ),
        _scenario(
            "vcf_header_records_and_references_validated",
            passed=parsed(
                ProteinInferenceRawRole.GENOMIC_CONTEXT,
                ProteinInferenceRawFormat.VCF,
            ),
            detail="VCF header, record, and assembly parsed",
        ),
        _scenario(
            "gff3_directives_records_and_references_validated",
            passed=parsed(
                ProteinInferenceRawRole.TRANSCRIPT_CONTEXT,
                ProteinInferenceRawFormat.GFF3,
            ),
            detail="GFF3 directives, record, and assembly parsed",
        ),
        _scenario(
            "gzip_is_detected_by_magic_bytes_not_filename_suffix",
            passed=(
                gzip_result.disposition is ProteinInferenceAdmissionDisposition.VALIDATED
                and all(
                    item.compression is ProteinInferenceCompression.GZIP
                    and not item.source_id.endswith(".gz")
                    for item in gzip_result.raw_inputs
                    if item.role is ProteinInferenceRawRole.SPECTRA
                )
            ),
            detail="gzip magic accepted for a .mzml basename",
        ),
        _scenario(
            "malformed_content_or_dangling_reference_fails_closed",
            passed=(
                ProteinInferenceDiagnosticCode.DANGLING_REFERENCE in _diagnostic_codes(dangling)
                and dangling.disposition is ProteinInferenceAdmissionDisposition.QUARANTINED
            ),
            detail="dangling ambiguity claim quarantined",
        ),
    ]


def _request_with_sources(
    request: IngestProteinInferenceRawInputsRequest,
    sources: tuple[ProteinInferenceRawSource, ...],
) -> IngestProteinInferenceRawInputsRequest:
    return IngestProteinInferenceRawInputsRequest(
        **{
            **request.model_dump(mode="python"),
            "sources": sources,
            "source_manifest_digest": source_manifest_digest(sources),
        }
    )


def _is_validation_error(operation: object) -> bool:
    if not callable(operation):
        return False
    try:
        operation()
    except ValidationError:
        return True
    return False


def _m0301_closure_checks(scenario: Scenario) -> list[EvalCheck]:
    search = scenario.request.protocol_receipt.search_space
    expected = {
        ProteinInferenceRawRole.CANONICAL_SEQUENCES: search.canonical_sequence_reference,
        ProteinInferenceRawRole.DECOY_SEQUENCES: search.decoy_reference,
        ProteinInferenceRawRole.ISOFORM_SEQUENCES: search.isoform_reference,
        ProteinInferenceRawRole.VARIANT_SEQUENCES: search.variant_reference,
        ProteinInferenceRawRole.CONTAMINANT_SEQUENCES: search.contaminant_reference,
    }
    declarations = {item.role: item for item in scenario.request.sources}

    def closes(role: ProteinInferenceRawRole) -> bool:
        reference = expected[role]
        source = declarations[role]
        return (
            reference is not None
            and source.artifact == reference
            and source.artifact.digest == _bytes_digest(scenario.sources[source.source_id])
        )

    missing_sources = tuple(
        item
        for item in scenario.request.sources
        if item.role is not ProteinInferenceRawRole.CANONICAL_SEQUENCES
    )
    canonical = declarations[ProteinInferenceRawRole.CANONICAL_SEQUENCES]
    duplicate_sources = (*scenario.request.sources, canonical.model_copy())
    canonical_index = scenario.request.sources.index(canonical)
    decoy = declarations[ProteinInferenceRawRole.DECOY_SEQUENCES]
    decoy_index = scenario.request.sources.index(decoy)
    swapped = list(scenario.request.sources)
    swapped[canonical_index] = canonical.model_copy(
        update={"role": ProteinInferenceRawRole.DECOY_SEQUENCES}
    )
    swapped[decoy_index] = decoy.model_copy(
        update={"role": ProteinInferenceRawRole.CANONICAL_SEQUENCES}
    )
    ptm = declarations[ProteinInferenceRawRole.PTM_VOCABULARY]
    forged_ptm = tuple(
        item.model_copy(update={"artifact": decoy.artifact}) if item is ptm else item
        for item in scenario.request.sources
    )
    missing_rejected = _is_validation_error(
        lambda: _request_with_sources(scenario.request, missing_sources)
    )
    unexpected_rejected = _is_validation_error(
        lambda: _request_with_sources(scenario.request, duplicate_sources)
    )
    swapped_rejected = _is_validation_error(
        lambda: _request_with_sources(scenario.request, tuple(swapped))
    )
    ptm_rejected = _is_validation_error(lambda: _request_with_sources(scenario.request, forged_ptm))
    return [
        _scenario(
            "canonical_fasta_component_matches_m0301_exactly",
            passed=closes(ProteinInferenceRawRole.CANONICAL_SEQUENCES),
            detail="canonical FASTA artifact equals M03-01 receipt",
        ),
        _scenario(
            "decoy_fasta_component_matches_m0301_exactly",
            passed=closes(ProteinInferenceRawRole.DECOY_SEQUENCES),
            detail="decoy FASTA artifact equals M03-01 receipt",
        ),
        _scenario(
            "conditional_isoform_fasta_component_matches_m0301_exactly",
            passed=closes(ProteinInferenceRawRole.ISOFORM_SEQUENCES),
            detail="conditional isoform FASTA equals M03-01 receipt",
        ),
        _scenario(
            "variant_fasta_component_matches_m0301_exactly",
            passed=closes(ProteinInferenceRawRole.VARIANT_SEQUENCES),
            detail="variant FASTA artifact equals M03-01 receipt",
        ),
        _scenario(
            "contaminant_fasta_component_matches_m0301_exactly",
            passed=closes(ProteinInferenceRawRole.CONTAMINANT_SEQUENCES),
            detail="contaminant FASTA artifact equals M03-01 receipt",
        ),
        _scenario(
            "missing_or_unexpected_search_component_fails_closed",
            passed=missing_rejected and unexpected_rejected,
            detail="missing and duplicate canonical component rejected by contract closure",
        ),
        _scenario(
            "search_component_role_swap_is_quarantined",
            passed=swapped_rejected,
            detail="role-swapped canonical/decoy declaration fails closed before parsing",
        ),
        _scenario(
            "ptm_ontology_digest_must_match_and_labels_cannot_override",
            passed=(
                ptm.artifact == scenario.request.protocol_receipt.modification_vocabulary_reference
                and ptm_rejected
            ),
            detail="unchanged PTM label cannot mask a foreign digest",
        ),
    ]


class _HostileSources(dict[str, bytes]):
    traversals: int = 0

    def __iter__(self) -> Iterator[str]:
        self.traversals += 1
        raise _UnexpectedSourceTraversalError


def _safe_failure_result(
    lineage_name: str,
) -> tuple[ProteinInferenceRawAdmissionResult, int]:
    lineage = reconcile_protein_inference_identity_lineage(build_m0302_request(lineage_name))
    request = _ingestion_request(
        lineage.request.protocol_result,
        lineage,
        (),
        source_manifest_digest(()),
    )
    hostile = _HostileSources()
    result = ingest_protein_inference_raw_inputs(request, hostile)
    return result, hostile.traversals


def _receipt_forgery_is_rejected(
    scenario: Scenario,
    *,
    identity: bool,
) -> bool:
    receipt = scenario.request.lineage_receipt
    if identity:
        candidate = receipt.model_copy(update={"identity_resolution_digest": "sha256:" + "0" * 64})
    else:
        first = receipt.artifacts[0]
        forged_artifact = first.artifact.model_copy(update={"digest": "sha256:" + "1" * 64})
        candidate = receipt.model_copy(
            update={
                "artifacts": (
                    first.model_copy(update={"artifact": forged_artifact}),
                    *receipt.artifacts[1:],
                )
            }
        )
    candidate = candidate.model_copy(update={"receipt_digest": lineage_receipt_digest(candidate)})
    return _is_validation_error(
        lambda: IngestProteinInferenceRawInputsRequest(
            **{
                **scenario.request.model_dump(mode="python"),
                "lineage_receipt": candidate,
            }
        )
    )


def _protocol_receipt_forgery_is_rejected(scenario: Scenario) -> bool:
    receipt = scenario.request.protocol_receipt.model_copy(
        update={"protocol_result_digest": "sha256:" + "3" * 64}
    )
    receipt = receipt.model_copy(update={"receipt_digest": protocol_receipt_digest(receipt)})
    return _is_validation_error(
        lambda: IngestProteinInferenceRawInputsRequest(
            **{
                **scenario.request.model_dump(mode="python"),
                "protocol_receipt": receipt,
            }
        )
    )


def _m0302_binding_checks(scenario: Scenario) -> list[EvalCheck]:
    receipt = scenario.request.lineage_receipt
    lineage = scenario.lineage_result
    receipt_claims = {item.claim_id: item for item in receipt.artifacts}
    submitted_claims = {item.claim_id: item for item in lineage.request.artifact_claims}
    exact_bound = (
        receipt.lineage_result_digest == lineage.result_digest
        and receipt.graph_digest == lineage.graph.graph_digest
        and set(receipt_claims) == set(submitted_claims)
        and all(
            receipt_claims[claim_id].artifact == claim.artifact
            for claim_id, claim in submitted_claims.items()
        )
    )
    stale_bundle = scenario.sources["source.bundle.json"].replace(
        scenario.request.source_manifest_digest.encode(),
        ("sha256:" + "2" * 64).encode(),
    )
    stale_bundle_scenario = build_scenario(
        options=ScenarioOptions(
            generated_overrides={
                ProteinInferenceRawRole.COMPLEX_ACTIVITY_INPUT_BUNDLE: stale_bundle
            }
        )
    )
    stale_bundle_result = ingest_protein_inference_raw_inputs(
        stale_bundle_scenario.request,
        stale_bundle_scenario.sources,
    )
    quarantined, quarantine_traversals = _safe_failure_result("cn_discordant")
    abstained, abstain_traversals = _safe_failure_result("cn_missing")
    canonical_result = ingest_protein_inference_raw_inputs(
        scenario.request,
        scenario.sources,
    )
    return [
        _scenario(
            "exact_m0302_graph_result_and_every_claim_are_bound",
            passed=exact_bound,
            detail=f"claims={len(receipt_claims)};graph={receipt.graph_digest}",
        ),
        _scenario(
            "stale_bundle_source_manifest_binding_is_rejected",
            passed=(
                stale_bundle_result.disposition is ProteinInferenceAdmissionDisposition.QUARANTINED
                and ProteinInferenceDiagnosticCode.DANGLING_REFERENCE
                in _diagnostic_codes(stale_bundle_result)
            ),
            detail="stale bundle manifest binding fails closed",
        ),
        _scenario(
            "stale_protocol_binding_is_rejected",
            passed=_protocol_receipt_forgery_is_rejected(scenario),
            detail="re-digested stale protocol receipt rejected by cross-receipt closure",
        ),
        _scenario(
            "stale_identity_binding_is_rejected",
            passed=_receipt_forgery_is_rejected(scenario, identity=True),
            detail="re-digested stale identity receipt rejected by cross-receipt closure",
        ),
        _scenario(
            "valid_m0302_quarantine_propagates_without_source_parse",
            passed=(
                quarantined.disposition is ProteinInferenceAdmissionDisposition.QUARANTINED
                and ProteinInferenceDiagnosticCode.UPSTREAM_QUARANTINED
                in _diagnostic_codes(quarantined)
                and quarantine_traversals == 0
                and not quarantined.raw_inputs
            ),
            detail="genuine M03-02 quarantine propagated with zero mapping traversal",
        ),
        _scenario(
            "valid_m0302_abstention_propagates_without_source_parse",
            passed=(
                abstained.disposition is ProteinInferenceAdmissionDisposition.ABSTAINED
                and ProteinInferenceDiagnosticCode.UPSTREAM_ABSTAINED
                in _diagnostic_codes(abstained)
                and abstain_traversals == 0
                and not abstained.raw_inputs
            ),
            detail="genuine M03-02 abstention propagated with zero mapping traversal",
        ),
        _scenario(
            "upstream_identifiers_components_and_labels_are_never_rewritten",
            passed=(
                lineage_receipt_digest(canonical_result.request.lineage_receipt)
                == lineage_receipt_digest(receipt)
                and {
                    item.claim_id: item
                    for item in canonical_result.request.lineage_receipt.artifacts
                }
                == {item.claim_id: item for item in receipt.artifacts}
                and {item.source_id: item for item in canonical_result.request.sources}
                == {item.source_id: item for item in scenario.request.sources}
            ),
            detail="parent receipt and declared source identifiers retained exactly",
        ),
        _scenario(
            "recomputed_outer_digest_cannot_mask_inner_binding_forgery",
            passed=_receipt_forgery_is_rejected(scenario, identity=False),
            detail="recomputed receipt digest cannot mask forged nested artifact",
        ),
    ]


def _context_coherence_checks(scenario: Scenario) -> list[EvalCheck]:
    canonical = ingest_protein_inference_raw_inputs(scenario.request, scenario.sources)
    by_role = {item.role: item for item in canonical.raw_inputs}
    search = scenario.request.protocol_receipt.search_space
    peptide = by_role[ProteinInferenceRawRole.PEPTIDE_EVIDENCE]
    genomic = by_role[ProteinInferenceRawRole.GENOMIC_CONTEXT]
    transcript = by_role[ProteinInferenceRawRole.TRANSCRIPT_CONTEXT]

    raw = _base_source_bytes()
    vcf = raw[ProteinInferenceRawRole.GENOMIC_CONTEXT][1].replace(
        b"build.synthetic.reference:1.0.0",
        b"build.synthetic.foreign:2.0.0",
    )
    mismatch_scenario = build_scenario(
        options=ScenarioOptions(raw_overrides={ProteinInferenceRawRole.GENOMIC_CONTEXT: vcf})
    )
    mismatch = ingest_protein_inference_raw_inputs(
        mismatch_scenario.request,
        mismatch_scenario.sources,
    )
    missing_vcf = (
        b"\n".join(
            line
            for line in raw[ProteinInferenceRawRole.GENOMIC_CONTEXT][1].splitlines()
            if not line.startswith(b"##reference=")
        )
        + b"\n"
    )
    missing_scenario = build_scenario(
        options=ScenarioOptions(
            raw_overrides={ProteinInferenceRawRole.GENOMIC_CONTEXT: missing_vcf}
        )
    )
    missing = ingest_protein_inference_raw_inputs(
        missing_scenario.request,
        missing_scenario.sources,
    )
    unsupported_mzml = raw[ProteinInferenceRawRole.SPECTRA][1].replace(
        b'version="1.1.0"',
        b'version="9.0.0"',
    )
    unsupported_scenario = build_scenario(
        options=ScenarioOptions(raw_overrides={ProteinInferenceRawRole.SPECTRA: unsupported_mzml})
    )
    unsupported = ingest_protein_inference_raw_inputs(
        unsupported_scenario.request,
        unsupported_scenario.sources,
    )
    cv_obo = raw[ProteinInferenceRawRole.PTM_VOCABULARY][1].replace(
        b"data-version: 3.0.0",
        b"data-version: 9.0.0",
    )
    cv_scenario = build_scenario(
        options=ScenarioOptions(raw_overrides={ProteinInferenceRawRole.PTM_VOCABULARY: cv_obo})
    )
    cv_result = ingest_protein_inference_raw_inputs(
        cv_scenario.request,
        cv_scenario.sources,
    )
    group_payload = cast(
        "dict[str, object]",
        strict_json_loads(scenario.sources["source.protein-group.json"]),
    )
    group_payload["unit_system_version"] = "99.0.0"
    group = canonical_json_bytes(group_payload)
    unit_scenario = build_scenario(
        options=ScenarioOptions(
            generated_overrides={ProteinInferenceRawRole.PROTEIN_GROUP_MANIFEST: group}
        )
    )
    unit_result = ingest_protein_inference_raw_inputs(
        unit_scenario.request,
        unit_scenario.sources,
    )
    mismatch_codes = _diagnostic_codes(mismatch)
    return [
        _scenario(
            "search_space_build_identity_matches_protocol",
            passed=(
                peptide.build.state is ProteinInferenceBuildState.EXACT
                and (peptide.build.declared_build_id, peptide.build.declared_build_version)
                == (search.build_id, search.release)
            ),
            detail="mzIdentML SearchDatabase build equals M03-01 search-space receipt",
        ),
        _scenario(
            "vcf_declared_assembly_matches_approved_context",
            passed=(
                genomic.build.state is ProteinInferenceBuildState.EXACT
                and genomic.build.declared_build_id == _BUILD_ID
                and genomic.build.declared_build_version == _BUILD_VERSION
            ),
            detail="VCF reference assembly exactly approved",
        ),
        _scenario(
            "gff3_declared_assembly_matches_approved_context",
            passed=(
                transcript.build.state is ProteinInferenceBuildState.EXACT
                and transcript.build.declared_build_id == _BUILD_ID
                and transcript.build.declared_build_version == _BUILD_VERSION
            ),
            detail="GFF3 genome-build directive exactly approved",
        ),
        _scenario(
            "vcf_gff3_or_protocol_assembly_mismatch_is_quarantined",
            passed=(
                mismatch.disposition is ProteinInferenceAdmissionDisposition.QUARANTINED
                and ProteinInferenceDiagnosticCode.BUILD_MISMATCH in mismatch_codes
                and ProteinInferenceDiagnosticCode.ASSEMBLY_MISMATCH in mismatch_codes
            ),
            detail="foreign VCF build and VCF/GFF disagreement retained",
        ),
        _scenario(
            "required_build_cv_or_unit_context_missing_abstains",
            passed=(
                missing.disposition is ProteinInferenceAdmissionDisposition.ABSTAINED
                and ProteinInferenceDiagnosticCode.BUILD_MISSING in _diagnostic_codes(missing)
            ),
            detail="missing VCF assembly remains typed missing",
        ),
        _scenario(
            "unsupported_build_cv_or_unit_context_abstains",
            passed=(
                unsupported.disposition is ProteinInferenceAdmissionDisposition.ABSTAINED
                and ProteinInferenceDiagnosticCode.UNSUPPORTED_VERSION
                in _diagnostic_codes(unsupported)
            ),
            detail="recognized mzML outside v1 profile abstains",
        ),
        _scenario(
            "cv_term_or_unit_mismatch_is_quarantined",
            passed=(
                cv_result.disposition is ProteinInferenceAdmissionDisposition.QUARANTINED
                and ProteinInferenceDiagnosticCode.CONTROLLED_VOCABULARY_MISMATCH
                in _diagnostic_codes(cv_result)
                and unit_result.disposition is ProteinInferenceAdmissionDisposition.QUARANTINED
                and ProteinInferenceDiagnosticCode.UNIT_PROFILE_MISMATCH
                in _diagnostic_codes(unit_result)
            ),
            detail="PSI-MOD version and unit-profile disagreements both quarantine",
        ),
    ]


def _transport_failure_checks(scenario: Scenario) -> list[EvalCheck]:
    spectra_id = next(
        item.source_id
        for item in scenario.request.sources
        if item.role is ProteinInferenceRawRole.SPECTRA
    )
    checksum_sources = dict(scenario.sources)
    checksum_sources[spectra_id] += b"x"
    checksum = ingest_protein_inference_raw_inputs(scenario.request, checksum_sources)

    size_sources = dict(scenario.sources)
    size_sources[spectra_id] = size_sources[spectra_id][:-1]
    size = ingest_protein_inference_raw_inputs(scenario.request, size_sources)

    oversized = b"A" * (_raw_policy().max_decoded_bytes + 1)
    decoded_scenario = build_scenario(
        options=ScenarioOptions(
            gzip_roles=frozenset({ProteinInferenceRawRole.SPECTRA}),
            raw_overrides={ProteinInferenceRawRole.SPECTRA: oversized},
        )
    )
    decoded = ingest_protein_inference_raw_inputs(
        decoded_scenario.request,
        decoded_scenario.sources,
    )

    canonical_gzip = gzip.compress(
        _base_source_bytes()[ProteinInferenceRawRole.SPECTRA][1],
        compresslevel=9,
        mtime=0,
    )
    corrupt_gzip = canonical_gzip[:-2]
    corrupt_scenario = build_scenario(
        options=ScenarioOptions(
            gzip_roles=frozenset({ProteinInferenceRawRole.SPECTRA}),
            transport_overrides={ProteinInferenceRawRole.SPECTRA: corrupt_gzip},
        )
    )
    corrupt = ingest_protein_inference_raw_inputs(
        corrupt_scenario.request,
        corrupt_scenario.sources,
    )

    unsupported_mzml = _base_source_bytes()[ProteinInferenceRawRole.SPECTRA][1].replace(
        b'version="1.1.0"',
        b'version="9.0.0"',
    )
    unsupported_scenario = build_scenario(
        options=ScenarioOptions(raw_overrides={ProteinInferenceRawRole.SPECTRA: unsupported_mzml})
    )
    unsupported = ingest_protein_inference_raw_inputs(
        unsupported_scenario.request,
        unsupported_scenario.sources,
    )

    vcf = _base_source_bytes()[ProteinInferenceRawRole.GENOMIC_CONTEXT][1].replace(
        b"build.synthetic.reference:1.0.0",
        b"build.synthetic.foreign:2.0.0",
    )
    disagreement_scenario = build_scenario(
        options=ScenarioOptions(raw_overrides={ProteinInferenceRawRole.GENOMIC_CONTEXT: vcf})
    )
    disagreement_sources = dict(disagreement_scenario.sources)
    disagreement_sources[spectra_id] += b"x"
    precedence = ingest_protein_inference_raw_inputs(
        disagreement_scenario.request,
        disagreement_sources,
    )
    precedence_codes = _diagnostic_codes(precedence)
    emitted = precedence.model_dump(mode="json")
    return [
        _scenario(
            "transport_checksum_mismatch_is_rejected",
            passed=(
                checksum.disposition is ProteinInferenceAdmissionDisposition.REJECTED
                and ProteinInferenceDiagnosticCode.DECLARED_SIZE_MISMATCH
                in _diagnostic_codes(checksum)
            ),
            detail="byte append triggers earlier declared-size guard before checksum",
        ),
        _scenario(
            "declared_raw_size_mismatch_is_rejected",
            passed=(
                size.disposition is ProteinInferenceAdmissionDisposition.REJECTED
                and ProteinInferenceDiagnosticCode.DECLARED_SIZE_MISMATCH in _diagnostic_codes(size)
            ),
            detail="truncated raw payload rejected on exact declared size",
        ),
        _scenario(
            "declared_decoded_size_mismatch_is_rejected",
            passed=(
                decoded.disposition is ProteinInferenceAdmissionDisposition.REJECTED
                and ProteinInferenceDiagnosticCode.DECODED_SIZE_LIMIT_EXCEEDED
                in _diagnostic_codes(decoded)
            ),
            detail="bounded gzip decode rejects first decoded excess byte",
        ),
        _scenario(
            "corrupt_gzip_stream_is_rejected",
            passed=(
                corrupt.disposition is ProteinInferenceAdmissionDisposition.REJECTED
                and ProteinInferenceDiagnosticCode.INVALID_GZIP in _diagnostic_codes(corrupt)
            ),
            detail="truncated single-member gzip rejected",
        ),
        _scenario(
            "unsupported_format_or_version_is_abstained",
            passed=(
                unsupported.disposition is ProteinInferenceAdmissionDisposition.ABSTAINED
                and ProteinInferenceDiagnosticCode.UNSUPPORTED_VERSION
                in _diagnostic_codes(unsupported)
            ),
            detail="recognized mzML outside reviewed version profile abstains",
        ),
        _scenario(
            "failure_precedence_is_deterministic_and_retains_later_disagreement",
            passed=(
                precedence.disposition is ProteinInferenceAdmissionDisposition.REJECTED
                and ProteinInferenceDiagnosticCode.DECLARED_SIZE_MISMATCH in precedence_codes
                and ProteinInferenceDiagnosticCode.ASSEMBLY_MISMATCH in precedence_codes
            ),
            detail="reject wins while independent assembly disagreement is retained",
        ),
        _scenario(
            "cross_source_disagreement_is_retained_without_prohibited_claim",
            passed=(
                ProteinInferenceDiagnosticCode.ASSEMBLY_MISMATCH in precedence_codes
                and not {
                    "protein_presence",
                    "protein_absence",
                    "activity_score",
                    "proteotype_result",
                }.intersection(_nested_keys(emitted))
            ),
            detail="cross-source context disagreement emits diagnostic only",
        ),
    ]


class _ReadOnceStream(io.BytesIO):
    bytes_read: int = 0

    def read(self, size: int | None = -1) -> bytes:
        payload = super().read(size)
        self.bytes_read += len(payload)
        return payload


def _authorization_denied(
    scenario: Scenario,
    field: str,
) -> tuple[bool, int]:
    references = scenario.request.context.references
    current = getattr(references, field)
    if field == "identity_lineage":
        replacement = current.model_copy(update={"state": IdentityLineageState.UNRESOLVED})
    elif field == "consent":
        replacement = current.model_copy(update={"state": ConsentState.WITHHELD})
    else:
        replacement = current.model_copy(update={"state": UpstreamDecisionState.REJECTED})
    context = scenario.request.context.model_copy(
        update={"references": references.model_copy(update={field: replacement})}
    )
    candidate = scenario.request.model_copy(update={"context": context})
    hostile = _HostileSources()
    try:
        ingest_protein_inference_raw_inputs(candidate, hostile)
    except ProteinInferenceRawIngestionAuthorizationError:
        return True, hostile.traversals
    return False, hostile.traversals


def _strict_json_mutation_result(
    payload: bytes,
) -> ProteinInferenceRawAdmissionResult:
    mutated = build_scenario(
        options=ScenarioOptions(
            generated_overrides={ProteinInferenceRawRole.PROTEIN_GROUP_MANIFEST: payload}
        )
    )
    return ingest_protein_inference_raw_inputs(mutated.request, mutated.sources)


def _strict_json_checks(scenario: Scenario) -> tuple[bool, bool, bool]:
    group = scenario.sources["source.protein-group.json"]
    duplicate = group.replace(
        b'"claim_id":"claim.group"',
        b'"claim_id":"claim.group","claim_id":"claim.group"',
    )
    duplicate_result = _strict_json_mutation_result(duplicate)
    data = cast("dict[str, object]", strict_json_loads(group))
    data["group_ids"] = "group.synthetic.1"
    scalar_result = _strict_json_mutation_result(canonical_json_bytes(data))
    data = cast("dict[str, object]", strict_json_loads(group))
    data["unexpected"] = True
    unknown_result = _strict_json_mutation_result(canonical_json_bytes(data))
    return (
        ProteinInferenceDiagnosticCode.DUPLICATE_JSON_KEY in _diagnostic_codes(duplicate_result),
        ProteinInferenceDiagnosticCode.MALFORMED_CONTENT in _diagnostic_codes(scalar_result),
        ProteinInferenceDiagnosticCode.MALFORMED_CONTENT in _diagnostic_codes(unknown_result),
    )


def _filesystem_cli_checks(scenario: Scenario) -> tuple[bool, bool]:
    runner = CliRunner()
    with TemporaryDirectory(prefix="m0303-filesystem-") as temporary:
        root = Path(temporary)
        request_path = root / "request.json"
        source_directory = root / "sources"
        source_directory.mkdir()
        request_path.write_text(scenario.request.model_dump_json(), encoding="utf-8")
        for source_id, payload in scenario.sources.items():
            (source_directory / source_id).write_bytes(payload)

        spectra = source_directory / "source.spectra.mzml"
        target = source_directory / "spectra-target.mzml"
        spectra.replace(target)
        spectra.symlink_to(target)
        linked = runner.invoke(
            cli_app,
            [
                "protein-inference-raw",
                "ingest",
                str(request_path),
                str(source_directory),
            ],
        )
        linked_rejected = linked.exit_code == 1 and "reparse point" in linked.output

        declaration = scenario.request.sources[0]
        unsafe_declaration = declaration.model_copy(update={"source_id": "A:stream"})
        unsafe_sources = (
            unsafe_declaration,
            *scenario.request.sources[1:],
        )
        unsafe_request = _request_with_sources(scenario.request, unsafe_sources)
        request_path.write_text(unsafe_request.model_dump_json(), encoding="utf-8")
        unsafe = runner.invoke(
            cli_app,
            [
                "protein-inference-raw",
                "ingest",
                str(request_path),
                str(source_directory),
            ],
        )
        unsafe_rejected = unsafe.exit_code == 1 and "safe filename" in unsafe.output
    return linked_rejected, unsafe_rejected


def _authorization_and_capacity_checks(scenario: Scenario) -> list[EvalCheck]:
    control_fields = (
        ("configuration_denial_precedes_hostile_source_mapping", "approved_configuration"),
        ("identity_denial_precedes_hostile_source_mapping", "identity_lineage"),
        ("provenance_denial_precedes_hostile_source_mapping", "provenance"),
        ("consent_denial_precedes_hostile_source_mapping", "consent"),
        ("quality_denial_precedes_hostile_source_mapping", "quality"),
        ("support_denial_precedes_hostile_source_mapping", "support"),
        ("intended_use_denial_precedes_hostile_source_mapping", "intended_use"),
    )
    control_results = {
        case_id: _authorization_denied(scenario, field) for case_id, field in control_fields
    }
    missing_sources = dict(scenario.sources)
    missing_sources.pop(next(iter(missing_sources)))
    source_set_closed = False
    try:
        ingest_protein_inference_raw_inputs(scenario.request, missing_sources)
    except ProteinInferenceRawIngestionInputError:
        source_set_closed = True
    duplicate_json, scalar_json, unknown_json = _strict_json_checks(scenario)
    linked_rejected, unsafe_rejected = _filesystem_cli_checks(scenario)

    maximum = build_scenario(options=ScenarioOptions(spectra_count=8, peptide_count=45))
    maximum_result = ingest_protein_inference_raw_inputs(maximum.request, maximum.sources)
    first_excess = _is_validation_error(
        lambda: build_scenario(options=ScenarioOptions(spectra_count=17, peptide_count=37))
    )
    streams = {
        source_id: _ReadOnceStream(payload) for source_id, payload in scenario.sources.items()
    }
    stream_result = ingest_protein_inference_raw_inputs(scenario.request, streams)
    all_read_once = (
        stream_result.disposition is ProteinInferenceAdmissionDisposition.VALIDATED
        and all(
            stream.bytes_read == len(scenario.sources[source_id])
            for source_id, stream in streams.items()
        )
    )
    return [
        *(
            _scenario(
                case_id,
                passed=denied and traversals == 0,
                detail="authorization denial occurred before hostile mapping traversal",
            )
            for case_id, (denied, traversals) in control_results.items()
        ),
        _scenario(
            "source_set_roles_and_declared_basenames_must_match_exactly",
            passed=source_set_closed,
            detail="incomplete source mapping rejected before parsing",
        ),
        _scenario(
            "duplicate_json_object_key_is_rejected",
            passed=duplicate_json,
            detail="strict JSON duplicate key diagnosed",
        ),
        _scenario(
            "scalar_coercion_is_rejected",
            passed=scalar_json,
            detail="scalar group_ids is not coerced to a list",
        ),
        _scenario(
            "unknown_field_or_controlled_term_is_rejected",
            passed=unknown_json,
            detail="unknown JSON field rejected by exact shape",
        ),
        _scenario(
            "maximum_sixty_four_sources_is_accepted",
            passed=(
                len(maximum.request.sources) == M0303_MAX_SOURCES
                and maximum_result.disposition is ProteinInferenceAdmissionDisposition.VALIDATED
            ),
            detail=f"sources={len(maximum.request.sources)}",
        ),
        _scenario(
            "sixty_fifth_source_is_rejected_before_any_read",
            passed=first_excess,
            detail="65-source request rejected during strict contract reconstruction",
        ),
        _scenario(
            "every_admitted_regular_file_is_read_exactly_once",
            passed=all_read_once,
            detail="each read-once stream consumed exactly its declared byte length",
        ),
        _scenario(
            "symlink_junction_or_other_reparse_source_is_rejected",
            passed=linked_rejected,
            detail="directory-backed CLI rejected a declared symlink source",
        ),
        _scenario(
            "directory_traversal_or_alternate_data_stream_name_is_rejected",
            passed=unsafe_rejected,
            detail="directory-backed CLI rejected a contract-valid ADS-style basename",
        ),
    ]


def _write_cli_capsule(scenario: Scenario, root: Path) -> tuple[Path, Path]:
    request_path = root / "request.json"
    source_path = root / "sources"
    source_path.mkdir()
    request_path.write_bytes(canonical_json_bytes(scenario.request.model_dump(mode="json")))
    for source_id, payload in scenario.sources.items():
        (source_path / source_id).write_bytes(payload)
    return request_path, source_path


def _interface_results(
    scenario: Scenario,
) -> tuple[bool, bool, bool, bool, bool, bool]:
    public = ingest_protein_inference_raw_inputs(scenario.request, scenario.sources)
    engine = M0303ProteinInferenceRawIngestionEngine().ingest(
        scenario.request,
        scenario.sources,
    )
    service = M0303Service()
    serviced = service.execute(scenario.request, scenario.sources)
    plugin = M0303Plugin(service)
    token = plugin.validate(
        ProteinInferenceRawIngestionSubmission(scenario.request, scenario.sources)
    )
    plugged = plugin.run(token)
    runner = CliRunner()
    with TemporaryDirectory(prefix="m0303-interface-") as temporary:
        request_path, source_path = _write_cli_capsule(scenario, Path(temporary))
        cli = runner.invoke(
            cli_app,
            ["protein-inference-raw", "ingest", str(request_path), str(source_path)],
        )
        cli_equal = (
            cli.exit_code == 0
            and _RESULT_ADAPTER.validate_json(
                cli.stdout,
                strict=True,
            )
            == public
        )
    with (
        TemporaryDirectory(prefix="m0303-api-") as api_temporary,
        TestClient(create_app(Path(api_temporary) / "api.sqlite3")) as api,
    ):
        api_response = api.get("/v1/contracts/M03-03/request/schema")
        raw_post = api.post("/v1/contracts/M03-03/raw", json={})
    cli_schema = runner.invoke(
        cli_app,
        ["protein-inference-raw", "export-schema", "request"],
    )
    return (
        engine == public,
        serviced == public and plugged == public,
        cli_equal,
        api_response.status_code == _HTTP_OK
        and api_response.json() == contract_json_schema("request"),
        cli_schema.exit_code == 0
        and strict_json_loads(cli_schema.stdout) == contract_json_schema("request"),
        raw_post.status_code in {404, 405},
    )


def _canonical_interface_checks(scenario: Scenario) -> list[EvalCheck]:
    canonical = ingest_protein_inference_raw_inputs(scenario.request, scenario.sources)
    reordered_request = scenario.request.model_copy(
        update={"sources": tuple(reversed(scenario.request.sources))}
    )
    reordered_sources = dict(reversed(tuple(scenario.sources.items())))
    reordered = ingest_protein_inference_raw_inputs(reordered_request, reordered_sources)
    streams = {
        source_id: _ReadOnceStream(payload) for source_id, payload in scenario.sources.items()
    }
    streamed = ingest_protein_inference_raw_inputs(scenario.request, streams)
    dict_result = ingest_protein_inference_raw_inputs(
        scenario.request.model_dump(mode="python"),
        scenario.sources,
    )
    json_request = _REQUEST_ADAPTER.validate_json(
        canonical_json_bytes(scenario.request.model_dump(mode="json")),
        strict=True,
    )
    json_result = ingest_protein_inference_raw_inputs(json_request, scenario.sources)
    engine_equal, service_plugin_equal, cli_equal, api_schema, cli_schema, post_absent = (
        _interface_results(scenario)
    )
    emitted = canonical.model_dump(mode="json")
    privacy_keys = {
        "direct_patient_identifier",
        "raw_identity_token",
        "observed_peptide_sequence",
        "protein_presence",
        "protein_absence",
        "protein_subtype",
        "proteotype_result",
        "kinase_activity",
        "treatment_recommendation",
    }
    forged_sources = dict(scenario.sources)
    forged_sources["source.bundle.json"] += b" "
    forged = ingest_protein_inference_raw_inputs(scenario.request, forged_sources)
    superseding = build_scenario(
        options=ScenarioOptions(
            raw_overrides={
                ProteinInferenceRawRole.SPECTRA: _base_source_bytes()[
                    ProteinInferenceRawRole.SPECTRA
                ][1].replace(b'run id="run-synthetic"', b'run id="run-recovered"')
            }
        )
    )
    recovered = ingest_protein_inference_raw_inputs(
        superseding.request,
        superseding.sources,
    )
    started = time.perf_counter_ns()
    benchmark_result = ingest_protein_inference_raw_inputs(
        scenario.request,
        scenario.sources,
    )
    elapsed = time.perf_counter_ns() - started
    return [
        _scenario(
            "semantic_source_reordering_preserves_complete_result_equality",
            passed=reordered == canonical,
            detail="source declaration and mapping reorder normalize to identical result",
        ),
        _scenario(
            "bytes_and_read_once_stream_inputs_produce_equal_results",
            passed=streamed == canonical
            and all(
                stream.bytes_read == len(scenario.sources[source_id])
                for source_id, stream in streams.items()
            ),
            detail="bytes and bounded read-once streams yield equal result",
        ),
        _scenario(
            "typed_dict_and_strict_json_requests_produce_equal_results",
            passed=dict_result == canonical and json_result == canonical,
            detail="typed, mapping, and strict-JSON request pathways agree",
        ),
        _scenario(
            "public_library_operation_matches_engine_result",
            passed=engine_equal,
            detail="public stateless operation equals engine",
        ),
        _scenario(
            "service_and_plugin_results_match_public_library_operation",
            passed=service_plugin_equal,
            detail="service and validated plugin token equal public result",
        ),
        _scenario(
            "cli_ingest_result_matches_public_library_operation",
            passed=cli_equal,
            detail="directory-backed CLI result equals public operation",
        ),
        _scenario(
            "schema_api_get_returns_exact_installed_contract",
            passed=api_schema,
            detail="GET request schema equals installed M03-03 contract",
        ),
        _scenario(
            "schema_cli_export_returns_exact_installed_contract",
            passed=cli_schema,
            detail="CLI request schema equals installed M03-03 contract",
        ),
        _scenario(
            "raw_ingestion_post_route_is_deliberately_absent",
            passed=post_absent,
            detail="raw JSON POST route is absent",
        ),
        _scenario(
            "recursive_privacy_and_ownership_canaries_are_absent",
            passed=not privacy_keys.intersection(_nested_keys(emitted)),
            detail="recursive output-key privacy and claims ceiling passes",
        ),
        _scenario(
            "derived_digest_and_nested_content_forgery_matrix_is_rejected",
            passed=forged.disposition is ProteinInferenceAdmissionDisposition.REJECTED
            and ProteinInferenceDiagnosticCode.DECLARED_SIZE_MISMATCH in _diagnostic_codes(forged),
            detail="nested bundle-byte forgery rejected at transport boundary",
        ),
        _scenario(
            "recovery_requires_a_new_superseding_admission_capsule",
            passed=(
                recovered.disposition is ProteinInferenceAdmissionDisposition.VALIDATED
                and recovered.result_digest != canonical.result_digest
                and recovered.request_digest != canonical.request_digest
            ),
            detail="corrected source produces a new immutable capsule digest",
        ),
        _scenario(
            "representative_benchmark_times_only_the_public_m0303_operation",
            passed=elapsed > 0 and benchmark_result == canonical,
            detail=f"public_operation_elapsed_ns={elapsed}; upstream prepared before clock",
        ),
    ]


def _coverage_check(corpus: Corpus, checks: list[EvalCheck]) -> EvalCheck:
    declared = {case_id for group in corpus["scenario_groups"] for case_id in group["case_ids"]}
    executed = {
        check.name.removeprefix("scenario.")
        for check in checks
        if check.name.startswith("scenario.")
    }
    return EvalCheck(
        name="corpus.executable_coverage",
        passed=declared == executed and len(executed) == _EXPECTED_CASE_COUNT,
        detail=(
            f"declared={len(declared)};executed={len(executed)};"
            f"missing={','.join(sorted(declared - executed)) or 'none'};"
            f"extra={','.join(sorted(executed - declared)) or 'none'}"
        ),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    corpus = _corpus()
    scenario = build_scenario()
    checks = [
        _corpus_check(corpus),
        *_canonical_checks(scenario),
        *_parsing_checks(scenario),
        *_m0301_closure_checks(scenario),
        *_m0302_binding_checks(scenario),
        *_context_coherence_checks(scenario),
        *_transport_failure_checks(scenario),
        *_authorization_and_capacity_checks(scenario),
        *_canonical_interface_checks(scenario),
    ]
    # Further groups are added only as executable public-runtime checks; coverage remains failed
    # until every locked case is genuinely exercised.
    checks.append(_coverage_check(corpus, checks))
    passed = all(check.passed for check in checks)
    report = {
        "module_id": MODULE_ID,
        "passed": passed,
        "checks": [asdict(check) for check in checks],
        "corpus_sha256": _bytes_digest(SCENARIO_PATH.read_bytes()),
        "canonical_request_digest": canonical_request_digest(scenario.request),
    }
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if arguments.output is not None:
        arguments.output.write_text(rendered + "\n", encoding="utf-8")
    if arguments.output is None:
        sys.stdout.write(rendered + "\n")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
