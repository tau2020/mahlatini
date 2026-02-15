#!/usr/bin/env python3
"""
add_planner_nodes.py — Inject Microsoft To Do integration nodes
into the Mahlatini n8n workflow JSON.

Adds 2 new nodes as a parallel branch from "Outlook: Send Email":
  1. ToDo: Build Task   (Code node — maps enquiry → Graph To Do API payload)
  2. ToDo: Create Task   (HTTP Request node — POST to Graph To Do API)

Uses the To Do API (Tasks.ReadWrite scope) which is available on
Exchange Online Essentials (no Planner license required).

Usage:
  python3 scripts/add_planner_nodes.py [input.json] [output.json]

Defaults:
  input  = n8n-workflows/01-enquiry-outlook-gemini.json
  output = n8n-workflows/01-enquiry-outlook-gemini.json  (in-place)
"""

import json
import sys
import copy
from pathlib import Path

# ─────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────
OAUTH2_CREDENTIAL_ID = "wZWUkzbncn5Ti9dm"
OAUTH2_CREDENTIAL_NAME = "Outlook Graph OAuth2"

# Node IDs (must be unique within workflow)
BUILD_TASK_NODE_ID = "todo-build-task"
CREATE_TASK_NODE_ID = "todo-create-task"

# Old Planner node IDs to clean up if present
OLD_NODE_IDS = {"planner-build-task", "planner-create-task"}
OLD_NODE_NAMES = {"Planner: Build Task", "Planner: Create Task"}

# Position: below Postgres: Log Classification (2784, 432) → offset down
BUILD_TASK_POSITION = [2784, 640]
CREATE_TASK_POSITION = [3008, 640]

# ─────────────────────────────────────────────────────────
# Node definitions
# ─────────────────────────────────────────────────────────

TODO_BUILD_TASK_NODE = {
    "parameters": {
        "jsCode": r"""// ═══════════════════════════════════════════════════════════
// TO DO: BUILD TASK — map enquiry data → MS To Do API payload
// Runs in parallel with Route + Postgres after email is sent.
// Uses $('Build Outlook Patch').first().json for normalised data
// (HTTP Request nodes replace $json with API response).
//
// API: POST /me/todo/lists/{listId}/tasks
// Docs: https://learn.microsoft.com/en-us/graph/api/todotasklist-post-tasks
// ═══════════════════════════════════════════════════════════
const data = $('Build Outlook Patch').first().json;
const client = data.client || {};
const enquiry = data.enquiry || {};
const intelligence = data.intelligence || {};
const cls = data.geminiClassification || 'IMPORTANT';

// --- Importance mapping: Gemini classification → To Do importance ---
// To Do supports: low, normal, high
const importanceMap = {
  'IMMEDIATE': 'high',
  'IMPORTANT': 'normal',
  'NOT_IMPORTANT': 'low',
};
const importance = importanceMap[cls] || 'normal';

// --- Task title ---
const destination = enquiry.destination || 'General';
const title = `[${cls}] ${client.name || 'Unknown'} — ${destination}`;

// --- Description (plain text) ---
const descParts = [
  `Name: ${client.name || 'N/A'}`,
  `Email: ${client.email || 'N/A'}`,
  `Phone: ${client.phone || 'Not provided'}`,
  `Destination: ${destination}`,
  `Travel Dates: ${enquiry.travel_dates || 'Flexible'}`,
  `Duration: ${enquiry.duration || 'TBD'}`,
  `Party: ${enquiry.adults || '?'} adults, ${enquiry.children || 0} children`,
  `Budget: ${enquiry.budget || 'Not specified'}`,
  `Experience: ${(enquiry.experience_type || []).join(', ') || 'Not specified'}`,
  `Lead Score: ${intelligence.lead_score || 'N/A'}`,
  `Booking Stage: ${intelligence.booking_stage || 'unknown'}`,
  `Urgency: ${intelligence.urgency || 'unknown'}`,
  `Classification: ${cls} (${data.geminiReason || 'N/A'})`,
  `Source: ${data._source || 'unknown'}`,
  '',
  'Message:',
  (enquiry.message || 'No message').substring(0, 1500),
];
const description = descParts.join('\n');

// --- Due date: 3 business days from now for follow-up ---
const now = new Date();
let dueDate = new Date(now);
let addedDays = 0;
while (addedDays < 3) {
  dueDate.setDate(dueDate.getDate() + 1);
  if (dueDate.getDay() !== 0 && dueDate.getDay() !== 6) addedDays++;
}

// --- Build the To Do task payload ---
const todoTask = {
  title: title.substring(0, 255),
  body: {
    content: description,
    contentType: 'text',
  },
  importance: importance,
  status: 'notStarted',
  dueDateTime: {
    dateTime: dueDate.toISOString().replace('Z', ''),
    timeZone: 'UTC',
  },
  categories: [cls],
};

// --- Build the API URL using the list ID from env ---
const listId = $env.TODO_LIST_ID;
const apiUrl = `https://graph.microsoft.com/v1.0/me/todo/lists/${listId}/tasks`;

return [{
  json: {
    todoTask,
    todoApiUrl: apiUrl,
    todoMeta: {
      clientEmail: client.email,
      clientName: client.name,
      classification: cls,
      source: data._source,
    },
  }
}];
"""
    },
    "id": BUILD_TASK_NODE_ID,
    "name": "ToDo: Build Task",
    "type": "n8n-nodes-base.code",
    "typeVersion": 2,
    "position": BUILD_TASK_POSITION
}

