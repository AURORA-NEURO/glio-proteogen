"""Bounded, content-first structural parsers owned by M03-03.

The parser returns only format metadata, counts, governed bindings, and stable diagnostics. Raw
identifiers, accessions, sequences, measurements, and scientific values never leave this module.
"""

from __future__ import annotations

import hashlib
import re
import zlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from glio_proteogen.contracts.m01_03 import RawFormat, RawInputDisposition
from glio_proteogen.contracts.m03_03 import (
    IngestProteinInferenceRawInputsRequest,
    ProteinInferenceBuildBindingReceipt,
    ProteinInferenceBuildState,
    ProteinInferenceCompression,
    ProteinInferenceDiagnosticCode,
    ProteinInferenceParseDiagnostic,
    ProteinInferenceRawFormat,
    ProteinInferenceRawRole,
    ProteinInferenceRawSource,
    ValidatedProteinInferenceRawInput,
    diagnostic_for,
)
from glio_proteogen.kernel.strict_json import (
    StrictJsonError,
    StrictJsonErrorCode,
    strict_json_loads,
)
from glio_proteogen.modules.c01_preanalytic.m01_03_raw_ingestion import (
    IngestionLimits,
    parse_raw_input,
)

if TYPE_CHECKING:
    from xml.etree.ElementTree import Element

_GZIP_MAGIC: Final = b"\x1f\x8b"
_XML_FORBIDDEN: Final = re.compile(rb"<!\s*(?:DOCTYPE|ENTITY)\b", re.IGNORECASE)
_OBO_ID: Final = re.compile(r"^id: MOD:\d{5}$")
_OBO_VERSION: Final = re.compile(r"^data-version: (\d+\.\d+\.\d+)$")
_SEMVER: Final = re.compile(r"^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)$")
_SEMVER_PART_COUNT: Final = 3
_KEY_VALUE_PART_COUNT: Final = 2

_IDENTIFIER: Final = re.compile(r"^[a-zA-Z][a-zA-Z0-9._:-]{0,127}$")
_MZIDENT_ID: Final = re.compile(r"^[A-Za-z_][A-Za-z0-9._-]{0,127}$")
_FASTA_IDENTIFIER: Final = re.compile(r"^[^\s\x00-\x1f\x7f>]{1,255}$")


@dataclass(frozen=True, slots=True)
class ParsedSource:
    """Private parse facts required for cross-source closure."""

    output: ValidatedProteinInferenceRawInput
    metadata: dict[str, object]


class _ParseFailure(ValueError):  # noqa: N818 - private typed parser signal.
    code: ProteinInferenceDiagnosticCode = ProteinInferenceDiagnosticCode.MALFORMED_CONTENT


class _UnsupportedVersion(_ParseFailure):
    code = ProteinInferenceDiagnosticCode.UNSUPPORTED_VERSION


class _ForbiddenXml(_ParseFailure):
    code = ProteinInferenceDiagnosticCode.FORBIDDEN_XML_CONSTRUCT


class _DanglingReference(_ParseFailure):
    code = ProteinInferenceDiagnosticCode.DANGLING_REFERENCE


class _DuplicateJson(_ParseFailure):
    code = ProteinInferenceDiagnosticCode.DUPLICATE_JSON_KEY


def diagnostic(
    code: ProteinInferenceDiagnosticCode,
    source_ids: tuple[str, ...] = (),
) -> ProteinInferenceParseDiagnostic:
    """Build one deterministic privacy-safe diagnostic."""

    return diagnostic_for(code, tuple(sorted(set(source_ids))))


