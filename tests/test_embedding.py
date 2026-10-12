import math
import numpy as np
import pytest

from app.config import Settings
from app.services.embedding import (
    EmbeddingService,
    EmbeddingServiceError,
    ModelLoadError,
    InferenceError,
    get_embedding_service,
)


class DummyModel:
    """Mock model simulating SentenceTransformer."""

    def __init__(self, output_dimension=384, return_nan=False, fail=False):
        self.output_dimension = output_dimension
        self.return_nan = return_nan
        self.fail = fail
        self.encode_calls = []

    def encode(self, text, normalize_embeddings=True):
        self.encode_calls.append({"text": text, "normalize": normalize_embeddings})
        if self.fail:
            raise RuntimeError("Inference hardware fault")
        if self.return_nan:
            vec = np.zeros(self.output_dimension, dtype=np.float32)
            vec[0] = float("nan")
            return vec
        # Return normalized unit vector
        vec = np.ones(self.output_dimension, dtype=np.float32)
        norm = np.linalg.norm(vec)
        return vec / norm


# ==============================================================================
# prepare_text tests
# ==============================================================================

def test_prepare_text_valid_formatting():
    """Verify prepare_text formats title and content with two newlines."""
    title = "Forest Canopy Observations"
    content = "High chlorophyll concentration detected."
    formatted = EmbeddingService.prepare_text(title, content)
    assert formatted == "Forest Canopy Observations\n\nHigh chlorophyll concentration detected."


def test_prepare_text_empty_title_raises_value_error():
    """Verify prepare_text rejects empty or whitespace-only title."""
    with pytest.raises(ValueError, match="title cannot be empty or whitespace-only"):
        EmbeddingService.prepare_text("", "Some content")

    with pytest.raises(ValueError, match="title cannot be empty or whitespace-only"):
        EmbeddingService.prepare_text("   \t  ", "Some content")


def test_prepare_text_empty_combined_text_raises_value_error():
    """Verify prepare_text rejects whitespace-only combined input."""
    with pytest.raises(ValueError):
        EmbeddingService.prepare_text("   ", "   ")


# ==============================================================================
# generate_embedding tests
# ==============================================================================

def test_generate_embedding_success():
    """Verify generate_embedding returns 384-dimensional normalized float list."""
    dummy_model = DummyModel(output_dimension=384)
    service = EmbeddingService(model=dummy_model)

    vector = service.generate_embedding("Valid research note text")

    assert len(vector) == 384
    assert all(isinstance(x, float) for x in vector)
    assert all(math.isfinite(x) for x in vector)
    # Norm of unit vector should be approximately 1.0
    norm = math.sqrt(sum(x * x for x in vector))
    assert pytest.approx(norm, rel=1e-5) == 1.0
    assert len(dummy_model.encode_calls) == 1
    assert dummy_model.encode_calls[0]["normalize"] is True


def test_generate_embedding_empty_or_whitespace_raises_value_error():
    """Verify empty or whitespace-only text raises ValueError and avoids model inference."""
    dummy_model = DummyModel()
    service = EmbeddingService(model=dummy_model)

    with pytest.raises(ValueError, match="cannot be empty or whitespace-only"):
        service.generate_embedding("")

    with pytest.raises(ValueError, match="cannot be empty or whitespace-only"):
        service.generate_embedding("   \n\t  ")

    assert len(dummy_model.encode_calls) == 0


def test_generate_embedding_dimension_mismatch_raises_inference_error():
    """Verify output with incorrect dimension raises InferenceError."""
    dummy_model = DummyModel(output_dimension=512)
    service = EmbeddingService(model=dummy_model)

    with pytest.raises(InferenceError, match="dimension mismatch"):
        service.generate_embedding("Sample text")


def test_generate_embedding_non_finite_values_raises_inference_error():
    """Verify output with NaN / Inf values raises InferenceError."""
    dummy_model = DummyModel(return_nan=True)
    service = EmbeddingService(model=dummy_model)

    with pytest.raises(InferenceError, match="non-finite values"):
        service.generate_embedding("Sample text")


def test_generate_embedding_inference_failure_raises_inference_error():
    """Verify underlying inference exception is wrapped in InferenceError without secret leaks."""
    dummy_model = DummyModel(fail=True)
    service = EmbeddingService(model=dummy_model)

    with pytest.raises(InferenceError) as exc_info:
        service.generate_embedding("Sample text")

    assert "hardware fault" not in str(exc_info.value)
    assert "InferenceError" in exc_info.type.__name__ or issubclass(exc_info.type, EmbeddingServiceError)


def test_model_loading_failure_raises_model_load_error(monkeypatch):
    """Verify failure importing or loading model raises ModelLoadError cleanly."""
    service = EmbeddingService(model_name="nonexistent-model-xyz")

    def mock_sentence_transformer(name):
        raise FileNotFoundError("Model file not found on disk")

    monkeypatch.setattr("sentence_transformers.SentenceTransformer", mock_sentence_transformer)

    with pytest.raises(ModelLoadError) as exc_info:
        service.generate_embedding("Sample text")

    assert "Model file not found on disk" not in str(exc_info.value)


# ==============================================================================
# get_embedding_service dependency tests
# ==============================================================================

def test_get_embedding_service_singleton_behavior():
    """Verify get_embedding_service reuses the same singleton for identical settings."""
    settings = Settings(
        MONGODB_URI="mongodb://localhost:27017",
        EMBEDDING_MODEL="sentence-transformers/all-MiniLM-L6-v2",
        _env_file=None,
    )
    s1 = get_embedding_service(settings)
    s2 = get_embedding_service(settings)
    assert s1 is s2


def test_get_embedding_service_recreates_on_model_change():
    """Verify get_embedding_service instantiates a new service if configured model changes."""
    settings_a = Settings(
        MONGODB_URI="mongodb://localhost:27017",
        EMBEDDING_MODEL="model-a",
        _env_file=None,
    )
    settings_b = Settings(
        MONGODB_URI="mongodb://localhost:27017",
        EMBEDDING_MODEL="model-b",
        _env_file=None,
    )
    s1 = get_embedding_service(settings_a)
    s2 = get_embedding_service(settings_b)
    assert s1 is not s2
    assert s1.model_name == "model-a"
    assert s2.model_name == "model-b"
