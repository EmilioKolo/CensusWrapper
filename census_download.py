#!/usr/bin/env python3

"""
census_download.py
Download raw estimates for a given set of variables (from a JSON file)
for all US states and save as a CSV table.

Usage:
    python census_download.py \
        --input median_age_by_sex.json
    python census_download.py \
        --input my_vars.json \
        --year 2024 \
        --dataset acs/acs5 \
        --output table.csv
"""

import os
import sys
import json
import argparse
import requests
import pandas as pd
from getpass import getpass

# ----------------------------------------------------------------------
# API key
# ----------------------------------------------------------------------

def get_api_key():
    key = os.environ.get("CENSUS_API_KEY")
    if key:
        return key
    print("A Census API key is required to download data.")
    print("Get one free at: https://api.census.gov/data/key_signup.html")
    print("You can set it as an environment variable with the following command:")
    print("[Linux/Mac] export CENSUS_API_KEY=YOUR_KEY")
    print("[Windows] setx CENSUS_API_KEY \"YOUR_KEY\"")
    print("Alternatively, you can enter it now (it will not be remembered).")
    key = getpass("Enter your Census API key: ").strip()
    if not key:
        sys.exit("ERROR: No API key provided. Exiting.")
    return key

# ----------------------------------------------------------------------
# State names
# ----------------------------------------------------------------------

STATE_NAMES = {
    '01': 'Alabama', '02': 'Alaska', '04': 'Arizona', '05': 'Arkansas',
    '06': 'California', '08': 'Colorado', '09': 'Connecticut', '10': 'Delaware',
    '11': 'District of Columbia', '12': 'Florida', '13': 'Georgia', '15': 'Hawaii',
    '16': 'Idaho', '17': 'Illinois', '18': 'Indiana', '19': 'Iowa',
    '20': 'Kansas', '21': 'Kentucky', '22': 'Louisiana', '23': 'Maine',
    '24': 'Maryland', '25': 'Massachusetts', '26': 'Michigan', '27': 'Minnesota',
    '28': 'Mississippi', '29': 'Missouri', '30': 'Montana', '31': 'Nebraska',
    '32': 'Nevada', '33': 'New Hampshire', '34': 'New Jersey', '35': 'New Mexico',
    '36': 'New York', '37': 'North Carolina', '38': 'North Dakota', '39': 'Ohio',
    '40': 'Oklahoma', '41': 'Oregon', '42': 'Pennsylvania', '44': 'Rhode Island',
    '45': 'South Carolina', '46': 'South Dakota', '47': 'Tennessee', '48': 'Texas',
    '49': 'Utah', '50': 'Vermont', '51': 'Virginia', '53': 'Washington',
    '54': 'West Virginia', '55': 'Wisconsin', '56': 'Wyoming'
}

# ----------------------------------------------------------------------
# Fetch data from Census API
# ----------------------------------------------------------------------

def fetch_variables(variables, year, dataset, api_key):
    """
    Fetch variables in batches of set size and return a merged DataFrame.
    """
    all_chunks = []
    batch_size = 50

    # Split variables into batches of batch_size
    for i in range(0, len(variables), batch_size):
        batch = variables[i:i+batch_size]
        var_str = ",".join(batch)
        url = f"https://api.census.gov/data/{year}/{dataset}?get={var_str}&for=state:*&key={api_key}"
        try:
            resp = requests.get(url, timeout=60)
        except requests.RequestException as e:
            sys.exit(f"ERROR: Network error: {e}")

        if resp.status_code != 200:
            sys.exit(f"ERROR: API request failed (HTTP {resp.status_code}).\n"
                     f"URL: {url}\nResponse snippet: {resp.text[:300]}")

        data = resp.json()
        if not data or len(data) < 2:
            sys.exit("ERROR: API returned unexpected or empty data.")

        header = data[0]
        missing = set(batch) - set(header)
        if missing:
            sys.exit(f"ERROR: These variables were not in the API response: {missing}\n"
                     f"Available variables include: {sorted(header)[:20]} ...")

        df_chunk = pd.DataFrame(data[1:], columns=data[0])
        for v in batch:
            df_chunk[v] = pd.to_numeric(df_chunk[v], errors="coerce")

        # Keep state columns for merging; only need to extract them once
        if 'state' in df_chunk.columns:
            df_chunk["state_fips"] = df_chunk["state"].astype(str).str.zfill(2)
            df_chunk["state_name"] = df_chunk["state_fips"].map(STATE_NAMES)
            df_chunk = df_chunk.drop(columns=["state"])
        all_chunks.append(df_chunk)

    # Merge all chunks on state_fips (and state_name)
    if not all_chunks:
        sys.exit("No data fetched.")
    final_df = all_chunks[0]
    for chunk in all_chunks[1:]:
        # merge on both state_fips and state_name to be safe
        final_df = final_df.merge(chunk, on=["state_fips", "state_name"], how="outer")

    return final_df