def parse_source(  # noqa: PLR0911 - typed transport failures are explicit outcomes.
    request: IngestProteinInferenceRawInputsRequest,
    declaration: ProteinInferenceRawSource,
    raw: bytes,
) -> ParsedSource:
    """Verify transport, decode once, and run the exact role-owned structural profile."""

    source_digest = f"sha256:{hashlib.sha256(raw).hexdigest()}"
    if len(raw) > request.policy.max_source_bytes:
        return _failure(
            declaration,
            source_digest,
            len(raw),
            ProteinInferenceDiagnosticCode.RAW_SIZE_LIMIT_EXCEEDED,
            source_limit=request.policy.max_source_bytes,
            decoded_limit=request.policy.max_decoded_bytes,
        )
    if len(raw) != declaration.byte_length:
        return _failure(
            declaration,
            source_digest,
            len(raw),
            ProteinInferenceDiagnosticCode.DECLARED_SIZE_MISMATCH,
            source_limit=request.policy.max_source_bytes,
            decoded_limit=request.policy.max_decoded_bytes,
        )
    if source_digest != declaration.artifact.digest:
        return _failure(
            declaration,
            source_digest,
            len(raw),
            ProteinInferenceDiagnosticCode.CHECKSUM_MISMATCH,
            source_limit=request.policy.max_source_bytes,
            decoded_limit=request.policy.max_decoded_bytes,
        )
    compression = (
        ProteinInferenceCompression.GZIP
        if raw.startswith(_GZIP_MAGIC)
        else ProteinInferenceCompression.NONE
    )
    if compression is not declaration.declared_compression:
        return _failure(
            declaration,
            source_digest,
            len(raw),
            ProteinInferenceDiagnosticCode.ROLE_FORMAT_MISMATCH,
            source_limit=request.policy.max_source_bytes,
            decoded_limit=request.policy.max_decoded_bytes,
            compression=compression,
        )
    try:
        decoded = _decode(raw, compression, request.policy.max_decoded_bytes)
    except _ParseFailure as error:
        return _failure(
            declaration,
            source_digest,
            len(raw),
            error.code,
            source_limit=request.policy.max_source_bytes,
            decoded_limit=request.policy.max_decoded_bytes,
            compression=compression,
        )
    decoded_digest = f"sha256:{hashlib.sha256(decoded).hexdigest()}"
    build = _build_receipt(declaration, None, None, request)
    try:
        version, records, references, metadata = _parse_profile(
            declaration,
            decoded,
            request,
        )
        declared_build = cast("str | None", metadata.get("build_id"))
        declared_version = cast("str | None", metadata.get("build_version"))
        build = _build_receipt(declaration, declared_build, declared_version, request)
        build_diagnostics = _build_diagnostics(declaration, build)
    except _ParseFailure as error:
        return _failure(
            declaration,
            source_digest,
            len(raw),
            error.code,
            source_limit=request.policy.max_source_bytes,
            decoded_limit=request.policy.max_decoded_bytes,
            compression=compression,
            decoded=decoded,
        )
    output = ValidatedProteinInferenceRawInput(
        source_id=declaration.source_id,
        role=declaration.role,
        source_digest=source_digest,
        source_size_bytes=len(raw),
        decoded_digest=decoded_digest,
        decoded_size_bytes=len(decoded),
        detected_format=declaration.declared_format,
        detected_version=_semantic_version(version),
        compression=compression,
        record_count=records,
        reference_count=references,
        build=build,
        diagnostics=build_diagnostics,
    )
    return ParsedSource(output=output, metadata=metadata)


def _decode(
    raw: bytes,
    compression: ProteinInferenceCompression,
    limit: int,
) -> bytes:
    if compression is ProteinInferenceCompression.NONE:
        if len(raw) > limit:
            failure = _ParseFailure()
            failure.code = ProteinInferenceDiagnosticCode.DECODED_SIZE_LIMIT_EXCEEDED
            raise failure
        return raw
    decompressor = zlib.decompressobj(wbits=16 + zlib.MAX_WBITS)
    try:
        decoded = decompressor.decompress(raw, limit + 1)
        if len(decoded) > limit or decompressor.unconsumed_tail:
            failure = _ParseFailure()
            failure.code = ProteinInferenceDiagnosticCode.DECODED_SIZE_LIMIT_EXCEEDED
            raise failure
        decoded += decompressor.flush(limit + 1 - len(decoded))
    except zlib.error:
        failure = _ParseFailure()
        failure.code = ProteinInferenceDiagnosticCode.INVALID_GZIP
        raise failure from None
    if len(decoded) > limit:
        failure = _ParseFailure()
        failure.code = ProteinInferenceDiagnosticCode.DECODED_SIZE_LIMIT_EXCEEDED
        raise failure
    if not decompressor.eof or decompressor.unused_data:
        failure = _ParseFailure()
        failure.code = ProteinInferenceDiagnosticCode.INVALID_GZIP
        raise failure
    return decoded


