"""Public M03-07 protein-inference support-routing contracts."""

from glio_proteogen.contracts.m03_07.canonical import *  # noqa: F403
from glio_proteogen.contracts.m03_07.canonical import __all__ as _canonical_exports
from glio_proteogen.contracts.m03_07.schema import (
    CONTRACT_VERSION,
    SCHEMA_ID_PREFIX,
    ContractName,
    contract_json_schema,
)
from glio_proteogen.contracts.m03_07.v1 import *  # noqa: F403
from glio_proteogen.contracts.m03_07.v1 import __all__ as _v1_exports

__all__: list[str] = [  # noqa: PLE0604 - explicit string exports composed from typed modules.
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    *_canonical_exports,
    *_v1_exports,
    "contract_json_schema",
]
