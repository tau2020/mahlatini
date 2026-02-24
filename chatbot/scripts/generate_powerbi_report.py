#!/usr/bin/env python3
"""
generate_powerbi_report.py
Generates a Power BI .pbix report file with a live connection to the
"Mahlatini Live Feed" streaming dataset.

Usage:
    python3 scripts/generate_powerbi_report.py

Output:
    exports/powerbi/Mahlatini_Live_Operations.pbix
"""

import json
import os
import uuid
import zipfile

# ── Configuration ──────────────────────────────────────────────────────────
WORKSPACE_NAME = "Mahlatini Operations"
WORKSPACE_ID = "e521c435-7d38-459e-889a-e374b9481ba4"
DATASET_ID = "cd9853ad-f9e8-4e80-9345-5bb373e1d031"
DATASET_NAME = "Mahlatini Live Feed"
TABLE_NAME = "RealTimeData"

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "exports", "powerbi")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "Mahlatini_Live_Operations.pbix")

# Power BI report dimensions (px)
PAGE_WIDTH = 1280
PAGE_HEIGHT = 720

# Colour palette
COLOURS = {
    "primary": "#1B3A5C",       # Mahlatini navy
    "accent": "#D4A843",        # Gold
    "immediate": "#D32F2F",     # Red
    "important": "#F57C00",     # Orange
    "not_important": "#7CB342", # Green
    "bg": "#F5F5F5",
    "card_bg": "#FFFFFF",
}


# ── Helper: unique visual IDs ─────────────────────────────────────────────
def vid():
    return str(uuid.uuid4()).replace("-", "")[:20]


# ── Helper: build a visual container ──────────────────────────────────────
def make_visual(visual_type, x, y, w, h, config, filters=None):
    """Create a visual container dict for the Layout JSON."""
    container = {
        "x": x,
        "y": y,
        "z": 0,
        "width": w,
        "height": h,
        "config": json.dumps(config),
        "filters": json.dumps(filters or []),
        "tabOrder": 0,
    }
    return container


# ── Visual configs ────────────────────────────────────────────────────────

def card_visual(title, table, column, agg="Count"):
    """Card KPI visual."""
    visual_id = vid()
    return {
        "name": visual_id,
        "layouts": [{"id": 0, "position": {"x": 0, "y": 0, "width": 1, "height": 1}}],
        "singleVisual": {
            "visualType": "card",
            "projections": {
                "Values": [{"queryRef": f"{table}.{column}"}]
            },
            "prototypeQuery": {
                "Version": 2,
                "From": [{"Name": "r", "Entity": table, "Type": 0}],
                "Select": [
                    {
                        "Aggregation": {
                            "Expression": {"Column": {"Expression": {"SourceRef": {"Source": "r"}}, "Property": column}},
                            "Function": _agg_function(agg),
                        },
                        "Name": f"{table}.{column}_{agg}",
                    }
                ],
            },
            "drillFilterOtherVisuals": True,
            "objects": {
                "labels": [{"properties": {"fontSize": {"expr": {"Literal": {"Value": "28D"}}}, "color": {"solid": {"color": {"expr": {"Literal": {"Value": f"'{COLOURS['primary']}'"}}}}}}}],
                "categoryLabels": [{"properties": {"show": {"expr": {"Literal": {"Value": "true"}}}, "text": {"expr": {"Literal": {"Value": f"'{title}'"}}}}}],
            },
            "vcObjects": {
                "title": [{"properties": {"show": {"expr": {"Literal": {"Value": "true"}}}, "text": {"expr": {"Literal": {"Value": f"'{title}'"}}}}}],
                "background": [{"properties": {"color": {"solid": {"color": {"expr": {"Literal": {"Value": f"'{COLOURS['card_bg']}'"}}}}}}}],
            },
        },
    }


