-- ═══════════════════════════════════════════════════════════════════════
-- create_powerbi_aggregates.sql
-- Creates real-time aggregate tables for Power BI streaming dashboard
--
-- These tables are automatically updated via triggers whenever new leads arrive
-- n8n reads from these tables and pushes to Power BI streaming dataset
--
-- Usage:
--   docker exec -i chatbot-postgres-1 psql -U mahlatini -d mahlatini_chatbot < scripts/create_powerbi_aggregates.sql
-- ═══════════════════════════════════════════════════════════════════════

-- ==========================
-- 1. REAL-TIME KPI TABLE
-- ==========================
-- Single-row table with current KPIs (updated on every insert)
CREATE TABLE IF NOT EXISTS powerbi_realtime_kpis (
    id INTEGER PRIMARY KEY DEFAULT 1,

    -- Core metrics
    total_enquiries INTEGER DEFAULT 0,
    total_pipeline_value NUMERIC(12,2) DEFAULT 0,
    avg_lead_score NUMERIC(5,2) DEFAULT 0,
    avg_response_time_secs NUMERIC(8,2) DEFAULT 0,
    avg_classification_confidence NUMERIC(4,3) DEFAULT 0,
    avg_pax_total NUMERIC(5,2) DEFAULT 0,

    -- Last hour metrics
    enquiries_last_hour INTEGER DEFAULT 0,
    pipeline_last_hour NUMERIC(12,2) DEFAULT 0,

    -- Classification breakdown (all time)
    count_immediate INTEGER DEFAULT 0,
    count_important INTEGER DEFAULT 0,
    count_not_important INTEGER DEFAULT 0,

    -- Source breakdown (all time)
    count_website INTEGER DEFAULT 0,
    count_chatbot INTEGER DEFAULT 0,

    -- Booking stage breakdown (all time)
    count_considering INTEGER DEFAULT 0,
    count_enquiring INTEGER DEFAULT 0,
    count_shortlisting INTEGER DEFAULT 0,
    count_closed_lost INTEGER DEFAULT 0,

    -- Timestamps
    last_updated_at TIMESTAMPTZ DEFAULT NOW(),
    last_enquiry_at TIMESTAMPTZ,

    -- Ensure only one row
    CONSTRAINT single_row_check CHECK (id = 1)
);

-- Initialize the single row
INSERT INTO powerbi_realtime_kpis (id) VALUES (1)
ON CONFLICT (id) DO NOTHING;

