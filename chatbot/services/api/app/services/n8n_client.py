"""
n8n Webhook Client
==================
Sends structured payloads to n8n for workflow automation.
Includes retry logic and HMAC signing for external webhook security.
"""

import asyncio
import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.config import settings
from app.models.schemas import BookingDetails, IntentClassification, LeadScore

logger = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(10.0, connect=5.0)
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2  # seconds


# ─── Dead-letter queue ───────────────────────────────────

async def _queue_failed_webhook(path: str, payload: dict) -> None:
    """Store a failed webhook payload in Redis for later retry.

    Falls back to logging if Redis is unavailable — never raises.
    """
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        entry = json.dumps({
            "path": path,
            "payload": payload,
            "failed_at": datetime.now(timezone.utc).isoformat(),
        })
        await r.lpush("n8n:dead_letter", entry)
        await r.close()
        logger.info(f"Queued failed webhook to dead-letter: {path}")
    except Exception as e:
        logger.error(f"Dead-letter queue write failed ({path}): {e}")


# ─── Core webhook sender ─────────────────────────────────

async def _send_webhook(path: str, payload: dict, retries: int = MAX_RETRIES) -> bool:
    """Send a POST request to an n8n webhook endpoint with retry logic.

    On permanent failure the payload is pushed to a Redis dead-letter queue
    so it can be retried later.
    """
    url = f"{settings.n8n_base_url}{path}"
    for attempt in range(1, retries + 1):
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                response = await client.post(url, json=payload)
                if response.status_code in (200, 201, 204):
                    logger.info(f"Webhook sent successfully: {path}")
                    return True
                elif response.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                    wait = RETRY_BACKOFF_BASE ** attempt
                    logger.warning(
                        f"Webhook {path} returned {response.status_code}, retrying in {wait}s "
                        f"(attempt {attempt}/{retries})"
                    )
                    await asyncio.sleep(wait)
                    continue
                else:
                    logger.warning(
                        f"Webhook {path} returned {response.status_code}: {response.text[:200]}"
                    )
                    await _queue_failed_webhook(path, payload)
                    return False
        except httpx.TimeoutException:
            if attempt < retries:
                wait = RETRY_BACKOFF_BASE ** attempt
                logger.warning(f"Webhook {path} timed out, retrying in {wait}s (attempt {attempt}/{retries})")
                await asyncio.sleep(wait)
            else:
                logger.error(f"Webhook {path} timed out after {retries} attempts")
                await _queue_failed_webhook(path, payload)
                return False
        except Exception as e:
            logger.error(f"Webhook {path} failed: {e}")
            await _queue_failed_webhook(path, payload)
            return False
    return False


# ─── Sub-workflow execution ──────────────────────────────

async def execute_subworkflow(
    path: str,
    payload: dict,
    timeout: float = 10.0,
) -> Optional[dict]:
    """Call an n8n sub-workflow webhook and return its JSON response.

    Unlike _send_webhook (fire-and-forget), this waits for a synchronous
    response — useful for availability checks, pricing lookups, etc.
    Returns None on any failure.
    """
    url = f"{settings.n8n_base_url}{path}"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=5.0)) as client:
            response = await client.post(url, json=payload)
            if response.status_code in (200, 201):
                return response.json()
            logger.warning(f"Sub-workflow {path} returned {response.status_code}: {response.text[:200]}")
            return None
    except httpx.TimeoutException:
        logger.warning(f"Sub-workflow {path} timed out after {timeout}s")
        return None
    except Exception as e:
        logger.error(f"Sub-workflow {path} failed: {e}")
        return None


def _sign_payload(payload: dict) -> str:
    """Generate HMAC-SHA256 signature for a payload."""
    secret = settings.n8n_webhook_secret
    if not secret:
        return ""
    sig = hmac.new(
        secret.encode(), json.dumps(payload, sort_keys=True).encode(), hashlib.sha256
    ).hexdigest()
    return f"sha256={sig}"