def bar_visual(title, table, axis_col, value_col, value_agg="Count"):
    """Clustered bar chart."""
    visual_id = vid()
    return {
        "name": visual_id,
        "layouts": [{"id": 0, "position": {"x": 0, "y": 0, "width": 1, "height": 1}}],
        "singleVisual": {
            "visualType": "clusteredBarChart",
            "projections": {
                "Category": [{"queryRef": f"{table}.{axis_col}"}],
                "Y": [{"queryRef": f"{table}.{value_col}"}],
            },
            "prototypeQuery": {
                "Version": 2,
                "From": [{"Name": "r", "Entity": table, "Type": 0}],
                "Select": [
                    {"Column": {"Expression": {"SourceRef": {"Source": "r"}}, "Property": axis_col}, "Name": f"{table}.{axis_col}"},
                    {"Aggregation": {"Expression": {"Column": {"Expression": {"SourceRef": {"Source": "r"}}, "Property": value_col}}, "Function": _agg_function(value_agg)}, "Name": f"{table}.{value_col}_{value_agg}"},
                ],
            },
            "drillFilterOtherVisuals": True,
            "vcObjects": {
                "title": [{"properties": {"show": {"expr": {"Literal": {"Value": "true"}}}, "text": {"expr": {"Literal": {"Value": f"'{title}'"}}}}}],
            },
        },
    }


def line_visual(title, table, axis_col, value_col, value_agg="Count"):
    """Line chart."""
    visual_id = vid()
    return {
        "name": visual_id,
        "layouts": [{"id": 0, "position": {"x": 0, "y": 0, "width": 1, "height": 1}}],
        "singleVisual": {
            "visualType": "lineChart",
            "projections": {
                "Category": [{"queryRef": f"{table}.{axis_col}"}],
                "Y": [{"queryRef": f"{table}.{value_col}"}],
            },
            "prototypeQuery": {
                "Version": 2,
                "From": [{"Name": "r", "Entity": table, "Type": 0}],
                "Select": [
                    {"Column": {"Expression": {"SourceRef": {"Source": "r"}}, "Property": axis_col}, "Name": f"{table}.{axis_col}"},
                    {"Aggregation": {"Expression": {"Column": {"Expression": {"SourceRef": {"Source": "r"}}, "Property": value_col}}, "Function": _agg_function(value_agg)}, "Name": f"{table}.{value_col}_{value_agg}"},
                ],
            },
            "drillFilterOtherVisuals": True,
            "vcObjects": {
                "title": [{"properties": {"show": {"expr": {"Literal": {"Value": "true"}}}, "text": {"expr": {"Literal": {"Value": f"'{title}'"}}}}}],
            },
        },
    }


def donut_visual(title, table, legend_col, value_col, value_agg="Count"):
    """Donut chart."""
    visual_id = vid()
    return {
        "name": visual_id,
        "layouts": [{"id": 0, "position": {"x": 0, "y": 0, "width": 1, "height": 1}}],
        "singleVisual": {
            "visualType": "donutChart",
            "projections": {
                "Category": [{"queryRef": f"{table}.{legend_col}"}],
                "Y": [{"queryRef": f"{table}.{value_col}"}],
            },
            "prototypeQuery": {
                "Version": 2,
                "From": [{"Name": "r", "Entity": table, "Type": 0}],
                "Select": [
                    {"Column": {"Expression": {"SourceRef": {"Source": "r"}}, "Property": legend_col}, "Name": f"{table}.{legend_col}"},
                    {"Aggregation": {"Expression": {"Column": {"Expression": {"SourceRef": {"Source": "r"}}, "Property": value_col}}, "Function": _agg_function(value_agg)}, "Name": f"{table}.{value_col}_{value_agg}"},
                ],
            },
            "drillFilterOtherVisuals": True,
            "vcObjects": {
                "title": [{"properties": {"show": {"expr": {"Literal": {"Value": "true"}}}, "text": {"expr": {"Literal": {"Value": f"'{title}'"}}}}}],
            },
        },
    }


