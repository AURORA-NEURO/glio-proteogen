"""Lock secret-scan detection and log-redaction behavior."""

from __future__ import annotations

from dataclasses import fields

from tools.scan_secrets import Finding, scan_text


def test_scan_text_detects_representative_credentials_without_retaining_values() -> None:
    github_token = "ghp_" + ("A" * 36)
    private_key_header = "-----BEGIN " + "PRIVATE KEY-----"
    generic_credential = "password=" + '"' + ("Z" * 24) + '"'
    source = f"{github_token}\n{private_key_header}\n{generic_credential}"

    findings = scan_text(source)

    assert {(finding.rule, finding.line) for finding in findings} == {
        ("github-token", 1),
        ("private-key", 2),
        ("credential-assignment", 3),
    }
    assert {field.name for field in fields(Finding)} == {"rule", "line"}
    rendered = repr(findings)
    assert github_token not in rendered
    assert private_key_header not in rendered
    assert generic_credential not in rendered


def test_scan_text_allows_placeholders_and_content_digests() -> None:
    source = "\n".join(
        (
            'api_key="synthetic-placeholder"',
            'password="****************"',
            "digest=sha256:" + ("a" * 64),
        )
    )

    assert scan_text(source) == ()
