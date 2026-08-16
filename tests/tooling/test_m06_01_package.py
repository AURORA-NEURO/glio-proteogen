"""M06-01 package/install boundary checks."""

from tools.verify_m06_01_package import _verify_import


def test_m06_01_package_exports_closed_provisional_schema_set() -> None:
    assert _verify_import() == {
        "module_id": "GLIO-PROTEOGEN-M06-01",
        "schema_count": 8,
        "provisional_abi": True,
    }
