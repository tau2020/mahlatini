-- ============================================
-- Migration: Add Gemini classification support
-- ============================================
-- Run this on existing databases to add the index for
-- enquiry classification events logged by the n8n workflow.
--
-- Safe to run multiple times (all statements are idempotent).
-- ============================================

-- Partial index for fast lookups of classification events
CREATE INDEX IF NOT EXISTS idx_analytics_enquiry_classified
    ON analytics_events (created_at DESC)
    WHERE event_type = 'enquiry_classified';

-- Partial index for n8n error events
CREATE INDEX IF NOT EXISTS idx_analytics_n8n_errors
    ON analytics_events (created_at DESC)
    WHERE event_type = 'n8n_error';

-- View: Enquiry classification summary (useful for Power BI / dashboards)
CREATE OR REPLACE VIEW v_enquiry_classifications AS
SELECT
    (payload->>'classification')::text AS gemini_classification,
    (payload->>'destination')::text AS destination,
    (payload->>'booking_stage')::text AS booking_stage,
    (payload->>'urgency')::text AS urgency,
    (payload->>'lead_score')::text AS lead_score,
    (payload->>'source')::text AS source,
    (payload->>'gemini_confidence')::float AS gemini_confidence,
    created_at
FROM analytics_events
WHERE event_type = 'enquiry_classified'
ORDER BY created_at DESC;

-- View: n8n error log
CREATE OR REPLACE VIEW v_n8n_errors AS
SELECT
    (payload->>'severity')::text AS severity,
    (payload->>'workflow_name')::text AS workflow_name,
    (payload->>'node_name')::text AS node_name,
    (payload->>'error_message')::text AS error_message,
    (payload->>'execution_id')::text AS execution_id,
    created_at
FROM analytics_events
WHERE event_type = 'n8n_error'
ORDER BY created_at DESC;
