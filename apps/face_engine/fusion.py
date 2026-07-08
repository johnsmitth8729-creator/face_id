import logging
import numpy as np

logger = logging.getLogger(__name__)


def validate_embedding(vector) -> bool:
    """
    Validate that the embedding:
    - Is not None
    - Has shape (512,) or length 512
    - Contains only finite numeric values (no NaN, no Inf)
    """
    if vector is None:
        logger.error("Embedding validation failed: Embedding is None")
        return False

    try:
        arr = np.asarray(vector, dtype=np.float32)
    except (ValueError, TypeError) as e:
        logger.error(f"Embedding validation failed: Cannot convert to float32 array: {e}")
        return False

    if arr.ndim != 1 or len(arr) != 512:
        logger.error(f"Embedding validation failed: Expected 1D array of size 512, got shape {arr.shape}")
        return False

    if not np.isfinite(arr).all():
        logger.error("Embedding validation failed: Contains non-finite values (NaN or Inf)")
        return False

    return True


def normalize_embedding(vector) -> np.ndarray:
    """
    Perform L2 normalization on a 1D vector.
    """
    arr = np.asarray(vector, dtype=np.float32)
    norm = np.linalg.norm(arr)
    if norm == 0:
        logger.warning("L2 normalization: Vector norm is zero, returning original vector")
        return arr
    return arr / norm


def average_embeddings(list_of_embeddings) -> np.ndarray:
    """
    Average the list of embeddings, then normalize the result.
    """
    if not list_of_embeddings:
        logger.error("Average embeddings failed: Empty list of embeddings")
        raise ValueError("Cannot average empty list of embeddings")

    arrays = [np.asarray(emb, dtype=np.float32) for emb in list_of_embeddings]
    avg = np.mean(arrays, axis=0)
    return normalize_embedding(avg)
