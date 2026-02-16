#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════
# export_powerbi_simple.sh
# Exports PRE-CALCULATED Power BI views to CSV (no DAX calculations needed)
#
# Usage: bash scripts/export_powerbi_simple.sh
# Output: Creates CSV files in exports/powerbi/ directory
# ═══════════════════════════════════════════════════════════════════════

EXPORT_DIR="/Users/ultraxen/mahlatini/chatbot/exports/powerbi"
CONTAINER="chatbot-postgres-1"
DB_USER="mahlatini"
DB_NAME="mahlatini_chatbot"

# Create export directory
mkdir -p "$EXPORT_DIR"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  Power BI Data Export (Pre-Calculated Views)                ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo "Export directory: $EXPORT_DIR"
echo ""

# Function to export a view to CSV
export_to_csv() {
    local view_name=$1
    local output_file="$EXPORT_DIR/${view_name}.csv"
    local friendly_name=$2

    echo "📊 Exporting: $friendly_name"
    docker exec -i "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -c "\COPY (SELECT * FROM $view_name) TO STDOUT WITH CSV HEADER" > "$output_file"

    # Get row count
    local row_count=$(docker exec -i "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT COUNT(*) FROM $view_name" | tr -d ' ')
    echo "   ✓ Exported $row_count rows to ${view_name}.csv"
    echo ""
}

# Export Dashboard 1: Operational Views
echo "┌──────────────────────────────────────────────────────────────┐"
echo "│ Dashboard 1: OPERATIONAL (Department Head)                   │"
echo "└──────────────────────────────────────────────────────────────┘"
export_to_csv "powerbi_today_kpis" "Today's KPI Summary"
export_to_csv "powerbi_agent_workload" "Agent Workload by Classification"
export_to_csv "powerbi_hourly_activity" "Hourly Activity (Last 48 hours)"
export_to_csv "powerbi_live_queue" "Live Enquiry Queue (Top 20)"
export_to_csv "powerbi_destination_summary" "Top 10 Destinations"

# Export Dashboard 2: Executive Views
echo "┌──────────────────────────────────────────────────────────────┐"
echo "│ Dashboard 2: EXECUTIVE (CEO)                                 │"
echo "└──────────────────────────────────────────────────────────────┘"
export_to_csv "powerbi_executive_kpis" "Executive Summary KPIs"
export_to_csv "powerbi_monthly_revenue" "Monthly Revenue Trends"
export_to_csv "powerbi_destination_revenue" "Destination Performance"

# Export Dashboard 3: Monitoring Views
echo "┌──────────────────────────────────────────────────────────────┐"
echo "│ Dashboard 3: MONITORING (Quality/Workflow)                   │"
echo "└──────────────────────────────────────────────────────────────┘"
export_to_csv "powerbi_workflow_status" "Workflow Stage Status"
export_to_csv "powerbi_sla_metrics" "SLA Performance Metrics"
export_to_csv "powerbi_quality_metrics" "Data Quality Metrics"
export_to_csv "powerbi_daily_activity" "Daily Activity (Last 30 days)"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  ✅ Export Complete!                                         ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "📁 Files location: $EXPORT_DIR"
echo "📊 Total files: 12 CSV files"
echo ""
echo "🔄 Next steps:"
echo "   1. Go to https://app.powerbi.com"
echo "   2. Navigate to 'Mahlatini Operations' workspace"
echo "   3. Click 'New' → 'Upload a file'"
echo "   4. Upload these CSV files"
echo "   5. Create dashboards using the uploaded datasets"
echo ""
echo "💡 Tip: These files contain PRE-CALCULATED values."
echo "   No DAX measures needed - just display the fields directly!"
echo ""
