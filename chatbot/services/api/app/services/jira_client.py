"""
Jira Client
============
Creates and updates Jira tickets for booking enquiries and escalations.
"""

import logging
from base64 import b64encode
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(15.0, connect=5.0)


def _auth_header() -> dict:
    """Build Jira basic auth header."""
    if not settings.jira_email or not settings.jira_api_token:
        return {}
    credentials = f"{settings.jira_email}:{settings.jira_api_token}"
    encoded = b64encode(credentials.encode()).decode()
    return {
        "Authorization": f"Basic {encoded}",
        "Content-Type": "application/json",
    }


def is_configured() -> bool:
    """Check if Jira credentials are configured."""
    return bool(
        settings.jira_base_url
        and settings.jira_email
        and settings.jira_api_token
    )


async def create_ticket(
    summary: str,
    description: str,
    priority: str = "Medium",
    labels: list[str] = None,
    custom_fields: dict = None,
) -> Optional[str]:
    """
    Create a Jira ticket.

    Args:
        summary: Ticket title
        description: Ticket description (Jira ADF or plain text)
        priority: Priority name (Lowest, Low, Medium, High, Highest)
        labels: List of labels to apply
        custom_fields: Additional custom field values

    Returns:
        Jira ticket key (e.g., 'MAHT-123') or None on failure
    """
    if not is_configured():
        logger.warning("Jira is not configured — skipping ticket creation")
        return None

    # Build the issue payload
    fields = {
        "project": {"key": settings.jira_project_key},
        "issuetype": {"name": "Task"},
        "summary": summary,
        "description": {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": description}],
                }
            ],
        },
        "priority": {"name": priority},
    }

    if labels:
        fields["labels"] = labels

    if custom_fields:
        fields.update(custom_fields)

    payload = {"fields": fields}

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                f"{settings.jira_base_url}/rest/api/3/issue",
                headers=_auth_header(),
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            ticket_key = data.get("key", "")
            logger.info(f"Jira ticket created: {ticket_key}")
            return ticket_key
    except Exception as e:
        logger.error(f"Jira ticket creation failed: {e}")
        return None


async def update_ticket_status(
    ticket_key: str,
    transition_name: str,
) -> bool:
    """
    Transition a Jira ticket to a new status.

    Args:
        ticket_key: The ticket key (e.g., 'MAHT-123')
        transition_name: Name of the target transition

    Returns:
        True if successful
    """
    if not is_configured():
        return False

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            # First, get available transitions
            resp = await client.get(
                f"{settings.jira_base_url}/rest/api/3/issue/{ticket_key}/transitions",
                headers=_auth_header(),
            )
            resp.raise_for_status()
            transitions = resp.json().get("transitions", [])

            # Find the matching transition
            transition_id = None
            for t in transitions:
                if t["name"].lower() == transition_name.lower():
                    transition_id = t["id"]
                    break

            if not transition_id:
                logger.warning(
                    f"Transition '{transition_name}' not found for {ticket_key}. "
                    f"Available: {[t['name'] for t in transitions]}"
                )
                return False

            # Execute the transition
            resp = await client.post(
                f"{settings.jira_base_url}/rest/api/3/issue/{ticket_key}/transitions",
                headers=_auth_header(),
                json={"transition": {"id": transition_id}},
            )
            resp.raise_for_status()
            logger.info(f"Jira ticket {ticket_key} transitioned to '{transition_name}'")
            return True
    except Exception as e:
        logger.error(f"Jira transition failed for {ticket_key}: {e}")
        return False


async def add_comment(ticket_key: str, comment: str) -> bool:
    """Add a comment to a Jira ticket."""
    if not is_configured():
        return False

    payload = {
        "body": {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": comment}],
                }
            ],
        }
    }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(
                f"{settings.jira_base_url}/rest/api/3/issue/{ticket_key}/comment",
                headers=_auth_header(),
                json=payload,
            )
            resp.raise_for_status()
            logger.info(f"Comment added to {ticket_key}")
            return True
    except Exception as e:
        logger.error(f"Failed to add comment to {ticket_key}: {e}")
        return False


def build_enquiry_summary(
    destination: str,
    client_name: str,
    budget_info: str,
) -> str:
    """Build a standard Jira ticket summary for an enquiry."""
    parts = ["New Enquiry"]
    if destination:
        parts.append(destination)
    if client_name:
        parts.append(client_name)
    if budget_info:
        parts.append(f"({budget_info})")
    return ": ".join(parts[:2]) + (" - " + " ".join(parts[2:]) if len(parts) > 2 else "")
