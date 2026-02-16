-- ═══════════════════════════════════════════════════════════════════════
-- create_powerbi_simple_views.sql
-- Creates PRE-CALCULATED views for Power BI Service (no DAX needed)
--
-- These views contain ALL calculations done in PostgreSQL, so Power BI
-- just displays the values directly.
--
-- Usage:
--   docker exec -i chatbot-postgres-1 psql -U mahlatini -d mahlatini_chatbot < scripts/create_powerbi_simple_views.sql
-- ═══════════════════════════════════════════════════════════════════════

-- ═══════════════════════════════════════════════════════════════════════
-- DASHBOARD 1: OPERATIONAL METRICS (Department Head View)
-- ═══════════════════════════════════════════════════════════════════════

-- View 1: Today's Summary (KPI Cards)
CREATE OR REPLACE VIEW powerbi_today_kpis AS
SELECT
    'Today' AS period,
    CURRENT_DATE AS metric_date,

    -- Today's Enquiries
    COUNT(*) FILTER (WHERE DATE(l.created_at) = CURRENT_DATE) AS todays_enquiries,

    -- Pending Tasks
    COUNT(*) FILTER (WHERE l.planner_bucket = 'Pending' AND l.converted = FALSE) AS pending_tasks,

    -- Avg Response Time (minutes)
    ROUND(AVG(c.response_time_avg_ms) FILTER (WHERE DATE(l.created_at) = CURRENT_DATE) / 1000.0 / 60.0, 1) AS avg_response_mins,

    -- SLA Compliance %
    ROUND(
        100.0 * COUNT(*) FILTER (
            WHERE sla.response_hours IS NOT NULL
            AND (c.response_time_avg_ms / 1000.0 / 3600.0) <= sla.response_hours
        ) / NULLIF(COUNT(*) FILTER (WHERE sla.response_hours IS NOT NULL), 0),
        1
    ) AS sla_compliance_pct,

    -- Conversion Rate %
    ROUND(100.0 * COUNT(*) FILTER (WHERE l.converted = TRUE) / NULLIF(COUNT(*), 0), 1) AS conversion_rate_pct,

    -- Agent Utilization %
    ROUND(100.0 * COUNT(*) FILTER (WHERE l.assigned_agent IS NOT NULL) / NULLIF(COUNT(*), 0), 1) AS agent_utilization_pct,

    -- High Priority Count
    COUNT(*) FILTER (WHERE l.classification = 'IMMEDIATE') AS high_priority_count,

    -- Yesterday's Enquiries (for comparison)
    COUNT(*) FILTER (WHERE DATE(l.created_at) = CURRENT_DATE - 1) AS yesterdays_enquiries

FROM leads l
LEFT JOIN conversations c ON c.id = l.conversation_id
LEFT JOIN sla_targets sla ON sla.classification = l.classification
WHERE l.created_at >= CURRENT_DATE - INTERVAL '7 days';

COMMENT ON VIEW powerbi_today_kpis IS 'Pre-calculated KPIs for Operational Dashboard - refreshes daily';

-- View 2: Agent Workload (Bar Chart Data)
CREATE OR REPLACE VIEW powerbi_agent_workload AS
SELECT
    COALESCE(l.assigned_agent, 'Unassigned') AS agent_name,
    l.classification,
    COUNT(*) AS enquiry_count,
    ROUND(AVG(l.lead_score), 0) AS avg_lead_score,
    ROUND(AVG(c.response_time_avg_ms) / 1000.0 / 60.0, 1) AS avg_response_mins,
    COUNT(*) FILTER (WHERE l.converted = TRUE) AS converted_count,
    ROUND(100.0 * COUNT(*) FILTER (WHERE l.converted = TRUE) / NULLIF(COUNT(*), 0), 1) AS conversion_rate_pct
FROM leads l
LEFT JOIN conversations c ON c.id = l.conversation_id
WHERE l.created_at >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY l.assigned_agent, l.classification
ORDER BY agent_name,
    CASE l.classification
        WHEN 'IMMEDIATE' THEN 1
        WHEN 'IMPORTANT' THEN 2
        WHEN 'NOT_IMPORTANT' THEN 3
        ELSE 4
    END;

COMMENT ON VIEW powerbi_agent_workload IS 'Agent workload by classification - for stacked bar chart';

-- View 3: Hourly Activity (Line Chart Data)
CREATE OR REPLACE VIEW powerbi_hourly_activity AS
SELECT
    DATE(l.created_at) AS activity_date,
    EXTRACT(HOUR FROM l.created_at)::INTEGER AS activity_hour,
    l.classification,
    COUNT(*) AS enquiry_count,
    ROUND(AVG(l.lead_score), 0) AS avg_lead_score
