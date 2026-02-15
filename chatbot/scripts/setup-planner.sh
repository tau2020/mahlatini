#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
# setup-planner.sh — Configure Microsoft Planner for Mahlatini n8n
#
# Prerequisites:
#   1. Azure AD app registration (same one used for Outlook OAuth2)
#   2. Microsoft 365 account with Planner license (mark@thevortextrader.com)
#   3. Microsoft Graph CLI (optional) or manual Azure Portal setup
#
# What this script does:
#   1. Documents required Azure AD permissions
#   2. Creates the Planner Plan + "Pending" bucket via Graph API
#   3. Outputs the IDs needed for .env configuration
#
# Usage:
#   export MS_ACCESS_TOKEN="<your-bearer-token>"
#   bash scripts/setup-planner.sh
# ═══════════════════════════════════════════════════════════════════════
set -euo pipefail

# ─────────────────────────────────────────────
# Colors
# ─────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  Mahlatini — Microsoft Planner Setup              ${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
echo ""

# ─────────────────────────────────────────────
# Step 0: Check prerequisites
# ─────────────────────────────────────────────
if [ -z "${MS_ACCESS_TOKEN:-}" ]; then
  echo -e "${RED}ERROR: MS_ACCESS_TOKEN not set.${NC}"
  echo ""
  echo "To get a token, either:"
  echo "  1. Use the Graph Explorer (https://developer.microsoft.com/en-us/graph/graph-explorer)"
  echo "     - Sign in as mark@thevortextrader.com"
  echo "     - Grant consent for: Tasks.ReadWrite, Group.ReadWrite.All"
  echo "     - Copy the access token"
  echo ""
  echo "  2. Use the existing n8n OAuth2 credential:"
  echo "     - Open n8n editor → Credentials → Outlook Graph OAuth2"
  echo "     - Add scopes: Tasks.ReadWrite Group.ReadWrite.All"
  echo "     - Re-authenticate and copy the access token from browser dev tools"
  echo ""
  echo "Then run:  export MS_ACCESS_TOKEN=\"<token>\" && bash scripts/setup-planner.sh"
  exit 1
fi

GRAPH="https://graph.microsoft.com/v1.0"
AUTH="Authorization: Bearer ${MS_ACCESS_TOKEN}"
CT="Content-Type: application/json"

echo -e "${GREEN}[1/6] Checking token validity...${NC}"
ME=$(curl -s -H "$AUTH" "${GRAPH}/me" 2>/dev/null)
UPN=$(echo "$ME" | python3 -c "import sys,json; print(json.load(sys.stdin).get('userPrincipalName','UNKNOWN'))" 2>/dev/null || echo "UNKNOWN")
if [ "$UPN" = "UNKNOWN" ]; then
  echo -e "${RED}Token appears invalid. Response:${NC}"
  echo "$ME" | python3 -m json.tool 2>/dev/null || echo "$ME"
  exit 1
fi
echo -e "  Authenticated as: ${CYAN}${UPN}${NC}"
echo ""

# ─────────────────────────────────────────────
# Step 1: Find or create a Microsoft 365 Group
# ─────────────────────────────────────────────
echo -e "${GREEN}[2/6] Looking for 'Mahlatini Enquiries' group...${NC}"
GROUP_SEARCH=$(curl -s -H "$AUTH" \
  "${GRAPH}/me/memberOf?\$filter=displayName eq 'Mahlatini Enquiries'&\$select=id,displayName" 2>/dev/null)

