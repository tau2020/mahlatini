"""
Pydantic schemas for API request/response models.
"""

from datetime import datetime, date
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field


# ─── Chat ─────────────────────────────────────────────────

class ChatMessageRequest(BaseModel):
    """Incoming chat message from the widget."""
    message: str = Field(..., min_length=1, max_length=4000)
    session_id: str = Field(..., min_length=1, max_length=64)
    source_page: Optional[str] = None
    provider: Optional[str] = None  # "groq" or "claude"; defaults to config


class ChatMessageResponse(BaseModel):
    """Response from the chatbot."""
    reply: str
    conversation_id: str
    confidence: float
    intent: Optional[str] = None
    requires_human: bool = False
    lead_captured: bool = False
    provider: Optional[str] = None
    enquiry_progress: Optional[dict] = None


class ConversationMessage(BaseModel):
    """A single message in conversation history."""
    role: str  # 'user' or 'assistant'
    content: str
    timestamp: datetime


# ─── Booking / Lead ───────────────────────────────────────

class DateRange(BaseModel):
    start: Optional[date] = None
    end: Optional[date] = None


class BudgetRange(BaseModel):
    min: Optional[float] = None
    max: Optional[float] = None
    currency: Optional[str] = None


class BookingDetails(BaseModel):
    """Extracted booking details from conversation."""
    destination: Optional[str] = None
    destination_region: Optional[str] = None
    travel_dates: Optional[DateRange] = None
    travel_month: Optional[str] = None
    duration_days: Optional[int] = None
    num_adults: Optional[int] = None
    num_children: Optional[int] = None
    children_ages: Optional[list[int]] = None
    budget_range: Optional[BudgetRange] = None
    experience_type: Optional[list[str]] = None
    accommodation_preference: Optional[str] = None
    special_requests: Optional[str] = None
    special_occasion: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None


# ─── Classification ───────────────────────────────────────

class IntentClassification(BaseModel):
    """Result of intent classification."""
    primary_intent: str
    urgency: str = "low"
    urgency_reason: Optional[str] = None
    booking_stage: str = "browsing"
    sentiment: str = "neutral"
    requires_human: bool = False
    escalation_reason: Optional[str] = None
    detected_keywords: list[str] = Field(default_factory=list)


class LeadScore(BaseModel):
    """Lead scoring result."""
    total_score: int = Field(ge=0, le=100)
    classification: str
    breakdown: dict[str, int] = Field(default_factory=dict)


# ─── n8n Webhooks ─────────────────────────────────────────

class EnquiryWebhookPayload(BaseModel):
    """Payload sent to n8n for new enquiries."""
    event_type: str = "new_enquiry"
    timestamp: datetime
    conversation_id: str
    session_id: str
    client: dict
    enquiry: dict
    intelligence: dict
    conversation_summary: str


# ─── Admin ────────────────────────────────────────────────

class KnowledgeBaseStats(BaseModel):
    """Stats about the knowledge base."""
    total_vectors: int
    collection_name: str
    categories: dict[str, int] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    services: dict[str, str] = Field(default_factory=dict)
