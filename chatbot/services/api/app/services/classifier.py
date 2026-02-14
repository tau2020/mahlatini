"""
Intent Classifier
=================
Classifies user messages for intent, urgency, sentiment, and escalation needs.
"""

import json
import logging
from typing import Optional

from app.config import settings
from app.services.llm import generate_json
from app.models.schemas import IntentClassification

logger = logging.getLogger(__name__)


def _load_prompt() -> str:
    """Load the intent classification prompt template."""
    path = settings.prompts_dir / "intent_classification.txt"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


# Keywords that trigger specific classifications without LLM
ESCALATION_KEYWORDS = {
    "complaint", "disappointed", "terrible", "disgusting", "unacceptable",
    "refund", "cancel", "sue", "lawyer", "legal",
}

BOOKING_KEYWORDS = {
    "book", "reserve", "booking", "reservation", "quote", "price",
    "cost", "budget", "availability", "available",
}

URGENT_KEYWORDS = {
    "urgent", "emergency", "asap", "tomorrow", "next week",
    "this week", "immediately", "rush",
}

CALLBACK_KEYWORDS = {
    "call me", "callback", "call back", "phone me", "ring me",
    "speak to someone", "talk to a human", "real person",
}


def _quick_classify(message: str) -> Optional[IntentClassification]:
    """
    Fast keyword-based classification for obvious cases.
    Returns None if no obvious classification found.
    """
    lower_msg = message.lower()

    # Check for explicit callback/human request
    if any(kw in lower_msg for kw in CALLBACK_KEYWORDS):
        return IntentClassification(
            primary_intent="callback_request",
            urgency="high",
            booking_stage="considering",
            sentiment="neutral",
            requires_human=True,
            escalation_reason="Client explicitly requested human contact",
        )

    # Check for complaints
    if any(kw in lower_msg for kw in ESCALATION_KEYWORDS):
        return IntentClassification(
            primary_intent="complaint",
            urgency="high",
            booking_stage="booked_followup",
            sentiment="negative",
            requires_human=True,
            escalation_reason="Complaint or negative experience detected",
        )

    return None


async def classify_intent(
    message: str,
    recent_context: list[dict] = None,
) -> IntentClassification:
    """
    Classify user intent using keyword shortcuts and LLM fallback.

    Args:
        message: The user's latest message
        recent_context: Last 3 messages for context

    Returns:
        IntentClassification with intent, urgency, sentiment, etc.
    """
    # Try fast keyword classification first
    quick = _quick_classify(message)
    if quick:
        return quick

    # Build context string
    if recent_context:
        context_str = "\n".join(
            f"{'Client' if m.get('role') == 'user' else 'Concierge'}: {m['content']}"
            for m in recent_context[-3:]
        )
    else:
        context_str = "No previous context."

    # LLM classification
    template = _load_prompt()
    if not template:
        # Fallback if no template
        return IntentClassification(
            primary_intent="general_enquiry",
            urgency="low",
            booking_stage="browsing",
            sentiment="neutral",
        )

    prompt = template.format(
        message=message,
        recent_context=context_str,
    )

    try:
        result = await generate_json(
            prompt=prompt,
            system_prompt="You are a classification engine. Return only valid JSON.",
            temperature=0.1,
        )

        return IntentClassification(
            primary_intent=result.get("primary_intent", "general_enquiry"),
            urgency=result.get("urgency", "low"),
            urgency_reason=result.get("urgency_reason"),
            booking_stage=result.get("booking_stage", "browsing"),
            sentiment=result.get("sentiment", "neutral"),
            requires_human=result.get("requires_human", False),
            escalation_reason=result.get("escalation_reason"),
            detected_keywords=result.get("detected_keywords", []),
        )
    except Exception as e:
        logger.warning(f"Intent classification failed: {e}")
        return IntentClassification(
            primary_intent="general_enquiry",
            urgency="low",
            booking_stage="browsing",
            sentiment="neutral",
        )