GROUP_ID=$(echo "$GROUP_SEARCH" | python3 -c "
import sys, json
data = json.load(sys.stdin)
groups = [g for g in data.get('value', []) if g.get('displayName') == 'Mahlatini Enquiries']
print(groups[0]['id'] if groups else '')
" 2>/dev/null || echo "")

if [ -z "$GROUP_ID" ]; then
  echo -e "  Group not found. ${YELLOW}Creating...${NC}"
  CREATE_GROUP=$(curl -s -X POST -H "$AUTH" -H "$CT" "${GRAPH}/groups" -d '{
    "displayName": "Mahlatini Enquiries",
    "description": "Task management for Mahlatini travel enquiries",
    "groupTypes": ["Unified"],
    "mailEnabled": true,
    "mailNickname": "mahlatini-enquiries",
    "securityEnabled": false,
    "visibility": "Private"
  }' 2>/dev/null)
  GROUP_ID=$(echo "$CREATE_GROUP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null || echo "")

  if [ -z "$GROUP_ID" ]; then
    echo -e "${RED}  Failed to create group. Response:${NC}"
    echo "$CREATE_GROUP" | python3 -m json.tool 2>/dev/null || echo "$CREATE_GROUP"
    echo ""
    echo -e "${YELLOW}  You may need Group.ReadWrite.All permission, or create the group manually.${NC}"
    echo "  Manual steps:"
    echo "    1. Go to https://admin.microsoft.com → Groups → Add a group"
    echo "    2. Type: Microsoft 365, Name: 'Mahlatini Enquiries'"
    echo "    3. Add mark@thevortextrader.com as owner"
    echo "    4. Copy the Group ID from the admin center"
    echo "    5. Set PLANNER_GROUP_ID in .env and re-run this script"
    exit 1
  fi

  echo -e "  ${GREEN}Created group: ${GROUP_ID}${NC}"
  echo "  Waiting 10s for group provisioning..."
  sleep 10
else
  echo -e "  ${GREEN}Found existing group: ${GROUP_ID}${NC}"
fi
echo ""

# ─────────────────────────────────────────────
# Step 2: Create Planner Plan
# ─────────────────────────────────────────────
echo -e "${GREEN}[3/6] Looking for 'Enquiry Pipeline' plan...${NC}"
PLANS=$(curl -s -H "$AUTH" "${GRAPH}/groups/${GROUP_ID}/planner/plans" 2>/dev/null)
PLAN_ID=$(echo "$PLANS" | python3 -c "
import sys, json
data = json.load(sys.stdin)
plans = [p for p in data.get('value', []) if p.get('title') == 'Enquiry Pipeline']
print(plans[0]['id'] if plans else '')
" 2>/dev/null || echo "")

if [ -z "$PLAN_ID" ]; then
  echo -e "  Plan not found. ${YELLOW}Creating...${NC}"
  CREATE_PLAN=$(curl -s -X POST -H "$AUTH" -H "$CT" "${GRAPH}/planner/plans" -d "{
    \"owner\": \"${GROUP_ID}\",
    \"title\": \"Enquiry Pipeline\"
  }" 2>/dev/null)
  PLAN_ID=$(echo "$CREATE_PLAN" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null || echo "")

  if [ -z "$PLAN_ID" ]; then
    echo -e "${RED}  Failed to create plan. Response:${NC}"
    echo "$CREATE_PLAN" | python3 -m json.tool 2>/dev/null || echo "$CREATE_PLAN"
    exit 1
  fi
  echo -e "  ${GREEN}Created plan: ${PLAN_ID}${NC}"
else
  echo -e "  ${GREEN}Found existing plan: ${PLAN_ID}${NC}"
fi
echo ""

# ─────────────────────────────────────────────
# Step 3: Create buckets
# ─────────────────────────────────────────────
echo -e "${GREEN}[4/6] Setting up buckets...${NC}"
BUCKETS=$(curl -s -H "$AUTH" "${GRAPH}/planner/plans/${PLAN_ID}/buckets" 2>/dev/null)

# Parse existing buckets
EXISTING_BUCKETS=$(echo "$BUCKETS" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for b in data.get('value', []):
    print(f\"{b['name']}|{b['id']}\")
" 2>/dev/null || echo "")

# Required buckets in display order (orderHint controls position)
declare -A BUCKET_IDS
REQUIRED_BUCKETS=("Pending" "In Progress" "Awaiting Client" "Completed" "Rejected")

for bucket_name in "${REQUIRED_BUCKETS[@]}"; do
  existing_id=$(echo "$EXISTING_BUCKETS" | grep "^${bucket_name}|" | cut -d'|' -f2)
  if [ -n "$existing_id" ]; then
    echo -e "  ${GREEN}Bucket '${bucket_name}' exists: ${existing_id}${NC}"
    BUCKET_IDS[$bucket_name]="$existing_id"
  else
    echo -e "  ${YELLOW}Creating bucket '${bucket_name}'...${NC}"
    CREATE_BUCKET=$(curl -s -X POST -H "$AUTH" -H "$CT" \
      "${GRAPH}/planner/plans/${PLAN_ID}/buckets" -d "{
        \"name\": \"${bucket_name}\",
        \"planId\": \"${PLAN_ID}\",
        \"orderHint\": \" !\"
      }" 2>/dev/null)
    BID=$(echo "$CREATE_BUCKET" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null || echo "")
    if [ -n "$BID" ]; then
      echo -e "  ${GREEN}Created: ${BID}${NC}"
      BUCKET_IDS[$bucket_name]="$BID"
    else
      echo -e "  ${RED}Failed to create bucket '${bucket_name}'${NC}"
      echo "$CREATE_BUCKET" | python3 -m json.tool 2>/dev/null || echo "$CREATE_BUCKET"
    fi
    sleep 1  # Rate limit protection
  fi
done

PENDING_BUCKET_ID="${BUCKET_IDS[Pending]:-}"
if [ -z "$PENDING_BUCKET_ID" ]; then
  echo -e "${RED}ERROR: Could not find or create 'Pending' bucket${NC}"
  exit 1
fi
echo ""

# ─────────────────────────────────────────────
# Step 4: Configure plan category labels
# ─────────────────────────────────────────────
echo -e "${GREEN}[5/6] Setting plan category labels...${NC}"
# Get plan details (need @odata.etag for PATCH)
PLAN_DETAILS=$(curl -s -H "$AUTH" "${GRAPH}/planner/plans/${PLAN_ID}/details" 2>/dev/null)
PLAN_ETAG=$(echo "$PLAN_DETAILS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('@odata.etag',''))" 2>/dev/null || echo "")

if [ -n "$PLAN_ETAG" ]; then
  LABEL_UPDATE=$(curl -s -X PATCH \
    -H "$AUTH" -H "$CT" \
    -H "If-Match: ${PLAN_ETAG}" \
    "${GRAPH}/planner/plans/${PLAN_ID}/details" -d '{
      "categoryDescriptions": {
        "category2": "IMMEDIATE",
        "category3": "IMPORTANT",
        "category5": "NOT_IMPORTANT"
      }
    }' 2>/dev/null)
  echo -e "  ${GREEN}Labels set: category2=IMMEDIATE(Red), category3=IMPORTANT(Yellow), category5=NOT_IMPORTANT(Blue)${NC}"
else
  echo -e "  ${YELLOW}Could not get plan details etag — set labels manually in Planner UI${NC}"
fi
echo ""

# ─────────────────────────────────────────────
# Step 5: Output configuration
# ─────────────────────────────────────────────
echo -e "${GREEN}[6/6] Configuration summary${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
echo ""
echo "Add these to your .env file:"
echo ""
echo -e "${YELLOW}# --- Microsoft Planner (Task Management) ---${NC}"
echo "PLANNER_GROUP_ID=${GROUP_ID}"
echo "PLANNER_PLAN_ID=${PLAN_ID}"
echo "PLANNER_BUCKET_ID=${PENDING_BUCKET_ID}"
echo ""
echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
echo ""
echo "Bucket IDs (for reference):"
for name in "${REQUIRED_BUCKETS[@]}"; do
  echo "  ${name}: ${BUCKET_IDS[$name]:-NOT CREATED}"
done
echo ""

# ─────────────────────────────────────────────
# Step 6: Azure AD permissions reminder
# ─────────────────────────────────────────────
echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
echo -e "${YELLOW}REQUIRED: Azure AD App Permission Update${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
echo ""
echo "Your existing OAuth2 app registration needs these ADDITIONAL"
echo "delegated permissions (add via Azure Portal → App registrations):"
echo ""
echo "  1. Tasks.ReadWrite          (Create/update Planner tasks)"
echo "  2. Group.Read.All           (Read group to find Plan)"
echo ""
echo "Steps:"
echo "  1. Go to: https://portal.azure.com → App registrations"
echo "  2. Find your app (the one used for Outlook Graph OAuth2)"
echo "  3. API permissions → Add a permission → Microsoft Graph"
echo "  4. Delegated permissions → search 'Tasks.ReadWrite' → Add"
echo "  5. Delegated permissions → search 'Group.Read.All' → Add"
echo "  6. Click 'Grant admin consent' (if you are admin)"
echo "  7. In n8n: Credentials → Outlook Graph OAuth2 → update scope:"
echo "     Add: Tasks.ReadWrite Group.Read.All"
echo "  8. Re-authenticate the credential"
echo ""
echo "Current n8n OAuth2 scopes should become:"
echo "  openid profile email offline_access"
echo "  Mail.ReadWrite Mail.Send"
echo "  MailboxSettings.ReadWrite"
echo "  Tasks.ReadWrite Group.Read.All"
echo ""
echo -e "${GREEN}Setup complete!${NC}"
echo "Next: Run deploy-planner-workflow.sh to deploy the updated workflow."
