#!/usr/bin/env python3

"""
census_explorer.py
Search Census variable names interactively and optionally export 
matches to a JSON snippet.
"""

import argparse
import sys
import requests
from collections import OrderedDict

def search_variables(year, dataset, keyword):
    """
    Return all variables whose label or concept contains `keyword` (case-insensitive).
    Each match is a tuple (variable_id, label, concept).
    """
    url = f"https://api.census.gov/data/{year}/{dataset}/variables.json"
    try:
        resp = requests.get(url, timeout=30)
    except requests.RequestException as e:
        sys.exit(f"ERROR: Network error fetching variables.json: {e}")

    if resp.status_code != 200:
        sys.exit(f"ERROR: HTTP {resp.status_code}. Cannot fetch variables for {dataset}/{year}.\n"
                 f"Check that the dataset and year are valid. URL: {url}")

    data = resp.json()
    variables = data.get("variables", {})
    if not variables:
        sys.exit("ERROR: No variables found in the response.")

    matches = []
    for var_id, info in variables.items():
        label = info.get("label", "")
        concept = info.get("concept", "")
        combined = f"{label} {concept}"
        if keyword.lower() in combined.lower():
            matches.append((var_id, label, concept))
    return matches


def group_by_concept(matches):
    """Group matches by concept, preserving order of first occurrence."""
    grouped = OrderedDict()
    for var_id, label, concept in matches:
        if concept not in grouped:
            grouped[concept] = {"count": 0, "first_var": var_id, "first_label": label}
        grouped[concept]["count"] += 1
    return grouped


def is_base_concept(concept_name):
    """
    Return True if the concept name does NOT contain a racial/ethnic subgroup
    marker inside parentheses (e.g., (WHITE ALONE), (BLACK...), etc.).
    """
    subgroup_markers = [
        "(white alone)",
        "(black or african american alone)",
        "(american indian and alaska native alone)",
        "(asian alone)",
        "(native hawaiian and other pacific islander alone)",
        "(some other race alone)",
        "(two or more races)",
        "(hispanic or latino)",
        "(not hispanic or latino)",
        "(white alone, not hispanic or latino)", 
    ]
    name_lower = concept_name.lower()
    for marker in subgroup_markers:
        if marker in name_lower:
            return False
    return True


def main():
    parser = argparse.ArgumentParser(description="Search Census variable names.")
    parser.add_argument("--year", type=int, default=2024, 
                        help="Data year (default: 2024)")
    parser.add_argument("--dataset", default="acs/acs5",
                        help="Dataset name (default: acs/acs5). Example: acs/acs1")
    parser.add_argument("--max-display", type=int, default=50,
                        help="Maximum number of matches to show (default: 50)")
    parser.add_argument("--max-label-len", type=int, default=90,
                        help="Truncate variable labels to this length in display (default: 90)")
    parser.add_argument("--group-by-concept", action="store_true",
                        help="Show one summary line per concept (table) instead of individual variables.")
    parser.add_argument("--sort-by", choices=["id", "alpha", "count"], default="id",
                        help="Sort concepts by first variable ID (id), name (alpha), or number of variables (count). Default: id.")
    parser.add_argument("--base-tables-only", action="store_true",
                        help="Show only base concepts (no race/ethnicity subgroup in name).")
    parser.add_argument("--keyword", default=None,
                        help="Optional keyword to search immediately (instead of interactive prompt).")
    args = parser.parse_args()

    print(f"Connected to {args.dataset}/{args.year}.\n")

    keep_loop = True
    while keep_loop:
        # Check if keyword was provided
        if args.keyword:
            keyword = args.keyword
            # Only run once if keyword is provided
            keep_loop = False
        else:
            keyword = input("Search keyword (type 'quit' to exit) : ").strip()
        
        if keyword.lower() in ("quit", "exit", "q"):
            break
        if not keyword:
            continue

        matches = search_variables(args.year, args.dataset, keyword)

        if not matches:
            print("No variables found.\n")
            continue

        if args.group_by_concept:
            grouped = group_by_concept(matches)

            if args.base_tables_only:
                grouped = OrderedDict(
                    (c, i) for c, i in grouped.items() if is_base_concept(c)
                )

            # Sort concepts according to --sort-by
            if args.sort_by == "count":
                sorted_items = sorted(grouped.items(), key=lambda x: x[1]["count"], reverse=True)
            elif args.sort_by == "id":
                sorted_items = sorted(grouped.items(), key=lambda x: x[1]["first_var"])
            else:  # alpha
                sorted_items = sorted(grouped.items(), key=lambda x: x[0].lower())

            # Rebuild as OrderedDict to maintain sort order
            sorted_grouped = OrderedDict(sorted_items)

            print(f"Found {len(matches)} variables across {len(sorted_grouped)} concepts:")
            shown = list(sorted_grouped.items())[:args.max_display]
            for concept, info in shown:
                print(f"  {info['first_var']:<16s} | {concept} ({info['count']} variables)")
            if len(sorted_grouped) > args.max_display:
                print(f"  ... and {len(sorted_grouped) - args.max_display} more concepts. Narrow your search.")
            print("\n(Use a more specific keyword to see the variables inside a concept.)")
        else:
            # Apply base-tables-only filter to flat variable list
            if args.base_tables_only:
                matches = [m for m in matches if is_base_concept(m[2])]

            # Detailed view: sort the flat variable list according to --sort-by
            if args.sort_by == "id":
                matches.sort(key=lambda x: x[0])
            elif args.sort_by == "alpha":
                matches.sort(key=lambda x: x[1].lower())

            shown = matches[:args.max_display]
            print(f"Found {len(matches)} matches (showing first {len(shown)}):")
            for var_id, label, concept in shown:
                short_label = label if len(label) <= args.max_label_len else label[:args.max_label_len-3] + "..."
                print(f"  {var_id:<16s} | {short_label}")
                if concept:
                    print(f"  {' ':<16s} |   Concept: {concept}")
            if len(matches) > args.max_display:
                print(f"  ... and {len(matches) - args.max_display} more. Narrow your search to see all.")
        print()


if __name__ == "__main__":
    main()