FROM leads l
WHERE l.created_at >= CURRENT_DATE - INTERVAL '2 days'
GROUP BY DATE(l.created_at), EXTRACT(HOUR FROM l.created_at), l.classification
ORDER BY activity_date DESC, activity_hour, classification;

COMMENT ON VIEW powerbi_hourly_activity IS 'Hourly enquiry activity - last 48 hours';

-- View 4: Live Queue (Table Data)
CREATE OR REPLACE VIEW powerbi_live_queue AS
SELECT
    l.id AS enquiry_id,
    l.classification AS priority,
    COALESCE(l.contact_name, 'Anonymous') AS client_name,
    l.destination,
    l.lead_score AS score,
    COALESCE(l.assigned_agent, 'Unassigned') AS agent,
    l.planner_bucket AS status,
    EXTRACT(EPOCH FROM (NOW() - l.created_at)) / 60 AS age_minutes,
    l.created_at
FROM leads l
WHERE l.converted = FALSE
    AND l.booking_stage NOT IN ('closed_lost')
ORDER BY
    CASE l.classification
        WHEN 'IMMEDIATE' THEN 1
        WHEN 'IMPORTANT' THEN 2
        WHEN 'NOT_IMPORTANT' THEN 3
        ELSE 4
    END,
    l.created_at DESC
LIMIT 20;

COMMENT ON VIEW powerbi_live_queue IS 'Live enquiry queue - top 20 pending';

-- View 5: Destination Distribution (Donut Chart Data)
CREATE OR REPLACE VIEW powerbi_destination_summary AS
SELECT
    COALESCE(l.destination, 'Not specified') AS destination,
    l.destination_region AS region,
    COUNT(*) AS enquiry_count,
    COUNT(*) FILTER (WHERE l.converted = TRUE) AS converted_count,
    ROUND(100.0 * COUNT(*) FILTER (WHERE l.converted = TRUE) / NULLIF(COUNT(*), 0), 1) AS conversion_rate_pct,
    SUM(l.budget_max) FILTER (WHERE l.booking_stage != 'closed_lost') AS pipeline_value
FROM leads l
WHERE l.created_at >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY l.destination, l.destination_region
ORDER BY enquiry_count DESC
LIMIT 10;

COMMENT ON VIEW powerbi_destination_summary IS 'Top 10 destinations - last 30 days';

-- ═══════════════════════════════════════════════════════════════════════
-- DASHBOARD 2: EXECUTIVE METRICS (CEO View)
-- ═══════════════════════════════════════════════════════════════════════

-- View 6: Executive Summary KPIs
CREATE OR REPLACE VIEW powerbi_executive_kpis AS
SELECT
    'Current Period' AS period,
    CURRENT_DATE AS metric_date,

    -- Pipeline Value
    SUM(l.budget_max) FILTER (WHERE l.booking_stage NOT IN ('closed_lost')) AS pipeline_value_gbp,

    -- Total Revenue
    SUM(l.booking_value) FILTER (WHERE l.converted = TRUE) AS total_revenue_gbp,

    -- Converted Deals
    COUNT(*) FILTER (WHERE l.converted = TRUE) AS converted_deals,

    -- Avg Deal Size
    ROUND(AVG(l.booking_value) FILTER (WHERE l.converted = TRUE), 0) AS avg_deal_size_gbp,

    -- Total Enquiries
    COUNT(*) AS total_enquiries,

    -- Conversion Rate
    ROUND(100.0 * COUNT(*) FILTER (WHERE l.converted = TRUE) / NULLIF(COUNT(*), 0), 1) AS conversion_rate_pct,

    -- MTD Enquiries
    COUNT(*) FILTER (WHERE DATE_TRUNC('month', l.created_at) = DATE_TRUNC('month', CURRENT_DATE)) AS mtd_enquiries,

    -- YTD Enquiries
    COUNT(*) FILTER (WHERE DATE_TRUNC('year', l.created_at) = DATE_TRUNC('year', CURRENT_DATE)) AS ytd_enquiries,

    -- Avg Lead Score
    ROUND(AVG(l.lead_score), 0) AS avg_lead_score,

    -- Pipeline Coverage (months)
    ROUND(
        SUM(l.budget_max) FILTER (WHERE l.booking_stage NOT IN ('closed_lost')) /
        NULLIF(AVG(l.booking_value) FILTER (WHERE l.converted = TRUE AND l.created_at >= CURRENT_DATE - INTERVAL '30 days'), 0),
        1
    ) AS pipeline_coverage_months

FROM leads l
WHERE l.created_at >= CURRENT_DATE - INTERVAL '12 months';

COMMENT ON VIEW powerbi_executive_kpis IS 'Executive summary KPIs - rolling 12 months';