def _parse_profile(
    declaration: ProteinInferenceRawSource,
    payload: bytes,
    request: IngestProteinInferenceRawInputsRequest,
) -> tuple[str | None, int, int, dict[str, object]]:
    role = declaration.role
    if role in {
        ProteinInferenceRawRole.SPECTRA,
        ProteinInferenceRawRole.PEPTIDE_EVIDENCE,
        ProteinInferenceRawRole.CANONICAL_SEQUENCES,
        ProteinInferenceRawRole.DECOY_SEQUENCES,
        ProteinInferenceRawRole.ISOFORM_SEQUENCES,
        ProteinInferenceRawRole.VARIANT_SEQUENCES,
        ProteinInferenceRawRole.CONTAMINANT_SEQUENCES,
        ProteinInferenceRawRole.GENOMIC_CONTEXT,
        ProteinInferenceRawRole.TRANSCRIPT_CONTEXT,
    }:
        return _parse_shared_profile(declaration, payload, request)
    if role is ProteinInferenceRawRole.PTM_VOCABULARY:
        return _parse_obo(payload, request)
    return _parse_json_profile(declaration, payload, request)


def _parse_shared_profile(
    declaration: ProteinInferenceRawSource,
    payload: bytes,
    request: IngestProteinInferenceRawInputsRequest,
) -> tuple[str | None, int, int, dict[str, object]]:
    raw_format = {
        ProteinInferenceRawFormat.MZML: RawFormat.MZML,
        ProteinInferenceRawFormat.MZIDENTML: RawFormat.MZIDENTML,
        ProteinInferenceRawFormat.FASTA: RawFormat.FASTA,
        ProteinInferenceRawFormat.VCF: RawFormat.VCF,
        ProteinInferenceRawFormat.GFF3: RawFormat.GFF3,
    }[declaration.declared_format]
    parsed = parse_raw_input(
        payload,
        source_id=declaration.source_id,
        expected_sha256=f"sha256:{hashlib.sha256(payload).hexdigest()}",
        limits=IngestionLimits(
            max_source_bytes=request.policy.max_decoded_bytes,
            max_decoded_bytes=request.policy.max_decoded_bytes,
            max_diagnostics=64,
        ),
    )
    if parsed.disposition is not RawInputDisposition.ACCEPTED or parsed.detected is None:
        code = parsed.diagnostics[0].code if parsed.diagnostics else "malformed_content"
        failure = _ParseFailure()
        failure.code = {
            "unsupported_version": ProteinInferenceDiagnosticCode.UNSUPPORTED_VERSION,
            "forbidden_xml_construct": ProteinInferenceDiagnosticCode.FORBIDDEN_XML_CONSTRUCT,
            "unsupported_format": ProteinInferenceDiagnosticCode.UNSUPPORTED_FORMAT,
        }.get(code, ProteinInferenceDiagnosticCode.MALFORMED_CONTENT)
        raise failure
    if parsed.detected.format is not raw_format:
        failure = _ParseFailure()
        failure.code = ProteinInferenceDiagnosticCode.ROLE_FORMAT_MISMATCH
        raise failure
    if raw_format is RawFormat.FASTA:
        _validate_fasta_identifiers(payload)
    metadata: dict[str, object] = {}
    references = 0
    if raw_format is RawFormat.MZIDENTML:
        references, metadata = _validate_mzidentml_references(payload)
    elif raw_format in {RawFormat.VCF, RawFormat.GFF3}:
        metadata = _assembly_metadata(payload, raw_format)
    return parsed.detected.version, parsed.record_count, references, metadata


def _xml_root(payload: bytes) -> Element:
    if _XML_FORBIDDEN.search(payload):
        raise _ForbiddenXml
    try:
        return ElementTree.fromstring(payload)
    except DefusedXmlException:
        raise _ForbiddenXml from None
    except ElementTree.ParseError:
        raise _ParseFailure from None