def pie_visual(title, table, legend_col, value_col, value_agg="Count"):
    """Pie chart (same structure as donut, different visualType)."""
    cfg = donut_visual(title, table, legend_col, value_col, value_agg)
    cfg["singleVisual"]["visualType"] = "pieChart"
    return cfg


def funnel_visual(title, table, category_col, value_col, value_agg="Count"):
    """Funnel chart."""
    visual_id = vid()
    return {
        "name": visual_id,
        "layouts": [{"id": 0, "position": {"x": 0, "y": 0, "width": 1, "height": 1}}],
        "singleVisual": {
            "visualType": "funnel",
            "projections": {
                "Category": [{"queryRef": f"{table}.{category_col}"}],
                "Y": [{"queryRef": f"{table}.{value_col}"}],
            },
            "prototypeQuery": {
                "Version": 2,
                "From": [{"Name": "r", "Entity": table, "Type": 0}],
                "Select": [
                    {"Column": {"Expression": {"SourceRef": {"Source": "r"}}, "Property": category_col}, "Name": f"{table}.{category_col}"},
                    {"Aggregation": {"Expression": {"Column": {"Expression": {"SourceRef": {"Source": "r"}}, "Property": value_col}}, "Function": _agg_function(value_agg)}, "Name": f"{table}.{value_col}_{value_agg}"},
                ],
            },
            "drillFilterOtherVisuals": True,
            "vcObjects": {
                "title": [{"properties": {"show": {"expr": {"Literal": {"Value": "true"}}}, "text": {"expr": {"Literal": {"Value": f"'{title}'"}}}}}],
            },
        },
    }


def table_visual(title, table, columns):
    """Table visual with multiple columns."""
    visual_id = vid()
    projections = [{"queryRef": f"{table}.{c}"} for c in columns]
    selects = [
        {"Column": {"Expression": {"SourceRef": {"Source": "r"}}, "Property": c}, "Name": f"{table}.{c}"}
        for c in columns
    ]
    return {
        "name": visual_id,
        "layouts": [{"id": 0, "position": {"x": 0, "y": 0, "width": 1, "height": 1}}],
        "singleVisual": {
            "visualType": "tableEx",
            "projections": {
                "Values": projections,
            },
            "prototypeQuery": {
                "Version": 2,
                "From": [{"Name": "r", "Entity": table, "Type": 0}],
                "Select": selects,
            },
            "drillFilterOtherVisuals": True,
            "vcObjects": {
                "title": [{"properties": {"show": {"expr": {"Literal": {"Value": "true"}}}, "text": {"expr": {"Literal": {"Value": f"'{title}'"}}}}}],
            },
        },
    }


def _agg_function(agg):
    """Map aggregation name to PBI function code."""
    return {
        "Count": 0,
        "Sum": 1,
        "Min": 2,
        "Max": 3,
        "Avg": 5,
        "CountNonNull": 5,
    }.get(agg, 0)


# ── Build report layout ──────────────────────────────────────────────────

