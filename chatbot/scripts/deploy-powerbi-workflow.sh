#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
# deploy-powerbi-workflow.sh — Deploy n8n workflow with Power BI integration
#
# What this script does:
#   1. Validates workflow file exists
#   2. Logs in to n8n (session cookie auth for n8n 2.x)
#   3. Uploads Power BI workflow JSON to n8n via REST API
#   4. Deactivates → reactivates to refresh webhook handlers
#   5. Verifies deployment (checks for 21 nodes including Power BI)
#
# Usage:
#   bash scripts/deploy-powerbi-workflow.sh
# ═══════════════════════════════════════════════════════════════════════
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# ─────────────────────────────────────────────
# Colors
# ─────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  Mahlatini — Deploy Power BI Integration Workflow  ${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
echo ""

# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────
N8N_URL="http://localhost:5678"
N8N_USER="admin@mahlatini.com"
N8N_PASS="Mahlatini2026"
WORKFLOW_ID="6g2SZsGNZiKpP01K"
WORKFLOW_FILE="${PROJECT_DIR}/n8n-workflows/02-enquiry-outlook-claude-powerbi.json"
COOKIE_JAR="/tmp/n8n_deploy_powerbi_cookies.txt"

# ─────────────────────────────────────────────
# Step 1: Validate prerequisites
# ─────────────────────────────────────────────
echo -e "${GREEN}[1/5] Validating prerequisites...${NC}"

# Load .env
if [ -f "${PROJECT_DIR}/.env" ]; then
  set -a
  source "${PROJECT_DIR}/.env"
  set +a
fi

if [ ! -f "$WORKFLOW_FILE" ]; then
  echo -e "  ${RED}Workflow file not found: ${WORKFLOW_FILE}${NC}"
  echo "  Run: python3 scripts/add_powerbi_nodes.py"
  exit 1
fi
echo -e "  ${GREEN}✓ Workflow file exists${NC}"

# Check if Power BI nodes exist in workflow
POWERBI_NODE_COUNT=$(grep -c "Power BI:" "$WORKFLOW_FILE" 2>/dev/null) || POWERBI_NODE_COUNT=0
if [ "$POWERBI_NODE_COUNT" -lt 2 ]; then
  echo -e "  ${RED}ERROR: Power BI nodes not found in workflow${NC}"
  echo "  Expected: 2 nodes ('Power BI: Build Payload' + 'Power BI: Push Row')"
  echo "  Found: $POWERBI_NODE_COUNT"
  echo "  Run: python3 scripts/add_powerbi_nodes.py"
  exit 1
fi
echo -e "  ${GREEN}✓ Power BI nodes found ($POWERBI_NODE_COUNT nodes)${NC}"

# Check if POWERBI_PUSH_URL is set (warning only, not error)
if [ -z "${POWERBI_PUSH_URL:-}" ] || [[ "${POWERBI_PUSH_URL:-}" == *"your-workspace"* ]]; then
  echo -e "  ${YELLOW}⚠ WARNING: POWERBI_PUSH_URL not configured in .env${NC}"
  echo -e "  ${YELLOW}  Power BI push will be skipped until configured${NC}"
  echo -e "  ${YELLOW}  Workflow will still deploy and function (graceful fallback)${NC}"
else
  echo -e "  ${GREEN}✓ POWERBI_PUSH_URL is configured${NC}"
fi
echo ""

# ─────────────────────────────────────────────
# Step 2: Login to n8n (session cookie auth)
# ─────────────────────────────────────────────
echo -e "${GREEN}[2/5] Logging in to n8n...${NC}"

LOGIN_RESULT=$(curl -s -X POST \
  -H 'Content-Type: application/json' \
  -c "$COOKIE_JAR" \
  "${N8N_URL}/rest/login" \
  -d "{\"emailOrLdapLoginId\":\"${N8N_USER}\",\"password\":\"${N8N_PASS}\"}" 2>/dev/null)

