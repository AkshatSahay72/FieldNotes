import logging
import math
from typing import Any, List, Optional
from fastapi import Depends

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


class EmbeddingServiceError(Exception):
    """Base exception for vector embedding operations."""
    pass


class ModelLoadError(EmbeddingServiceError):
    """Raised when the embedding model cannot be loaded."""
    pass


class InferenceError(EmbeddingServiceError):
    """Raised when vector embedding inference fails."""
    pass


class EmbeddingService:
    """Service for computing normalized vector embeddings using SentenceTransformers.
    
    Adheres to Milestone 6 specifications:
    - Model: sentence-transformers/all-MiniLM-L6-v2
    - Dimensionality: 384 finite float dimensions
    - Metric compatibility: Cosine similarity via unit vector normalization
    - Lazy loading: Weights loaded once upon first invocation
    - Clean failure semantics: Internal exceptions wrapped without leaking paths or secrets
    """

    EXPECTED_DIMENSION: int = 384

    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        model: Optional[Any] = None,
    ) -> None:
        self.model_name = model_name
        self._model = model

    def _load_model(self) -> Any:
        """Lazily load and cache the underlying SentenceTransformer model instance."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                try:
                    # Prefer local cache to prevent slow unauthenticated HF Hub network checks (cuts load from ~60s to ~2s)
                    self._model = SentenceTransformer(self.model_name, local_files_only=True)
                except (TypeError, Exception):
                    self._model = SentenceTransformer(self.model_name)
                logger.info("SentenceTransformer model '%s' loaded successfully.", self.model_name)
            except Exception as err:
                logger.error("Failed to load embedding model '%s': %s", self.model_name, type(err).__name__)
                raise ModelLoadError(f"Failed to load embedding model '{self.model_name}'") from err
        return self._model

    @staticmethod
    def prepare_text(title: str, content: str) -> str:
        """Format note title and content for embedding inference.
        
        Input schema: title + '\\n\\n' + content.
        Validates that the combined text contains non-whitespace content.
        """
        if not title or not title.strip():
            raise ValueError("Embedding input title cannot be empty or whitespace-only")
        combined = f"{title}\n\n{content}"
        if not combined.strip():
            raise ValueError("Embedding input text cannot be empty or whitespace-only")
        return combined

    def generate_embedding(self, text: str) -> List[float]:
        """Generate a 384-dimensional normalized vector embedding for the input text.
        
        Validates input, normalizes vectors for cosine similarity, and verifies
        finite numeric values across all dimensions.
        """
        if not text or not text.strip():
            raise ValueError("Embedding input text cannot be empty or whitespace-only")

        model = self._load_model()
        try:
            # normalize_embeddings=True outputs unit vectors where dot product == cosine similarity
            vector = model.encode(text, normalize_embeddings=True)
        except Exception as err:
            logger.error("Inference failed for model '%s': %s", self.model_name, type(err).__name__)
            raise InferenceError(f"Embedding inference failed for model '{self.model_name}'") from err

        if hasattr(vector, "tolist"):
            raw_list = vector.tolist()
        else:
            raw_list = list(vector)

        vector_floats = [float(x) for x in raw_list]

        if len(vector_floats) != self.EXPECTED_DIMENSION:
            raise InferenceError(
                f"Embedding dimension mismatch: expected {self.EXPECTED_DIMENSION}, got {len(vector_floats)}"
            )

        if not all(math.isfinite(x) for x in vector_floats):
            raise InferenceError("Embedding vector contains non-finite values (NaN or Inf)")

        return vector_floats


_embedding_service_instance: Optional[EmbeddingService] = None


def get_embedding_service(
    settings: Settings = Depends(get_settings),
) -> EmbeddingService:
    """FastAPI dependency provider returning the shared singleton EmbeddingService."""
    global _embedding_service_instance
    if (
        _embedding_service_instance is None
        or _embedding_service_instance.model_name != settings.embedding_model
    ):
        _embedding_service_instance = EmbeddingService(model_name=settings.embedding_model)
    return _embedding_service_instance
