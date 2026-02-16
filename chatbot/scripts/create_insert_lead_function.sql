-- ═══════════════════════════════════════════════════════════════════════
-- create_insert_lead_function.sql
-- Creates a PostgreSQL function for n8n to call for inserting enquiry data
--
-- Usage from n8n:
--   SELECT * FROM insert_enquiry_from_webhook($json_payload);
-- ═══════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION insert_enquiry_from_webhook(
  p_source TEXT,
  p_client_name TEXT,
  p_client_email TEXT,
  p_client_phone TEXT DEFAULT NULL,
  p_destination TEXT DEFAULT NULL,
  p_adults INTEGER DEFAULT NULL,
  p_children INTEGER DEFAULT 0,
  p_budget_max NUMERIC DEFAULT NULL,
  p_message TEXT DEFAULT NULL,
  p_lead_score INTEGER DEFAULT NULL,
  p_classification TEXT DEFAULT 'NOT_IMPORTANT',
  p_booking_stage TEXT DEFAULT 'new',
  p_urgency TEXT DEFAULT 'low'
)
RETURNS TABLE (
  lead_id UUID,
  conversation_id UUID,
  success BOOLEAN,
  message TEXT
) AS $$
DECLARE
  v_conversation_id UUID;
  v_lead_id UUID;
BEGIN
  -- Insert conversation
  INSERT INTO conversations (
    session_id,
    source_page,
    started_at,
    message_count
  ) VALUES (
    NOW()::TEXT,  -- Use current timestamp as session_id
    p_source,
    NOW(),
    1
  )
  RETURNING id INTO v_conversation_id;

  -- Insert lead
  INSERT INTO leads (
    conversation_id,
    contact_name,
    contact_email,
    contact_phone,
    destination,
    pax_adults,
    pax_children,
    budget_max,
    budget_currency,
    special_requests,
    lead_score,
    classification,
    booking_stage,
    urgency,
    planner_bucket,
    planner_synced_at
  ) VALUES (
    v_conversation_id,
    p_client_name,
    p_client_email,
    p_client_phone,
    p_destination,
    p_adults,
    p_children,
    p_budget_max,
    'GBP',
    p_message,
    p_lead_score,
    p_classification,
    p_booking_stage,
    p_urgency,
    'Pending',
    NOW()
  )
  RETURNING id INTO v_lead_id;

  -- Return success
  RETURN QUERY SELECT
    v_lead_id,
    v_conversation_id,
    TRUE::BOOLEAN,
    'Enquiry inserted successfully'::TEXT;

EXCEPTION WHEN OTHERS THEN
  -- Return error
  RETURN QUERY SELECT
    NULL::UUID,
    NULL::UUID,
    FALSE::BOOLEAN,
    SQLERRM::TEXT;
END;
$$ LANGUAGE plpgsql;

-- Test the function
SELECT * FROM insert_enquiry_from_webhook(
  'test',
  'Function Test User',
  'function.test@example.com',
  '+44 7700 000000',
  'Namibia',
  2,
  1,
  12000.00,
  'Testing the PostgreSQL function',
  75,
  'IMPORTANT',
  'enquiring',
  'high'
);

-- Verify
SELECT
  '=== VERIFICATION ===' as info,
  (SELECT COUNT(*) FROM leads) as lead_count,
  (SELECT COUNT(*) FROM conversations) as conv_count,
  (SELECT total_enquiries FROM powerbi_realtime_kpis) as kpi_total;