def _local(tag: object) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _validate_mzidentml_shape(root: Element) -> None:
    if _local(root.tag) != "MzIdentML":
        raise _ParseFailure
    if root.attrib.get("version") not in {"1.2", "1.2.0", "1.3", "1.3.0"}:
        raise _UnsupportedVersion
    data_collections = [element for element in root if _local(element.tag) == "DataCollection"]
    if len(data_collections) != 1:
        raise _ParseFailure
    data_collection = data_collections[0]
    if sum(_local(element.tag) == "Inputs" for element in data_collection) != 1:
        raise _ParseFailure
    if sum(_local(element.tag) == "AnalysisData" for element in data_collection) != 1:
        raise _ParseFailure


def _mzidentml_index(
    root: Element,
) -> tuple[set[str], list[str]]:
    identifiers: set[str] = set()
    references: list[str] = []
    for element in root.iter():
        identifier = element.attrib.get("id")
        if identifier is not None:
            if not _MZIDENT_ID.fullmatch(identifier) or identifier in identifiers:
                raise _ParseFailure
            identifiers.add(identifier)
        for attribute, value in element.attrib.items():
            if not attribute.endswith("_ref"):
                continue
            if not _MZIDENT_ID.fullmatch(value):
                raise _ParseFailure
            references.append(value)
    return identifiers, references


def _validate_mzidentml_references(payload: bytes) -> tuple[int, dict[str, object]]:
    root = _xml_root(payload)
    _validate_mzidentml_shape(root)
    identifiers, references = _mzidentml_index(root)
    if any(value not in identifiers for value in references):
        raise _DanglingReference
    databases = [element for element in root.iter() if _local(element.tag) == "SearchDatabase"]
    spectra_data = [element for element in root.iter() if _local(element.tag) == "SpectraData"]
    if len(databases) != 1 or len(spectra_data) == 0:
        raise _ParseFailure
    if any(element.attrib.get("id") is None for element in (*databases, *spectra_data)):
        raise _ParseFailure
    build_id = databases[0].attrib.get("databaseName")
    build_version = databases[0].attrib.get("version")
    metadata: dict[str, object] = {
        "build_id": build_id,
        "build_version": build_version,
    }
    return len(references), metadata


def _validate_fasta_identifiers(payload: bytes) -> None:
    """Reject ambiguous sequence keys while retaining only structural metadata."""

    try:
        lines = payload.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        raise _ParseFailure from None
    identifiers: set[str] = set()
    for line in lines:
        if not line.startswith(">"):
            continue
        identifier = line[1:].split(maxsplit=1)[0] if line[1:].strip() else ""
        if (
            not identifier
            or not _FASTA_IDENTIFIER.fullmatch(identifier)
            or identifier in identifiers
        ):
            raise _ParseFailure
        identifiers.add(identifier)


def _assembly_metadata(payload: bytes, raw_format: RawFormat) -> dict[str, object]:
    try:
        lines = payload.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        raise _ParseFailure from None
    if raw_format is RawFormat.VCF:
        values = [
            line.removeprefix("##reference=") for line in lines if line.startswith("##reference=")
        ]
    else:
        values = [
            line.split(maxsplit=1)[1]
            for line in lines
            if line.startswith("##genome-build ")
            and len(line.split(maxsplit=1)) == _KEY_VALUE_PART_COUNT
        ]
    if not values:
        return {}
    if len(values) != 1:
        raise _ParseFailure
    value = values[0]
    if ":" not in value:
        return {"build_id": value, "build_version": None}
    build_id, build_version = value.rsplit(":", 1)
    return {"build_id": build_id, "build_version": build_version}


