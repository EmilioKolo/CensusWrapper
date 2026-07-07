#!/usr/bin/env python3

"""
census_table_dump.py
Dump all estimate variables for a specific Census table ID, or list the
distinct categories available in a table (with example variable IDs).
Usage:
    python census_table_dump.py --table B01001
    python census_table_dump.py --table B01001 --json > column.json
"""

import argparse
import json
import requests
import os
import sys

from collections import OrderedDict


def get_estimate_variables(year, dataset, table_prefix):
    """Return a list of (var_id, label, concept) for estimate variables matching the prefix."""
    url = f"https://api.census.gov/data/{year}/{dataset}/variables.json"
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        sys.exit(f"ERROR: Failed to fetch variables.json: {e}")

    data = resp.json()
    variables = data.get("variables", {})
    if not variables:
        sys.exit("ERROR: No variables found in response.")

    matches = []
    for var_id, info in variables.items():
        if var_id.startswith(table_prefix) and var_id.endswith('E'):
            label = info.get("label", "")
            concept = info.get("concept", "")
            matches.append((var_id, label, concept))

    # Sort by variable ID for a natural order
    matches.sort(key=lambda x: x[0])
    return matches

def main():
    parser = argparse.ArgumentParser(description="Dump all estimate variables for a Census table.")
    parser.add_argument("--year", type=int, default=2024, help="Data year (default: 2024)")
    parser.add_argument("--dataset", default="acs/acs5", help="Dataset (default: acs/acs5)")
    parser.add_argument("--table", required=True, help="Table ID prefix (e.g., B01001)")
    parser.add_argument("--max-display", type=int, default=50,
                        help="Max variables to display (default: 50, use 9999 for all)")
    parser.add_argument("--max-label-len", type=int, default=100,
                        help="Truncate labels to this length (default: 100)")
    parser.add_argument("--list-categories", action="store_true",
                        help="Show distinct category names and their example variable IDs, then exit.")
    parser.add_argument("--output-folder", default=".",
                        help="Folder where JSON files will be saved (default: current directory).")
    args = parser.parse_args()

    table_prefix = args.table.upper()
    matches = get_estimate_variables(args.year, args.dataset, table_prefix)

    if not matches:
        sys.exit(f"No estimate variables found for table prefix '{table_prefix}'.")

    # --- Category listing mode ---
    if args.list_categories:
        # Group variables by their leaf category (the text after the last '!!')
        categories = OrderedDict()
        for var_id, label, concept in matches:
            # Extract the leaf part (e.g., "White alone" from "Estimate!!Total:!!White alone")
            parts = label.split('!!')
            leaf = parts[-1] if len(parts) >= 2 else label
            if leaf not in categories:
                categories[leaf] = {"first_var": var_id, "count": 0, "label": leaf}
            categories[leaf]["count"] += 1

        # Also add a "Total" entry if the table has a variable with just "Total:" without leaf
        # (handled by the fact that leaf might be "Total" for the universe estimate)
        if not categories:
            sys.exit("No categories found (table may only have totals).")

        print(f"Distinct categories in table {table_prefix}:")
        for leaf, info in categories.items():
            print(f"  {info['first_var']:<16s} | {leaf:<40s} ({info['count']} variable{'s' if info['count']>1 else ''})")

        # Optionally export the whole list as a JSON array of category objects (for scripting)
        export = input("\nExport this category list as JSON? (y/N): ").strip().lower()
        if export == 'y':
            outname = input("Save to file (e.g., B02001_categories.json): ").strip()
            if outname:
                if not outname.endswith('.json'):
                    outname += '.json'
                outpath = os.path.join(args.output_folder, outname)
                with open(outpath, 'w') as f:
                    json.dump(list(categories.values()), f, indent=4)
                print(f"Category list saved to {outpath}")
        sys.exit(0)

    # --- Normal variable listing mode (human-readable or interactive JSON export) ---

    # Human-readable display
    print(f"Table {table_prefix}: {len(matches)} estimate variables.")
    shown = matches[:args.max_display]
    for var_id, label, concept in shown:
        short = label if len(label) <= args.max_label_len else label[:args.max_label_len-3] + "..."
        print(f"  {var_id:<16s} | {short}")
        if concept:
            print(f"  {' ':<16s} |   Concept: {concept}")
    if len(matches) > args.max_display:
        print(f"  ... and {len(matches) - args.max_display} more variables. Use --max-display 9999 to see all.")

    # Offer interactive JSON snippet
    if len(matches) <= args.max_display:
        snippet = input("\nExport this full table as a JSON snippet? (y/N): ").strip().lower()
        if snippet == 'y':
            col_label = input("Column label (default=concept name): ").strip() or matches[0][2]
            outpath = input("Save to file (e.g., B01001_column): ").strip()
            if not outpath:
                print("No filename given; skipping export.")
            else:
                # Ensure the filename ends with .json
                if not outpath.lower().endswith('.json'):
                    outpath += '.json'
                # Prepend the output folder
                outpath = os.path.join(args.output_folder, outpath)
                entry = {"label": col_label, "variables": [m[0] for m in matches]}
                try:
                    with open(outpath, 'w') as f:
                        json.dump(entry, f, indent=4)
                    print(f"JSON snippet written to {outpath}")
                except Exception as e:
                    print(f"ERROR: Could not write file: {e}")


if __name__ == "__main__":
    main()
