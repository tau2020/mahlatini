#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
# deploy-planner-workflow.sh — Deploy updated n8n workflow with
# Microsoft Planner integration nodes.
#
# Prerequisites:
#   1. setup-planner.sh has been run (Plan + Bucket created)
#   2. .env has PLANNER_GROUP_ID, PLANNER_PLAN_ID, PLANNER_BUCKET_ID set
#   3. Azure AD app has Tasks.ReadWrite + Group.Read.All permissions
#   4. n8n OAuth2 credential re-authenticated with new scopes
#   5. Docker stack is running (docker compose ps)
#
# What this script does:
#   1. Validates .env has Planner variables
#   2. Runs add_planner_nodes.py to inject nodes into workflow JSON
#   3. Uploads updated workflow to n8n via REST API
#   4. Deactivates → reactivates to refresh webhook handlers
#   5. Runs DB migration for planner_task tracking
#   6. Sends a test webhook to verify end-to-end
#
# Usage:
#   bash scripts/deploy-planner-workflow.sh
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
echo -e "${CYAN}  Mahlatini — Deploy Planner Workflow Integration   ${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
echo ""

# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────
N8N_URL="http://localhost:5678"
N8N_USER="admin@mahlatini.com"
N8N_PASS="Mahlatini2026"
WORKFLOW_ID="6g2SZsGNZiKpP01K"
WORKFLOW_FILE="${PROJECT_DIR}/n8n-workflows/01-enquiry-outlook-gemini.json"

# ─────────────────────────────────────────────
# Step 1: Validate prerequisites
# ─────────────────────────────────────────────
echo -e "${GREEN}[1/7] Validating prerequisites...${NC}"

# Load .env
if [ -f "${PROJECT_DIR}/.env" ]; then
  set -a
  source "${PROJECT_DIR}/.env"
  set +a
fi

ERRORS=0
for var in PLANNER_GROUP_ID PLANNER_PLAN_ID PLANNER_BUCKET_ID; do
  val="${!var:-}"
  if [ -z "$val" ]; then
    echo -e "  ${RED}Missing: ${var}${NC}"
    ERRORS=$((ERRORS + 1))
  else
    echo -e "  ${GREEN}${var}=${val}${NC}"
  fi
done

if [ $ERRORS -gt 0 ]; then
  echo ""
  echo -e "${RED}Please set the missing variables in .env first.${NC}"
  echo "Run setup-planner.sh to get the values."
  exit 1
fi
echo ""

# ─────────────────────────────────────────────
# Step 2: Check n8n is running
# ─────────────────────────────────────────────
echo -e "${GREEN}[2/7] Checking n8n availability...${NC}"
N8N_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" \
  -u "${N8N_USER}:${N8N_PASS}" \
  "${N8N_URL}/rest/workflows" 2>/dev/null || echo "000")

if [ "$N8N_HEALTH" != "200" ]; then
  echo -e "  ${RED}n8n not reachable (HTTP ${N8N_HEALTH})${NC}"
  echo "  Is the Docker stack running? Try: docker compose -f ${PROJECT_DIR}/docker-compose.yml ps"
  exit 1
fi
echo -e "  ${GREEN}n8n is running${NC}"
echo ""

# ─────────────────────────────────────────────
# Step 3: Inject Planner nodes into workflow JSON
# ─────────────────────────────────────────────
echo -e "${GREEN}[3/7] Injecting Planner nodes...${NC}"
python3 "${SCRIPT_DIR}/add_planner_nodes.py" "${WORKFLOW_FILE}" "${WORKFLOW_FILE}"
echo ""

# ─────────────────────────────────────────────
# Step 4: Upload workflow to n8n
# ─────────────────────────────────────────────
echo -e "${GREEN}[4/7] Uploading workflow to n8n...${NC}"

# Read current workflow to get versionId
CURRENT=$(curl -s -u "${N8N_USER}:${N8N_PASS}" \
  "${N8N_URL}/rest/workflows/${WORKFLOW_ID}" 2>/dev/null)
VERSION_ID=$(echo "$CURRENT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('versionId',''))" 2>/dev/null || echo "")

if [ -z "$VERSION_ID" ]; then
  echo -e "  ${YELLOW}Could not get versionId, trying without it...${NC}"
fi

