"""Exact released model metadata projected through a caller-admitted HGNC snapshot.

Only the input metadata of the byte-locked artifact is read. No parameter is
decoded, no model loader is called, and no expression or clinical input is read.
The caller admits the HGNC source with the existing hard-locked file reader;
the canonical reference digest below binds the actual indexes used here.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from functools import lru_cache
from importlib.resources import files
from typing import Annotated, Final, Literal, NoReturn, Self, SupportsIndex

from pydantic import Field, model_validator

from glio_proteogen.kernel.models import FrozenModel, Sha256Digest
from glio_proteogen.research.cptac_gbm_external_admission.contracts import (
    GeneIdentity,
    HgncReference,
)
from glio_proteogen.research.cptac_gbm_external_admission.identity import HGNC_LOCK
from glio_proteogen.research.gbm_rna_purity.catalog import (
    CATALOG_RESOURCE,
    EXPECTED_ARTIFACT_SHA256,
    EXPECTED_CONTENT_DIGEST,
    EXPECTED_FEATURE_ORDER_DIGEST,
)
from glio_proteogen.research.gbm_rna_purity.contracts import MODEL_FEATURE_COUNT

from .contracts import AdmissionError, digest

MODEL_ARTIFACT_BYTES: Final = 1_083_994
REFERENCE_STATES: Final = ("resolved", "unresolved_reference", "ambiguous_identity")
ReferenceState = Literal["resolved", "unresolved_reference", "ambiguous_identity"]
_Count = Annotated[int, Field(ge=0, le=MODEL_FEATURE_COUNT)]


class ModelAxisError(AdmissionError):
    """A sanitized released-axis or exact-reference admission failure."""


class ModelAxisReceipt(FrozenModel):
    """Reference-only aggregate provenance; no input sample or count vector."""

    schema_version: Literal["glio-proteogen.purity-model-axis-receipt/1.0.0"] = (
        "glio-proteogen.purity-model-axis-receipt/1.0.0"
    )
    profile_id: Literal["cptac-gbm-native-star-purity-preflight/1.0.0"] = (
        "cptac-gbm-native-star-purity-preflight/1.0.0"
    )
    model_id: Literal["gbmpurity-primary-idhwt-rna/1.0.0"] = "gbmpurity-primary-idhwt-rna/1.0.0"
    model_artifact_sha256: Sha256Digest
    model_artifact_bytes: Literal[1_083_994] = MODEL_ARTIFACT_BYTES
    model_content_digest: Sha256Digest
    feature_order_digest: Sha256Digest
    feature_length_digest: Sha256Digest
    canonical_hgnc_reference_digest: Sha256Digest
    hgnc_source_sha256: Sha256Digest
    hgnc_source_bytes: Literal[16_948_224] = 16_948_224
    feature_mapping_digest: Sha256Digest
    model_feature_count: Literal[5_829] = 5_829
    resolved_features: _Count
    unresolved_reference_features: _Count
    ambiguous_identity_features: _Count

    @model_validator(mode="after")
    def exact_release_and_partition(self) -> Self:
        if (
            self.model_artifact_sha256 != EXPECTED_ARTIFACT_SHA256
            or self.model_content_digest != EXPECTED_CONTENT_DIGEST
            or self.feature_order_digest != EXPECTED_FEATURE_ORDER_DIGEST
            or self.hgnc_source_sha256 != "sha256:" + HGNC_LOCK.sha256
            or self.resolved_features
            + self.unresolved_reference_features
            + self.ambiguous_identity_features
            != MODEL_FEATURE_COUNT
        ):
            raise ValueError("model-axis receipt does not bind the fixed release and partition")
        return self


@dataclass(frozen=True, slots=True)
class ModelInputFeature:
    """One original source feature, never an alias or replacement feature."""

    source_symbol: str
    source_length: float
    identity: GeneIdentity | None
    reference_state: ReferenceState

    def __post_init__(self) -> None:
        if (
            type(self.source_symbol) is not str
            or not self.source_symbol
            or len(self.source_symbol) > 128
            or any(char.isspace() or ord(char) < 32 for char in self.source_symbol)
            or type(self.source_length) is not float
            or not math.isfinite(self.source_length)
            or self.source_length <= 0
            or self.reference_state not in REFERENCE_STATES
            or (self.identity is not None and type(self.identity) is not GeneIdentity)
        ):
            raise ModelAxisError("model input feature is invalid")
        if self.identity is not None and self.identity.symbol != self.source_symbol:
            raise ModelAxisError("model input feature differs from its exact approved symbol")
        if self.reference_state in {"resolved", "ambiguous_identity"} and (
            self.identity is None or self.identity.ensembl_gene_id is None
        ):
            raise ModelAxisError("model input feature reference state is inconsistent")
        if self.reference_state == "unresolved_reference" and (
            self.identity is not None and self.identity.ensembl_gene_id is not None
        ):
            raise ModelAxisError("model input feature reference state is inconsistent")


def _read_released_metadata() -> bytes:
    try:
        resource = files("glio_proteogen.research.gbm_rna_purity").joinpath(CATALOG_RESOURCE)
        with resource.open("rb") as stream:
            payload = stream.read(MODEL_ARTIFACT_BYTES + 1)
    except (OSError, ValueError):
        raise ModelAxisError("released model metadata could not be read") from None
    if (
        len(payload) != MODEL_ARTIFACT_BYTES
        or "sha256:" + hashlib.sha256(payload).hexdigest() != EXPECTED_ARTIFACT_SHA256
    ):
        raise ModelAxisError("released model metadata byte lock differs")
    return payload


@lru_cache(maxsize=1)
def _released_metadata() -> tuple[tuple[str, ...], tuple[float, ...]]:
    # The entire artifact byte lock precedes JSON parsing. Parameters are opaque
    # JSON here: neither their base64 bytes nor numerical tensors are decoded.
    try:
        document = json.loads(_read_released_metadata())
        names = document["input"]["feature_names"]
        lengths = document["input"]["feature_lengths"]
        if (
            type(names) is not list
            or len(names) != MODEL_FEATURE_COUNT
            or any(type(name) is not str for name in names)
            or len(set(names)) != MODEL_FEATURE_COUNT
            or digest(names) != EXPECTED_FEATURE_ORDER_DIGEST
            or type(lengths) is not list
            or len(lengths) != MODEL_FEATURE_COUNT
            or any(
                type(length) not in (int, float) or not math.isfinite(length) or length <= 0
                for length in lengths
            )
            or document["content_digest"] != EXPECTED_CONTENT_DIGEST
        ):
            raise ModelAxisError("released model input metadata is invalid")  # noqa: TRY301
        return tuple(names), tuple(float(length) for length in lengths)
    except ModelAxisError:
        raise
    except (KeyError, TypeError, ValueError, UnicodeError, OverflowError):
        raise ModelAxisError("released model input metadata is invalid") from None


def canonical_hgnc_reference_digest(hgnc: HgncReference) -> str:
    """Bind the exact actual identities and ambiguity groups, without aliases."""
    if type(hgnc) is not HgncReference:
        raise ModelAxisError("a validated approved reference is required")
    # Reconstructing rejects even object.__setattr__ corruption of the legacy
    # frozen object, rather than claiming the declared file lock authenticates it.
    try:
        checked = HgncReference(hgnc.by_hgnc, hgnc.by_ensembl, hgnc.by_symbol)
    except (AttributeError, TypeError, ValueError):
        raise ModelAxisError("approved reference indexes are inconsistent") from None
    return digest(
        {
            "identities": tuple(asdict(checked.by_hgnc[key]) for key in sorted(checked.by_hgnc)),
            "ensembl_groups": {
                key: tuple(sorted(identity.hgnc_id for identity in identities))
                for key, identities in sorted(checked.by_ensembl.items())
            },
        }
    )


def _feature(symbol: str, length: float, hgnc: HgncReference) -> ModelInputFeature:
    identity = hgnc.by_symbol.get(symbol)
    if identity is None or identity.ensembl_gene_id is None:
        state: ReferenceState = "unresolved_reference"
    else:
        candidates = hgnc.by_ensembl.get(identity.ensembl_gene_id, ())
        state = (
            "resolved"
            if hgnc.by_hgnc.get(identity.hgnc_id) == identity
            and len(candidates) == 1
            and candidates[0] == identity
            else "ambiguous_identity"
        )
    return ModelInputFeature(symbol, length, identity, state)


def _mapping_digest(features: tuple[ModelInputFeature, ...]) -> str:
    return digest(tuple(asdict(feature) for feature in features))


class ModelInputAxis:
    """Immutable reference metadata bound to the exact released source axis."""

    __slots__ = ("_features", "_receipt")
    _features: tuple[ModelInputFeature, ...]
    _receipt: ModelAxisReceipt

    def __init__(self, features: tuple[ModelInputFeature, ...], receipt: ModelAxisReceipt) -> None:
        if type(features) is not tuple or any(
            type(item) is not ModelInputFeature for item in features
        ):
            raise ModelAxisError("model axis requires exact source feature metadata")
        if type(receipt) is not ModelAxisReceipt:
            raise ModelAxisError("a validated model-axis receipt is required")
        try:
            checked = ModelAxisReceipt.model_validate(receipt.model_dump(mode="python"))
        except ValueError:
            raise ModelAxisError("model-axis receipt is invalid") from None
        names, lengths = _released_metadata()
        if (
            tuple(feature.source_symbol for feature in features) != names
            or tuple(feature.source_length for feature in features) != lengths
            or checked.feature_length_digest != digest(lengths)
            or checked.feature_mapping_digest != _mapping_digest(features)
            or tuple(
                sum(feature.reference_state == state for feature in features)
                for state in REFERENCE_STATES
            )
            != (
                checked.resolved_features,
                checked.unresolved_reference_features,
                checked.ambiguous_identity_features,
            )
        ):
            raise ModelAxisError("model axis differs from its released metadata or receipt")
        object.__setattr__(self, "_features", features)
        object.__setattr__(self, "_receipt", checked)

    def __setattr__(self, _name: str, _value: object) -> NoReturn:
        raise AttributeError("model input axis is immutable")

    @property
    def features(self) -> tuple[ModelInputFeature, ...]:
        return self._features

    @property
    def receipt(self) -> ModelAxisReceipt:
        return self._receipt

    @property
    def digest(self) -> str:
        return digest(self.receipt.model_dump(mode="json"))

    def __repr__(self) -> str:
        return "ModelInputAxis(released_features=5829)"

    def __getstate__(self) -> NoReturn:
        raise TypeError("model input axis cannot be implicitly serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("model input axis cannot be implicitly serialized")


def admit_model_axis(hgnc: HgncReference) -> ModelInputAxis:
    """Admit fixed model metadata against caller-owned, hard-locked HGNC input."""
    reference_digest = canonical_hgnc_reference_digest(hgnc)
    names, lengths = _released_metadata()
    features = tuple(
        _feature(name, length, hgnc) for name, length in zip(names, lengths, strict=True)
    )
    receipt = ModelAxisReceipt(
        model_artifact_sha256=EXPECTED_ARTIFACT_SHA256,
        model_content_digest=EXPECTED_CONTENT_DIGEST,
        feature_order_digest=EXPECTED_FEATURE_ORDER_DIGEST,
        feature_length_digest=digest(lengths),
        canonical_hgnc_reference_digest=reference_digest,
        hgnc_source_sha256="sha256:" + HGNC_LOCK.sha256,
        feature_mapping_digest=_mapping_digest(features),
        resolved_features=sum(feature.reference_state == "resolved" for feature in features),
        unresolved_reference_features=sum(
            feature.reference_state == "unresolved_reference" for feature in features
        ),
        ambiguous_identity_features=sum(
            feature.reference_state == "ambiguous_identity" for feature in features
        ),
    )
    return ModelInputAxis(features, receipt)


def validate_model_axis(model_axis: ModelInputAxis, *, hgnc: HgncReference) -> None:
    """Reject foreign references, forged bindings and reordered/replaced features."""
    if type(model_axis) is not ModelInputAxis:
        raise ModelAxisError("an exact released model axis is required")
    expected = admit_model_axis(hgnc)
    if model_axis.features != expected.features or model_axis.receipt != expected.receipt:
        raise ModelAxisError("model axis is not bound to this exact approved reference")


__all__ = [
    "MODEL_ARTIFACT_BYTES",
    "REFERENCE_STATES",
    "ModelAxisError",
    "ModelAxisReceipt",
    "ModelInputAxis",
    "ModelInputFeature",
    "ReferenceState",
    "admit_model_axis",
    "canonical_hgnc_reference_digest",
    "validate_model_axis",
]
