# Power BI Web (Mac) - Simple Dashboard Guide
## ✅ No Calculations, No DAX, Just Display Values

---

## 🎯 APPROACH: Pre-Calculate Everything in PostgreSQL

Since Power BI Service tiles can't calculate, we:
1. ✅ Calculate ALL metrics in PostgreSQL views
2. ✅ Export to CSV files
3. ✅ Upload to Power BI Service
4. ✅ Create simple tiles that just DISPLAY the values

**No DAX. No formulas. Just pure visualization.**

---

# STEP 1: PREPARE DATA (10 minutes)

## 1.1 Create Views & Export Data

```bash
# Navigate to project directory
cd /Users/ultraxen/mahlatini/chatbot

# Start Docker services
docker compose up -d
sleep 30

# Create pre-calculated views
docker exec -i chatbot-postgres-1 psql -U mahlatini -d mahlatini_chatbot < scripts/create_powerbi_simple_views.sql

# Export to CSV files
chmod +x scripts/export_powerbi_simple.sh
bash scripts/export_powerbi_simple.sh
```

**Result:** 12 CSV files in `/Users/ultraxen/mahlatini/chatbot/exports/powerbi/`

---

# STEP 2: UPLOAD TO POWER BI SERVICE (10 minutes)

## 2.1 Login

1. Open browser: **https://app.powerbi.com**
2. Login with your Microsoft account
3. Navigate to **Workspaces**

## 2.2 Create/Access Workspace

- If "Mahlatini Operations" exists → Click it
- If not → Click **"Create workspace"** → Name: `Mahlatini Operations`

## 2.3 Upload CSV Files

For each CSV file:

1. Click **"+ New"** → **"Upload a file"**
2. Select **"Local File"**
3. Navigate to `/Users/ultraxen/mahlatini/chatbot/exports/powerbi/`
4. Upload files in this order:

### Dashboard 1 Files:
- `powerbi_today_kpis.csv`
- `powerbi_agent_workload.csv`
- `powerbi_hourly_activity.csv`
- `powerbi_live_queue.csv`
- `powerbi_destination_summary.csv`

### Dashboard 2 Files:
- `powerbi_executive_kpis.csv`
- `powerbi_monthly_revenue.csv`
- `powerbi_destination_revenue.csv`

### Dashboard 3 Files:
- `powerbi_workflow_status.csv`
- `powerbi_sla_metrics.csv`
- `powerbi_quality_metrics.csv`
- `powerbi_daily_activity.csv`

---

# STEP 3: DASHBOARD 1 - OPERATIONAL (30 minutes)

## 3.1 Create Dashboard

1. In workspace, click **"+ New"** → **"Dashboard"**
2. Name: `Operational Dashboard`
3. Click **"Create"**

## 3.2 Add KPI Cards (Direct Values)

### Tile 1: Today's Enquiries

1. Click **"+ Add tile"** → **"Web content"** → **No wait!**

**Correct Method:**
1. Click **"+ New"** → **"Report"**
2. Select dataset: **`powerbi_today_kpis`**
3. This opens the report editor

**In Report Editor:**
1. Click **Visualizations** → **Card**
2. Drag field **`todays_enquiries`** to **Fields** well
3. Format:
   - Font size: 48pt
   - Data label: "Today's Enquiries"
4. Click **"File"** → **"Save"**
5. Name: `Operational Metrics`
6. Go back to dashboard → Click **"+ Add tile"** → **"Existing content"**
7. Select report → Select this visual → Click **"Pin"**

### Tile 2-6: Repeat for Other KPIs

Use the SAME report, add more **Card** visuals:

| Tile | Field from `powerbi_today_kpis` | Color Rule |
|------|--------------------------------|------------|
| Pending Tasks | `pending_tasks` | >30 = Red |
| Avg Response | `avg_response_mins` | >10 = Red |
| SLA Compliance % | `sla_compliance_pct` | <90 = Red |
| Conversion Rate % | `conversion_rate_pct` | <20 = Red |
| Agent Utilization % | `agent_utilization_pct` | <80 = Yellow |

**To add conditional formatting:**
1. Select the card visual
2. Format visual → **Conditional formatting** → **Background color**
3. Add rules (see table above)

## 3.3 Add Agent Workload Chart

