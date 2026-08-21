"""Shared embedding primitives for writer and searcher.

The writer and searcher keep different business wrappers, but both use this
module so model loading, caching, normalization, and dimensions stay aligned.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

_models: dict[str, SentenceTransformer] = {}


def _configured_model_name() -> str:
    return os.getenv("EMBEDDING_MODEL", "BAAI/bge-large-zh-v1.5")


def get_embedding_model(model_name: str | None = None) -> SentenceTransformer:
    """Load and cache one model by its configured name or local path."""
    name = model_name or _configured_model_name()
    model = _models.get(name)
    if model is not None:
        return model

    logger.info("Loading embedding model: %s", name)
    model = SentenceTransformer(name)
    _models[name] = model
    dimension = model.get_sentence_embedding_dimension()
    logger.info("Embedding model loaded: %s (dim=%s)", name, dimension)
    return model


def embedding_dimension(model_name: str | None = None) -> int:
    """Return the output dimension of the selected embedding model."""
    return int(get_embedding_model(model_name).get_sentence_embedding_dimension())


def text_to_vector(text: str, model_name: str | None = None) -> np.ndarray:
    """Encode one query/document text with normalized embeddings."""
    model = get_embedding_model(model_name)
    return np.asarray(model.encode(text, normalize_embeddings=True))


def batch_text_to_vectors(
    texts: list[str],
    model_name: str | None = None,
    batch_size: int | None = None,
) -> list[np.ndarray]:
    """Encode multiple texts for ingestion using the same model contract."""
    if not texts:
        return []
    model = get_embedding_model(model_name)
    kwargs: dict[str, Any] = {
        "normalize_embeddings": True,
        "show_progress_bar": False,
    }
    if batch_size is not None:
        kwargs["batch_size"] = batch_size
    embeddings = model.encode(texts, **kwargs)
    return [np.asarray(embedding) for embedding in embeddings]