def _parse_obo(
    payload: bytes,
    request: IngestProteinInferenceRawInputsRequest,
) -> tuple[str | None, int, int, dict[str, object]]:
    try:
        lines = payload.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        raise _ParseFailure from None
    if not lines or lines[0] != "format-version: 1.2":
        raise _UnsupportedVersion
    versions = [match.group(1) for line in lines if (match := _OBO_VERSION.fullmatch(line))]
    if len(versions) != 1:
        raise _ParseFailure
    terms = 0
    identifiers: set[str] = set()
    for index, line in enumerate(lines):
        if line == "[Term]":
            terms += 1
            if index + 1 >= len(lines) or not _OBO_ID.fullmatch(lines[index + 1]):
                raise _ParseFailure
            if lines[index + 1] in identifiers:
                raise _ParseFailure
            identifiers.add(lines[index + 1])
    if terms == 0:
        raise _ParseFailure
    expected = request.protocol_receipt.controlled_vocabulary_version
    metadata: dict[str, object] = {
        "controlled_vocabulary_id": request.protocol_receipt.controlled_vocabulary_id,
        "controlled_vocabulary_version": versions[0],
        "build_id": request.protocol_receipt.controlled_vocabulary_id,
        "build_version": versions[0],
    }
    if versions[0] != expected:
        metadata["cv_mismatch"] = True
    return versions[0], terms, 0, metadata


def _parse_json_profile(
    declaration: ProteinInferenceRawSource,
    payload: bytes,
    request: IngestProteinInferenceRawInputsRequest,
) -> tuple[str | None, int, int, dict[str, object]]:
    try:
        decoded = strict_json_loads(payload, max_bytes=request.policy.max_decoded_bytes)
    except StrictJsonError as error:
        if error.code is StrictJsonErrorCode.DUPLICATE_KEY:
            raise _DuplicateJson from None
        raise _ParseFailure from None
    if not isinstance(decoded, dict):
        raise _ParseFailure
    data = cast("dict[str, object]", decoded)
    shared = {
        "schema_version",
        "claim_id",
        "protocol_result_digest",
        "search_space_digest",
        "controlled_vocabulary_id",
        "controlled_vocabulary_version",
        "unit_system_version",
    }
    role = declaration.role
    if role is ProteinInferenceRawRole.PROTEIN_GROUP_MANIFEST:
        expected = shared | {"group_ids"}
        collection = "group_ids"
    elif role is ProteinInferenceRawRole.AMBIGUITY_MANIFEST:
        expected = shared | {"group_claim_id", "group_claim_digest", "ambiguity_ids"}
        collection = "ambiguity_ids"
    else:
        expected = {
            "schema_version",
            "claim_id",
            "source_manifest_digest",
            "protein_group_claim_id",
            "protein_group_digest",
            "ambiguity_claim_id",
            "ambiguity_digest",
        }
        collection = None
    if set(data) != expected or data.get("schema_version") != "1.0.0":
        raise _ParseFailure
    if data.get("claim_id") != declaration.bound_claim_id:
        raise _DanglingReference
    if collection is not None:
        values = data.get(collection)
        if (
            not isinstance(values, list)
            or any(not isinstance(item, str) or not item for item in values)
            or len(values) != len(set(values))
        ):
            raise _ParseFailure
        _validate_protocol_fields(data, request)
        records = len(values)
    else:
        records = 1
    return "1.0.0", records, 0, data


def _validate_protocol_fields(
    data: dict[str, object],
    request: IngestProteinInferenceRawInputsRequest,
) -> None:
    exact = {
        "protocol_result_digest": request.protocol_receipt.protocol_result_digest,
        "search_space_digest": request.protocol_receipt.search_space_digest,
    }
    if any(data.get(key) != value for key, value in exact.items()):
        raise _DanglingReference
    if (
        data.get("controlled_vocabulary_id") != request.protocol_receipt.controlled_vocabulary_id
        or data.get("controlled_vocabulary_version")
        != request.protocol_receipt.controlled_vocabulary_version
    ):
        data["cv_mismatch"] = True
    if data.get("unit_system_version") != request.protocol_receipt.unit_system_version:
        data["unit_mismatch"] = True