def build_layout():
    """Build the complete Report/Layout JSON."""
    T = TABLE_NAME

    # ── Page 1: Operations Overview ────────────────────────────────────
    page1_visuals = [
        # Row 1: KPI Cards (4 across the top)
        make_visual("card", 20, 20, 295, 130,
                     card_visual("Total Enquiries", T, "enquiryId", "Count")),
        make_visual("card", 335, 20, 295, 130,
                     card_visual("Avg Lead Score", T, "leadScore", "Avg")),
        make_visual("card", 650, 20, 295, 130,
                     card_visual("Avg Budget (GBP)", T, "budgetMax", "Avg")),
        make_visual("card", 965, 20, 295, 130,
                     card_visual("AI Confidence", T, "classificationConfidence", "Avg")),

        # Row 2: Bar charts
        make_visual("clusteredBarChart", 20, 170, 615, 250,
                     bar_visual("Enquiries by Classification", T, "classification", "enquiryId", "Count")),
        make_visual("clusteredBarChart", 650, 170, 610, 250,
                     bar_visual("Enquiries by Destination", T, "destination", "enquiryId", "Count")),

        # Row 3: Timeline + Table
        make_visual("lineChart", 20, 440, 615, 260,
                     line_visual("Enquiry Timeline", T, "createdDate", "enquiryId", "Count")),
        make_visual("tableEx", 650, 440, 610, 260,
                     table_visual("Recent Enquiries", T,
                                  ["clientName", "destination", "classification", "leadScore", "budgetMax", "createdDate"])),
    ]

    # ── Page 2: Pipeline & Performance ─────────────────────────────────
    page2_visuals = [
        # Row 1: KPI Cards
        make_visual("card", 20, 20, 400, 130,
                     card_visual("Pipeline Value (GBP)", T, "budgetMax", "Sum")),
        make_visual("card", 440, 20, 400, 130,
                     card_visual("Total Travellers", T, "paxTotal", "Sum")),
        make_visual("card", 860, 20, 400, 130,
                     card_visual("Avg Response (secs)", T, "responseTimeSecs", "Avg")),

        # Row 2: Charts
        make_visual("donutChart", 20, 170, 400, 250,
                     donut_visual("By Urgency", T, "urgency", "enquiryId", "Count")),
        make_visual("funnel", 440, 170, 400, 250,
                     funnel_visual("By Booking Stage", T, "bookingStage", "enquiryId", "Count")),
        make_visual("pieChart", 860, 170, 400, 250,
                     pie_visual("By Source", T, "source", "enquiryId", "Count")),

        # Row 3: Bar + Table
        make_visual("clusteredBarChart", 20, 440, 500, 260,
                     bar_visual("Agent Workload", T, "assignedAgent", "enquiryId", "Count")),
        make_visual("tableEx", 540, 440, 720, 260,
                     table_visual("Enquiry Detail", T,
                                  ["enquiryId", "clientName", "clientEmail", "destination", "classification", "urgency", "leadScore"])),
    ]

    layout = {
        "id": 0,
        "resourcePackages": [
            {
                "resourcePackage": {
                    "name": "SharedResources",
                    "type": 2,
                    "items": [],
                    "disabled": False,
                }
            }
        ],
        "sections": [
            {
                "name": vid(),
                "displayName": "Operations Overview",
                "displayOption": 1,
                "width": PAGE_WIDTH,
                "height": PAGE_HEIGHT,
                "filters": "[]",
                "ordinal": 0,
                "visualContainers": page1_visuals,
                "config": json.dumps({
                    "name": vid(),
                    "layouts": [{"id": 0, "position": {}}],
                    "singleVisualGroup": None,
                }),
            },
            {
                "name": vid(),
                "displayName": "Pipeline & Performance",
                "displayOption": 1,
                "width": PAGE_WIDTH,
                "height": PAGE_HEIGHT,
                "filters": "[]",
                "ordinal": 1,
                "visualContainers": page2_visuals,
                "config": json.dumps({
                    "name": vid(),
                    "layouts": [{"id": 0, "position": {}}],
                    "singleVisualGroup": None,
                }),
            },
        ],
        "config": json.dumps({
            "version": "5.50",
            "themeCollection": {"baseTheme": {"name": "CY24SU06", "version": "5.50", "type": 2}},
            "activeSectionIndex": 0,
            "defaultDrillFilterOtherVisuals": True,
            "linguisticSchemaSyncVersion": 2,
            "settings": {
                "useStylableVisualContainerHeader": True,
                "exportDataMode": 1,
                "useNewFilterPaneExperience": True,
                "allowChangeFilterTypes": True,
                "isPersistentUserStateDisabled": True,
            },
        }),
        "filters": "[]",
    }
    return layout


# ── Build .pbix file components ───────────────────────────────────────────

def content_types_xml():
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="json" ContentType="application/json"/>
  <Default Extension="xml" ContentType="application/xml"/>
