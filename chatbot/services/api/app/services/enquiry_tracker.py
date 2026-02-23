"""
Enquiry Tracker
================
State machine for tracking enquiry completeness during conversation.
Determines what fields have been collected, what's missing, and what
phase the conversation is in (exploring → collecting → confirming → submitted).

The tracker generates a plain-English "collection context" that gets injected
into the LLM prompt so it knows what to ask for next.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional

from app.models.schemas import BookingDetails


class EnquiryPhase(str, Enum):
    EXPLORING = "exploring"       # General chat, no booking details yet
    COLLECTING = "collecting"     # Actively gathering enquiry details
    CONFIRMING = "confirming"     # All required fields filled, awaiting user OK
    SUBMITTED = "submitted"       # Sent to n8n, done


# Fields that must be collected before an enquiry can be submitted
REQUIRED_FIELDS = {
    "destination",
    "travel_month",
    "num_adults",
    "contact_name",
    "contact_email",
}

# Human-friendly labels used in the LLM prompt
FIELD_LABELS = {
    "destination": "where they want to go",
    "travel_month": "when they want to travel",
    "num_adults": "how many adults are travelling",
    "contact_name": "their name",
    "contact_email": "their email address",
    "duration_days": "how long the trip should be",
    "budget_range": "their budget",
    "num_children": "whether any children are joining",
    "experience_type": "what kind of experience they want",
    "accommodation_preference": "accommodation preferences",
    "special_requests": "any special requests",
    "special_occasion": "whether it's a special occasion",
    "contact_phone": "their phone number",
    "destination_region": "which specific area or region",
}


@dataclass
class EnquiryState:
    phase: EnquiryPhase = EnquiryPhase.EXPLORING
    booking: Optional[BookingDetails] = None
    filled_required: set = field(default_factory=set)
    filled_optional: set = field(default_factory=set)
    missing_required: set = field(default_factory=lambda: set(REQUIRED_FIELDS))
    confirmation_shown: bool = False
    submitted: bool = False


def compute_filled_fields(booking: BookingDetails) -> tuple[set, set]:
    """Inspect a BookingDetails and return (filled_required, filled_optional)."""
    filled_req = set()
    filled_opt = set()

    # Required fields
    if booking.destination:
        filled_req.add("destination")
    if booking.travel_month or (booking.travel_dates and booking.travel_dates.start):
        filled_req.add("travel_month")
    if booking.num_adults is not None:
        filled_req.add("num_adults")
    if booking.contact_name:
        filled_req.add("contact_name")
    if booking.contact_email:
        filled_req.add("contact_email")

    # Optional fields
    if booking.duration_days is not None:
        filled_opt.add("duration_days")
    if booking.budget_range and (booking.budget_range.min or booking.budget_range.max):
        filled_opt.add("budget_range")
    if booking.num_children is not None:
        filled_opt.add("num_children")
    if booking.children_ages:
        filled_opt.add("children_ages")
    if booking.experience_type:
        filled_opt.add("experience_type")
    if booking.accommodation_preference:
        filled_opt.add("accommodation_preference")
    if booking.special_requests:
        filled_opt.add("special_requests")
    if booking.special_occasion:
        filled_opt.add("special_occasion")
    if booking.contact_phone:
        filled_opt.add("contact_phone")
    if booking.destination_region:
        filled_opt.add("destination_region")

    return filled_req, filled_opt


def determine_phase(state: EnquiryState) -> EnquiryPhase:
    """Determine which conversation phase we're in based on field completeness."""
    if state.submitted:
        return EnquiryPhase.SUBMITTED

    if not state.missing_required:
        return EnquiryPhase.CONFIRMING

    if state.filled_required:
        return EnquiryPhase.COLLECTING

    return EnquiryPhase.EXPLORING


def update_state(state: EnquiryState, booking: BookingDetails) -> EnquiryState:
    """Update the enquiry state with newly extracted booking details."""
    state.booking = booking
    filled_req, filled_opt = compute_filled_fields(booking)
    state.filled_required = filled_req
    state.filled_optional = filled_opt
    state.missing_required = REQUIRED_FIELDS - filled_req
    state.phase = determine_phase(state)

    # Mark confirmation_shown when we first enter CONFIRMING
    if state.phase == EnquiryPhase.CONFIRMING and not state.confirmation_shown:
        state.confirmation_shown = True

    return state


