"""
Chat Router
============
REST and WebSocket endpoints for the chat interface.

Enquiry collection model:
  EXPLORING  — general chat, no booking details yet
  COLLECTING — actively gathering enquiry fields (1 per response)
  CONFIRMING — all required fields filled, awaiting user confirmation
  SUBMITTED  — enquiry sent to n8n, conversation continues informally

Human escalation is restricted to complaints, callbacks, and legal threats.
"""

import hashlib
import hmac as hmac_mod
import json
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Query, Request

from app.models.schemas import (
    ChatMessageRequest,
    ChatMessageResponse,
    BookingDetails,
    N8nCallbackRequest,
    N8nCallbackResponse,
)
from app.services.rag import answer_query
from app.services.classifier import classify_intent
from app.services.lead_scorer import score_lead
from app.services.llm import generate_json
from app.services import n8n_client
from app.services.enquiry_tracker import (
    EnquiryPhase,
    EnquiryState,
    update_state,
    build_collection_context,
    build_progress,
)
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["Chat"])

# ─── In-memory session store (use Redis in production) ────
_sessions: dict[str, dict] = {}

# ─── Pending messages pushed from n8n (per session) ──────
_n8n_pending: dict[str, list[dict]] = {}


def _get_session(session_id: str) -> dict:
    """Get or create a conversation session."""
    if session_id not in _sessions:
        _sessions[session_id] = {
            "conversation_id": str(uuid.uuid4()),
            "messages": [],
            "enquiry_state": EnquiryState(),
            "lead_scored": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    return _sessions[session_id]


def _load_booking_prompt() -> str:
    path = settings.prompts_dir / "booking_extraction.txt"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def _count_user_messages(messages: list[dict]) -> int:
    """Count only user messages in the conversation."""
    return sum(1 for m in messages if m.get("role") == "user")


# ─── Confirmation Detection ──────────────────────────────

CONFIRM_PATTERNS = {
    "yes", "yeah", "yep", "correct", "that's right", "looks good",
    "all good", "perfect", "go ahead", "submit", "send it",
    "that's correct", "confirmed", "looks right", "that works",
    "good to go", "please submit", "yes please",
}

CORRECTION_PATTERNS = {
    "no", "not quite", "actually", "change", "wrong", "correction",
    "update", "instead", "wait", "hold on", "let me correct",
}


def _detect_confirmation(message: str, state: EnquiryState) -> Optional[str]:
    """
    If in CONFIRMING phase, detect whether the user confirmed or corrected.
    Returns: "confirmed", "corrected", or None (ambiguous — let LLM handle it)
    """
    if state.phase != EnquiryPhase.CONFIRMING:
        return None

    lower = message.lower().strip()

    if any(p in lower for p in CONFIRM_PATTERNS):
        return "confirmed"
    if any(p in lower for p in CORRECTION_PATTERNS):
        return "corrected"

    return None


# ─── HMAC verification for n8n callbacks ─────────────────

def _verify_hmac(body: bytes, signature: str) -> bool:
    """Verify an HMAC-SHA256 signature from n8n.

    If no webhook secret is configured, accept all requests (open mode).
    """
    secret = settings.n8n_webhook_secret
    if not secret:
        return True  # No secret configured — accept everything
    if not signature:
        return False  # Secret configured but no signature provided

    expected = "sha256=" + hmac_mod.new(
        secret.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac_mod.compare_digest(expected, signature)


# ─── Shared lead-capture helper ──────────────────────────

# Intents that warrant booking extraction
_BOOKING_INTENTS = {
    "booking_intent", "enquiry", "booking", "travel_planning",
    "general_enquiry", "destination_enquiry",
}
_MIN_MESSAGES_FOR_EXTRACTION = 5  # trigger on message count alone


async def _process_lead_capture(
    session: dict,
    session_id: str,
    classification,
    source_page: Optional[str] = None,
) -> bool:
    """Extract booking details, score the lead, and push to n8n if qualified.

    Returns True if a booking was extracted (regardless of score),
    False if extraction was skipped or yielded nothing.
    """
    if session["lead_scored"]:
        return False

    user_msg_count = sum(1 for m in session["messages"] if m.get("role") == "user")
    intent_relevant = classification.primary_intent in _BOOKING_INTENTS
    count_trigger = user_msg_count >= _MIN_MESSAGES_FOR_EXTRACTION

    if not intent_relevant and not count_trigger:
        return False

    booking = await _extract_booking(session["messages"])
    if not booking:
        return False

    lead = score_lead(
        booking=booking,
        booking_stage=classification.booking_stage,
        message_count=len(session["messages"]),
    )

    # Only push to n8n if score is high enough (≥40) and has contact info
    if lead.total_score >= 40 and booking.contact_email:
        await n8n_client.send_new_enquiry(
            conversation_id=session["conversation_id"],
            session_id=session_id,
            booking=booking,
            classification=classification,
            lead_score=lead,
            conversation_summary=_summarise_conversation(session["messages"]),
            source_page=source_page,
        )
        session["lead_scored"] = True

        if lead.classification in ("vip", "high_value"):
            await n8n_client.send_high_value_alert(
                conversation_id=session["conversation_id"],
                lead_score=lead,
                booking=booking,
            )

    return True


# ─── REST endpoint ───────────────────────────────────────

@router.post("/message", response_model=ChatMessageResponse)
async def send_message(request: ChatMessageRequest):
    """Handle an incoming chat message via REST."""
    session = _get_session(request.session_id)
    state = session["enquiry_state"]

    # Add user message to history
    session["messages"].append({
        "role": "user",
        "content": request.message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    # Classify intent
    classification = await classify_intent(
        message=request.message,
        recent_context=session["messages"][-6:],
    )

    # Check for confirmation before generating response
    confirmation = _detect_confirmation(request.message, state)

    if confirmation == "confirmed" and state.phase == EnquiryPhase.CONFIRMING:
        # Submit the enquiry to n8n
        lead_score = score_lead(
            booking=state.booking,
            booking_stage="ready_to_book",
            message_count=len(session["messages"]),
        )
        try:
            await n8n_client.send_new_enquiry(
                conversation_id=session["conversation_id"],
                session_id=request.session_id,
                booking=state.booking,
                classification=classification,
                lead_score=lead_score,
                conversation_summary=_summarise_conversation(session["messages"]),
                source_page=request.source_page,
            )
            state.phase = EnquiryPhase.SUBMITTED
            state.submitted = True
            session["lead_scored"] = True

            if lead_score.classification in ("vip", "high_value"):
                await n8n_client.send_high_value_alert(
                    conversation_id=session["conversation_id"],
                    lead_score=lead_score,
                    booking=state.booking,
                )
            logger.info(f"Enquiry submitted for session {request.session_id} (score={lead_score.total_score})")
        except Exception as e:
            logger.error(f"Failed to submit enquiry: {e}")

    elif confirmation == "corrected":
        # Go back to collecting — user wants to fix something
        state.phase = EnquiryPhase.COLLECTING
        state.confirmation_shown = False

    # Extract/update booking state (unless already submitted)
    if state.phase != EnquiryPhase.SUBMITTED and _count_user_messages(session["messages"]) >= 1:
        booking = await _extract_booking(session["messages"])
        if booking:
            update_state(state, booking)

    # Build collection context for the LLM
    collection_context = build_collection_context(state)

    # RAG-powered response with collection context
    rag_result = await answer_query(
        question=request.message,
        conversation_history=session["messages"][-settings.max_conversation_history:],
        provider=request.provider,
        collection_context=collection_context,
    )

    reply = rag_result["reply"]
    confidence = rag_result["confidence"]
    provider_used = rag_result["provider"]

    # Add assistant message to history
    session["messages"].append({
        "role": "assistant",
        "content": reply,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    # Handle escalation (only complaints/callbacks)
    if classification.requires_human:
        await n8n_client.send_escalation(
            conversation_id=session["conversation_id"],
            reason=classification.escalation_reason or "Human requested",
            classification=classification,
        )

    return ChatMessageResponse(
        reply=reply,
        conversation_id=session["conversation_id"],
        confidence=confidence,
        intent=classification.primary_intent,
        requires_human=classification.requires_human,
        lead_captured=state.submitted,
        provider=provider_used,
        enquiry_progress=build_progress(state),
    )


# ─── WebSocket endpoint ──────────────────────────────────

@router.websocket("/ws/{session_id}")
async def websocket_chat(
    websocket: WebSocket,
    session_id: str,
    provider: Optional[str] = Query(default=None),
):
    """Handle real-time chat via WebSocket."""
    await websocket.accept()
    session = _get_session(session_id)

    logger.info(f"WebSocket connected: {session_id} (provider={provider or 'default'})")

    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            user_message = message_data.get("message", "").strip()

            if not user_message:
                continue

            msg_provider = message_data.get("provider", provider)
            state = session["enquiry_state"]

            session["messages"].append({
                "role": "user",
                "content": user_message,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

            # Send typing indicator
            await websocket.send_json({"type": "typing", "status": True})

            # Classify
            classification = await classify_intent(
                message=user_message,
                recent_context=session["messages"][-6:],
            )

            # Check for confirmation
            confirmation = _detect_confirmation(user_message, state)

            if confirmation == "confirmed" and state.phase == EnquiryPhase.CONFIRMING:
                lead_score = score_lead(
                    booking=state.booking,
                    booking_stage="ready_to_book",
                    message_count=len(session["messages"]),
                )
                try:
                    source_page = message_data.get("source_page", "")
                    await n8n_client.send_new_enquiry(
                        conversation_id=session["conversation_id"],
                        session_id=session_id,
                        booking=state.booking,
                        classification=classification,
                        lead_score=lead_score,
                        conversation_summary=_summarise_conversation(session["messages"]),
                        source_page=source_page,
                    )
                    state.phase = EnquiryPhase.SUBMITTED
                    state.submitted = True
                    session["lead_scored"] = True

                    if lead_score.classification in ("vip", "high_value"):
                        await n8n_client.send_high_value_alert(
                            conversation_id=session["conversation_id"],
                            lead_score=lead_score,
                            booking=state.booking,
                        )
                    logger.info(f"WS enquiry submitted for session {session_id}")
                except Exception as e:
                    logger.error(f"WS enquiry submission failed: {e}")

            elif confirmation == "corrected":
                state.phase = EnquiryPhase.COLLECTING
                state.confirmation_shown = False

            # Extract/update booking state
            if state.phase != EnquiryPhase.SUBMITTED and _count_user_messages(session["messages"]) >= 1:
                try:
                    booking = await _extract_booking(session["messages"])
                    if booking:
                        update_state(state, booking)
                except Exception as e:
                    logger.warning(f"WS booking extraction failed: {e}")

            # Build collection context
            collection_context = build_collection_context(state)

            # Generate response with collection context
            rag_result = await answer_query(
                question=user_message,
                conversation_history=session["messages"][-settings.max_conversation_history:],
                provider=msg_provider,
                collection_context=collection_context,
            )

            reply = rag_result["reply"]

            session["messages"].append({
                "role": "assistant",
                "content": reply,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

            # Send response with progress
            await websocket.send_json({
                "type": "message",
                "reply": reply,
                "confidence": rag_result["confidence"],
                "intent": classification.primary_intent,
                "requires_human": classification.requires_human,
                "provider": rag_result["provider"],
                "enquiry_progress": build_progress(state),
            })

            # Handle escalation
            if classification.requires_human:
                await n8n_client.send_escalation(
                    conversation_id=session["conversation_id"],
                    reason=classification.escalation_reason or "Human requested",
                    classification=classification,
                )

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error for {session_id}: {e}")
        try:
            await websocket.close()
        except Exception:
            pass


# ─── n8n callback endpoint (n8n → chatbot push) ─────────

@router.post("/n8n-callback", response_model=N8nCallbackResponse)
async def n8n_callback(request: Request):
    """Receive a message pushed from n8n and queue it for the chat session.

    n8n calls this after assigning a specialist, sending an itinerary, etc.
    The widget polls /n8n-pending/{session_id} to pick these up.
    """
    body = await request.body()
    signature = request.headers.get("X-Webhook-Signature", "")

    if not _verify_hmac(body, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    from pydantic import ValidationError as PydanticValidationError
    try:
        payload = N8nCallbackRequest.model_validate_json(body)
    except PydanticValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors())

    # Queue the message for the session
    _n8n_pending.setdefault(payload.session_id, []).append({
        "message": payload.message,
        "message_type": payload.message_type,
        "metadata": payload.metadata or {},
        "conversation_id": payload.conversation_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    logger.info(f"n8n callback queued for session {payload.session_id} ({payload.message_type})")

    return N8nCallbackResponse(status="queued", session_id=payload.session_id)


@router.get("/n8n-pending/{session_id}")
async def get_pending_messages(session_id: str):
    """Drain and return any pending n8n messages for a session.

    Called by the chat widget to pick up async notifications
    (specialist assigned, itinerary ready, escalation updates, etc.).
    """
    messages = _n8n_pending.pop(session_id, [])
    return {"messages": messages, "count": len(messages)}


# ─── Helpers ──────────────────────────────────────────────

async def _extract_booking(messages: list[dict]) -> BookingDetails | None:
    """Use LLM to extract booking details from the conversation."""
    template = _load_booking_prompt()
    if not template:
        return None

    conversation_text = "\n".join(
        f"{'Client' if m['role'] == 'user' else 'Concierge'}: {m['content']}"
        for m in messages
    )

    prompt = template.format(conversation=conversation_text)

    result = await generate_json(
        prompt=prompt,
        system_prompt="Extract travel details from the conversation. Return only valid JSON.",
    )

    if not result:
        return None

    return BookingDetails(
        destination=result.get("destination"),
        destination_region=result.get("destination_region"),
        travel_month=result.get("travel_month"),
        duration_days=result.get("duration_days"),
        num_adults=result.get("num_adults"),
        num_children=result.get("num_children"),
        children_ages=result.get("children_ages"),
        experience_type=result.get("experience_type"),
        accommodation_preference=result.get("accommodation_preference"),
        special_requests=result.get("special_requests"),
        special_occasion=result.get("special_occasion"),
        contact_name=result.get("contact_name"),
        contact_email=result.get("contact_email"),
        contact_phone=result.get("contact_phone"),
    )


def _summarise_conversation(messages: list[dict], max_messages: int = 8) -> str:
    """Create a brief summary of the conversation for n8n payloads."""
    recent = messages[-max_messages:]
    lines = []
    for m in recent:
        role = "Client" if m["role"] == "user" else "Concierge"
        content = m["content"][:150]
        lines.append(f"{role}: {content}")
    return "\n".join(lines)
