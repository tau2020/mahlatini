#!/usr/bin/env python3
"""
Migrate n8n workflow from Gemini to Claude (Anthropic Messages API).

Changes:
1. Replaces Gemini HTTP Request node with Claude API call
2. Updates response parser for Claude's response format
3. Renames fallback node
4. Renames all field references: gemini* → classification*
5. Updates connections map (keyed by node names)
6. Updates workflow name
"""
import json
import sys
import os

WORKFLOW_IN = os.path.join(os.path.dirname(__file__), "..", "n8n-workflows", "01-enquiry-outlook-gemini.json")
WORKFLOW_OUT = os.path.join(os.path.dirname(__file__), "..", "n8n-workflows", "01-enquiry-outlook-claude.json")

# ── Claude API node (replaces Gemini HTTP Request) ─────────────────────────
CLAUDE_CLASSIFY_NODE = {
    "parameters": {
        "method": "POST",
        "url": "https://api.anthropic.com/v1/messages",
        "sendHeaders": True,
        "headerParameters": {
            "parameters": [
                {"name": "x-api-key", "value": "={{ $env.ANTHROPIC_API_KEY }}"},
                {"name": "anthropic-version", "value": "2023-06-01"},
                {"name": "content-type", "value": "application/json"},
            ]
        },
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": '={{ JSON.stringify({ model: $env.CLAUDE_MODEL || "claude-sonnet-4-5-20250929", max_tokens: 200, temperature: 0.1, messages: [{ role: "user", content: "You are an email priority classifier for Mahlatini, a luxury African safari and travel company.\\n\\nClassify the following customer enquiry into exactly ONE priority level.\\n\\nRules:\\n- IMMEDIATE: Travel within 30 days, OR explicitly says urgent/ASAP, OR lead_score >= 80, OR booking_stage is ready_to_book, OR mentions complaint/problem with existing booking, OR urgency is high/critical\\n- IMPORTANT: Travel within 90 days, OR lead_score >= 50, OR budget > £10000, OR booking_stage is considering, OR group size >= 6, OR special_occasion is set\\n- NOT_IMPORTANT: General browsing, no dates, low budget signals, newsletter signups, blog-related questions, lead_score < 30\\n\\nRespond with ONLY valid JSON, no markdown:\\n{\\"classification\\": \\"IMMEDIATE|IMPORTANT|NOT_IMPORTANT\\", \\"reason\\": \\"one sentence explanation\\", \\"confidence\\": 0.0-1.0}\\n\\n---\\nENQUIRY:\\nName: " + $json.client.name + "\\nDestination: " + ($json.enquiry.destination || "Not specified") + "\\nTravel Dates: " + ($json.enquiry.travel_dates || "Not specified") + "\\nBudget: " + ($json.enquiry.budget || "Not specified") + "\\nParty Size: " + (($json.enquiry.adults || 0) + ($json.enquiry.children || 0)) + " people\\nLead Score: " + ($json.intelligence.lead_score || "N/A") + "\\nBooking Stage: " + ($json.intelligence.booking_stage || "unknown") + "\\nUrgency: " + ($json.intelligence.urgency || "unknown") + "\\nSpecial Occasion: " + ($json.enquiry.special_occasion || "None") + "\\nMessage: " + ($json.enquiry.message || "No message").substring(0, 1000) }] }) }}',
        "options": {
            "timeout": 30000,
        },
    },
    "id": "claude-classify",
    "name": "Claude: Classify Priority",
    "type": "n8n-nodes-base.httpRequest",
    "typeVersion": 4.2,
    "position": [1648, 432],
    "retryOnFail": True,
    "maxTries": 3,
    "waitBetweenTries": 2000,
    "onError": "continueErrorOutput",
}

# ── Parse Classification node (updated for Claude response format) ──────────
PARSE_CLASSIFICATION_CODE = r"""// ═══════════════════════════════════════════════════════════════
// PARSE CLAUDE RESPONSE — extract classification from JSON
// Claude Messages API: { content: [{ type: "text", text: "..." }] }
// ═══════════════════════════════════════════════════════════════
const prevData = $('Capture Message ID').first().json;
const claudeResponse = $input.first().json;

let classification;
try {
  const rawText = claudeResponse.content[0].text;
  // Strip markdown code fences if present
  const cleaned = rawText.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/i, '').trim();
  classification = JSON.parse(cleaned);
} catch (e) {
  classification = {
    classification: 'IMPORTANT',
    reason: 'Claude response parse error — defaulting to IMPORTANT for safety',
    confidence: 0.0,
  };
}

// Validate classification value
const valid = ['IMMEDIATE', 'IMPORTANT', 'NOT_IMPORTANT'];
if (!valid.includes(classification.classification)) {
  classification.classification = 'IMPORTANT';
  classification.reason = 'Invalid classification value — defaulting to IMPORTANT';
}

return [{
  json: {
    ...prevData,
    classification: classification.classification,
    classificationReason: classification.reason,
    classificationConfidence: classification.confidence || 0,
  }
}];
"""

