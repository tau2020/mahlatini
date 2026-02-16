#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════
# export_powerbi_data.sh
# Exports Power BI analytical views to CSV files for web upload
#
# Usage: bash scripts/export_powerbi_data.sh
# Output: Creates CSV files in exports/ directory
# ═══════════════════════════════════════════════════════════════════════

EXPORT_DIR="/Users/ultraxen/mahlatini/chatbot/exports"
CONTAINER="chatbot-postgres-1"
DB_USER="mahlatini"
DB_NAME="mahlatini_chatbot"

# Create export directory
mkdir -p "$EXPORT_DIR"

echo "Starting Power BI data export..."
echo "Export directory: $EXPORT_DIR"
echo ""

# Function to export a view/table to CSV
export_to_csv() {
    local table_name=$1
    local output_file="$EXPORT_DIR/${table_name}.csv"

    echo "Exporting $table_name..."
    docker exec -i "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -c "\COPY (SELECT * FROM $table_name) TO STDOUT WITH CSV HEADER" > "$output_file"

    # Get row count
    local row_count=$(docker exec -i "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT COUNT(*) FROM $table_name")
    echo "  ✓ Exported $row_count rows to ${table_name}.csv"
}

# Export dimension tables
echo "=== Exporting Dimension Tables ==="
export_to_csv "dim_agents"
export_to_csv "dim_date"
export_to_csv "destinations"
export_to_csv "sla_targets"
echo ""

# Export analytical views
echo "=== Exporting Analytical Views ==="
export_to_csv "v_powerbi_enquiry_fact"
export_to_csv "v_powerbi_agent_performance"
export_to_csv "v_powerbi_sla_compliance"
export_to_csv "v_powerbi_revenue_pipeline"
export_to_csv "v_powerbi_monthly_trends"
export_to_csv "v_powerbi_destination_stats"
echo ""

# Export base tables (for reference)
echo "=== Exporting Base Tables ==="
export_to_csv "leads"
export_to_csv "conversations"
echo ""

echo "════════════════════════════════════════════════════════════════════"
echo "Export complete!"
echo "Files location: $EXPORT_DIR"
echo ""
echo "Next steps:"
echo "1. Go to https://app.powerbi.com"
echo "2. Navigate to your workspace"
echo "3. Click 'New' → 'Upload a file'"
echo "4. Upload the CSV files"
echo "════════════════════════════════════════════════════════════════════"