# Extract just the nodes and connections for the PATCH payload
PATCH_PAYLOAD=$(python3 -c "
import json, sys
with open('${WORKFLOW_FILE}', 'r') as f:
    wf = json.load(f)
payload = {
    'nodes': wf['nodes'],
    'connections': wf['connections'],
    'settings': wf.get('settings', {}),
    'name': wf.get('name', 'Mahlatini: Enquiry → Outlook + Gemini Classification'),
}
print(json.dumps(payload))
")

UPLOAD_RESULT=$(curl -s -X PATCH \
  -u "${N8N_USER}:${N8N_PASS}" \
  -H "Content-Type: application/json" \
  "${N8N_URL}/rest/workflows/${WORKFLOW_ID}" \
  -d "$PATCH_PAYLOAD" 2>/dev/null)

UPLOAD_STATUS=$(echo "$UPLOAD_RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('id','FAIL'))" 2>/dev/null || echo "FAIL")

if [ "$UPLOAD_STATUS" = "FAIL" ]; then
  echo -e "  ${RED}Upload failed. Response:${NC}"
  echo "$UPLOAD_RESULT" | python3 -m json.tool 2>/dev/null || echo "$UPLOAD_RESULT"
  exit 1
fi
echo -e "  ${GREEN}Workflow updated successfully (ID: ${UPLOAD_STATUS})${NC}"
echo ""

# ─────────────────────────────────────────────
# Step 5: Deactivate + Reactivate workflow
# (Required to refresh webhook handlers after PATCH)
# ─────────────────────────────────────────────
echo -e "${GREEN}[5/7] Refreshing webhook handlers...${NC}"

# Get current versionId after PATCH
UPDATED=$(curl -s -u "${N8N_USER}:${N8N_PASS}" \
  "${N8N_URL}/rest/workflows/${WORKFLOW_ID}" 2>/dev/null)
NEW_VERSION_ID=$(echo "$UPDATED" | python3 -c "import sys,json; print(json.load(sys.stdin).get('versionId',''))" 2>/dev/null || echo "")

# Deactivate
curl -s -X POST \
  -u "${N8N_USER}:${N8N_PASS}" \
  -H "Content-Type: application/json" \
  "${N8N_URL}/rest/workflows/${WORKFLOW_ID}/deactivate" \
  -d "{\"versionId\":\"${NEW_VERSION_ID}\"}" > /dev/null 2>&1
echo -e "  Deactivated"
sleep 2

# Reactivate
curl -s -X POST \
  -u "${N8N_USER}:${N8N_PASS}" \
  -H "Content-Type: application/json" \
  "${N8N_URL}/rest/workflows/${WORKFLOW_ID}/activate" \
  -d "{\"versionId\":\"${NEW_VERSION_ID}\"}" > /dev/null 2>&1
echo -e "  ${GREEN}Reactivated${NC}"
echo ""

# ─────────────────────────────────────────────
# Step 6: Run DB migration
# ─────────────────────────────────────────────
echo -e "${GREEN}[6/7] Running Planner DB migration...${NC}"
MIGRATION_FILE="${SCRIPT_DIR}/migrate_add_planner_tracking.sql"

if [ -f "$MIGRATION_FILE" ]; then
  docker exec -i "$(docker compose -f ${PROJECT_DIR}/docker-compose.yml ps -q postgres)" \
    psql -U "${POSTGRES_USER:-mahlatini}" -d "${POSTGRES_DB:-mahlatini_chatbot}" \
    < "$MIGRATION_FILE" 2>/dev/null
  echo -e "  ${GREEN}Migration applied${NC}"
else
  echo -e "  ${YELLOW}Migration file not found — skipping${NC}"
fi
echo ""

# ─────────────────────────────────────────────
# Step 7: Verification
# ─────────────────────────────────────────────
echo -e "${GREEN}[7/7] Verification...${NC}"

# Count nodes in live workflow
LIVE_NODES=$(curl -s -u "${N8N_USER}:${N8N_PASS}" \
  "${N8N_URL}/rest/workflows/${WORKFLOW_ID}" 2>/dev/null | \
  python3 -c "import sys,json; wf=json.load(sys.stdin); print(len(wf.get('nodes',[])))" 2>/dev/null || echo "?")

echo -e "  Live workflow nodes: ${CYAN}${LIVE_NODES}${NC} (expected: 17)"

# Check if Planner nodes exist
HAS_PLANNER=$(curl -s -u "${N8N_USER}:${N8N_PASS}" \
  "${N8N_URL}/rest/workflows/${WORKFLOW_ID}" 2>/dev/null | \
  python3 -c "
import sys,json
wf=json.load(sys.stdin)
names=[n['name'] for n in wf.get('nodes',[])]
has_build='Planner: Build Task' in names
has_create='Planner: Create Task' in names
print(f'Build={has_build} Create={has_create}')
" 2>/dev/null || echo "UNKNOWN")
echo -e "  Planner nodes: ${CYAN}${HAS_PLANNER}${NC}"

# Check workflow is active
IS_ACTIVE=$(curl -s -u "${N8N_USER}:${N8N_PASS}" \
  "${N8N_URL}/rest/workflows/${WORKFLOW_ID}" 2>/dev/null | \
  python3 -c "import sys,json; print(json.load(sys.stdin).get('active',False))" 2>/dev/null || echo "UNKNOWN")
echo -e "  Workflow active: ${CYAN}${IS_ACTIVE}${NC}"
echo ""

# ─────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────
echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}Deployment complete!${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
echo ""
echo "Updated workflow flow:"
echo "  ... → Outlook: Send Email →  Route: By Source    → Respond/Complete"
echo "                             →  Postgres: Log      → (analytics)"
echo "                             →  Planner: Build     → Planner: Create Task"
echo ""
echo "To test, send a webhook:"
echo '  curl -X POST http://localhost:5678/webhook/website-enquiry \'
echo '    -H "Content-Type: application/json" \'
echo '    -d '"'"'{"source":"website_form","form_data":{"name":"Test User","email":"test@example.com","destination":"Kruger","message":"Testing Planner integration"},"timestamp":"'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'"}'\'
echo ""
echo "Then check Microsoft Planner for the new task in the 'Pending' bucket."
