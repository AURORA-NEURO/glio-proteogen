"""Research-lane errors for SPHINKS signature-concordance inference."""


class MasterKinaseError(RuntimeError):
    """Base exception for independent master-kinase concordance inference."""


class CatalogIntegrityError(MasterKinaseError):
    """Raised when the pinned scientific catalog fails a content lock."""


__all__ = ["CatalogIntegrityError", "MasterKinaseError"]
