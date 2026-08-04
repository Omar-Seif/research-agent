# src/utils/hashing.py

import hashlib
from pydantic import HttpUrl


def generate_source_id(url: HttpUrl) -> str:
    """Generate a stable ID for a source by hashing its URL."""
    return hashlib.sha256(str(url).encode()).hexdigest()[:16]