-- View 7: Monthly Trends (Line/Area Chart Data)
CREATE OR REPLACE VIEW powerbi_monthly_revenue AS
SELECT
    DATE_TRUNC('month', l.created_at)::DATE AS month_start,
    TO_CHAR(l.created_at, 'YYYY-MM') AS month_label,
    EXTRACT(YEAR FROM l.created_at)::INTEGER AS year,
    EXTRACT(MONTH FROM l.created_at)::INTEGER AS month,
    l.destination_region AS region,

    -- Metrics
    COUNT(*) AS enquiry_count,
    COUNT(*) FILTER (WHERE l.converted = TRUE) AS converted_count,
    SUM(l.booking_value) FILTER (WHERE l.converted = TRUE) AS revenue_gbp,
    SUM(l.budget_max) FILTER (WHERE l.booking_stage NOT IN ('closed_lost')) AS pipeline_gbp,
    ROUND(AVG(l.lead_score), 0) AS avg_lead_score,
    ROUND(100.0 * COUNT(*) FILTER (WHERE l.converted = TRUE) / NULLIF(COUNT(*), 0), 1) AS conversion_rate_pct

FROM leads l
WHERE l.created_at >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '12 months'
GROUP BY DATE_TRUNC('month', l.created_at), TO_CHAR(l.created_at, 'YYYY-MM'),
    EXTRACT(YEAR FROM l.created_at), EXTRACT(MONTH FROM l.created_at), l.destination_region
ORDER BY month_start DESC, region;

COMMENT ON VIEW powerbi_monthly_revenue IS 'Monthly revenue trends by region - last 12 months';

-- View 8: Destination Performance (Treemap Data)
CREATE OR REPLACE VIEW powerbi_destination_revenue AS
SELECT
    l.destination,
    l.destination_region AS region,
    d.country,

    -- Metrics
    COUNT(*) AS total_enquiries,
    COUNT(*) FILTER (WHERE l.converted = TRUE) AS converted_count,
    ROUND(100.0 * COUNT(*) FILTER (WHERE l.converted = TRUE) / NULLIF(COUNT(*), 0), 1) AS conversion_rate_pct,
    SUM(l.booking_value) FILTER (WHERE l.converted = TRUE) AS total_revenue_gbp,
    ROUND(AVG(l.booking_value) FILTER (WHERE l.converted = TRUE), 0) AS avg_deal_size_gbp,
    SUM(l.budget_max) FILTER (WHERE l.booking_stage NOT IN ('closed_lost')) AS pipeline_gbp,
    ROUND(AVG(l.lead_score), 0) AS avg_lead_score

FROM leads l
LEFT JOIN destinations d ON d.name = l.destination
WHERE l.created_at >= CURRENT_DATE - INTERVAL '6 months'
GROUP BY l.destination, l.destination_region, d.country
HAVING COUNT(*) >= 3  -- Only show destinations with 3+ enquiries
ORDER BY total_revenue_gbp DESC NULLS LAST, total_enquiries DESC;

COMMENT ON VIEW powerbi_destination_revenue IS 'Destination performance metrics - last 6 months';

-- ═══════════════════════════════════════════════════════════════════════
-- DASHBOARD 3: MONITORING METRICS (Workflow/Quality View)
-- ═══════════════════════════════════════════════════════════════════════

-- View 9: Workflow Status (Funnel Chart Data)
CREATE OR REPLACE VIEW powerbi_workflow_status AS
SELECT
    l.planner_bucket AS stage,
    COUNT(*) AS enquiry_count,
    ROUND(AVG(EXTRACT(EPOCH FROM (NOW() - l.created_at)) / 3600), 1) AS avg_age_hours,
    ROUND(AVG(l.lead_score), 0) AS avg_lead_score,
    COUNT(*) FILTER (WHERE l.classification = 'IMMEDIATE') AS high_priority_count
FROM leads l
WHERE l.converted = FALSE
    AND l.booking_stage NOT IN ('closed_lost')
GROUP BY l.planner_bucket
ORDER BY
    CASE l.planner_bucket
        WHEN 'Pending' THEN 1
        WHEN 'In Progress' THEN 2
        WHEN 'Completed' THEN 3
        ELSE 4
    END;

COMMENT ON VIEW powerbi_workflow_status IS 'Current workflow stage distribution';

-- View 10: SLA Performance (Gauge/Table Data)
CREATE OR REPLACE VIEW powerbi_sla_metrics AS
SELECT
    l.classification,
    sla.response_hours AS sla_target_hours,

    -- Metrics
    COUNT(*) AS total_enquiries,
    COUNT(*) FILTER (WHERE (c.response_time_avg_ms / 1000.0 / 3600.0) <= sla.response_hours) AS met_sla_count,
    COUNT(*) FILTER (WHERE (c.response_time_avg_ms / 1000.0 / 3600.0) > sla.response_hours) AS breached_sla_count,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE (c.response_time_avg_ms / 1000.0 / 3600.0) <= sla.response_hours) /
        NULLIF(COUNT(*), 0),
        1
    ) AS sla_compliance_pct,
    ROUND(AVG(c.response_time_avg_ms) / 1000.0 / 60.0, 1) AS avg_response_mins,
    ROUND(AVG(c.response_time_avg_ms) FILTER (WHERE (c.response_time_avg_ms / 1000.0 / 3600.0) > sla.response_hours) / 1000.0 / 60.0, 1) AS avg_breach_mins

