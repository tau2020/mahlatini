"""
Tests for n8n integration: callback endpoint, lead capture, sub-workflow,
dead-letter queue, and HMAC verification.
"""

import asyncio
import hashlib
import hmac
import json
import os
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import httpx

# ─── App imports (after conftest sets env) ────────────────

from app.models.schemas import (
    BookingDetails,
    BudgetRange,
    IntentClassification,
    LeadScore,
    N8nCallbackRequest,
    N8nCallbackResponse,
)


# ─── Schema validation tests ─────────────────────────────

class TestN8nCallbackSchemas:
    """Test Pydantic schema validation for the new n8n callback models."""

    def test_valid_callback_request(self):
        req = N8nCallbackRequest(
            session_id="sess_123",
            conversation_id="conv_456",
            message="Your specialist will call you shortly.",
            message_type="notification",
            metadata={"specialist": "Sarah"},
        )
        assert req.session_id == "sess_123"
        assert req.message_type == "notification"
        assert req.metadata["specialist"] == "Sarah"

    def test_callback_request_default_type(self):
        req = N8nCallbackRequest(
            session_id="sess_123",
            conversation_id="conv_456",
            message="Hello",
        )
        assert req.message_type == "notification"
        assert req.metadata is None

    def test_callback_request_all_message_types(self):
        for msg_type in ("notification", "escalation_update", "itinerary", "agent_assigned"):
            req = N8nCallbackRequest(
                session_id="s",
                conversation_id="c",
                message="m",
                message_type=msg_type,
            )
            assert req.message_type == msg_type

    def test_callback_request_invalid_type_rejected(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            N8nCallbackRequest(
                session_id="s",
                conversation_id="c",
                message="m",
                message_type="invalid_type",
            )

    def test_callback_request_empty_session_rejected(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            N8nCallbackRequest(
                session_id="",
                conversation_id="c",
                message="m",
            )

    def test_callback_request_empty_message_rejected(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            N8nCallbackRequest(
                session_id="s",
                conversation_id="c",
                message="",
            )

    def test_callback_response(self):
        resp = N8nCallbackResponse(status="queued", session_id="sess_123")
        assert resp.status == "queued"
        assert resp.session_id == "sess_123"


# ─── HMAC verification tests ─────────────────────────────

class TestHMACVerification:
    """Test HMAC signature verification for the callback endpoint."""

    def test_verify_hmac_valid(self):
        from app.routers.chat import _verify_hmac

        body = b'{"session_id":"s","message":"hello"}'
        secret = "test-secret-key"
        sig = "sha256=" + hmac.new(
            secret.encode(), body, hashlib.sha256
        ).hexdigest()

        assert _verify_hmac(body, sig) is True

    def test_verify_hmac_invalid(self):
        from app.routers.chat import _verify_hmac

        body = b'{"session_id":"s","message":"hello"}'
        assert _verify_hmac(body, "sha256=badhash") is False

    def test_verify_hmac_no_secret_configured(self):
        from app.routers.chat import _verify_hmac

        with patch("app.routers.chat.settings") as mock_settings:
            mock_settings.n8n_webhook_secret = ""
            body = b'{"anything":"here"}'
            assert _verify_hmac(body, "") is True

    def test_verify_hmac_empty_signature_with_secret(self):
        from app.routers.chat import _verify_hmac

        body = b'{"data":"test"}'
        # When secret is configured, empty signature should fail
        assert _verify_hmac(body, "") is False


# ─── n8n callback endpoint tests (using FastAPI TestClient) ─

class TestN8nCallbackEndpoint:
    """Test the POST /api/chat/n8n-callback endpoint."""

    @pytest.fixture
    def client(self):
        """Create a FastAPI TestClient with mocked dependencies."""
        from fastapi.testclient import TestClient
        from app.main import app
        return TestClient(app)

    def _sign(self, body: bytes, secret: str = "test-secret-key") -> str:
        return "sha256=" + hmac.new(
            secret.encode(), body, hashlib.sha256
        ).hexdigest()

    def test_callback_queues_message(self, client):
        from app.routers.chat import _n8n_pending

        payload = {
            "session_id": "test_sess_1",
            "conversation_id": "conv_abc",
            "message": "Your specialist is Sarah.",
            "message_type": "agent_assigned",
            "metadata": {"specialist_name": "Sarah"},
        }
        body = json.dumps(payload).encode()
        sig = self._sign(body)

        response = client.post(
            "/api/chat/n8n-callback",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Signature": sig,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "queued"
        assert data["session_id"] == "test_sess_1"

        # Verify it was actually queued
        pending = _n8n_pending.get("test_sess_1", [])
        assert len(pending) >= 1
        assert pending[-1]["message"] == "Your specialist is Sarah."
        assert pending[-1]["message_type"] == "agent_assigned"

        # Clean up
        _n8n_pending.pop("test_sess_1", None)

    def test_callback_rejects_bad_signature(self, client):
        payload = {
            "session_id": "s",
            "conversation_id": "c",
            "message": "test",
        }
        body = json.dumps(payload).encode()

        response = client.post(
            "/api/chat/n8n-callback",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Signature": "sha256=definitely_wrong",
            },
        )

        assert response.status_code == 401

    def test_callback_rejects_invalid_payload(self, client):
        body = json.dumps({"session_id": "", "message": ""}).encode()
        sig = self._sign(body)

        response = client.post(
            "/api/chat/n8n-callback",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Signature": sig,
            },
        )

        assert response.status_code == 422  # Pydantic validation error


# ─── Pending messages polling endpoint ────────────────────

class TestPendingMessagesEndpoint:
    """Test the GET /api/chat/n8n-pending/{session_id} endpoint."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from app.main import app
        return TestClient(app)

    def test_get_pending_empty(self, client):
        response = client.get("/api/chat/n8n-pending/nonexistent_session")
        assert response.status_code == 200
        data = response.json()
        assert data["messages"] == []
        assert data["count"] == 0

    def test_get_pending_drains_queue(self, client):
        from app.routers.chat import _n8n_pending

        # Seed some pending messages
        _n8n_pending["drain_test"] = [
            {"message": "msg1", "message_type": "notification", "metadata": {}, "conversation_id": "c", "timestamp": "t"},
            {"message": "msg2", "message_type": "itinerary", "metadata": {}, "conversation_id": "c", "timestamp": "t"},
        ]

        response = client.get("/api/chat/n8n-pending/drain_test")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert data["messages"][0]["message"] == "msg1"
        assert data["messages"][1]["message"] == "msg2"

        # Second call should be empty (drained)
        response2 = client.get("/api/chat/n8n-pending/drain_test")
        assert response2.json()["count"] == 0


# ─── Lead capture shared helper tests ────────────────────

class TestProcessLeadCapture:
    """Test the _process_lead_capture shared helper."""

    @pytest.fixture
    def mock_session(self):
        return {
            "conversation_id": "test-conv-id",
            "messages": [
                {"role": "user", "content": "I want a safari in Botswana"},
                {"role": "assistant", "content": "Great choice!"},
                {"role": "user", "content": "For 2 adults, June 2026"},
                {"role": "assistant", "content": "Let me help you."},
                {"role": "user", "content": "Budget around 10000 GBP"},
                {"role": "assistant", "content": "Excellent."},
            ],
            "lead_scored": False,
        }

    @pytest.fixture
    def mock_classification(self):
        return IntentClassification(
            primary_intent="booking_intent",
            booking_stage="considering",
            urgency="medium",
            sentiment="positive",
        )

    @pytest.mark.asyncio
    async def test_lead_capture_triggers_on_booking_intent(self, mock_session, mock_classification):
        from app.routers.chat import _process_lead_capture

        booking = BookingDetails(
            destination="Botswana",
            contact_email="test@example.com",
        )

        lead = LeadScore(total_score=55, classification="standard", breakdown={})

        with patch("app.routers.chat._extract_booking", new_callable=AsyncMock, return_value=booking), \
             patch("app.routers.chat.score_lead", return_value=lead), \
             patch("app.services.n8n_client.send_new_enquiry", new_callable=AsyncMock, return_value=True) as mock_send:

            result = await _process_lead_capture(mock_session, "sess_1", mock_classification)

            assert result is True
            mock_send.assert_called_once()
            assert mock_session["lead_scored"] is True

    @pytest.mark.asyncio
    async def test_lead_capture_skips_low_score(self, mock_session, mock_classification):
        from app.routers.chat import _process_lead_capture

        booking = BookingDetails(destination="Kenya")
        lead = LeadScore(total_score=20, classification="standard", breakdown={})

        with patch("app.routers.chat._extract_booking", new_callable=AsyncMock, return_value=booking), \
             patch("app.routers.chat.score_lead", return_value=lead), \
             patch("app.services.n8n_client.send_new_enquiry", new_callable=AsyncMock) as mock_send:

            result = await _process_lead_capture(mock_session, "sess_1", mock_classification)

            # Booking was extracted but score too low for n8n
            assert result is True  # lead was captured (booking extracted)
            mock_send.assert_not_called()
            assert mock_session["lead_scored"] is False

    @pytest.mark.asyncio
    async def test_lead_capture_skips_already_scored(self, mock_session, mock_classification):
        from app.routers.chat import _process_lead_capture

        mock_session["lead_scored"] = True
        booking = BookingDetails(destination="Tanzania", contact_email="t@t.com")
        lead = LeadScore(total_score=75, classification="high_value", breakdown={})

        with patch("app.routers.chat._extract_booking", new_callable=AsyncMock, return_value=booking), \
             patch("app.routers.chat.score_lead", return_value=lead), \
             patch("app.services.n8n_client.send_new_enquiry", new_callable=AsyncMock) as mock_send:

            result = await _process_lead_capture(mock_session, "sess_1", mock_classification)
            mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_lead_capture_triggers_high_value_alert(self, mock_session, mock_classification):
        from app.routers.chat import _process_lead_capture

        booking = BookingDetails(
            destination="Maldives",
            contact_email="vip@example.com",
            budget_range=BudgetRange(min=20000, max=50000, currency="GBP"),
        )
        lead = LeadScore(total_score=90, classification="vip", breakdown={})

        with patch("app.routers.chat._extract_booking", new_callable=AsyncMock, return_value=booking), \
             patch("app.routers.chat.score_lead", return_value=lead), \
             patch("app.services.n8n_client.send_new_enquiry", new_callable=AsyncMock, return_value=True), \
             patch("app.services.n8n_client.send_high_value_alert", new_callable=AsyncMock, return_value=True) as mock_alert:

            result = await _process_lead_capture(mock_session, "sess_1", mock_classification)

            assert result is True
            mock_alert.assert_called_once()

    @pytest.mark.asyncio
    async def test_lead_capture_skips_irrelevant_intent(self):
        from app.routers.chat import _process_lead_capture

        session = {
            "conversation_id": "c",
            "messages": [{"role": "user", "content": "hi"}],
            "lead_scored": False,
        }
        classification = IntentClassification(
            primary_intent="off_topic",
            booking_stage="browsing",
        )

        with patch("app.routers.chat._extract_booking", new_callable=AsyncMock) as mock_extract:
            result = await _process_lead_capture(session, "sess_1", classification)

            assert result is False
            mock_extract.assert_not_called()

    @pytest.mark.asyncio
    async def test_lead_capture_triggers_on_message_count(self):
        from app.routers.chat import _process_lead_capture

        session = {
            "conversation_id": "c",
            "messages": [{"role": "user", "content": f"msg {i}"} for i in range(7)],
            "lead_scored": False,
        }
        classification = IntentClassification(
            primary_intent="general_enquiry",
            booking_stage="browsing",
        )

        with patch("app.routers.chat._extract_booking", new_callable=AsyncMock, return_value=None):
            result = await _process_lead_capture(session, "sess_1", classification)
            # Triggered by message count but no booking extracted
            assert result is False


# ─── n8n_client tests ────────────────────────────────────

class TestN8nClient:
    """Test n8n_client functions: sub-workflow execution, dead-letter queue."""

    @pytest.mark.asyncio
    async def test_execute_subworkflow_success(self):
        from app.services.n8n_client import execute_subworkflow

        mock_response = httpx.Response(
            200,
            json={"available": True, "price": 2500},
            request=httpx.Request("POST", "http://test/webhook/check"),
        )

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
            result = await execute_subworkflow("/webhook/check", {"lodge": "Mombo"})

            assert result is not None
            assert result["available"] is True
            assert result["price"] == 2500

    @pytest.mark.asyncio
    async def test_execute_subworkflow_timeout(self):
        from app.services.n8n_client import execute_subworkflow

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=httpx.TimeoutException("timeout")):
            result = await execute_subworkflow("/webhook/check", {}, timeout=1.0)
            assert result is None

    @pytest.mark.asyncio
    async def test_execute_subworkflow_error_status(self):
        from app.services.n8n_client import execute_subworkflow

        mock_response = httpx.Response(
            500,
            text="Internal Server Error",
            request=httpx.Request("POST", "http://test/webhook/check"),
        )

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
            result = await execute_subworkflow("/webhook/check", {})
            assert result is None

    @pytest.mark.asyncio
    async def test_dead_letter_queue_stores_payload(self):
        from app.services.n8n_client import _queue_failed_webhook

        mock_redis = AsyncMock()
        mock_redis.lpush = AsyncMock()
        mock_redis.close = AsyncMock()

        with patch("redis.asyncio.from_url", return_value=mock_redis):
            await _queue_failed_webhook("/webhook/test", {"key": "value"})

            mock_redis.lpush.assert_called_once()
            call_args = mock_redis.lpush.call_args
            assert call_args[0][0] == "n8n:dead_letter"
            stored = json.loads(call_args[0][1])
            assert stored["path"] == "/webhook/test"
            assert stored["payload"] == {"key": "value"}
            assert "failed_at" in stored

    @pytest.mark.asyncio
    async def test_dead_letter_queue_handles_redis_failure(self):
        from app.services.n8n_client import _queue_failed_webhook

        with patch("redis.asyncio.from_url", side_effect=Exception("Redis down")):
            # Should not raise — just log
            await _queue_failed_webhook("/webhook/test", {"key": "value"})

    @pytest.mark.asyncio
    async def test_send_webhook_queues_on_failure(self):
        from app.services.n8n_client import _send_webhook

        mock_response = httpx.Response(
            400,
            text="Bad Request",
            request=httpx.Request("POST", "http://test/webhook/test"),
        )

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response), \
             patch("app.services.n8n_client._queue_failed_webhook", new_callable=AsyncMock) as mock_queue:

            result = await _send_webhook("/webhook/test", {"data": "test"}, retries=1)

            assert result is False
            mock_queue.assert_called_once_with("/webhook/test", {"data": "test"})


# ─── HMAC signing tests ──────────────────────────────────

class TestHMACSigning:
    """Test the existing _sign_payload function."""

    def test_sign_payload_with_secret(self):
        from app.services.n8n_client import _sign_payload

        payload = {"key": "value"}
        sig = _sign_payload(payload)

        # With test-secret-key from conftest
        assert sig.startswith("sha256=")
        assert len(sig) > 10

    def test_sign_payload_deterministic(self):
        from app.services.n8n_client import _sign_payload

        payload = {"a": 1, "b": 2}
        sig1 = _sign_payload(payload)
        sig2 = _sign_payload(payload)
        assert sig1 == sig2

    def test_sign_payload_no_secret(self):
        from app.services.n8n_client import _sign_payload

        with patch("app.services.n8n_client.settings") as mock_settings:
            mock_settings.n8n_webhook_secret = ""
            sig = _sign_payload({"key": "value"})
            assert sig == ""
