#!/usr/bin/env python3
"""
Add Power BI nodes to n8n workflow
Adds two nodes: Power BI: Build Payload (Code) + Power BI: Push Row (HTTP Request)
Connects them after "Outlook: Send Email" in parallel with Postgres/ToDo nodes
"""

import json
import sys
from pathlib import Path

def add_powerbi_nodes(input_file, output_file):
    """Add Power BI nodes to the workflow"""

    # Read the workflow
    with open(input_file, 'r') as f:
        workflow = json.load(f)

    data = workflow['data']

    # Define the Power BI: Build Payload node (Code node)
    powerbi_build_node = {
        "parameters": {
            "mode": "runOnceForAllItems",
            "jsCode": """// Power BI: Build Payload
// Transforms n8n payload to Power BI streaming dataset schema

const payload = $('Normalise Payload').first().json;
const classification = $('Parse Classification').first().json;

// Check if Power BI is configured
if (!$env.POWERBI_PUSH_URL || $env.POWERBI_PUSH_URL.includes('your-workspace')) {
  console.log('Power BI not configured - skipping push');
  return []; // Skip if not configured
}

// Build Power BI row (16 columns)
const powerbiRow = {
  enquiryCount: 1,
  enquiryId: Math.abs(Date.now() % 2147483647),
  clientName: payload.clientName || 'Anonymous',
  clientEmail: payload.clientEmail || 'not-provided@example.com',
  destination: payload.destination || 'Not specified',
  classification: classification.classification || 'IMPORTANT',
  leadScore: parseInt(payload.lead_score || 50),
  budgetMax: parseFloat(payload.budget_max || 0),
  paxTotal: parseInt(payload.pax_adults || 0) + parseInt(payload.pax_children || 0),
  bookingStage: payload.booking_stage || 'considering',
  source: payload.source || 'website',
  assignedAgent: 'Unassigned', // Will be updated when To Do task is assigned
  createdDate: new Date().toISOString(),
  responseTimeSecs: Math.round((Date.now() - new Date(payload.submitted_at || Date.now()).getTime()) / 1000),
  classificationConfidence: parseFloat(classification.classificationConfidence || 0.8),
  urgency: classification.classification === 'IMMEDIATE' ? 'high' :
           classification.classification === 'IMPORTANT' ? 'medium' : 'low'
};

console.log('Power BI payload built:', JSON.stringify(powerbiRow, null, 2));
return [{ json: powerbiRow }];"""
        },
        "id": "powerbi-build-payload-node-id",
        "name": "Power BI: Build Payload",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [2784, 800],
        "alwaysOutputData": False,
        "continueOnFail": True
    }

    # Define the Power BI: Push Row node (HTTP Request)
    powerbi_push_node = {
        "parameters": {
            "method": "POST",
            "url": "={{ $env.POWERBI_PUSH_URL }}",
            "authentication": "none",
            "sendBody": True,
            "bodyContentType": "json",
            "specifyBody": "json",
            "jsonBody": "=[{{ $json }}]",
            "options": {
                "timeout": 10000,
                "redirect": {
                    "redirect": {
                        "followRedirects": True,
                        "maxRedirects": 5
                    }
                }
            }
        },
        "id": "powerbi-push-row-node-id",
        "name": "Power BI: Push Row",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [3008, 800],
        "alwaysOutputData": False,
        "continueOnFail": True
    }

    # Add nodes to the workflow
    data['nodes'].append(powerbi_build_node)
    data['nodes'].append(powerbi_push_node)

    # Add connections
    # Connection from "Outlook: Send Email" to "Power BI: Build Payload"
    if "Outlook: Send Email" not in data['connections']:
        data['connections']["Outlook: Send Email"] = {}

    if "main" not in data['connections']["Outlook: Send Email"]:
        data['connections']["Outlook: Send Email"]["main"] = []

    # Ensure we have at least one main output array
    while len(data['connections']["Outlook: Send Email"]["main"]) < 1:
        data['connections']["Outlook: Send Email"]["main"].append([])

    # Add connection to Power BI: Build Payload (parallel with existing connections)
    data['connections']["Outlook: Send Email"]["main"][0].append({
        "node": "Power BI: Build Payload",
        "type": "main",
        "index": 0
    })

    # Connection from "Power BI: Build Payload" to "Power BI: Push Row"
    data['connections']["Power BI: Build Payload"] = {
        "main": [
            [
                {
                    "node": "Power BI: Push Row",
                    "type": "main",
                    "index": 0
                }
            ]
        ]
    }

    # Update workflow metadata
    data['name'] = "Mahlatini: Enquiry → Outlook + Claude + Power BI"

    # Write the modified workflow
    with open(output_file, 'w') as f:
        json.dump(workflow, f, indent=2)

    print(f"✅ Power BI nodes added successfully")
    print(f"   Total nodes: {len(data['nodes'])} (was {len(data['nodes']) - 2})")
    print(f"   Total connections: {len(data['connections'])}")
    print(f"   Output file: {output_file}")
    print(f"\nNew nodes:")
    print(f"  1. Power BI: Build Payload (Code node at {powerbi_build_node['position']})")
    print(f"  2. Power BI: Push Row (HTTP Request at {powerbi_push_node['position']})")

if __name__ == "__main__":
    # Input and output files
    input_file = Path("/Users/ultraxen/mahlatini/chatbot/n8n-workflows/01-enquiry-outlook-claude-BACKUP.json")
    output_file = Path("/Users/ultraxen/mahlatini/chatbot/n8n-workflows/02-enquiry-outlook-claude-powerbi.json")

    if not input_file.exists():
        print(f"❌ Error: Input file not found: {input_file}")
        sys.exit(1)

    add_powerbi_nodes(input_file, output_file)