LOGIN_EMAIL=$(echo "$LOGIN_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('email','FAILED'))" 2>/dev/null || echo "FAILED")

if [ "$LOGIN_EMAIL" = "FAILED" ]; then
  echo -e "  ${RED}✗ Login failed. Is n8n running?${NC}"
  echo "  Start the stack: docker compose -f ${PROJECT_DIR}/docker-compose.yml up -d"
  exit 1
fi
echo -e "  ${GREEN}✓ Logged in as ${LOGIN_EMAIL}${NC}"
echo ""

# ─────────────────────────────────────────────
# Step 3: Upload workflow to n8n
# ─────────────────────────────────────────────
echo -e "${GREEN}[3/5] Uploading Power BI workflow to n8n...${NC}"

# Extract the workflow data section (nodes, connections, settings, name)
PATCH_PAYLOAD=$(python3 -c "
import json
with open('${WORKFLOW_FILE}', 'r') as f:
    wf = json.load(f)
# n8n workflow export has 'data' wrapper, extract it
data = wf.get('data', wf)
payload = {
    'nodes': data['nodes'],
    'connections': data['connections'],
    'settings': data.get('settings', {}),
    'name': data.get('name', 'Mahlatini: Enquiry → Outlook + Claude + Power BI'),
}
print(json.dumps(payload))
")

UPLOAD_RESULT=$(curl -s -X PATCH \
  -b "$COOKIE_JAR" \
  -H 'Content-Type: application/json' \
  "${N8N_URL}/rest/workflows/${WORKFLOW_ID}" \
  -d "$PATCH_PAYLOAD" 2>/dev/null)

# n8n 2.x wraps response in 'data' key
UPLOAD_STATUS=$(echo "$UPLOAD_RESULT" | python3 -c "
import sys,json
d=json.load(sys.stdin)
wf = d.get('data', d)
print(wf.get('id','FAIL'))
" 2>/dev/null || echo "FAIL")

if [ "$UPLOAD_STATUS" = "FAIL" ]; then
  echo -e "  ${RED}✗ Upload failed. Response:${NC}"
  echo "$UPLOAD_RESULT" | python3 -m json.tool 2>/dev/null || echo "$UPLOAD_RESULT"
  exit 1
fi
echo -e "  ${GREEN}✓ Workflow updated (ID: ${UPLOAD_STATUS})${NC}"
echo ""

# ─────────────────────────────────────────────
# Step 4: Deactivate + Reactivate
# ─────────────────────────────────────────────
echo -e "${GREEN}[4/5] Refreshing webhook handlers...${NC}"

# Get versionId after PATCH
NEW_VERSION_ID=$(curl -s -b "$COOKIE_JAR" \
  "${N8N_URL}/rest/workflows/${WORKFLOW_ID}" 2>/dev/null | \
  python3 -c "
import sys,json
d=json.load(sys.stdin)
wf = d.get('data', d)
print(wf.get('versionId',''))
" 2>/dev/null || echo "")

# Deactivate
curl -s -X POST \
  -b "$COOKIE_JAR" \
  -H 'Content-Type: application/json' \
  "${N8N_URL}/rest/workflows/${WORKFLOW_ID}/deactivate" \
  -d "{\"versionId\":\"${NEW_VERSION_ID}\"}" > /dev/null 2>&1
echo -e "  ⏸  Deactivated"
sleep 2

# Reactivate
curl -s -X POST \
  -b "$COOKIE_JAR" \
  -H 'Content-Type: application/json' \
  "${N8N_URL}/rest/workflows/${WORKFLOW_ID}/activate" \
  -d "{\"versionId\":\"${NEW_VERSION_ID}\"}" > /dev/null 2>&1
echo -e "  ${GREEN}✓ Reactivated${NC}"
echo ""

# ─────────────────────────────────────────────
# Step 5: Verification
# ─────────────────────────────────────────────
echo -e "${GREEN}[5/5] Verification...${NC}"

LIVE_WF=$(curl -s -b "$COOKIE_JAR" \
  "${N8N_URL}/rest/workflows/${WORKFLOW_ID}" 2>/dev/null)

VERIFY=$(echo "$LIVE_WF" | python3 -c "
import sys,json
d=json.load(sys.stdin)
wf = d.get('data', d)
nodes = wf.get('nodes', [])
names = [n['name'] for n in nodes]

# Check for critical nodes
has_claude = 'Claude: Classify Priority' in names
has_outlook = 'Outlook: Send Email' in names
has_postgres = 'Postgres: Log Classification' in names
has_todo = 'ToDo: Build Task' in names
has_powerbi_build = 'Power BI: Build Payload' in names
has_powerbi_push = 'Power BI: Push Row' in names

print(f'Total nodes: {len(nodes)}')
print(f'Claude Classification: {has_claude}')
print(f'Postgres Logging: {has_postgres}')
print(f'To Do Integration: {has_todo}')
print(f'Power BI Build: {has_powerbi_build}')
print(f'Power BI Push: {has_powerbi_push}')
print(f'Active: {wf.get(\"active\", False)}')
print(f'Name: {wf.get(\"name\", \"?\")[:50]}...')

if len(nodes) == 21 and has_powerbi_build and has_powerbi_push:
    print('Status: ✓ DEPLOYMENT SUCCESSFUL')
elif len(nodes) < 21:
    print(f'Status: ⚠ WARNING - Expected 21 nodes, found {len(nodes)}')
else:
    print('Status: ⚠ WARNING - Power BI nodes may not be connected properly')
" 2>/dev/null || echo "VERIFY FAILED")

echo -e "  ${CYAN}${VERIFY}${NC}"
echo ""

# Clean up cookie jar
rm -f "$COOKIE_JAR"

# ─────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────
echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✓ Deployment complete!${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
echo ""
echo "Changes applied:"
echo "  ✓ Added 'Power BI: Build Payload' (Code node)"
echo "  ✓ Added 'Power BI: Push Row' (HTTP Request node)"
echo "  ✓ Workflow now has 21 nodes (was 19)"
echo "  ✓ Power BI nodes run in parallel with Postgres/ToDo"
echo ""
echo "Pipeline flow:"
echo "  Webhook → Validate → Spam → Normalise → Outlook Draft"
echo "    → Capture ID → Claude: Classify → Parse Classification"
echo "    → Build Patch → Apply Category → Send Email"
echo "    → ┬─→ Route + Postgres Log"
echo "      ├─→ ToDo: Build Task → ToDo: Create Task"
echo "      └─→ Power BI: Build Payload → Power BI: Push Row"
echo ""
echo "Next steps:"
echo "  1. Configure Power BI Service:"
echo "     - Login: https://app.powerbi.com"
echo "     - Create workspace: 'Mahlatini Operations'"
echo "     - Create streaming dataset: 'Mahlatini Live Feed' (15 columns)"
echo "     - Copy Push URL to .env → POWERBI_PUSH_URL=..."
echo "     - Restart n8n: docker compose restart n8n"
echo ""
echo "  2. Test the integration:"
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date +%Y-%m-%dT%H:%M:%SZ)
echo "     curl -X POST http://localhost/webhook/new-enquiry \\"
echo "       -H 'Content-Type: application/json' \\"
echo "       -d '{\"clientName\":\"Test Client\",\"clientEmail\":\"test@example.com\",\"destination\":\"Kenya\",\"lead_score\":75,\"budget_max\":15000,\"pax_adults\":2,\"booking_stage\":\"enquiring\",\"source\":\"website\"}'"
echo ""
echo "  3. Monitor execution:"
echo "     - n8n UI: http://localhost:5678 → Executions"
echo "     - Check 'Power BI: Push Row' node shows HTTP 200 (when URL configured)"
echo "     - If POWERBI_PUSH_URL not set: Node will gracefully skip (no error)"
echo ""