1. In same report, add new **Stacked bar chart**
2. Configuration:
   - **Y-axis:** `agent_name` (from `powerbi_agent_workload`)
   - **X-axis:** `enquiry_count`
   - **Legend:** `classification`
3. Format → Data colors:
   - IMMEDIATE: #D32F2F (red)
   - IMPORTANT: #F57C00 (orange)
   - NOT_IMPORTANT: #7CB342 (green)
4. Data labels: On
5. Pin to dashboard

## 3.4 Add Hourly Trend Line Chart

1. Add **Line chart**
2. Dataset: `powerbi_hourly_activity`
3. Configuration:
   - **X-axis:** `activity_hour` (0-23)
   - **Y-axis:** `enquiry_count`
   - **Legend:** `classification`
4. Same colors as above
5. Pin to dashboard

## 3.5 Add Live Queue Table

1. Add **Table** visual
2. Dataset: `powerbi_live_queue`
3. Add columns (in order):
   - `priority` → rename to "Pri"
   - `client_name` → rename to "Client"
   - `destination`
   - `score`
   - `agent`
   - `status`
   - `age_minutes` → rename to "Age (min)"
4. Conditional formatting on `priority`:
   - IMMEDIATE: Red background
   - IMPORTANT: Orange background
   - NOT_IMPORTANT: Green background
5. Sort by `age_minutes` descending
6. Pin to dashboard

## 3.6 Add Destination Donut Chart

1. Add **Donut chart**
2. Dataset: `powerbi_destination_summary`
3. Configuration:
   - **Legend:** `destination`
   - **Values:** `enquiry_count`
4. Data labels: Percentage + value
5. Pin to dashboard

---

# STEP 4: DASHBOARD 2 - EXECUTIVE (30 minutes)

## 4.1 Create Dashboard

1. Click **"+ New"** → **"Dashboard"**
2. Name: `Executive Dashboard`

## 4.2 Create Executive Report

1. Click **"+ New"** → **"Report"**
2. Select dataset: **`powerbi_executive_kpis`**

### Add Executive KPI Cards

Create **6 Card visuals** (no calculations needed!):

| Card | Field | Format |
|------|-------|--------|
| Pipeline Value | `pipeline_value_gbp` | £#,##0 |
| Total Revenue | `total_revenue_gbp` | £#,##0 |
| Converted Deals | `converted_deals` | #,##0 |
| Avg Deal Size | `avg_deal_size_gbp` | £#,##0 |
| Conversion Rate | `conversion_rate_pct` | 0.0% |
| Pipeline Coverage | `pipeline_coverage_months` | 0.0 "months" |

Pin all to Executive Dashboard.

## 4.3 Add Monthly Revenue Trend

1. In new report, select dataset: **`powerbi_monthly_revenue`**
2. Add **Area chart**
3. Configuration:
   - **X-axis:** `month_label` (e.g., "2026-02")
   - **Y-axis:** `revenue_gbp`
   - **Legend:** `region`
4. Sort by `month_start` ascending
5. Pin to dashboard

## 4.4 Add Destination Treemap

1. Select dataset: **`powerbi_destination_revenue`**
2. Add **Treemap**
3. Configuration:
   - **Group:** `destination`
   - **Values:** `total_revenue_gbp`
   - **Tooltips:** Add `conversion_rate_pct`, `avg_deal_size_gbp`
4. Pin to dashboard

## 4.5 Add Monthly Trends Table

1. Select dataset: **`powerbi_monthly_revenue`**
2. Add **Table**
3. Columns:
   - `month_label`
   - `enquiry_count`
   - `converted_count`
   - `revenue_gbp`
   - `conversion_rate_pct`
4. Sort by `month_start` descending
5. Pin to dashboard

---

# STEP 5: DASHBOARD 3 - MONITORING (30 minutes)

## 5.1 Create Dashboard

1. Click **"+ New"** → **"Dashboard"**
2. Name: `Monitoring Dashboard`

## 5.2 Add Workflow Funnel

1. Create report with dataset: **`powerbi_workflow_status`**
2. Add **Funnel** chart
3. Configuration:
   - **Group:** `stage` (Pending → In Progress → Completed)
   - **Values:** `enquiry_count`