# ── Fallback node (updated naming) ─────────────────────────────────────────
FALLBACK_CODE = r"""// ═══════════════════════════════════════════════════════════════
// CLAUDE FALLBACK — API failed after retries, default safe
// ═══════════════════════════════════════════════════════════════
const prevData = $('Capture Message ID').first().json;

return [{
  json: {
    ...prevData,
    classification: 'IMPORTANT',
    classificationReason: 'Claude API unavailable — defaulting to IMPORTANT for human review',
    classificationConfidence: 0.0,
    classificationError: true,
  }
}];
"""

# ── Build Outlook Patch (updated field names) ──────────────────────────────
BUILD_PATCH_CODE = r"""// ═══════════════════════════════════════════════════════════════
// BUILD PATCH — construct the Outlook update body based on
// Claude classification
// ═══════════════════════════════════════════════════════════════
const data = $input.first().json;
const cls = data.classification;

const importanceMap = {
  'IMMEDIATE': 'high',
  'IMPORTANT': 'normal',
  'NOT_IMPORTANT': 'low',
};

const flagMap = {
  'IMMEDIATE': 'flagged',
  'IMPORTANT': 'notFlagged',
  'NOT_IMPORTANT': 'notFlagged',
};

return [{
  json: {
    ...data,
    outlookPatch: {
      categories: [cls],
      importance: importanceMap[cls] || 'normal',
      flag: {
        flagStatus: flagMap[cls] || 'notFlagged',
      },
    },
  }
}];
"""

# ── Respond to Webhook (updated field names) ────────────────────────────────
RESPOND_BODY = '={{ JSON.stringify({ status: "ok", classification: $("Build Outlook Patch").first().json.classification || "UNKNOWN", reason: $("Build Outlook Patch").first().json.classificationReason || "", confidence: $("Build Outlook Patch").first().json.classificationConfidence || 0, outlook_message_id: $("Capture Message ID").first().json.outlookMessageId || "" }) }}'

# ── Chatbot Complete (updated field names) ──────────────────────────────────
CHATBOT_COMPLETE_CODE = r"""// ═══════════════════════════════════════════════════════════════
// CHATBOT LOG — for chatbot-sourced leads, just return OK
// (no webhook response needed — chatbot uses fire-and-forget)
// ═══════════════════════════════════════════════════════════════
return [{ json: { status: 'ok', source: 'chatbot', classification: $json.classification } }];
"""

# ── Normalise Payload (update comment only — "Gemini" → "Claude") ──────────
def fix_normalise_comment(code: str) -> str:
    return code.replace(
        "a common schema for downstream Outlook + Gemini nodes",
        "a common schema for downstream Outlook + Claude nodes"
    )

# ── ToDo: Build Task (updated field names) ─────────────────────────────────
def fix_todo_build_task(code: str) -> str:
    code = code.replace("data.geminiClassification", "data.classification")
    code = code.replace("data.geminiReason", "data.classificationReason")
    code = code.replace("Gemini classification", "Claude classification")
    return code


# ── Node name remap (for connections map) ───────────────────────────────────
NODE_RENAME = {
    "Gemini: Classify Priority": "Claude: Classify Priority",
    "Gemini Fallback (IMPORTANT)": "Claude Fallback (IMPORTANT)",
}


