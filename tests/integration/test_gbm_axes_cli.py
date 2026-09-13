"""Central CLI lifecycle for the published GBM proteomic-axis lane."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from typer.testing import CliRunner

from glio_proteogen.adapters.cli import app

if TYPE_CHECKING:
    from pathlib import Path


def test_gbm_axes_cli_profile_demo_analyze_and_verify(tmp_path: Path) -> None:
    runner = CliRunner()
    profile = runner.invoke(app, ["gbm-axes", "profile"])
    demo = runner.invoke(app, ["gbm-axes", "demo"])

    assert profile.exit_code == 0, profile.output
    assert demo.exit_code == 0, demo.output
    assert json.loads(profile.output)["profile_id"] == "gbm-proteomic-axes/1.0.0"
    request = json.loads(demo.output)
    request["bootstrap_replicates"] = 0
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")

    analysis = runner.invoke(app, ["gbm-axes", "analyze", str(request_path)])
    assert analysis.exit_code == 0, analysis.output
    result = json.loads(analysis.output)
    assert result["sample_id"] == request["sample_id"]

    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(
        json.dumps({"request": request, "result": result}),
        encoding="utf-8",
    )
    verification = runner.invoke(app, ["gbm-axes", "verify", str(receipt_path)])
    assert verification.exit_code == 0, verification.output
    assert json.loads(verification.output)["verified"] is True


def test_gbm_axes_cli_verify_exits_nonzero_for_forged_receipt(tmp_path: Path) -> None:
    runner = CliRunner()
    request = json.loads(runner.invoke(app, ["gbm-axes", "demo"]).output)
    request["bootstrap_replicates"] = 0
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")
    result = json.loads(
        runner.invoke(app, ["gbm-axes", "analyze", str(request_path)]).output
    )
    result["result_digest"] = "sha256:" + "f" * 64
    receipt_path = tmp_path / "forged.json"
    receipt_path.write_text(
        json.dumps({"request": request, "result": result}),
        encoding="utf-8",
    )

    verification = runner.invoke(app, ["gbm-axes", "verify", str(receipt_path)])

    assert verification.exit_code == 1
    assert json.loads(verification.output)["verified"] is False
