"""Shared content hashing utilities."""

from __future__ import annotations

import hashlib


def sha256_hash(text: str) -> str:
    """Return the SHA256 hex digest of UTF-8 text with normalized newlines."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def compute_chunk_hashes(chunks: list[dict]) -> dict[str, str]:
    """Return ``{chunk_id: content_hash}`` for chunks that have an ID."""
    return {
        chunk["chunk_id"]: sha256_hash(chunk.get("content", ""))
        for chunk in chunks
        if chunk.get("chunk_id")
    }
