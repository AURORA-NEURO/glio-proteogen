"""Package/install boundary checks for M05-07."""

from tools.verify_m05_07_package import _verify_import


def test_m05_07_package_exports_closed_provisional_schema_set() -> None:
    report = _verify_import()

    assert report == {
        "module_id": "GLIO-PROTEOGEN-M05-07",
        "provisional_abi": True,
        "schema_count": 6,
    }