def migrate_nodes(nodes: list) -> list:
    """Process a list of n8n nodes, replacing Gemini with Claude."""
    new_nodes = []
    for node in nodes:
        name = node.get("name", "")
        nid = node.get("id", "")

        # ── Replace Gemini classify node entirely
        if nid == "gemini-classify" or name == "Gemini: Classify Priority":
            new_nodes.append(CLAUDE_CLASSIFY_NODE)
            continue

        # ── Update Parse Classification
        if nid == "parse-gemini" or name == "Parse Classification":
            node = dict(node)
            node["id"] = "parse-claude"
            node["parameters"] = {"jsCode": PARSE_CLASSIFICATION_CODE}
            new_nodes.append(node)
            continue

        # ── Update Fallback
        if nid == "gemini-fallback" or name == "Gemini Fallback (IMPORTANT)":
            node = dict(node)
            node["id"] = "claude-fallback"
            node["name"] = "Claude Fallback (IMPORTANT)"
            node["parameters"] = {"jsCode": FALLBACK_CODE}
            new_nodes.append(node)
            continue

        # ── Update Build Outlook Patch
        if nid == "build-patch" or name == "Build Outlook Patch":
            node = dict(node)
            node["parameters"] = {"jsCode": BUILD_PATCH_CODE}
            new_nodes.append(node)
            continue

        # ── Update Respond to Webhook
        if nid == "respond-webhook" or name == "Respond to Webhook":
            node = dict(node)
            node["parameters"] = dict(node.get("parameters", {}))
            node["parameters"]["responseBody"] = RESPOND_BODY
            new_nodes.append(node)
            continue

        # ── Update Chatbot: Complete
        if nid == "chatbot-complete" or name == "Chatbot: Complete":
            node = dict(node)
            node["parameters"] = {"jsCode": CHATBOT_COMPLETE_CODE}
            new_nodes.append(node)
            continue

        # ── Update Normalise Payload (comment only)
        if nid == "normalise-payload" or name == "Normalise Payload":
            node = dict(node)
            node["parameters"] = dict(node.get("parameters", {}))
            if "jsCode" in node["parameters"]:
                node["parameters"]["jsCode"] = fix_normalise_comment(node["parameters"]["jsCode"])
            new_nodes.append(node)
            continue

        # ── Update ToDo: Build Task
        if nid == "todo-build-task" or name == "ToDo: Build Task":
            node = dict(node)
            node["parameters"] = dict(node.get("parameters", {}))
            if "jsCode" in node["parameters"]:
                node["parameters"]["jsCode"] = fix_todo_build_task(node["parameters"]["jsCode"])
            new_nodes.append(node)
            continue

        # ── Everything else passes through unchanged
        new_nodes.append(node)

    return new_nodes


def migrate_connections(connections: dict) -> dict:
    """Rename node references in the connections map."""
    new_connections = {}
    for src_name, outputs in connections.items():
        # Rename source key
        new_src = NODE_RENAME.get(src_name, src_name)

        # Rename target references
        new_outputs = {}
        for output_type, output_list in outputs.items():
            new_output_list = []
            for targets in output_list:
                new_targets = []
                for target in targets:
                    target = dict(target)
                    target["node"] = NODE_RENAME.get(target["node"], target["node"])
                    new_targets.append(target)
                new_output_list.append(new_targets)
            new_outputs[output_type] = new_output_list
        new_connections[new_src] = new_outputs

    return new_connections


def main():
    print(f"Reading: {WORKFLOW_IN}")
    with open(WORKFLOW_IN, "r") as f:
        wf = json.load(f)

    # ── Update workflow name
    wf["name"] = wf["name"].replace("Gemini", "Claude")

    # ── Migrate top-level nodes + connections
    wf["nodes"] = migrate_nodes(wf.get("nodes", []))
    wf["connections"] = migrate_connections(wf.get("connections", {}))

    # ── Migrate activeVersion nodes + connections
    if "activeVersion" in wf and wf["activeVersion"]:
        av = wf["activeVersion"]
        av["nodes"] = migrate_nodes(av.get("nodes", []))
        av["connections"] = migrate_connections(av.get("connections", {}))

    # ── Bump version counter
    wf["versionCounter"] = wf.get("versionCounter", 0) + 1

    # ── Write output
    print(f"Writing: {WORKFLOW_OUT}")
    with open(WORKFLOW_OUT, "w") as f:
        json.dump(wf, f, indent=2, ensure_ascii=False)

    # ── Summary
    node_names = [n["name"] for n in wf.get("nodes", [])]
    print(f"\n✓ Migrated workflow: {wf['name']}")
    print(f"  Nodes ({len(node_names)}):")
    for n in node_names:
        marker = " ← UPDATED" if "Claude" in n or "Parse" in n or "Build Outlook" in n or "Respond" in n or "Chatbot: Complete" in n or "ToDo: Build" in n else ""
        print(f"    - {n}{marker}")

    conn_keys = list(wf.get("connections", {}).keys())
    print(f"  Connections ({len(conn_keys)}):")
    for k in conn_keys:
        print(f"    - {k}")

    print(f"\n✓ Version counter: {wf['versionCounter']}")
    print(f"✓ Output: {WORKFLOW_OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
