"""Package/import verifier checks for provisional M06-04."""

from tools.verify_m06_04_package import _verify_import

_SCHEMA_COUNT = 7


def test_m06_04_import_and_schema_package_verifier() -> None:
    report = _verify_import()

    assert report["module_id"] == "GLIO-PROTEOGEN-M06-04"
    assert report["schema_count"] == _SCHEMA_COUNT
    assert report["provisional_abi"] is True
