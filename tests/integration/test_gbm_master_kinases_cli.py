"""Standalone CLI lifecycle for GBM master-kinase concordance inference."""

from __future__ import annotations

import json
from io import BytesIO
from types import SimpleNamespace
from typing import TYPE_CHECKING

from typer.testing import CliRunner

from glio_proteogen.adapters import gbm_master_kinases as adapter
from glio_proteogen.adapters.gbm_master_kinases import cli
from glio_proteogen.research.gbm_master_kinases import ALGORITHM_PROFILE_ID

if TYPE_CHECKING:
    from pathlib import Path


def test_gbm_master_kinases_cli_profile_demo_analyze_and_verify(tmp_path: Path) -> None:
    runner = CliRunner()
    profile = runner.invoke(cli, ["profile"])
    demo = runner.invoke(cli, ["demo"])

    assert profile.exit_code == 0, profile.output
    assert demo.exit_code == 0, demo.output
    assert json.loads(profile.output)["profile_id"] == ALGORITHM_PROFILE_ID
    request = json.loads(demo.output)
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")

    analysis = runner.invoke(cli, ["analyze", str(request_path)])
    assert analysis.exit_code == 0, analysis.output
    result = json.loads(analysis.output)
    assert result["sample_id"] == request["sample_id"]

    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(
        json.dumps({"request": request, "result": result}),
        encoding="utf-8",
    )
    verification = runner.invoke(cli, ["verify", str(receipt_path)])
    assert verification.exit_code == 0, verification.output
    assert json.loads(verification.output)["verified"] is True


def test_gbm_master_kinases_cli_forgery_and_invalid_input_are_sanitized(
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    request = json.loads(runner.invoke(cli, ["demo"]).output)
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")
    result = json.loads(runner.invoke(cli, ["analyze", str(request_path)]).output)
    result["result_digest"] = "sha256:" + "f" * 64
    receipt_path = tmp_path / "forged.json"
    receipt_path.write_text(
        json.dumps({"request": request, "result": result}),
        encoding="utf-8",
    )

    verification = runner.invoke(cli, ["verify", str(receipt_path)])
    assert verification.exit_code == 1
    assert json.loads(verification.output)["verified"] is False

    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text(
        '{"sample_id":"patient-secret-a","sample_id":"patient-secret-b"}',
        encoding="utf-8",
    )
    invalid = runner.invoke(cli, ["analyze", str(invalid_path)])
    assert invalid.exit_code != 0
    assert "patient-secret" not in invalid.output
    assert "does not satisfy" in invalid.output


def test_cli_emits_exact_unicode_profile_as_utf8_bytes(
    monkeypatch,
) -> None:
    output = BytesIO()
    monkeypatch.setattr(adapter.sys, "stdout", SimpleNamespace(buffer=output))

    adapter._emit({"article_title": "PKCδ and DNA-PK"})

    assert output.getvalue() == '{"article_title":"PKCδ and DNA-PK"}\n'.encode()