def _build_receipt(
    declaration: ProteinInferenceRawSource,
    declared_id: str | None,
    declared_version: str | None,
    request: IngestProteinInferenceRawInputsRequest,
) -> ProteinInferenceBuildBindingReceipt:
    expected_id = declaration.expected_build_id
    expected_version = declaration.expected_build_version
    valid_declared = (
        declared_id is not None
        and declared_version is not None
        and _IDENTIFIER.fullmatch(declared_id) is not None
        and _SEMVER.fullmatch(declared_version) is not None
    )
    if expected_id is None:
        state = ProteinInferenceBuildState.NOT_APPLICABLE
    elif declared_id is None or declared_version is None:
        state = ProteinInferenceBuildState.MISSING
    elif not valid_declared:
        state = ProteinInferenceBuildState.UNSUPPORTED
    elif (declared_id, declared_version) != (expected_id, expected_version):
        state = ProteinInferenceBuildState.MISMATCHED
    elif declaration.role in {
        ProteinInferenceRawRole.PEPTIDE_EVIDENCE,
        ProteinInferenceRawRole.PTM_VOCABULARY,
    }:
        state = ProteinInferenceBuildState.EXACT
    else:
        approved = (
            request.policy.approved_genome_builds
            if declaration.role is ProteinInferenceRawRole.GENOMIC_CONTEXT
            else request.policy.approved_transcript_builds
        )
        state = (
            ProteinInferenceBuildState.EXACT
            if any(
                (item.build_id, item.version) == (declared_id, declared_version)
                for item in approved
            )
            else ProteinInferenceBuildState.UNSUPPORTED
        )
    return ProteinInferenceBuildBindingReceipt(
        state=state,
        declared_build_id=declared_id if valid_declared else None,
        declared_build_version=declared_version if valid_declared else None,
        expected_build_id=expected_id,
        expected_build_version=expected_version,
    )


def _build_diagnostics(
    declaration: ProteinInferenceRawSource,
    build: ProteinInferenceBuildBindingReceipt,
) -> tuple[ProteinInferenceParseDiagnostic, ...]:
    values = {
        ProteinInferenceBuildState.MISSING: ProteinInferenceDiagnosticCode.BUILD_MISSING,
        ProteinInferenceBuildState.UNSUPPORTED: (ProteinInferenceDiagnosticCode.BUILD_UNSUPPORTED),
        ProteinInferenceBuildState.MISMATCHED: (ProteinInferenceDiagnosticCode.BUILD_MISMATCH),
    }
    if build.state not in values:
        return ()
    return (diagnostic(values[build.state], (declaration.source_id,)),)


def _failure(  # noqa: PLR0913 - every transport fact is explicit.
    declaration: ProteinInferenceRawSource,
    source_digest: str,
    source_size: int,
    code: ProteinInferenceDiagnosticCode,
    *,
    source_limit: int,
    decoded_limit: int,
    compression: ProteinInferenceCompression | None = None,
    decoded: bytes | None = None,
) -> ParsedSource:
    item = diagnostic(
        code,
        (declaration.source_id,),
    )
    return ParsedSource(
        output=ValidatedProteinInferenceRawInput(
            source_id=declaration.source_id,
            role=declaration.role,
            source_digest=source_digest,
            source_size_bytes=min(source_size, source_limit + 1),
            decoded_digest=(
                f"sha256:{hashlib.sha256(decoded).hexdigest()}" if decoded is not None else None
            ),
            decoded_size_bytes=(
                decoded_limit + 1
                if code is ProteinInferenceDiagnosticCode.DECODED_SIZE_LIMIT_EXCEEDED
                else min(len(decoded or b""), decoded_limit)
            ),
            compression=compression,
            record_count=0,
            reference_count=0,
            build=ProteinInferenceBuildBindingReceipt(
                state=ProteinInferenceBuildState.NOT_APPLICABLE,
                expected_build_id=declaration.expected_build_id,
                expected_build_version=declaration.expected_build_version,
            ),
            diagnostics=(item,),
        ),
        metadata={},
    )


