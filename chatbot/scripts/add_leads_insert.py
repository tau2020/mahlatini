#!/usr/bin/env python3
"""
Surgically adds a leads table INSERT node to the n8n workflow.
Positions it after "Parse Classification" to capture all enquiry data.
"""

import json
import sys
from pathlib import Path

WORKFLOW_FILE = Path(__file__).parent.parent / "n8n-workflows/02-enquiry-outlook-claude-powerbi.json"
OUTPUT_FILE = Path(__file__).parent.parent / "n8n-workflows/03-enquiry-with-leads-insert.json"

def create_leads_insert_node():
    """Creates the PostgreSQL INSERT node for leads + conversations tables"""
    return {
        "parameters": {
            "operation": "executeQuery",
            "query": """-- Insert conversation record (if from website form, create minimal record)
WITH new_conversation AS (
  INSERT INTO conversations (
    session_id,
    source_page,
    started_at,
    message_count,
    client_classification,
    primary_intent,
    escalated,
    resolved_by_bot
  ) VALUES (
    '{{ $json.timestamp }}',  -- Use timestamp as session_id for website forms
    '{{ $json._source }}',
    NOW(),
    1,
    '{{ $json.classification || "NOT_IMPORTANT" }}',
    '{{ $json.intelligence?.primary_intent || "website_enquiry" }}',
    false,
    false
  )
  RETURNING id
),
-- Insert lead record
new_lead AS (
  INSERT INTO leads (
    conversation_id,
    contact_name,
    contact_email,
    contact_phone,
    destination,
    destination_region,
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
  )
  SELECT
    new_conversation.id,
    '{{ $json.client?.name || "Unknown" }}',
    '{{ $json.client?.email || "" }}',
    '{{ $json.client?.phone || "" }}',
    '{{ $json.enquiry?.destination || "" }}',
    NULL,  -- Will be populated by trigger if destination exists in destinations table
    NULLIF('{{ $json.enquiry?.adults || "" }}', '')::INTEGER,
    NULLIF('{{ $json.enquiry?.children || "0" }}', '')::INTEGER,
    NULLIF(REGEXP_REPLACE('{{ $json.enquiry?.budget || "" }}', '[^0-9.]', '', 'g'), '')::NUMERIC,
    'GBP',
    '{{ $json.enquiry?.message || "" }}',
    NULLIF('{{ $json.intelligence?.lead_score || "" }}', '')::INTEGER,
    '{{ $json.classification || "NOT_IMPORTANT" }}',
    '{{ $json.intelligence?.booking_stage || "new" }}',
    '{{ $json.intelligence?.urgency || "low" }}',
    'Pending',
    NOW()
  FROM new_conversation
  RETURNING id, conversation_id, contact_name, contact_email, destination, classification, lead_score
)
SELECT
  new_lead.id::TEXT AS lead_id,
  new_lead.conversation_id::TEXT AS conversation_id,
  new_lead.contact_name,
  new_lead.contact_email,
  new_lead.destination,
  new_lead.classification,
  new_lead.lead_score
FROM new_lead;""",
            "options": {}
        },
        "id": "postgres-insert-lead",
        "name": "Postgres: Insert Lead",
        "type": "n8n-nodes-base.postgres",
        "typeVersion": 2.4,
        "position": [1632, 432],
        "credentials": {
            "postgres": {
                "id": "GldFK4j9aQixrrxs",
                "name": "PostgreSQL account"
            }
        }
    }

def add_node_to_workflow():
    """Reads workflow, adds the leads insert node, updates connections"""
    with open(WORKFLOW_FILE) as f:
        workflow = json.load(f)

    nodes = workflow['data']['nodes']
    connections = workflow['data']['connections']

    # Find the "Parse Classification" node index
    parse_idx = next(i for i, n in enumerate(nodes) if n['name'] == 'Parse Classification')

    # Create new node
    new_node = create_leads_insert_node()

    # Insert after Parse Classification
    nodes.insert(parse_idx + 1, new_node)

    # Update connections:
    # Parse Classification -> Postgres Insert Lead -> Build Outlook Patch

    # Store original Parse -> Fallback connection
    parse_node_id = nodes[parse_idx]['id']

    # Update Parse Classification to point to new node
    if parse_node_id in connections:
        # Parse currently goes to Claude Fallback
        # We'll insert our node in between
        connections['postgres-insert-lead'] = {
            'main': connections[parse_node_id]['main']  # Copy Parse's output connections
        }
        # Update Parse to go to our new node
        connections[parse_node_id]['main'][0] = [
            {'node': 'Postgres: Insert Lead', 'type': 'main', 'index': 0}
        ]

    # Write updated workflow
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(workflow, f, indent=2)

    print(f"✅ Created workflow with leads INSERT node: {OUTPUT_FILE}")
    print(f"   - Added 'Postgres: Insert Lead' node after 'Parse Classification'")
    print(f"   - Inserts into both conversations + leads tables")
    print(f"   - Triggers KPI table auto-updates")
    print(f"\n📋 Node count: {len(nodes)} (was {len(nodes) - 1})")
    return OUTPUT_FILE

if __name__ == '__main__':
    try:
        output = add_node_to_workflow()
        sys.exit(0)
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