def get_variable_labels(variables, year, dataset):
    """Return a dict mapping each variable ID to its label.
    Falls back to the variable ID if the label isn't found."""
    url = f"https://api.census.gov/data/{year}/{dataset}/variables.json"
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        all_vars = resp.json()["variables"]
    except Exception as e:
        print(f"WARNING: Could not fetch variable labels ({e}). Using IDs.")
        return {v: v for v in variables}

    labels = {}
    for v in variables:
        if v in all_vars:
            # Use the clean label
            labels[v] = clean_label(all_vars[v]["label"])
        else:
            labels[v] = v
    return labels

def clean_label(raw_label):
    """
    Convert Census label like 'Estimate!!Total:!!Male:!!Under 5 years'
    to 'Total_Male_Under 5 years'.
    """
    # Remove leading 'Estimate!!'
    if raw_label.startswith("Estimate!!"):
        raw_label = raw_label[len("Estimate!!"):]
    # Split on '!!' and clean each segment
    parts = raw_label.split("!!")
    cleaned = []
    for p in parts:
        # remove trailing colon and whitespace
        p = p.strip().rstrip(":")
        # Remove commas
        p = p.replace(",", "")
        # Remove semicolons
        p = p.replace(";", "")
        # Change spaces to underscores
        p = p.replace(" ", "_")
        cleaned.append(p)
    return "//".join(cleaned)

def save_depth_tables(df, output_prefix, separator="//"):
    """
    Save one CSV per depth level.
    For depth D, include:
      - every column exactly at depth D (leaf or not)
      - any leaf column whose depth is < D (it ends early, so carry it forward)
    """
    var_cols = [c for c in df.columns if c != "State"]
    if not var_cols:
        print("WARNING: No variable columns found. Skipping depth split.")
        return

    # Identify leaf status and depth for each variable column
    leaf_status = {}
    depth_map = {}
    for col in var_cols:
        depth = len(col.split(separator))
        depth_map[col] = depth
        # A column is a leaf if no other column starts with col + separator
        is_leaf = not any(other.startswith(col + separator) for other in var_cols if other != col)
        leaf_status[col] = is_leaf

    max_depth = max(depth_map.values())

    for d in range(1, max_depth + 1):
        selected = set()
        for col in var_cols:
            if depth_map[col] == d:
                selected.add(col)
            elif leaf_status[col] and depth_map[col] < d:
                selected.add(col)

        if not selected:
            print(f"WARNING: No columns for depth {d}. Skipping.")
            continue

        # Keep original column order
        selected_ordered = [c for c in df.columns if c == "State" or c in selected]
        sub_df = df[selected_ordered]
        outfile = f"{output_prefix}_depth_{d}.csv"
        sub_df.to_csv(outfile, index=False)
        print(f"Saved {outfile} ({len(selected)} variable columns).")

# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Download raw Census variables by state from a JSON definition."
    )
    parser.add_argument(
        "--input", 
        required=True, 
        help="JSON file with 'label' and 'variables' (list of variable IDs)."
    )
    parser.add_argument(
        "--year", 
        type=int, 
        default=2024, 
        help="Data year (default: 2024)"
    )
    parser.add_argument(
        "--dataset", 
        default="acs/acs5", 
        help="Dataset (default: acs/acs5)"
    )
    parser.add_argument(
        "--output", 
        default=None, 
        help="Output CSV file. Default: <label>.csv"
    )
    args = parser.parse_args()

    # Load the JSON definition
    with open(args.input) as f:
        col_def = json.load(f)

    if "variables" not in col_def or not isinstance(col_def["variables"], list):
        sys.exit("ERROR: JSON file must contain a 'variables' list.")
    label = col_def.get("label", "data")
    variables = col_def["variables"]

    # Make sure the output folder exists
    if args.output:
        output_folder = os.path.dirname(args.output)
        if output_folder and not os.path.exists(output_folder):
            os.makedirs(output_folder, exist_ok=True)

    print(f"Fetching {len(variables)} variables for {label}...")
    api_key = get_api_key()

    raw = fetch_variables(variables, args.year, args.dataset, api_key)

    # Get human-readable labels for the columns
    var_labels = get_variable_labels(variables, args.year, args.dataset)

    out_df = raw[["state_name"] + variables].copy()
    # Rename variable columns to their labels
    out_df.rename(columns=var_labels, inplace=True)
    out_df.rename(columns={"state_name": "State"}, inplace=True)

    
    # Define output file name
    if args.output:
        outfile = args.output
        output_folder = os.path.dirname(outfile)
        basename = os.path.basename(outfile).split(".")[0]
    else:
        # Define a safe label for filenames
        safe_label = label.replace(" ", "_").replace("/", "_").replace("\\", "_")
        outfile = f"{safe_label}_total.csv"
        basename = safe_label

    out_df.to_csv(outfile, index=False)
    print(f"Table saved to {outfile} ({len(out_df)} rows, {len(out_df.columns)} columns).")
    print("Preview:")
    print(out_df.head())
    # Save the different depth tables
    save_depth_tables(out_df, os.path.join(output_folder, basename))


if __name__ == "__main__":
    main()
