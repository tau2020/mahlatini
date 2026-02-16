#!/bin/bash
# Auto-sync script - runs backfill every 5 minutes
# Syncs analytics_events → leads table → triggers KPI updates

docker exec -i chatbot-postgres-1 psql -U mahlatini -d mahlatini_chatbot \
  < /Users/ultraxen/mahlatini/chatbot/scripts/backfill_leads_from_analytics.sql
