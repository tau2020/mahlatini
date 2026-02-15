"""
Shared test fixtures for the Mahlatini chatbot API tests.
"""

import os
import sys
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
