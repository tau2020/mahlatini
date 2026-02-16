#!/usr/bin/env python3
"""
Fixes the orphaned 'Postgres: Insert Lead' node by properly wiring it into the workflow.

Current flow: Parse Classification → Claude Fallback → ...
Target flow:  Parse Classification → Postgres: Insert Lead → Claude Fallback → ...
"""

import json
import sys
from pathlib import Path

INPUT_FILE = Path(__file__).parent.parent / "n8n-workflows/03-enquiry-with-leads-insert.json"
OUTPUT_FILE = Path(__file__).parent.parent / "n8n-workflows/04-enquiry-leads-connected.json"

def fix_connections():
    """Properly wire the Postgres Insert Lead node into the workflow"""

    with open(INPUT_FILE) as f:
        workflow = json.load(f)

    connections = workflow['data']['connections']

    # Step 1: Find what "Parse Classification" currently connects to
    parse_node_name = 'Parse Classification'  # The name, not ID

    if parse_node_name in connections:
        print(f"✓ Found '{parse_node_name}' node connections")
        parse_connections = connections[parse_node_name]

        # Get the current target (should be Claude Fallback)
        current_targets = parse_connections.get('main', [[]])

        print(f"  Current targets: {current_targets}")

        # Step 2: Redirect Parse Classification → Postgres Insert Lead
        connections[parse_node_name] = {
            'main': [[{
                'node': 'Postgres: Insert Lead',
                'type': 'main',
                'index': 0
            }]]
        }
        print(f"  ✓ Redirected to Postgres: Insert Lead")

        # Step 3: Connect Postgres Insert Lead → original target
        connections['postgres-insert-lead'] = {
            'main': current_targets
        }
        print(f"  ✓ Connected Postgres: Insert Lead → {current_targets[0][0]['node'] if current_targets and current_targets[0] else 'unknown'}")

    else:
        print(f"✗ Could not find '{parse_node_name}' in connections")
        print(f"Available connection keys: {list(connections.keys())}")
        return None

    # Write updated workflow
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(workflow, f, indent=2)

    print(f"\n✅ Fixed workflow saved to: {OUTPUT_FILE}")
    print(f"   Flow: Parse Classification → Postgres Insert Lead → Claude Fallback")

    return OUTPUT_FILE

if __name__ == '__main__':
    try:
        output = fix_connections()
        if output:
            sys.exit(0)
        else:
            sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