4. Pin to dashboard

## 5.3 Add SLA Compliance Gauge

1. Select dataset: **`powerbi_sla_metrics`**
2. Add **Gauge** (for IMMEDIATE classification)
3. Filter: `classification = "IMMEDIATE"`
4. Configuration:
   - **Value:** `sla_compliance_pct`
   - **Target:** 95
   - **Min:** 0
   - **Max:** 100
5. Format ranges:
   - 0-90: Red
   - 90-95: Yellow
   - 95-100: Green
6. Pin to dashboard

**Repeat for IMPORTANT and NOT_IMPORTANT** (3 gauges total)

## 5.4 Add SLA Performance Table

1. Select dataset: **`powerbi_sla_metrics`**
2. Add **Table**
3. Columns:
   - `classification`
   - `total_enquiries`
   - `met_sla_count`
   - `breached_sla_count`
   - `sla_compliance_pct`
   - `avg_response_mins`
4. Conditional formatting on `sla_compliance_pct`:
   - <90: Red
   - 90-95: Yellow
   - ≥95: Green
5. Pin to dashboard

## 5.5 Add Quality Metrics Cards

1. Select dataset: **`powerbi_quality_metrics`**
2. Add **4 Card visuals**:

| Card | Field | Good Threshold |
|------|-------|----------------|
| Avg Confidence | `avg_confidence` | ≥0.85 |
| Bot Resolution % | `bot_resolution_rate_pct` | ≥60% |
| Destination Complete % | `destination_complete_pct` | ≥95% |
| Avg Sync Delay | `avg_sync_delay_mins` | ≤5 min |

3. Pin all to dashboard

## 5.6 Add Daily Activity Heatmap

1. Select dataset: **`powerbi_daily_activity`**
2. Add **Matrix** visual
3. Configuration:
   - **Rows:** `day_name` (Mon, Tue, Wed...)
   - **Columns:** `activity_date`
   - **Values:** `enquiry_count`
4. Conditional formatting:
   - Color scale: White (0) → Green (high)
5. Pin to dashboard

---

# STEP 6: ORGANIZE DASHBOARDS (15 minutes)

## 6.1 Arrange Tiles

For each dashboard:

1. Click **"Edit"** → **"Edit dashboard"**
2. Drag tiles to arrange:

### Operational Dashboard Layout:
```
┌─────────────────────────────────────────────────┐
│ [Header: Operational Dashboard]                 │
├──────┬──────┬──────┬──────┬──────┬──────────────┤
│ KPI  │ KPI  │ KPI  │ KPI  │ KPI  │ KPI          │
│ #1   │ #2   │ #3   │ #4   │ #5   │ #6           │
├──────┴──────┴──────┴──────┴──────┴──────────────┤
│ [Agent Workload Bar Chart - Full Width]         │
├──────────────────────────┬──────────────────────┤
│ Hourly Trend Line Chart  │ Live Queue Table     │
├──────────────────────────┴──────────────────────┤
│ Destination Donut Chart  │ [Future: More]       │
└──────────────────────────┴──────────────────────┘
```

3. Click **"Save"** → **"Stop editing"**

## 6.2 Set Auto-Refresh (for datasets)

1. Go to **Workspace** → **Datasets**
2. For each dataset → Click **"..."** → **"Settings"**
3. Enable **"Refresh"** (if available - depends on data source type)
4. CSV files require manual re-upload

---

# STEP 7: AUTOMATION (OPTIONAL)

## 7.1 Schedule Daily Data Export

Add to cron (Mac):

```bash
# Edit crontab
crontab -e

# Add this line (runs daily at 6 AM)
0 6 * * * cd /Users/ultraxen/mahlatini/chatbot && bash scripts/export_powerbi_simple.sh >> logs/powerbi_export.log 2>&1
```

## 7.2 Manual Refresh Process

**Every morning:**
1. Run: `bash scripts/export_powerbi_simple.sh`
2. Go to Power BI Service
3. For each dataset:
   - Click **"..."** → **"Delete"** (removes old data)
   - Click **"Upload"** → Re-upload fresh CSV
4. Dashboards auto-update

---

# TROUBLESHOOTING

## Issue 1: "Cannot calculate measure"
**Solution:** You're trying to create a DAX measure. Don't! Just display the field directly.

