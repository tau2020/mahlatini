-- ═══════════════════════════════════════════════════════════════════════
-- backfill_leads_from_analytics.sql
-- Syncs data from analytics_events to leads table using the function
--
-- Run this to backfill any enquiries that were logged but not inserted:
--   docker exec -i chatbot-postgres-1 psql -U mahlatini -d mahlatini_chatbot < scripts/backfill_leads_from_analytics.sql
-- ═══════════════════════════════════════════════════════════════════════

-- Helper function to extract number from budget string
CREATE OR REPLACE FUNCTION extract_budget(budget_str TEXT)
RETURNS NUMERIC AS $$
BEGIN
  RETURN NULLIF(REGEXP_REPLACE(budget_str, '[^0-9.]', '', 'g'), '')::NUMERIC;
EXCEPTION WHEN OTHERS THEN
  RETURN NULL;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Backfill leads from analytics_events
DO $$
DECLARE
  event_rec RECORD;
  result_rec RECORD;
  inserted_count INT := 0;
BEGIN
  -- Process each analytics event that doesn't have a corresponding lead
  FOR event_rec IN
    SELECT
      ae.id,
      ae.payload,
      ae.created_at
    FROM analytics_events ae
    WHERE ae.event_type = 'enquiry_classified'
      AND NOT EXISTS (
        SELECT 1 FROM leads l
        WHERE l.contact_email = ae.payload->'client'->>'email'
          AND l.created_at::date = ae.created_at::date
      )
    ORDER BY ae.created_at
  LOOP
    -- Call the insert function
    SELECT * INTO result_rec FROM insert_enquiry_from_webhook(
      event_rec.payload,
      COALESCE(event_rec.payload->>'_source', 'unknown'),
      COALESCE(event_rec.payload->'client'->>'name', 'Unknown'),
      COALESCE(event_rec.payload->'client'->>'email', ''),
      NULLIF(event_rec.payload->'client'->>'phone', ''),
      NULLIF(event_rec.payload->'enquiry'->>'destination', ''),
      COALESCE((event_rec.payload->'enquiry'->>'adults')::INTEGER, 0),
      COALESCE((event_rec.payload->'enquiry'->>'children')::INTEGER, 0),
      extract_budget(event_rec.payload->'enquiry'->>'budget'),
      COALESCE(event_rec.payload->'enquiry'->>'message', ''),
      NULLIF(event_rec.payload->'intelligence'->>'lead_score', '')::INTEGER,
      COALESCE(event_rec.payload->>'classification', 'NOT_IMPORTANT'),
      COALESCE(event_rec.payload->'intelligence'->>'booking_stage', 'new'),
      COALESCE(event_rec.payload->'intelligence'->>'urgency', 'low')
    );

    IF result_rec.success THEN
      inserted_count := inserted_count + 1;
      RAISE NOTICE 'Inserted lead for % (ID: %)',
        event_rec.payload->'client'->>'name',
        result_rec.lead_id;
    ELSE
      RAISE WARNING 'Failed to insert for %: %',
        event_rec.payload->'client'->>'name',
        result_rec.message;
    END IF;
  END LOOP;

  RAISE NOTICE '=== BACKFILL COMPLETE ===';
  RAISE NOTICE 'Inserted % new leads from analytics_events', inserted_count;
END $$;

-- Verification
SELECT
  '=== VERIFICATION ===' as info,
  (SELECT COUNT(*) FROM leads) as total_leads,
  (SELECT COUNT(*) FROM conversations) as total_conversations,
  (SELECT COUNT(*) FROM analytics_events WHERE event_type = 'enquiry_classified') as total_analytics,
  (SELECT total_enquiries FROM powerbi_realtime_kpis) as kpi_total;
