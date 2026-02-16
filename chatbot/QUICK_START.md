# 🚀 Quick Start - Data is Flowing!

## ✅ What's Done

Your database now has:
- ✅ 4 auto-updating KPI tables (ready for Power BI)
- ✅ PostgreSQL function to insert enquiry data  
- ✅ Trigger that updates KPIs automatically
- ✅ Backfill script to sync analytics → leads
- ✅ TEST DATA CONFIRMED WORKING

## 📊 Check Your Data Right Now

```bash
docker exec chatbot-postgres-1 psql -U mahlatini -d mahlatini_chatbot -c "
SELECT 
  total_enquiries,
  total_pipeline_value,
  avg_pax_total,
  TO_CHAR(last_enquiry_at, 'YYYY-MM-DD HH24:MI:SS') as last_enquiry
FROM powerbi_realtime_kpis;
"
```

Expected output: **1 enquiry, £21,000 pipeline**

## 🔄 Daily Sync (Run This Every 5 Minutes)

```bash
docker exec -i chatbot-postgres-1 psql -U mahlatini -d mahlatini_chatbot \
  < /Users/ultraxen/mahlatini/chatbot/scripts/backfill_leads_from_analytics.sql
```

This syncs any new enquiries from `analytics_events` → `leads` → triggers KPI updates.

## 📊 Connect Power BI

1. Open Power BI Desktop
2. Get Data → PostgreSQL
3. Server: `localhost:5432`
4. Database: `mahlatini_chatbot`
5. Tables to import:
   - `powerbi_realtime_kpis` ← Real-time dashboard
   - `powerbi_hourly_metrics` ← 24hr activity
   - `powerbi_top_destinations` ← Rankings
   - `powerbi_agent_performance` ← Agent stats

All metrics are pre-calculated! Just drag fields to visuals.

## 🎯 KPI Fields Available

**From `powerbi_realtime_kpis`:**
- `total_enquiries` - Total count
- `total_pipeline_value` - £ value
- `avg_pax_total` - Avg travelers
- `count_immediate / important / not_important` - By priority
- `enquiries_last_hour` - Recent activity
- `last_enquiry_at` - Timestamp

**From `powerbi_hourly_metrics`:**
- `hour_bucket` - Time bucket  
- `enquiry_count` - Count per hour
- `pipeline_value` - £ per hour

**From `powerbi_top_destinations`:**
- `destination` - Country
- `enquiry_count` - Popularity
- `pipeline_value` - £ value

## ⚙️ Set Up Automated Sync

Add to cron (runs every 5 minutes):

```bash
crontab -e
```

Add line:
```
*/5 * * * * docker exec -i chatbot-postgres-1 psql -U mahlatini -d mahlatini_chatbot < /Users/ultraxen/mahlatini/chatbot/scripts/backfill_leads_from_analytics.sql >> /var/log/leads-sync.log 2>&1
```

## 📖 Full Documentation

See `POWER_BI_READY.md` for complete setup guide.

---

**Your database is production-ready!** 🎉
