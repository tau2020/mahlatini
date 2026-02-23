"""
Shared test fixtures for the Mahlatini chatbot API tests.
"""

import os
import sys
import types
from unittest.mock import MagicMock

import pytest

# Ensure the app package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Override settings before any app imports
os.environ.update({
    "APP_ENV": "test",
    "N8N_BASE_URL": "http://n8n-test:5678",
    "N8N_WEBHOOK_SECRET": "test-secret-key",
    "REDIS_URL": "redis://localhost:6379/15",
    "QDRANT_HOST": "localhost",
    "POSTGRES_HOST": "localhost",
})

# ─── Mock heavy ML dependencies that are only in Docker ──
# sentence_transformers pulls in PyTorch (~2GB); mock it for
# integration tests that never touch embeddings.
if "sentence_transformers" not in sys.modules:
    _st = types.ModuleType("sentence_transformers")
    _st.SentenceTransformer = MagicMock()
    sys.modules["sentence_transformers"] = _st
