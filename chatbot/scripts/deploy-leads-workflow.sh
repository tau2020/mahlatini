#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════
# deploy-leads-workflow.sh
# Deploys the updated workflow with leads table INSERT to n8n
# ═══════════════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
WORKFLOW_FILE="$PROJECT_ROOT/n8n-workflows/04-enquiry-leads-connected.json"

N8N_URL="http://localhost:5678"
WORKFLOW_ID="6g2SZsGNZiKpP01K"

# Load credentials from .env
if [[ -f "$PROJECT_ROOT/chatbot/.env" ]]; then
    source "$PROJECT_ROOT/chatbot/.env"
elif [[ -f "$PROJECT_ROOT/.env" ]]; then
    source "$PROJECT_ROOT/.env"
else
    echo "❌ .env file not found"
    exit 1
fi

N8N_USER="${N8N_ADMIN_EMAIL:-admin@mahlatini.com}"
N8N_PASS="${N8N_ADMIN_PASSWORD:-Mahlatini2026}"

echo "🔐 Logging in to n8n..."
LOGIN_RESPONSE=$(curl -s -c /tmp/n8n-cookies.txt \
    -X POST "$N8N_URL/rest/login" \
    -H "Content-Type: application/json" \
    -d "{\"emailOrLdapLoginId\":\"$N8N_USER\",\"password\":\"$N8N_PASS\"}")

if echo "$LOGIN_RESPONSE" | grep -q "error"; then
    echo "❌ Login failed: $LOGIN_RESPONSE"
    exit 1
fi

echo "✅ Logged in successfully"

# Get current workflow version
echo "📡 Fetching current workflow..."
CURRENT=$(curl -s -b /tmp/n8n-cookies.txt "$N8N_URL/rest/workflows/$WORKFLOW_ID")
CURRENT_VERSION=$(echo "$CURRENT" | jq -r '.versionId')

echo "   Current versionId: $CURRENT_VERSION"

# Deactivate workflow
echo "⏸️  Deactivating workflow..."
curl -s -b /tmp/n8n-cookies.txt \
    -X PATCH "$N8N_URL/rest/workflows/$WORKFLOW_ID" \
    -H "Content-Type: application/json" \
    -d "{\"active\":false,\"versionId\":\"$CURRENT_VERSION\"}" > /dev/null

sleep 1

# Prepare update payload (extract workflow data, update versionId)
echo "📝 Preparing workflow update..."
WORKFLOW_DATA=$(cat "$WORKFLOW_FILE" | jq '.data')
UPDATE_PAYLOAD=$(jq -n \
    --argjson data "$WORKFLOW_DATA" \
    --arg versionId "$CURRENT_VERSION" \
    '{
        name: "Mahlatini: Enquiry → Outlook + Claude + Leads + Power BI",
        nodes: $data.nodes,
        connections: $data.connections,
        settings: $data.settings,
        staticData: $data.staticData,
        tags: $data.tags,
        versionId: $versionId
    }')

# Update workflow
echo "🚀 Deploying updated workflow..."
UPDATE_RESPONSE=$(curl -s -b /tmp/n8n-cookies.txt \
    -X PATCH "$N8N_URL/rest/workflows/$WORKFLOW_ID" \
    -H "Content-Type: application/json" \
    -d "$UPDATE_PAYLOAD")

NEW_VERSION=$(echo "$UPDATE_RESPONSE" | jq -r '.versionId')
echo "   New versionId: $NEW_VERSION"

# Reactivate
echo "▶️  Reactivating workflow..."
curl -s -b /tmp/n8n-cookies.txt \
    -X PATCH "$N8N_URL/rest/workflows/$WORKFLOW_ID" \
    -H "Content-Type: application/json" \
    -d "{\"active\":true,\"versionId\":\"$NEW_VERSION\"}" > /dev/null

sleep 2

# Verify
echo "🔍 Verifying deployment..."
FINAL=$(curl -s -b /tmp/n8n-cookies.txt "$N8N_URL/rest/workflows/$WORKFLOW_ID")
IS_ACTIVE=$(echo "$FINAL" | jq -r '.active')
NODE_COUNT=$(echo "$FINAL" | jq '.nodes | length')

if [[ "$IS_ACTIVE" == "true" ]]; then
    echo "✅ Workflow deployed successfully!"
    echo "   - Status: ACTIVE"
    echo "   - Nodes: $NODE_COUNT"
    echo "   - Webhook: $N8N_URL/webhook/new-enquiry"
    echo ""
    echo "🎯 Changes:"
    echo "   - Added 'Postgres: Insert Lead' node"
    echo "   - Inserts into conversations + leads tables"
    echo "   - Auto-triggers KPI table updates"
else
    echo "⚠️  Workflow deployed but not active"
    exit 1
fi

# Cleanup
rm -f /tmp/n8n-cookies.txt

echo ""
echo "📊 Next: Test with webhook POST to verify data flow"