## Issue 2: Values not updating
**Solution:**
1. Re-export CSV: `bash scripts/export_powerbi_simple.sh`
2. Delete old dataset in Power BI
3. Upload new CSV

## Issue 3: Chart shows wrong data
**Solution:** Check field mapping - ensure you're using the right column from the CSV.

## Issue 4: Conditional formatting not working
**Solution:** Format → Conditional formatting → Rules → Set thresholds on the FIELD itself, not a measure.

---

# QUICK REFERENCE: FIELD MAPPING

## Dashboard 1 (Operational)

| Visual | Dataset | Fields |
|--------|---------|--------|
| Today's Enquiries | `powerbi_today_kpis` | `todays_enquiries` |
| Pending Tasks | `powerbi_today_kpis` | `pending_tasks` |
| Agent Workload | `powerbi_agent_workload` | Y:`agent_name`, X:`enquiry_count`, Legend:`classification` |
| Hourly Trend | `powerbi_hourly_activity` | X:`activity_hour`, Y:`enquiry_count`, Legend:`classification` |
| Live Queue | `powerbi_live_queue` | All columns |
| Destination Donut | `powerbi_destination_summary` | Legend:`destination`, Values:`enquiry_count` |

## Dashboard 2 (Executive)

| Visual | Dataset | Fields |
|--------|---------|--------|
| Pipeline Value | `powerbi_executive_kpis` | `pipeline_value_gbp` |
| Total Revenue | `powerbi_executive_kpis` | `total_revenue_gbp` |
| Monthly Trend | `powerbi_monthly_revenue` | X:`month_label`, Y:`revenue_gbp`, Legend:`region` |
| Destination Treemap | `powerbi_destination_revenue` | Group:`destination`, Values:`total_revenue_gbp` |

## Dashboard 3 (Monitoring)

| Visual | Dataset | Fields |
|--------|---------|--------|
| Workflow Funnel | `powerbi_workflow_status` | Group:`stage`, Values:`enquiry_count` |
| SLA Gauge | `powerbi_sla_metrics` | Value:`sla_compliance_pct` (filtered by classification) |
| Quality Cards | `powerbi_quality_metrics` | Individual fields |
| Daily Heatmap | `powerbi_daily_activity` | Rows:`day_name`, Values:`enquiry_count` |

---

# SUCCESS CHECKLIST

## Data Preparation
- [ ] Docker services running
- [ ] Views created (12 views)
- [ ] CSVs exported (12 files)
- [ ] Files verified in `exports/powerbi/`

## Power BI Service
- [ ] Workspace created/accessed
- [ ] 12 CSV files uploaded
- [ ] 12 datasets visible

## Dashboard 1: Operational
- [ ] Dashboard created
- [ ] 6 KPI cards added
- [ ] Agent workload chart
- [ ] Hourly trend chart
- [ ] Live queue table
- [ ] Destination donut chart

## Dashboard 2: Executive
- [ ] Dashboard created
- [ ] 6 executive KPI cards
- [ ] Monthly revenue trend
- [ ] Destination treemap
- [ ] Performance table

## Dashboard 3: Monitoring
- [ ] Dashboard created
- [ ] Workflow funnel
- [ ] 3 SLA gauges
- [ ] SLA table
- [ ] 4 quality metric cards
- [ ] Daily activity heatmap

## Sharing & Access
- [ ] Dashboards shared with users
- [ ] Workspace permissions set
- [ ] Mobile layout checked

---

# ESTIMATED TIME

| Phase | Time | Complexity |
|-------|------|------------|
| Data preparation | 10 min | Easy |
| CSV upload | 10 min | Easy |
| Dashboard 1 | 30 min | Medium |
| Dashboard 2 | 30 min | Medium |
| Dashboard 3 | 30 min | Medium |
| Formatting & sharing | 15 min | Easy |
| **TOTAL** | **~2 hours** | **All dashboards** |

---

# NEXT STEPS

1. **Run the setup commands** (Step 1)
2. **Upload CSVs** (Step 2)
3. **Create dashboards** (Steps 3-5)
4. **Share with team**
5. **Schedule daily refresh** (Step 7)

**No DAX. No calculations. Just visualization. 🎉**
