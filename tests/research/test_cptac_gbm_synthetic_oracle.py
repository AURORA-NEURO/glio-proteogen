from __future__ import annotations

from typing import cast

from tools import evaluate_cptac_gbm_synthetic_oracle as oracle


def test_synthetic_oracle_passes_and_is_replay_stable() -> None:
    first = oracle.evaluate()
    second = oracle.evaluate()
    assert first == second
    assert first["pass"] is True
    solver = cast("dict[str, object]", first["solver"])
    assert cast("float", solver["direction_cosine"]) >= oracle.MIN_DIRECTION_COSINE
    assert cast("float", solver["direction_recovery_fraction"]) >= oracle.MIN_SIGN_RECOVERY
    adjustment = cast("dict[str, object]", first["parent_adjustment"])
    assert adjustment["outlier_resistance"] is True
    assert adjustment["replay_equal"] is True


def test_synthetic_oracle_digest_is_content_bound() -> None:
    result = oracle.evaluate()
    assert str(result["oracle_digest"]).startswith("sha256:")
    assert result["oracle_id"] == oracle.ORACLE_ID
