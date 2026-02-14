"""
Lead Scorer
============
Scores leads 0–100 based on weighted criteria and classifies them
into categories (VIP, high-value, corporate, urgent, etc.).
"""

import logging
from datetime import date, timedelta
from typing import Optional

from app.models.schemas import BookingDetails, LeadScore

logger = logging.getLogger(__name__)

# ─── Scoring weights (must sum to 1.0) ───────────────────
WEIGHTS = {
    "budget": 0.25,
    "booking_stage": 0.20,
    "date_specificity": 0.15,
    "contact_details": 0.15,
    "engagement": 0.10,
    "repeat_customer": 0.10,
    "group_size": 0.05,
}


def _score_budget(booking: BookingDetails) -> int:
    """Score based on indicated budget (normalised to GBP)."""
    budget_max = None
    if booking.budget_range and booking.budget_range.max:
        budget_max = booking.budget_range.max
        currency = (booking.budget_range.currency or "GBP").upper()
        # Rough normalisation to GBP
        fx = {"GBP": 1.0, "USD": 0.79, "EUR": 0.86, "ZAR": 0.042}
        budget_max *= fx.get(currency, 1.0)

    if budget_max is None:
        return 30  # unknown — assume moderate
    if budget_max > 15000:
        return 100
    if budget_max > 8000:
        return 75
    if budget_max > 4000:
        return 50
    return 25


def _score_booking_stage(stage: str) -> int:
    """Score based on how close to booking."""
    stages = {
        "ready_to_book": 100,
        "considering": 60,
        "browsing": 20,
        "booked_followup": 40,
    }
    return stages.get(stage, 20)


def _score_date_specificity(booking: BookingDetails) -> int:
    """Score based on how specific the travel dates are."""
    if booking.travel_dates and booking.travel_dates.start:
        return 100  # exact dates
    if booking.travel_month:
        return 60   # month mentioned
    if booking.duration_days:
        return 40   # duration known but no date
    return 10       # no date info


def _score_contact_details(booking: BookingDetails) -> int:
    """Score based on contact info provided."""
    score = 0
    if booking.contact_email:
        score += 60
    if booking.contact_phone:
        score += 40
    if booking.contact_name and not booking.contact_email and not booking.contact_phone:
        score = 30
    return min(score, 100)


def _score_engagement(message_count: int) -> int:
    """Score based on conversation depth."""
    if message_count > 10:
        return 100
    if message_count > 5:
        return 60
    if message_count > 2:
        return 30
    return 10


def _score_repeat(is_repeat: bool) -> int:
    """Score based on repeat customer status."""
    return 100 if is_repeat else 30


def _score_group_size(booking: BookingDetails) -> int:
    """Score based on party size."""
    total = (booking.num_adults or 0) + (booking.num_children or 0)
    if total >= 6:
        return 100
    if total >= 4:
        return 70
    if total >= 2:
        return 50
    if total == 1:
        return 30
    return 20  # unknown


def _classify(
    total_score: int,
    booking: BookingDetails,
    booking_stage: str,
) -> str:
    """Determine client classification from score and attributes."""
    lower_requests = (booking.special_requests or "").lower()
    lower_occasion = (booking.special_occasion or "").lower()

    # Check urgency first
    if booking.travel_dates and booking.travel_dates.start:
        days_until = (booking.travel_dates.start - date.today()).days
        if days_until <= 7:
            return "urgent"

    # Corporate keywords
    corporate_kw = {"corporate", "team building", "conference", "incentive", "company"}
    if any(kw in lower_requests for kw in corporate_kw):
        total_pax = (booking.num_adults or 0) + (booking.num_children or 0)
        if total_pax >= 8:
            return "corporate"

    # VIP
    if total_score >= 85:
        return "vip"

    # High-value
    if total_score >= 65:
        return "high_value"

    # Honeymoon / special occasion
    if lower_occasion in ("honeymoon", "anniversary", "proposal"):
        return "honeymoon"

    # Family
    if booking.num_children and booking.num_children > 0:
        return "family"

    # Standard
    return "standard"


def score_lead(
    booking: BookingDetails,
    booking_stage: str = "browsing",
    message_count: int = 1,
    is_repeat_customer: bool = False,
) -> LeadScore:
    """
    Score a lead 0–100 and classify them.

    Args:
        booking: Extracted booking details
        booking_stage: Current stage (browsing, considering, ready_to_book)
        message_count: Number of messages in conversation
        is_repeat_customer: Whether client is a returning customer

    Returns:
        LeadScore with total, classification, and breakdown
    """
    breakdown = {
        "budget": _score_budget(booking),
        "booking_stage": _score_booking_stage(booking_stage),
        "date_specificity": _score_date_specificity(booking),
        "contact_details": _score_contact_details(booking),
        "engagement": _score_engagement(message_count),
        "repeat_customer": _score_repeat(is_repeat_customer),
        "group_size": _score_group_size(booking),
    }

    # Weighted sum
    total = sum(
        breakdown[key] * WEIGHTS[key]
        for key in WEIGHTS
    )
    total = round(total)

    classification = _classify(total, booking, booking_stage)

    return LeadScore(
        total_score=total,
        classification=classification,
        breakdown=breakdown,
    )