def cross_source_diagnostics(  # noqa: C901 - one closed cross-source rule matrix.
    request: IngestProteinInferenceRawInputsRequest,
    parsed: tuple[ParsedSource, ...],
) -> tuple[ProteinInferenceParseDiagnostic, ...]:
    """Close JSON claim references, manifest binding, CV/unit context, and assemblies."""

    by_role = {item.output.role: item for item in parsed}
    source_by_role = {item.role: item for item in request.sources}
    diagnostics: list[ProteinInferenceParseDiagnostic] = []
    group = by_role.get(ProteinInferenceRawRole.PROTEIN_GROUP_MANIFEST)
    ambiguity = by_role.get(ProteinInferenceRawRole.AMBIGUITY_MANIFEST)
    bundle = by_role.get(ProteinInferenceRawRole.COMPLEX_ACTIVITY_INPUT_BUNDLE)
    if group and ambiguity and not (group.output.diagnostics or ambiguity.output.diagnostics):
        group_source = source_by_role[ProteinInferenceRawRole.PROTEIN_GROUP_MANIFEST]
        if (
            ambiguity.metadata.get("group_claim_id") != group_source.bound_claim_id
            or ambiguity.metadata.get("group_claim_digest") != group_source.artifact.digest
        ):
            diagnostics.append(
                diagnostic(
                    ProteinInferenceDiagnosticCode.DANGLING_REFERENCE,
                    (group.output.source_id, ambiguity.output.source_id),
                )
            )
    if (
        bundle
        and group
        and ambiguity
        and not any(item.output.diagnostics for item in (bundle, group, ambiguity))
    ):
        group_source = source_by_role[ProteinInferenceRawRole.PROTEIN_GROUP_MANIFEST]
        ambiguity_source = source_by_role[ProteinInferenceRawRole.AMBIGUITY_MANIFEST]
        expected = {
            "source_manifest_digest": request.source_manifest_digest,
            "protein_group_claim_id": group_source.bound_claim_id,
            "protein_group_digest": group_source.artifact.digest,
            "ambiguity_claim_id": ambiguity_source.bound_claim_id,
            "ambiguity_digest": ambiguity_source.artifact.digest,
        }
        if any(bundle.metadata.get(key) != value for key, value in expected.items()):
            diagnostics.append(
                diagnostic(
                    ProteinInferenceDiagnosticCode.DANGLING_REFERENCE,
                    tuple(
                        sorted(
                            {
                                bundle.output.source_id,
                                group.output.source_id,
                                ambiguity.output.source_id,
                            }
                        )
                    ),
                )
            )
    obo = by_role.get(ProteinInferenceRawRole.PTM_VOCABULARY)
    if obo and obo.metadata.get("cv_mismatch"):
        diagnostics.append(
            diagnostic(
                ProteinInferenceDiagnosticCode.CONTROLLED_VOCABULARY_MISMATCH,
                (obo.output.source_id,),
            )
        )
    for item in (group, ambiguity):
        if item is None:
            continue
        if item.metadata.get("cv_mismatch"):
            diagnostics.append(
                diagnostic(
                    ProteinInferenceDiagnosticCode.CONTROLLED_VOCABULARY_MISMATCH,
                    (item.output.source_id,),
                )
            )
        if item.metadata.get("unit_mismatch"):
            diagnostics.append(
                diagnostic(
                    ProteinInferenceDiagnosticCode.UNIT_PROFILE_MISMATCH,
                    (item.output.source_id,),
                )
            )
    genomic = by_role.get(ProteinInferenceRawRole.GENOMIC_CONTEXT)
    transcript = by_role.get(ProteinInferenceRawRole.TRANSCRIPT_CONTEXT)
    if genomic and transcript:
        left = (genomic.metadata.get("build_id"), genomic.metadata.get("build_version"))
        right = (transcript.metadata.get("build_id"), transcript.metadata.get("build_version"))
        if all(value is not None for value in (*left, *right)) and left != right:
            diagnostics.append(
                diagnostic(
                    ProteinInferenceDiagnosticCode.ASSEMBLY_MISMATCH,
                    (genomic.output.source_id, transcript.output.source_id),
                )
            )
    return tuple(diagnostics)


def _semantic_version(value: str | None) -> str | None:
    if value is None:
        return None
    if _SEMVER.fullmatch(value):
        return value
    parts = value.split(".")
    if all(part.isdigit() for part in parts) and 1 <= len(parts) < _SEMVER_PART_COUNT:
        return ".".join((*parts, *("0" for _ in range(_SEMVER_PART_COUNT - len(parts)))))
    raise _UnsupportedVersion


__all__ = ["ParsedSource", "cross_source_diagnostics", "diagnostic", "parse_source"]
