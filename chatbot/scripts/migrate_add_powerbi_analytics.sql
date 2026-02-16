-- ═══════════════════════════════════════════════════════════════════════
-- migrate_add_powerbi_analytics.sql
-- Creates Power BI analytics dimension tables and views
--
-- This migration adds:
-- 1. dim_agents (agent dimension with email for RLS)
-- 2. dim_date (date dimension for time intelligence)
-- 3. sla_targets (SLA benchmark targets)
-- 4. Enhanced analytical views for Power BI
--
-- Safe to run multiple times (idempotent).
--
-- Usage:
--   docker exec -i chatbot-postgres-1 psql -U mahlatini -d mahlatini_chatbot < scripts/migrate_add_powerbi_analytics.sql
-- ═══════════════════════════════════════════════════════════════════════

-- ==========================
-- 1. DIMENSION: dim_agents
-- ==========================
CREATE TABLE IF NOT EXISTS dim_agents (
    agent_id SERIAL PRIMARY KEY,
    agent_name VARCHAR(128) NOT NULL UNIQUE,
    agent_email VARCHAR(256),
    manager_email VARCHAR(256),
    department VARCHAR(64),
    is_active BOOLEAN DEFAULT TRUE,
    hire_date DATE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Seed with existing agents (extracted from leads.assigned_agent)
INSERT INTO dim_agents (agent_name, agent_email, manager_email, department, is_active)
VALUES
    ('Sarah Johnson', 'sarah.johnson@mahlatini.com', 'saleshead@mahlatini.com', 'Sales', TRUE),
    ('Mark Trader', 'mark.trader@mahlatini.com', 'saleshead@mahlatini.com', 'Sales', TRUE)
ON CONFLICT (agent_name) DO NOTHING;

-- ==========================
-- 2. DIMENSION: dim_date
-- ==========================
CREATE TABLE IF NOT EXISTS dim_date (
    date_key INTEGER PRIMARY KEY,
    date_full DATE NOT NULL UNIQUE,
    year INTEGER NOT NULL,
    quarter INTEGER NOT NULL CHECK (quarter BETWEEN 1 AND 4),
    month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
    month_name VARCHAR(20) NOT NULL,
    week INTEGER NOT NULL CHECK (week BETWEEN 1 AND 53),
    day_of_month INTEGER NOT NULL CHECK (day_of_month BETWEEN 1 AND 31),
    day_of_week INTEGER NOT NULL CHECK (day_of_week BETWEEN 1 AND 7),
    day_name VARCHAR(20) NOT NULL,
    is_weekend BOOLEAN NOT NULL,
    is_business_day BOOLEAN NOT NULL,
    fiscal_year INTEGER NOT NULL,
    fiscal_quarter INTEGER NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Populate date dimension (2024-2028, ~1,827 days)
DO $$
DECLARE
    start_date DATE := '2024-01-01';
    end_date DATE := '2028-12-31';
    current_date_iter DATE;
    fiscal_year_val INTEGER;
    fiscal_quarter_val INTEGER;
BEGIN
    current_date_iter := start_date;
    WHILE current_date_iter <= end_date LOOP
        -- Calculate fiscal year (April 1 start)
        IF EXTRACT(MONTH FROM current_date_iter) >= 4 THEN
            fiscal_year_val := EXTRACT(YEAR FROM current_date_iter);
        ELSE
            fiscal_year_val := EXTRACT(YEAR FROM current_date_iter) - 1;
        END IF;

        -- Calculate fiscal quarter
        fiscal_quarter_val := CASE
            WHEN EXTRACT(MONTH FROM current_date_iter) BETWEEN 4 AND 6 THEN 1
            WHEN EXTRACT(MONTH FROM current_date_iter) BETWEEN 7 AND 9 THEN 2
            WHEN EXTRACT(MONTH FROM current_date_iter) BETWEEN 10 AND 12 THEN 3
            ELSE 4
        END;

        INSERT INTO dim_date (
            date_key,
            date_full,
            year,
            quarter,
            month,
            month_name,
            week,
            day_of_month,
            day_of_week,
            day_name,
            is_weekend,
            is_business_day,
            fiscal_year,
            fiscal_quarter
        ) VALUES (
            TO_CHAR(current_date_iter, 'YYYYMMDD')::INTEGER,
            current_date_iter,
            EXTRACT(YEAR FROM current_date_iter),
            EXTRACT(QUARTER FROM current_date_iter),
            EXTRACT(MONTH FROM current_date_iter),
            TO_CHAR(current_date_iter, 'Month'),
            EXTRACT(WEEK FROM current_date_iter),
            EXTRACT(DAY FROM current_date_iter),
            EXTRACT(ISODOW FROM current_date_iter),
            TO_CHAR(current_date_iter, 'Day'),
            EXTRACT(ISODOW FROM current_date_iter) IN (6, 7),
            EXTRACT(ISODOW FROM current_date_iter) NOT IN (6, 7),
            fiscal_year_val,
            fiscal_quarter_val
        ) ON CONFLICT (date_full) DO NOTHING;

        current_date_iter := current_date_iter + INTERVAL '1 day';
    END LOOP;
END $$;

-- ==========================
-- 3. DIMENSION: sla_targets
-- ==========================
CREATE TABLE IF NOT EXISTS sla_targets (
    classification VARCHAR(32) PRIMARY KEY,
    response_hours NUMERIC(5,2) NOT NULL,
    resolution_days INTEGER NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO sla_targets (classification, response_hours, resolution_days, description) VALUES
    ('IMMEDIATE', 0.25, 1, 'Urgent enquiries: 15-minute response, 1-day resolution'),
    ('IMPORTANT', 2.0, 3, 'High-value enquiries: 2-hour response, 3-day resolution'),
    ('NOT_IMPORTANT', 24.0, 7, 'Standard enquiries: 24-hour response, 7-day resolution')
ON CONFLICT (classification) DO NOTHING;

-- ==========================
-- 4. ANALYTICAL VIEW: v_powerbi_enquiry_fact
-- ==========================
CREATE OR REPLACE VIEW v_powerbi_enquiry_fact AS
SELECT
    -- Primary keys
    l.id AS enquiry_id,
    TO_CHAR(l.created_at, 'YYYYMMDD')::INTEGER AS date_key,

    -- Enquiry details
    l.destination,
    l.destination_region,
    l.classification,
    l.urgency,
    l.lead_score,
    l.booking_stage,
    l.assigned_agent,

    -- Financial metrics
    l.budget_min,
    l.budget_max,
    l.budget_currency,
    l.converted,
    l.booking_value,
    COALESCE(l.booking_value, 0) AS booking_value_cleaned,

    -- Customer metrics
    l.pax_adults,
    l.pax_children,
    (l.pax_adults + COALESCE(l.pax_children, 0)) AS total_pax,

    -- Date/time metrics
    l.created_at AS enquiry_datetime,
    l.updated_at,
    l.conversion_date,
    EXTRACT(EPOCH FROM (l.updated_at - l.created_at)) AS processing_time_secs,

    -- Task tracking
    l.planner_bucket,
    l.planner_task_id,
    l.planner_synced_at,

    -- Conversation metrics
    c.source_page AS enquiry_source,
    c.message_count,
    c.escalated,
    c.resolved_by_bot,
    COALESCE(c.response_time_avg_ms, 0) / 1000 / 60 AS response_time_mins,
    c.response_time_avg_ms AS response_time_secs,

    -- SLA compliance
    sla.response_hours AS sla_target_hours,
    sla.resolution_days AS sla_target_days,
    CASE
        WHEN c.response_time_avg_ms / 1000 / 3600 <= sla.response_hours THEN TRUE
        ELSE FALSE
    END AS met_sla,

    -- Agent email for RLS
    da.agent_email AS assigned_agent_email,
    da.manager_email AS assigned_manager_email

FROM leads l
LEFT JOIN conversations c ON c.id = l.conversation_id
LEFT JOIN sla_targets sla ON sla.classification = l.classification
LEFT JOIN dim_agents da ON da.agent_name = l.assigned_agent;

-- ==========================
-- 5. ANALYTICAL VIEW: v_powerbi_agent_performance
-- ==========================
CREATE OR REPLACE VIEW v_powerbi_agent_performance AS
SELECT
    l.assigned_agent AS agent_name,
    da.agent_email,
    da.department,
    COUNT(*) AS total_enquiries,
    COUNT(*) FILTER (WHERE l.classification = 'IMMEDIATE') AS immediate_count,
    COUNT(*) FILTER (WHERE l.classification = 'IMPORTANT') AS important_count,
    COUNT(*) FILTER (WHERE l.classification = 'NOT_IMPORTANT') AS not_important_count,
    COUNT(*) FILTER (WHERE l.converted = TRUE) AS converted_count,
    ROUND(100.0 * COUNT(*) FILTER (WHERE l.converted = TRUE) / NULLIF(COUNT(*), 0), 2) AS conversion_rate_pct,
    AVG(l.lead_score) AS avg_lead_score,
    SUM(l.booking_value) FILTER (WHERE l.converted = TRUE) AS total_revenue,
    AVG(l.booking_value) FILTER (WHERE l.converted = TRUE) AS avg_booking_value,
    AVG(c.response_time_avg_ms) / 1000 / 60 AS avg_response_time_mins,
    COUNT(*) FILTER (WHERE c.escalated = TRUE) AS escalated_count,
    COUNT(*) FILTER (WHERE c.resolved_by_bot = TRUE) AS bot_resolved_count,
    MAX(l.updated_at) AS last_activity
FROM leads l
LEFT JOIN conversations c ON c.id = l.conversation_id
LEFT JOIN dim_agents da ON da.agent_name = l.assigned_agent
WHERE l.assigned_agent IS NOT NULL
GROUP BY l.assigned_agent, da.agent_email, da.department;

-- ==========================
-- 6. ANALYTICAL VIEW: v_powerbi_sla_compliance
-- ==========================
CREATE OR REPLACE VIEW v_powerbi_sla_compliance AS
SELECT
    l.id AS enquiry_id,
    l.classification,
    l.created_at AS enquiry_datetime,
    sla.response_hours AS sla_target_hours,
    sla.resolution_days AS sla_target_days,
    c.response_time_avg_ms,
    c.response_time_avg_ms / 1000 / 3600 AS response_time_hours,
    CASE
        WHEN c.response_time_avg_ms / 1000 / 3600 <= sla.response_hours THEN TRUE
        ELSE FALSE
    END AS met_sla,
    CASE
        WHEN c.response_time_avg_ms / 1000 / 3600 <= sla.response_hours THEN 0
        ELSE c.response_time_avg_ms / 1000 / 3600 - sla.response_hours
    END AS sla_breach_hours,
    l.planner_bucket,
    l.assigned_agent
FROM leads l
LEFT JOIN conversations c ON c.id = l.conversation_id
LEFT JOIN sla_targets sla ON sla.classification = l.classification
WHERE sla.response_hours IS NOT NULL;

-- ==========================
-- 7. ANALYTICAL VIEW: v_powerbi_revenue_pipeline
-- ==========================
CREATE OR REPLACE VIEW v_powerbi_revenue_pipeline AS
SELECT
    l.id AS enquiry_id,
    l.booking_stage,
    l.destination,
    l.destination_region,
    l.classification,
    l.lead_score,
    l.budget_max AS pipeline_value,
    l.booking_value,
    l.converted,
    l.assigned_agent,
    l.created_at,
    CASE
        WHEN l.booking_stage = 'closed_lost' THEN 0
        WHEN l.converted = TRUE THEN l.booking_value
        ELSE l.budget_max
    END AS weighted_pipeline_value,
    CASE
        WHEN l.booking_stage = 'shortlisting' AND l.lead_score >= 70 THEN 0.7
        WHEN l.booking_stage = 'enquiring' AND l.lead_score >= 60 THEN 0.4
        WHEN l.booking_stage = 'considering' AND l.lead_score >= 50 THEN 0.2
        ELSE 0.1
    END AS conversion_probability
FROM leads l;

-- ==========================
-- 8. ANALYTICAL VIEW: v_powerbi_monthly_trends
-- ==========================
CREATE OR REPLACE VIEW v_powerbi_monthly_trends AS
SELECT
    TO_CHAR(l.created_at, 'YYYY-MM') AS month_year,
    EXTRACT(YEAR FROM l.created_at) AS year,
    EXTRACT(MONTH FROM l.created_at) AS month,
    COUNT(*) AS total_enquiries,
    COUNT(*) FILTER (WHERE l.converted = TRUE) AS converted_count,
    ROUND(100.0 * COUNT(*) FILTER (WHERE l.converted = TRUE) / NULLIF(COUNT(*), 0), 2) AS conversion_rate_pct,
    AVG(l.lead_score) AS avg_lead_score,
    SUM(l.budget_max) FILTER (WHERE l.booking_stage != 'closed_lost') AS pipeline_value,
    SUM(l.booking_value) FILTER (WHERE l.converted = TRUE) AS total_revenue,
    AVG(l.booking_value) FILTER (WHERE l.converted = TRUE) AS avg_deal_size,
    COUNT(DISTINCT l.assigned_agent) AS active_agents,
    COUNT(DISTINCT l.destination) AS destinations_served
FROM leads l
GROUP BY TO_CHAR(l.created_at, 'YYYY-MM'), EXTRACT(YEAR FROM l.created_at), EXTRACT(MONTH FROM l.created_at)
ORDER BY month_year DESC;

-- ==========================
-- 9. ANALYTICAL VIEW: v_powerbi_destination_stats
-- ==========================
CREATE OR REPLACE VIEW v_powerbi_destination_stats AS
SELECT
    l.destination,
    l.destination_region,
    d.country,
    COUNT(*) AS total_enquiries,
    COUNT(*) FILTER (WHERE l.converted = TRUE) AS converted_count,
    ROUND(100.0 * COUNT(*) FILTER (WHERE l.converted = TRUE) / NULLIF(COUNT(*), 0), 2) AS conversion_rate_pct,
    AVG(l.lead_score) AS avg_lead_score,
    SUM(l.budget_max) FILTER (WHERE l.booking_stage != 'closed_lost') AS pipeline_value,
    SUM(l.booking_value) FILTER (WHERE l.converted = TRUE) AS total_revenue,
    AVG(l.booking_value) FILTER (WHERE l.converted = TRUE) AS avg_deal_size,
    COUNT(DISTINCT l.assigned_agent) AS agents_handling,
    MAX(l.created_at) AS last_enquiry_date
FROM leads l
LEFT JOIN destinations d ON d.name = l.destination
GROUP BY l.destination, l.destination_region, d.country;

-- ==========================
-- 10. INDEXES for Performance
-- ==========================
-- JSONB indexes for analytics_events payload queries
CREATE INDEX IF NOT EXISTS idx_analytics_payload_classification
    ON analytics_events USING btree ((payload->>'classification'));

CREATE INDEX IF NOT EXISTS idx_analytics_payload_confidence
    ON analytics_events USING btree (((payload->>'classificationConfidence')::FLOAT));

CREATE INDEX IF NOT EXISTS idx_analytics_payload_source
    ON analytics_events USING btree ((payload->>'source'));

-- Date-based indexes for time-series queries
CREATE INDEX IF NOT EXISTS idx_leads_created_at_date
    ON leads USING btree (DATE(created_at));

CREATE INDEX IF NOT EXISTS idx_conversations_started_at_date
    ON conversations USING btree (DATE(started_at));

-- ==========================
-- 11. VALIDATION QUERIES
-- ==========================
-- Verify table row counts
DO $$
BEGIN
    RAISE NOTICE '=== Power BI Migration Complete ===';
    RAISE NOTICE 'dim_agents: % rows', (SELECT COUNT(*) FROM dim_agents);
    RAISE NOTICE 'dim_date: % rows', (SELECT COUNT(*) FROM dim_date);
    RAISE NOTICE 'sla_targets: % rows', (SELECT COUNT(*) FROM sla_targets);
    RAISE NOTICE 'v_powerbi_enquiry_fact: % rows', (SELECT COUNT(*) FROM v_powerbi_enquiry_fact);
    RAISE NOTICE 'v_powerbi_agent_performance: % rows', (SELECT COUNT(*) FROM v_powerbi_agent_performance);
    RAISE NOTICE 'v_powerbi_sla_compliance: % rows', (SELECT COUNT(*) FROM v_powerbi_sla_compliance);
    RAISE NOTICE '====================================';
END $$;

SELECT 'Power BI analytics migration complete' AS status;
