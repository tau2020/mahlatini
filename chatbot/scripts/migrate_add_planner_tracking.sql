-- ═══════════════════════════════════════════════════════════════════════
-- migrate_add_planner_tracking.sql
-- Adds Microsoft Planner task tracking columns to leads table
-- and creates an analytics view for Planner task monitoring.
--
-- Safe to run multiple times (idempotent).
--
-- Usage:
--   docker exec -i <postgres_container> psql -U mahlatini -d mahlatini_chatbot < scripts/migrate_add_planner_tracking.sql
-- ═══════════════════════════════════════════════════════════════════════

-- 1. Add Planner tracking columns to leads table
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'leads' AND column_name = 'planner_task_id'
  ) THEN
    ALTER TABLE leads ADD COLUMN planner_task_id TEXT;
    RAISE NOTICE 'Added column: leads.planner_task_id';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'leads' AND column_name = 'planner_task_url'
  ) THEN
    ALTER TABLE leads ADD COLUMN planner_task_url TEXT;
    RAISE NOTICE 'Added column: leads.planner_task_url';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'leads' AND column_name = 'planner_bucket'
  ) THEN
    ALTER TABLE leads ADD COLUMN planner_bucket TEXT DEFAULT 'Pending';
    RAISE NOTICE 'Added column: leads.planner_bucket';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'leads' AND column_name = 'planner_synced_at'
  ) THEN
    ALTER TABLE leads ADD COLUMN planner_synced_at TIMESTAMPTZ;
    RAISE NOTICE 'Added column: leads.planner_synced_at';
  END IF;
END $$;

-- 2. Index for Planner task lookups
CREATE INDEX IF NOT EXISTS idx_leads_planner_task_id
  ON leads (planner_task_id)
  WHERE planner_task_id IS NOT NULL;

-- 3. Index for analytics: Planner task creation events
CREATE INDEX IF NOT EXISTS idx_analytics_planner_task
  ON analytics_events USING btree (event_type)
  WHERE event_type = 'planner_task_created';

-- 4. View: Planner task creation summary
CREATE OR REPLACE VIEW v_planner_tasks AS
SELECT
  ae.id,
  ae.payload->>'clientName' AS client_name,
  ae.payload->>'clientEmail' AS client_email,
  ae.payload->>'classification' AS classification,
  ae.payload->>'plannerTaskId' AS planner_task_id,
  ae.payload->>'bucketName' AS bucket,
  ae.payload->>'source' AS source,
  ae.created_at
FROM analytics_events ae
WHERE ae.event_type = 'planner_task_created'
ORDER BY ae.created_at DESC;

-- 5. Composite view: Full lead pipeline with Planner status
CREATE OR REPLACE VIEW v_lead_pipeline_planner AS
SELECT
  l.id,
  l.name,
  l.email,
  l.classification,
  l.lead_score,
  l.booking_stage,
  l.planner_task_id,
  l.planner_bucket,
  l.planner_synced_at,
  c.message_count,
  c.created_at AS first_contact
FROM leads l
LEFT JOIN (
  SELECT
    conversation_id,
    COUNT(*) AS message_count,
    MIN(created_at) AS created_at
  FROM messages
  GROUP BY conversation_id
) c ON c.conversation_id = l.conversation_id
ORDER BY l.created_at DESC;

SELECT 'Planner tracking migration complete' AS status;