-- ==========================
-- 2. HOURLY BREAKDOWN TABLE
-- ==========================
-- Rolling window of last 24 hours (one row per hour)
CREATE TABLE IF NOT EXISTS powerbi_hourly_metrics (
    hour_bucket TIMESTAMPTZ PRIMARY KEY,

    enquiry_count INTEGER DEFAULT 0,
    pipeline_value NUMERIC(12,2) DEFAULT 0,
    avg_lead_score NUMERIC(5,2) DEFAULT 0,
    avg_response_time NUMERIC(8,2) DEFAULT 0,

    count_immediate INTEGER DEFAULT 0,
    count_important INTEGER DEFAULT 0,
    count_not_important INTEGER DEFAULT 0,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS idx_hourly_metrics_bucket
    ON powerbi_hourly_metrics(hour_bucket DESC);

-- ==========================
-- 3. TOP DESTINATIONS TABLE
-- ==========================
-- Current top 10 destinations by enquiry count
CREATE TABLE IF NOT EXISTS powerbi_top_destinations (
    destination VARCHAR(128) PRIMARY KEY,

    enquiry_count INTEGER DEFAULT 0,
    pipeline_value NUMERIC(12,2) DEFAULT 0,
    avg_lead_score NUMERIC(5,2) DEFAULT 0,

    last_enquiry_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ==========================
-- 4. AGENT PERFORMANCE TABLE
-- ==========================
-- Real-time agent metrics
CREATE TABLE IF NOT EXISTS powerbi_agent_performance (
    agent_name VARCHAR(128) PRIMARY KEY,

    total_enquiries INTEGER DEFAULT 0,
    pipeline_value NUMERIC(12,2) DEFAULT 0,
    avg_lead_score NUMERIC(5,2) DEFAULT 0,

    count_immediate INTEGER DEFAULT 0,
    count_important INTEGER DEFAULT 0,
    count_not_important INTEGER DEFAULT 0,

    last_activity_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ==========================
-- 5. TRIGGER FUNCTION: Update Aggregates
-- ==========================
CREATE OR REPLACE FUNCTION update_powerbi_aggregates()
RETURNS TRIGGER AS $$
DECLARE
    hour_bucket_ts TIMESTAMPTZ;
BEGIN
    -- Calculate hour bucket for the new enquiry
    hour_bucket_ts := date_trunc('hour', NEW.created_at);

    -- ==================
    -- Update KPI Table
    -- ==================
    UPDATE powerbi_realtime_kpis SET
        total_enquiries = (SELECT COUNT(*) FROM leads),
        total_pipeline_value = (SELECT COALESCE(SUM(budget_max), 0) FROM leads WHERE booking_stage != 'closed_lost'),
        avg_lead_score = (SELECT COALESCE(AVG(lead_score), 0) FROM leads),
        avg_response_time_secs = (
            SELECT COALESCE(AVG(response_time_avg_ms), 0) / 1000
            FROM conversations
            WHERE response_time_avg_ms IS NOT NULL
        ),
        avg_classification_confidence = (
            SELECT COALESCE(AVG((payload->>'classificationConfidence')::NUMERIC), 0)
            FROM analytics_events
            WHERE event_type = 'classification'
        ),
        avg_pax_total = (SELECT COALESCE(AVG(pax_adults + COALESCE(pax_children, 0)), 0) FROM leads),

        -- Last hour metrics
        enquiries_last_hour = (
            SELECT COUNT(*) FROM leads
            WHERE created_at >= NOW() - INTERVAL '1 hour'
        ),
        pipeline_last_hour = (
            SELECT COALESCE(SUM(budget_max), 0) FROM leads
            WHERE created_at >= NOW() - INTERVAL '1 hour'
            AND booking_stage != 'closed_lost'
        ),

        -- Classification breakdown
        count_immediate = (SELECT COUNT(*) FROM leads WHERE classification = 'IMMEDIATE'),
        count_important = (SELECT COUNT(*) FROM leads WHERE classification = 'IMPORTANT'),
        count_not_important = (SELECT COUNT(*) FROM leads WHERE classification = 'NOT_IMPORTANT'),

        -- Source breakdown
        count_website = (
            SELECT COUNT(*) FROM conversations
            WHERE source_page LIKE '%website%' OR source_page = 'website_form'
        ),
        count_chatbot = (
            SELECT COUNT(*) FROM conversations
            WHERE source_page NOT LIKE '%website%' AND source_page != 'website_form'
        ),

        -- Booking stage breakdown
        count_considering = (SELECT COUNT(*) FROM leads WHERE booking_stage = 'considering'),
        count_enquiring = (SELECT COUNT(*) FROM leads WHERE booking_stage = 'enquiring'),
        count_shortlisting = (SELECT COUNT(*) FROM leads WHERE booking_stage = 'shortlisting'),
        count_closed_lost = (SELECT COUNT(*) FROM leads WHERE booking_stage = 'closed_lost'),

        last_updated_at = NOW(),
        last_enquiry_at = NEW.created_at
    WHERE id = 1;

    -- ==================
    -- Update Hourly Metrics
    -- ==================
    INSERT INTO powerbi_hourly_metrics (
        hour_bucket,
        enquiry_count,
        pipeline_value,
        avg_lead_score,
        avg_response_time
    )
    SELECT
        hour_bucket_ts,
        COUNT(*),
        COALESCE(SUM(l.budget_max), 0),
        COALESCE(AVG(l.lead_score), 0),
        COALESCE(AVG(c.response_time_avg_ms), 0) / 1000
    FROM leads l
    LEFT JOIN conversations c ON c.id = l.conversation_id
    WHERE date_trunc('hour', l.created_at) = hour_bucket_ts
    ON CONFLICT (hour_bucket) DO UPDATE SET
        enquiry_count = EXCLUDED.enquiry_count,
        pipeline_value = EXCLUDED.pipeline_value,
        avg_lead_score = EXCLUDED.avg_lead_score,
        avg_response_time = EXCLUDED.avg_response_time;

    -- Clean up old hourly data (keep last 24 hours)
    DELETE FROM powerbi_hourly_metrics
    WHERE hour_bucket < NOW() - INTERVAL '24 hours';

    -- ==================
    -- Update Top Destinations
    -- ==================
    INSERT INTO powerbi_top_destinations (
        destination,
        enquiry_count,
        pipeline_value,
        avg_lead_score,
        last_enquiry_at,
        updated_at
    )
    VALUES (
        NEW.destination,
        1,
        COALESCE(NEW.budget_max, 0),
        NEW.lead_score,
        NEW.created_at,
        NOW()
    )
    ON CONFLICT (destination) DO UPDATE SET
        enquiry_count = (SELECT COUNT(*) FROM leads WHERE destination = EXCLUDED.destination),
        pipeline_value = (SELECT COALESCE(SUM(budget_max), 0) FROM leads WHERE destination = EXCLUDED.destination),
        avg_lead_score = (SELECT AVG(lead_score) FROM leads WHERE destination = EXCLUDED.destination),
        last_enquiry_at = GREATEST(powerbi_top_destinations.last_enquiry_at, EXCLUDED.last_enquiry_at),
        updated_at = NOW();

    -- ==================
    -- Update Agent Performance
    -- ==================
    IF NEW.assigned_agent IS NOT NULL THEN
        INSERT INTO powerbi_agent_performance (
            agent_name,
            total_enquiries,
            pipeline_value,
            avg_lead_score,
            count_immediate,
            count_important,
            count_not_important,
            last_activity_at,
            updated_at
        )
        VALUES (
            NEW.assigned_agent,
            1,
            COALESCE(NEW.budget_max, 0),
            NEW.lead_score,
            CASE WHEN NEW.classification = 'IMMEDIATE' THEN 1 ELSE 0 END,
            CASE WHEN NEW.classification = 'IMPORTANT' THEN 1 ELSE 0 END,
            CASE WHEN NEW.classification = 'NOT_IMPORTANT' THEN 1 ELSE 0 END,
            NEW.created_at,
            NOW()
        )
        ON CONFLICT (agent_name) DO UPDATE SET
            total_enquiries = (SELECT COUNT(*) FROM leads WHERE assigned_agent = EXCLUDED.agent_name),
            pipeline_value = (SELECT COALESCE(SUM(budget_max), 0) FROM leads WHERE assigned_agent = EXCLUDED.agent_name),
            avg_lead_score = (SELECT AVG(lead_score) FROM leads WHERE assigned_agent = EXCLUDED.agent_name),
            count_immediate = (SELECT COUNT(*) FROM leads WHERE assigned_agent = EXCLUDED.agent_name AND classification = 'IMMEDIATE'),
            count_important = (SELECT COUNT(*) FROM leads WHERE assigned_agent = EXCLUDED.agent_name AND classification = 'IMPORTANT'),
            count_not_important = (SELECT COUNT(*) FROM leads WHERE assigned_agent = EXCLUDED.agent_name AND classification = 'NOT_IMPORTANT'),
            last_activity_at = GREATEST(powerbi_agent_performance.last_activity_at, EXCLUDED.last_activity_at),
            updated_at = NOW();
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ==========================
-- 6. ATTACH TRIGGER
-- ==========================
DROP TRIGGER IF EXISTS trigger_update_powerbi_aggregates ON leads;

CREATE TRIGGER trigger_update_powerbi_aggregates
    AFTER INSERT ON leads
    FOR EACH ROW
    EXECUTE FUNCTION update_powerbi_aggregates();

-- ==========================
-- 7. INITIAL POPULATION
-- ==========================
-- Populate tables with existing data
DO $$
BEGIN
    -- Trigger function on existing leads to populate tables
    -- (For initial setup only)
    IF (SELECT COUNT(*) FROM leads) > 0 THEN
        RAISE NOTICE 'Populating aggregate tables from existing leads...';

        -- Force recalculation by updating a dummy field
        UPDATE leads SET updated_at = updated_at WHERE id IS NOT NULL LIMIT 1;
    END IF;
END $$;

-- ==========================
-- 8. VALIDATION
-- ==========================
SELECT
    'powerbi_realtime_kpis' AS table_name,
    total_enquiries,
    total_pipeline_value,
    avg_lead_score,
    last_updated_at
FROM powerbi_realtime_kpis;

SELECT
    'powerbi_top_destinations' AS table_name,
    COUNT(*) AS destination_count,
    SUM(enquiry_count) AS total_enquiries
FROM powerbi_top_destinations;

SELECT
    'powerbi_agent_performance' AS table_name,
    COUNT(*) AS agent_count,
    SUM(total_enquiries) AS total_enquiries
FROM powerbi_agent_performance;

SELECT 'Power BI aggregate tables created successfully' AS status;
