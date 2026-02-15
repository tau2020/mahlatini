#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
# deploy-claude-workflow.sh — Deploy n8n workflow with Claude replacing
# Gemini for enquiry classification.
#
# What this script does:
#   1. Validates ANTHROPIC_API_KEY is set
#   2. Logs in to n8n (session cookie auth for n8n 2.x)
#   3. Uploads Claude workflow JSON to n8n via REST API
#   4. Deactivates → reactivates to refresh webhook handlers
#   5. Verifies deployment
#
# Usage:
#   bash scripts/deploy-claude-workflow.sh
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
echo -e "${CYAN}  Mahlatini — Deploy Claude Classification Workflow ${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
echo ""

# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────
N8N_URL="http://localhost:5678"
N8N_USER="admin@mahlatini.com"
N8N_PASS="Mahlatini2026"
WORKFLOW_ID="6g2SZsGNZiKpP01K"
WORKFLOW_FILE="${PROJECT_DIR}/n8n-workflows/01-enquiry-outlook-claude.json"
COOKIE_JAR="/tmp/n8n_deploy_cookies.txt"

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

if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo -e "  ${RED}Missing: ANTHROPIC_API_KEY in .env${NC}"
  exit 1
fi
echo -e "  ${GREEN}ANTHROPIC_API_KEY is set${NC}"

if [ ! -f "$WORKFLOW_FILE" ]; then
  echo -e "  ${RED}Workflow file not found: ${WORKFLOW_FILE}${NC}"
  echo "  Run: python3 scripts/migrate_gemini_to_claude.py"
  exit 1
fi
echo -e "  ${GREEN}Workflow file exists${NC}"

# Verify no Gemini references in workflow
GEMINI_COUNT=$(grep -ci "gemini" "$WORKFLOW_FILE" 2>/dev/null) || GEMINI_COUNT=0
if [ "$GEMINI_COUNT" -gt 0 ]; then
  echo -e "  ${RED}WARNING: ${GEMINI_COUNT} Gemini references found in workflow file${NC}"
  echo "  Re-run: python3 scripts/migrate_gemini_to_claude.py"
  exit 1
fi
echo -e "  ${GREEN}Zero Gemini references in workflow ✓${NC}"
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
  echo -e "  ${RED}Login failed. Is n8n running?${NC}"
  echo "  Start the stack: docker compose -f ${PROJECT_DIR}/docker-compose.yml up -d"
  exit 1
fi
echo -e "  ${GREEN}Logged in as ${LOGIN_EMAIL}${NC}"
echo ""

# ─────────────────────────────────────────────
# Step 3: Upload workflow to n8n
# ─────────────────────────────────────────────
echo -e "${GREEN}[3/5] Uploading Claude workflow to n8n...${NC}"

# Extract nodes, connections, settings, name for the PATCH payload
PATCH_PAYLOAD=$(python3 -c "
import json
with open('${WORKFLOW_FILE}', 'r') as f:
    wf = json.load(f)
payload = {
    'nodes': wf['nodes'],
    'connections': wf['connections'],
    'settings': wf.get('settings', {}),
    'name': wf.get('name', 'Mahlatini: Enquiry → Outlook + Claude Classification'),
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
  echo -e "  ${RED}Upload failed. Response:${NC}"
  echo "$UPLOAD_RESULT" | python3 -m json.tool 2>/dev/null || echo "$UPLOAD_RESULT"
  exit 1
fi
echo -e "  ${GREEN}Workflow updated (ID: ${UPLOAD_STATUS})${NC}"
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
echo -e "  Deactivated"
sleep 2

# Reactivate
curl -s -X POST \
  -b "$COOKIE_JAR" \
  -H 'Content-Type: application/json' \
  "${N8N_URL}/rest/workflows/${WORKFLOW_ID}/activate" \
  -d "{\"versionId\":\"${NEW_VERSION_ID}\"}" > /dev/null 2>&1
echo -e "  ${GREEN}Reactivated${NC}"
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
names=[n['name'] for n in wf.get('nodes',[])]
has_claude = 'Claude: Classify Priority' in names
has_fallback = 'Claude Fallback (IMPORTANT)' in names
has_gemini = any('Gemini' in n for n in names)
print(f'Nodes: {len(names)}')
print(f'Claude: {has_claude}  Fallback: {has_fallback}  Gemini: {has_gemini}')
print(f'Active: {wf.get(\"active\",False)}')
print(f'Name: {wf.get(\"name\",\"?\")}')" 2>/dev/null || echo "VERIFY FAILED")

echo -e "  ${CYAN}${VERIFY}${NC}"
echo ""

# Clean up cookie jar
rm -f "$COOKIE_JAR"

# ─────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────
echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}Deployment complete!${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
echo ""
echo "Changes applied:"
echo "  - Gemini API call → Claude Messages API (Anthropic)"
echo "  - Response parser updated for Claude format"
echo "  - All 'gemini*' field names → 'classification*'"
echo "  - Fallback node renamed to Claude Fallback"
echo "  - GEMINI_API_KEY no longer required"
echo ""
echo "Pipeline flow:"
echo "  Webhook → Validate → Spam → Normalise → Outlook Draft"
echo "    → Capture ID → Claude: Classify → Parse Classification"
echo "    → Build Patch → Apply Category → Send Email"
echo "    → Route + Postgres Log + ToDo: Create Task"
echo ""
echo "To test:"
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
echo "  curl -X POST http://localhost:5678/webhook/website-enquiry \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"source\":\"website_form\",\"form_data\":{\"name\":\"Test User\",\"email\":\"test@example.com\",\"destination\":\"Kruger Safari\",\"message\":\"Testing Claude classification\",\"budget_range\":\"£15000\"},\"timestamp\":\"${TS}\"}'"
echo ""