FROM leads l
LEFT JOIN conversations c ON c.id = l.conversation_id
LEFT JOIN sla_targets sla ON sla.classification = l.classification
WHERE sla.response_hours IS NOT NULL
    AND l.created_at >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY l.classification, sla.response_hours
ORDER BY
    CASE l.classification
        WHEN 'IMMEDIATE' THEN 1
        WHEN 'IMPORTANT' THEN 2
        WHEN 'NOT_IMPORTANT' THEN 3
        ELSE 4
    END;

COMMENT ON VIEW powerbi_sla_metrics IS 'SLA compliance metrics by classification - last 30 days';

-- View 11: Data Quality Metrics
CREATE OR REPLACE VIEW powerbi_quality_metrics AS
SELECT
    'Quality Check' AS metric_category,
    CURRENT_DATE AS metric_date,

    -- Classification Confidence
    ROUND(AVG((ae.payload->>'classificationConfidence')::FLOAT), 2) AS avg_confidence,
    COUNT(*) FILTER (WHERE (ae.payload->>'classificationConfidence')::FLOAT >= 0.90) AS high_confidence_count,
    COUNT(*) FILTER (WHERE (ae.payload->>'classificationConfidence')::FLOAT < 0.70) AS low_confidence_count,

    -- Bot Resolution
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE c.resolved_by_bot = TRUE) /
        NULLIF(COUNT(*) FILTER (WHERE c.source_page = 'chatbot'), 0),
        1
    ) AS bot_resolution_rate_pct,

    -- Data Completeness
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE l.destination IS NOT NULL) / NULLIF(COUNT(*), 0),
        1
    ) AS destination_complete_pct,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE l.budget_max IS NOT NULL) / NULLIF(COUNT(*), 0),
        1
    ) AS budget_complete_pct,

    -- Processing Timeliness
    ROUND(AVG(EXTRACT(EPOCH FROM (l.planner_synced_at - l.created_at)) / 60), 1) AS avg_sync_delay_mins,
    COUNT(*) FILTER (WHERE l.assigned_agent IS NOT NULL) AS assigned_count,
    COUNT(*) FILTER (WHERE l.assigned_agent IS NULL) AS unassigned_count

FROM leads l
LEFT JOIN conversations c ON c.id = l.conversation_id
LEFT JOIN analytics_events ae ON ae.lead_id = l.id AND ae.event_type = 'enquiry_classified'
WHERE l.created_at >= CURRENT_DATE - INTERVAL '7 days';

COMMENT ON VIEW powerbi_quality_metrics IS 'Data quality and processing metrics - last 7 days';

-- View 12: Daily Activity Heatmap
CREATE OR REPLACE VIEW powerbi_daily_activity AS
SELECT
    DATE(l.created_at) AS activity_date,
    TO_CHAR(l.created_at, 'Day') AS day_name,
    EXTRACT(DOW FROM l.created_at)::INTEGER AS day_of_week,
    COUNT(*) AS enquiry_count,
    COUNT(*) FILTER (WHERE l.classification = 'IMMEDIATE') AS immediate_count,
    COUNT(*) FILTER (WHERE l.converted = TRUE) AS converted_count,
    ROUND(AVG(l.lead_score), 0) AS avg_lead_score,
    SUM(l.booking_value) FILTER (WHERE l.converted = TRUE) AS daily_revenue_gbp
FROM leads l
WHERE l.created_at >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY DATE(l.created_at), TO_CHAR(l.created_at, 'Day'), EXTRACT(DOW FROM l.created_at)
ORDER BY activity_date DESC;

COMMENT ON VIEW powerbi_daily_activity IS 'Daily activity metrics - last 30 days';

-- ═══════════════════════════════════════════════════════════════════════
-- SUMMARY VALIDATION
-- ═══════════════════════════════════════════════════════════════════════

DO $$
BEGIN
    RAISE NOTICE '=== Power BI Simple Views Created ===';
    RAISE NOTICE 'Dashboard 1 (Operational): 5 views';
    RAISE NOTICE 'Dashboard 2 (Executive): 3 views';
    RAISE NOTICE 'Dashboard 3 (Monitoring): 4 views';
    RAISE NOTICE 'Total: 12 pre-calculated views ready for Power BI';
    RAISE NOTICE '======================================';
    RAISE NOTICE 'Next step: Run export script to generate CSVs';
END $$;

SELECT 'Power BI simple views created successfully' AS status;
