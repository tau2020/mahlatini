"""
Admin Router
=============
Administrative endpoints for health checks, knowledge base stats,
and system management.
"""

import logging

from fastapi import APIRouter
from fastapi.responses import FileResponse
from pathlib import Path

from app.models.schemas import HealthResponse, KnowledgeBaseStats
from app.services.vector_store import get_collection_info
from app.services.llm import get_llm
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Admin"])

APP_VERSION = "1.0.0"

# ─── Health Check ─────────────────────────────────────────

@router.get("/health", response_model=HealthResponse)
async def health_check():
    """System health check — used by Docker and Nginx."""
    services = {}

    # Check Qdrant
    try:
        info = get_collection_info()
        services["qdrant"] = "healthy" if info.get("status") != "error" else "unhealthy"
    except Exception:
        services["qdrant"] = "unreachable"

    # Check Groq
    try:
        groq = get_llm("groq")
        groq_ok = await groq.is_healthy()
        services["groq"] = "healthy" if groq_ok else "unreachable"
    except Exception:
        services["groq"] = "unreachable"

    # Check Claude (only if API key is configured)
    if settings.anthropic_api_key:
        try:
            claude = get_llm("claude")
            claude_ok = await claude.is_healthy()
            services["claude"] = "healthy" if claude_ok else "unreachable"
        except Exception:
            services["claude"] = "unreachable"

    overall = "healthy" if all(v == "healthy" for v in services.values()) else "degraded"

    return HealthResponse(
        status=overall,
        version=APP_VERSION,
        services=services,
    )


# ─── Knowledge Base Stats ────────────────────────────────

@router.get("/api/admin/knowledge-base", response_model=KnowledgeBaseStats)
async def knowledge_base_stats():
    """Get knowledge base statistics."""
    info = get_collection_info()
    return KnowledgeBaseStats(
        total_vectors=info.get("points_count", 0),
        collection_name=info.get("name", "unknown"),
    )


# ─── Chat Widget Static Files ────────────────────────────

WIDGET_DIR = Path(__file__).parent.parent.parent / "widget"


@router.get("/widget/chat-widget.js")
async def serve_widget_js():
    """Serve the chat widget JavaScript."""
    js_path = WIDGET_DIR / "chat-widget.js"
    if js_path.exists():
        return FileResponse(js_path, media_type="application/javascript")
    return {"error": "Widget not found"}


@router.get("/widget/chat-widget.css")
async def serve_widget_css():
    """Serve the chat widget CSS."""
    css_path = WIDGET_DIR / "chat-widget.css"
    if css_path.exists():
        return FileResponse(css_path, media_type="text/css")
    return {"error": "Widget styles not found"}


@router.get("/widget/enquiry-form.js")
async def serve_enquiry_form_js():
    """Serve the enquiry form submission handler JavaScript."""
    js_path = WIDGET_DIR / "enquiry-form.js"
    if js_path.exists():
        return FileResponse(js_path, media_type="application/javascript")
    return {"error": "Enquiry form widget not found"}


@router.get("/widget/sarah-avatar.png")
async def serve_avatar():
    """Serve the chatbot avatar image."""
    img_path = WIDGET_DIR / "sarah-avatar.png"
    if img_path.exists():
        return FileResponse(img_path, media_type="image/png")
    return {"error": "Avatar not found"}
