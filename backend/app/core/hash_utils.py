import hashlib


def sha256_digest(text: str) -> str:
    """Return a full SHA-256 hex digest of *text*."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