def build_collection_context(state: EnquiryState) -> str:
    """
    Build a plain-English context string for injection into the LLM prompt.
    This tells the LLM what information has been collected and what's still needed.
    """
    if state.phase == EnquiryPhase.EXPLORING:
        return (
            "ENQUIRY STATUS: The client is still exploring. No specific trip details yet.\n"
            "If the conversation naturally allows it, start learning about their trip — "
            "where they'd like to go is a great place to start."
        )

    if state.phase == EnquiryPhase.COLLECTING:
        all_filled = state.filled_required | state.filled_optional
        known = ", ".join(FIELD_LABELS[f] for f in sorted(all_filled) if f in FIELD_LABELS)
        missing = ", ".join(FIELD_LABELS[f] for f in sorted(state.missing_required) if f in FIELD_LABELS)

        return (
            f"ENQUIRY STATUS: Collecting trip details.\n"
            f"Already know: {known}\n"
            f"Still need: {missing}\n"
            f"Work ONE of the missing details into your next response naturally. "
            f"Don't ask for contact details (name/email) until you've collected "
            f"destination, dates, and group size first."
        )

    if state.phase == EnquiryPhase.CONFIRMING:
        summary = _build_booking_summary(state.booking)
        return (
            f"ENQUIRY STATUS: All key details collected! Summarise what you know and "
            f"ask the client to confirm before you submit.\n"
            f"Details to confirm:\n{summary}\n"
            f"Ask naturally, like: \"Just to make sure I've got everything right — "
            f"[summary]. Does that all look good, or anything you'd change?\""
        )

    if state.phase == EnquiryPhase.SUBMITTED:
        return (
            "ENQUIRY STATUS: Enquiry already submitted successfully.\n"
            "The client has been told the team will be in touch. You can continue "
            "chatting about destinations or answering questions, but don't collect "
            "new enquiry details unless they explicitly want to plan another trip."
        )

    return ""


def _build_booking_summary(booking: BookingDetails) -> str:
    """Build a human-readable summary of collected booking details."""
    parts = []

    if booking.destination:
        dest = booking.destination
        if booking.destination_region:
            dest += f" ({booking.destination_region})"
        parts.append(f"- Destination: {dest}")

    if booking.travel_month:
        parts.append(f"- When: {booking.travel_month}")
    elif booking.travel_dates and booking.travel_dates.start:
        dates = str(booking.travel_dates.start)
        if booking.travel_dates.end:
            dates += f" to {booking.travel_dates.end}"
        parts.append(f"- When: {dates}")

    if booking.duration_days:
        parts.append(f"- Duration: {booking.duration_days} days")

    if booking.num_adults is not None:
        pax = f"{booking.num_adults} adult{'s' if booking.num_adults != 1 else ''}"
        if booking.num_children:
            pax += f", {booking.num_children} child{'ren' if booking.num_children != 1 else ''}"
            if booking.children_ages:
                pax += f" (ages {', '.join(str(a) for a in booking.children_ages)})"
        parts.append(f"- Travellers: {pax}")

    if booking.budget_range and (booking.budget_range.min or booking.budget_range.max):
        currency = booking.budget_range.currency or "GBP"
        if booking.budget_range.min and booking.budget_range.max:
            parts.append(f"- Budget: {currency} {booking.budget_range.min:,.0f}–{booking.budget_range.max:,.0f}")
        elif booking.budget_range.max:
            parts.append(f"- Budget: up to {currency} {booking.budget_range.max:,.0f}")

    if booking.experience_type:
        parts.append(f"- Experience: {', '.join(booking.experience_type)}")

    if booking.special_occasion:
        parts.append(f"- Special occasion: {booking.special_occasion}")

    if booking.special_requests:
        parts.append(f"- Special requests: {booking.special_requests}")

    if booking.contact_name:
        parts.append(f"- Name: {booking.contact_name}")

    if booking.contact_email:
        parts.append(f"- Email: {booking.contact_email}")

    if booking.contact_phone:
        parts.append(f"- Phone: {booking.contact_phone}")

    return "\n".join(parts)


def build_progress(state: EnquiryState) -> dict:
    """Build progress data for the frontend widget."""
    total = len(REQUIRED_FIELDS)
    filled = len(state.filled_required)
    return {
        "phase": state.phase.value,
        "filled_count": filled,
        "total_required": total,
        "percentage": round((filled / total) * 100) if total else 0,
        "missing_fields": sorted(state.missing_required),
        "filled_fields": sorted(state.filled_required | state.filled_optional),
    }