TODO_CREATE_TASK_NODE = {
    "parameters": {
        "method": "POST",
        "url": "={{ $json.todoApiUrl }}",
        "authentication": "genericCredentialType",
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": "={{ JSON.stringify($json.todoTask) }}",
        "options": {
            "timeout": 15000
        },
        "genericAuthType": "oAuth2Api"
    },
    "id": CREATE_TASK_NODE_ID,
    "name": "ToDo: Create Task",
    "type": "n8n-nodes-base.httpRequest",
    "typeVersion": 4.2,
    "position": CREATE_TASK_POSITION,
    "retryOnFail": True,
    "maxTries": 3,
    "waitBetweenTries": 2000,
    "onError": "continueRegularOutput",
    "credentials": {
        "oAuth2Api": {
            "id": OAUTH2_CREDENTIAL_ID,
            "name": OAUTH2_CREDENTIAL_NAME
        }
    }
}


def add_todo_nodes(workflow: dict) -> dict:
    """Add To Do nodes to workflow, preserving all existing structure."""
    wf = copy.deepcopy(workflow)

    # --- Clean up old Planner nodes if present ---
    wf["nodes"] = [n for n in wf["nodes"] if n["id"] not in OLD_NODE_IDS]
    for old_name in OLD_NODE_NAMES:
        wf["connections"].pop(old_name, None)
    # Remove old Planner connections from Outlook: Send Email
    send_conns = wf["connections"].get("Outlook: Send Email", {}).get("main", [[]])
    if len(send_conns) > 0:
        send_conns[0] = [c for c in send_conns[0] if c["node"] not in OLD_NODE_NAMES]

    # --- Guard: check if already added ---
    existing_ids = {n["id"] for n in wf["nodes"]}
    if BUILD_TASK_NODE_ID in existing_ids:
        print("  [SKIP] ToDo nodes already present in top-level nodes")
    else:
        wf["nodes"].append(TODO_BUILD_TASK_NODE)
        wf["nodes"].append(TODO_CREATE_TASK_NODE)
        print("  [ADD] Added 2 ToDo nodes to top-level nodes")

    # --- Add connection: Outlook: Send Email → ToDo: Build Task ---
    send_conns = wf["connections"].get("Outlook: Send Email", {}).get("main", [[]])
    if len(send_conns) > 0:
        output_0 = send_conns[0]
        todo_conn = {
            "node": "ToDo: Build Task",
            "type": "main",
            "index": 0
        }
        if not any(c["node"] == "ToDo: Build Task" for c in output_0):
            output_0.append(todo_conn)
            print("  [ADD] Connected Outlook: Send Email → ToDo: Build Task")
        else:
            print("  [SKIP] Connection already exists")

    # --- Add connection: ToDo: Build Task → ToDo: Create Task ---
    if "ToDo: Build Task" not in wf["connections"]:
        wf["connections"]["ToDo: Build Task"] = {
            "main": [[{
                "node": "ToDo: Create Task",
                "type": "main",
                "index": 0
            }]]
        }
        print("  [ADD] Connected ToDo: Build Task → ToDo: Create Task")
    else:
        print("  [SKIP] ToDo: Build Task connection already exists")

    # --- Also update activeVersion if present ---
    if "activeVersion" in wf and wf["activeVersion"]:
        av = wf["activeVersion"]
        if "nodes" in av:
            # Clean up old Planner nodes
            av["nodes"] = [n for n in av["nodes"] if n["id"] not in OLD_NODE_IDS]
            av_ids = {n["id"] for n in av["nodes"]}
            if BUILD_TASK_NODE_ID not in av_ids:
                av["nodes"].append(TODO_BUILD_TASK_NODE)
                av["nodes"].append(TODO_CREATE_TASK_NODE)
                print("  [ADD] Added 2 ToDo nodes to activeVersion")

        if "connections" in av:
            # Clean up old Planner connections
            for old_name in OLD_NODE_NAMES:
                av["connections"].pop(old_name, None)
            av_send = av["connections"].get("Outlook: Send Email", {}).get("main", [[]])
            if len(av_send) > 0:
                av_send[0] = [c for c in av_send[0] if c["node"] not in OLD_NODE_NAMES]
                if not any(c["node"] == "ToDo: Build Task" for c in av_send[0]):
                    av_send[0].append({
                        "node": "ToDo: Build Task",
                        "type": "main",
                        "index": 0
                    })
            if "ToDo: Build Task" not in av["connections"]:
                av["connections"]["ToDo: Build Task"] = {
                    "main": [[{
                        "node": "ToDo: Create Task",
                        "type": "main",
                        "index": 0
                    }]]
                }
            print("  [ADD] Updated activeVersion connections")

    # --- Bump version counter ---
    wf["versionCounter"] = wf.get("versionCounter", 0) + 1

    return wf


def main():
    base = Path(__file__).resolve().parent.parent
    default_path = base / "n8n-workflows" / "01-enquiry-outlook-gemini.json"

    input_path = Path(sys.argv[1]) if len(sys.argv) > 1 else default_path
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else input_path

    print(f"Reading workflow from: {input_path}")
    with open(input_path, "r") as f:
        workflow = json.load(f)

    print(f"Current nodes: {len(workflow['nodes'])}")
    print(f"Current connections: {len(workflow['connections'])}")

    updated = add_todo_nodes(workflow)

    print(f"Updated nodes: {len(updated['nodes'])}")
    print(f"Updated connections: {len(updated['connections'])}")

    with open(output_path, "w") as f:
        json.dump(updated, f, indent=2, ensure_ascii=False)

    print(f"Written to: {output_path}")
    print("Done! Workflow now has Microsoft To Do integration nodes.")


if __name__ == "__main__":
    main()