</Types>"""


def connections_json():
    conn_string = (
        f"Data Source=powerbi://api.powerbi.com/v1.0/myorg/{WORKSPACE_NAME};"
        f"Initial Catalog={DATASET_NAME};"
        "Integrated Security=ClaimsToken"
    )
    return json.dumps({
        "Version": 3,
        "Connections": [
            {
                "Name": "EntityDataSource",
                "ConnectionString": conn_string,
                "ConnectionType": "analysisServicesDatabase",
            }
        ],
    })


def metadata_json():
    return json.dumps({"createdFrom": "Cloud", "version": "1.0"})


def settings_json():
    return json.dumps({"allowChangeConnections": True})


def diagram_layout_json():
    return json.dumps({"version": "1.0", "pages": [], "scrollPosition": {"x": 0, "y": 0}})


def version_txt():
    return "2.134.340.0"


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.abspath(OUTPUT_FILE)

    print("=" * 60)
    print("  Power BI Report Generator")
    print("  Mahlatini Live Operations")
    print("=" * 60)
    print()
    print(f"  Workspace : {WORKSPACE_NAME}")
    print(f"  Dataset   : {DATASET_NAME} ({DATASET_ID})")
    print(f"  Table     : {TABLE_NAME}")
    print(f"  Output    : {output_path}")
    print()

    layout = build_layout()

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types_xml())
        zf.writestr("Version", version_txt())
        zf.writestr("Connections", connections_json())
        zf.writestr("Report/Layout", json.dumps(layout))
        zf.writestr("Metadata", metadata_json())
        zf.writestr("Settings", settings_json())
        zf.writestr("DiagramLayout", diagram_layout_json())

    size_kb = os.path.getsize(output_path) / 1024
    print(f"  Generated: {output_path} ({size_kb:.1f} KB)")
    print()
    print("  Report pages:")
    print("    1. Operations Overview  — 8 visuals (4 KPIs, 2 bars, 1 line, 1 table)")
    print("    2. Pipeline & Performance — 8 visuals (3 KPIs, donut, funnel, pie, bar, table)")
    print()
    print("  Next steps:")
    print("    1. Go to https://app.powerbi.com")
    print(f"    2. Open workspace '{WORKSPACE_NAME}'")
    print("    3. Click '+ New' -> 'Upload a file' -> 'Local File'")
    print(f"    4. Select: {output_path}")
    print(f"    5. If prompted, bind to dataset '{DATASET_NAME}'")
    print("    6. Open the report and verify visuals")
    print()

    # Print field mapping reference
    print("  Field mapping reference (if creating manually):")
    print("  " + "-" * 56)
    print("  | Visual                 | Fields                        |")
    print("  " + "-" * 56)
    fields = [
        ("Total Enquiries (Card)", "COUNT(enquiryId)"),
        ("Avg Lead Score (Card)", "AVG(leadScore)"),
        ("Avg Budget (Card)", "AVG(budgetMax)"),
        ("AI Confidence (Card)", "AVG(classificationConfidence)"),
        ("By Classification (Bar)", "classification / COUNT(enquiryId)"),
        ("By Destination (Bar)", "destination / COUNT(enquiryId)"),
        ("Enquiry Timeline (Line)", "createdDate / COUNT(enquiryId)"),
        ("Recent Enquiries (Table)", "clientName, destination, ..."),
        ("Pipeline Value (Card)", "SUM(budgetMax)"),
        ("Total Travellers (Card)", "SUM(paxTotal)"),
        ("Avg Response (Card)", "AVG(responseTimeSecs)"),
        ("By Urgency (Donut)", "urgency / COUNT(enquiryId)"),
        ("By Booking Stage (Funnel)", "bookingStage / COUNT(enquiryId)"),
        ("By Source (Pie)", "source / COUNT(enquiryId)"),
        ("Agent Workload (Bar)", "assignedAgent / COUNT(enquiryId)"),
        ("Enquiry Detail (Table)", "enquiryId, clientName, ..."),
    ]
    for vis, flds in fields:
        print(f"  | {vis:<22} | {flds:<29} |")
    print("  " + "-" * 56)
    print()


if __name__ == "__main__":
    main()
