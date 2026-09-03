from __future__ import annotations

from pathlib import Path

import pytest
from tools.generate_gbmap_hgnc_feature_crosswalk import (
    GbmapFeatureIdentityGeneratorError,
    _decode_feature,
    _hash_held_h5ad,
    _require_acknowledgements,
    main,
)

ERROR_EXIT = 2


@pytest.mark.parametrize(
    ("reviewed", "identity_only"),
    [(False, False), (False, True), (True, False)],
)
def test_acknowledgements_are_required_before_source_access(
    reviewed: bool,  # noqa: FBT001
    identity_only: bool,  # noqa: FBT001
) -> None:
    with pytest.raises(GbmapFeatureIdentityGeneratorError):
        _require_acknowledgements(
            reviewed_source_digests=reviewed,
            feature_identity_only=identity_only,
        )
    assert (
        main(
            [
                "--gbmap-h5ad",
                "missing.h5ad",
                "--hgnc-tsv",
                "missing.tsv",
                "--output",
                "never-created.json",
                *(["--acknowledge-reviewed-source-digests"] if reviewed else []),
                *(["--acknowledge-feature-identity-only"] if identity_only else []),
            ]
        )
        == ERROR_EXIT
    )
    assert not Path("never-created.json").exists()


def test_feature_text_decode_and_stream_hash_are_exact(tmp_path: Path) -> None:
    assert _decode_feature(b"GENE") == "GENE"
    assert _decode_feature("GENE") == "GENE"
    for invalid in (b"\xff", 1, " PADDED ", ""):
        with pytest.raises(GbmapFeatureIdentityGeneratorError):
            _decode_feature(invalid)
    source = tmp_path / "fixture.h5ad"
    source.write_bytes(b"abc")
    with source.open("rb") as handle:
        assert _hash_held_h5ad(handle) == (
            3,
            "900150983cd24fb0d6963f7d28e17f72",
            "sha256:ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        )
