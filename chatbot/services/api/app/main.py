"""
Mahlatini AI Chatbot — FastAPI Application
==========================================
Main entry point for the API server.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers.chat import router as chat_router
from app.routers.admin import router as admin_router

# ─── Logging ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if settings.app_debug else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("mahlatini")


# ─── Lifespan (startup / shutdown) ────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    logger.info("=" * 60)
    logger.info("  Mahlatini AI Chatbot — Starting Up")
    logger.info(f"  Environment: {settings.app_env}")
    logger.info(f"  Qdrant:      {settings.qdrant_host}:{settings.qdrant_port}")
    logger.info(f"  LLM Default: {settings.default_provider}")
    logger.info(f"  Groq Model:  {settings.groq_model}")
    logger.info(f"  Claude Model:{settings.claude_model}")
    logger.info(f"  Claude Key:  {'set' if settings.anthropic_api_key else 'not set'}")
    logger.info("=" * 60)

    # Pre-load the embedding model at startup
    try:
        from app.services.embeddings import get_embedding_model
        get_embedding_model()
        logger.info("Embedding model loaded successfully")
    except Exception as e:
        logger.warning(f"Embedding model pre-load failed (will retry on first request): {e}")

    yield

    logger.info("Mahlatini AI Chatbot — Shutting Down")


# ─── App ──────────────────────────────────────────────────
app = FastAPI(
    title="Mahlatini AI Chatbot",
    description="AI-powered travel concierge for Mahlatini Luxury Travel",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs" if settings.app_debug else None,
    redoc_url="/api/redoc" if settings.app_debug else None,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(chat_router)
app.include_router(admin_router)


# ─── Root redirect ───────────────────────────────────────
@app.get("/")
async def root():
    return {
        "name": "Mahlatini AI Chatbot",
        "version": "1.0.0",
        "docs": "/api/docs" if settings.app_debug else None,
    }