async def send_new_enquiry(
    conversation_id: str,
    session_id: str,
    booking: BookingDetails,
    classification: IntentClassification,
    lead_score: LeadScore,
    conversation_summary: str,
    source_page: Optional[str] = None,
) -> bool:
    """Send a new enquiry event to n8n."""
    payload = {
        "event_type": "new_enquiry",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "conversation_id": conversation_id,
        "session_id": session_id,
        "client": {
            "name": booking.contact_name,
            "email": booking.contact_email,
            "phone": booking.contact_phone,
            "classification": lead_score.classification,
            "lead_score": lead_score.total_score,
            "source_page": source_page,
        },
        "enquiry": {
            "destination": booking.destination,
            "destination_region": booking.destination_region,
            "travel_dates": {
                "start": booking.travel_dates.start.isoformat() if booking.travel_dates and booking.travel_dates.start else None,
                "end": booking.travel_dates.end.isoformat() if booking.travel_dates and booking.travel_dates.end else None,
            },
            "duration_days": booking.duration_days,
            "pax": {
                "adults": booking.num_adults,
                "children": booking.num_children,
            },
            "experience_type": booking.experience_type,
            "budget_range": {
                "min": booking.budget_range.min if booking.budget_range else None,
                "max": booking.budget_range.max if booking.budget_range else None,
                "currency": booking.budget_range.currency if booking.budget_range else None,
            },
            "special_requests": booking.special_requests,
        },
        "intelligence": {
            "primary_intent": classification.primary_intent,
            "booking_stage": classification.booking_stage,
            "urgency": classification.urgency,
            "sentiment": classification.sentiment,
            "lead_score": lead_score.total_score,
            "classification": lead_score.classification,
        },
        "conversation_summary": conversation_summary,
    }

    return await _send_webhook(settings.n8n_webhook_new_enquiry, payload)


async def send_high_value_alert(
    conversation_id: str,
    lead_score: LeadScore,
    booking: BookingDetails,
) -> bool:
    """Send a high-value lead alert to n8n."""
    payload = {
        "event_type": "high_value_lead",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "conversation_id": conversation_id,
        "lead_score": lead_score.total_score,
        "classification": lead_score.classification,
        "client_name": booking.contact_name,
        "client_email": booking.contact_email,
        "destination": booking.destination,
        "budget_max": booking.budget_range.max if booking.budget_range else None,
        "budget_currency": booking.budget_range.currency if booking.budget_range else None,
    }

    return await _send_webhook(settings.n8n_webhook_high_value, payload)


async def send_escalation(
    conversation_id: str,
    reason: str,
    classification: IntentClassification,
) -> bool:
    """Send an escalation event to n8n."""
    payload = {
        "event_type": "escalation",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "conversation_id": conversation_id,
        "reason": reason,
        "urgency": classification.urgency,
        "sentiment": classification.sentiment,
        "primary_intent": classification.primary_intent,
    }

    return await _send_webhook(settings.n8n_webhook_escalation, payload)


async def send_booking_update(
    conversation_id: str,
    jira_ticket_key: str,
    new_stage: str,
    details: Optional[dict] = None,
) -> bool:
    """Send a booking stage update to n8n."""
    payload = {
        "event_type": "booking_update",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "conversation_id": conversation_id,
        "jira_ticket_key": jira_ticket_key,
        "new_stage": new_stage,
        "details": details or {},
    }

    return await _send_webhook(settings.n8n_webhook_booking_update, payload)


async def forward_website_enquiry(form_data: dict, metadata: Optional[dict] = None) -> bool:
    """Forward a website form enquiry directly to n8n for Outlook + Claude classification.

    Use this when the FastAPI backend receives a form submission that should
    bypass the chatbot pipeline and go straight to the n8n automation workflow.
    """
    payload = {
        "source": "website_form",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "form_data": form_data,
        "metadata": metadata or {},
    }

    # Sign for webhook verification
    sig = _sign_payload(payload)
    if sig:
        payload["hmac_signature"] = sig

    return await _send_webhook(settings.n8n_webhook_website_enquiry, payload)
