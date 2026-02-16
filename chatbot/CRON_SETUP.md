# ✅ Cron Job Setup - Complete

## Status: ACTIVE ✓

Your automated sync is now running every 5 minutes.

---

## What's Running

**Schedule:** Every 5 minutes (`*/5 * * * *`)

**Script:** `/Users/ultraxen/mahlatini/chatbot/scripts/sync-leads.sh`

**Logs:** `/Users/ultraxen/mahlatini/chatbot/logs/sync.log`

**Function:** Syncs `analytics_events` → `leads` → triggers KPI updates

---

## Monitor Your Sync

### Watch logs in real-time
```bash
tail -f /Users/ultraxen/mahlatini/chatbot/logs/sync.log
```

### Check last 20 lines
```bash
tail -20 /Users/ultraxen/mahlatini/chatbot/logs/sync.log
```

### Check if cron is running
```bash
crontab -l
```

### Verify data is syncing
```bash
docker exec chatbot-postgres-1 psql -U mahlatini -d mahlatini_chatbot -c "
SELECT
  (SELECT COUNT(*) FROM leads) as leads,
  (SELECT COUNT(*) FROM analytics_events WHERE event_type = 'enquiry_classified') as analytics,
  (SELECT total_enquiries FROM powerbi_realtime_kpis) as kpi_total;
"
```

**These should match** (or be very close)

---

## Manual Commands

### Run sync manually (anytime)
```bash
/Users/ultraxen/mahlatini/chatbot/scripts/sync-leads.sh
```

### Stop automatic sync
```bash
crontab -l | grep -v sync-leads.sh | crontab -
```

### Restart automatic sync
```bash
echo "*/5 * * * * /Users/ultraxen/mahlatini/chatbot/scripts/sync-leads.sh >> /Users/ultraxen/mahlatini/chatbot/logs/sync.log 2>&1" | crontab -
```

### Clear logs (if they get too large)
```bash
> /Users/ultraxen/mahlatini/chatbot/logs/sync.log
```

---

## Expected Log Output

Every 5 minutes you should see:
```
CREATE FUNCTION
NOTICE:  === BACKFILL COMPLETE ===
NOTICE:  Inserted X new leads from analytics_events
DO
         info         | total_leads | total_conversations | total_analytics | kpi_total
----------------------+-------------+---------------------+-----------------+-----------
 === VERIFICATION === |           N |                   N |               N |         N
```

**"Inserted 0"** is normal if no new enquiries since last run.

---

## Troubleshooting

### Cron not running?
```bash
# Check if cron daemon is active (macOS)
sudo launchctl list | grep cron
```

### No logs appearing?
```bash
# Run manually to see output
/Users/ultraxen/mahlatini/chatbot/scripts/sync-leads.sh

# Check file permissions
ls -la /Users/ultraxen/mahlatini/chatbot/scripts/sync-leads.sh
# Should show: -rwxr-xr-x (executable)
```

### Data not syncing?
```bash
# Check Docker container
docker ps | grep postgres

# Check if backfill script exists
ls -la /Users/ultraxen/mahlatini/chatbot/scripts/backfill_leads_from_analytics.sql
```

---

## Success Indicators

✅ Cron job listed in `crontab -l`
✅ Log file exists and grows over time
✅ Lead count matches analytics count
✅ KPI table `total_enquiries` increases
✅ No errors in log file

---

**Your database is now auto-syncing every 5 minutes!** 🎉
