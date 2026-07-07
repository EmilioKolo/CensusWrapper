# CensusWrapper
Python scripts to explore, download, and process US Census Bureau data (ACS 5‑year and 1‑year estimates) by state.

## Scripts

| Script | Purpose |
|--------|---------|
| `census_explorer.py` | Search variables by keyword or browse a specific table. Supports grouping by concept, base‑table filtering, and sorting. |
| `census_table_dump.py` | Dump all estimate variables for a table prefix (e.g., `B01001_`). Also lists distinct categories with example IDs. |
| `census_simple_download.py` | Download raw data for a column definition (JSON with `"label"` and `"variables"`). Saves a CSV with cleaned labels and optional depth‑split files. |

## Usage workflow

1. **Explore available tables / variables**
```bash
python census_explorer.py --year 2024 --dataset acs/acs5
```
Use `--group-by-concept` for a high‑level view, `--base-tables-only` to skip racial subgroups, `--keyword "sex by age"` to perform a query without the .

2. **Create column definitions** (for raw download)
Use `census_table_dump.py` to generate a JSON file with all variables of a table:

```bash
python census_table_dump.py --table B01001_ --output-folder ./json_tables
```

3. **Download raw data** (simple, one‑variable‑per‑column)

```bash
python census_simple_download.py --input ./json_tables/B01001_sex_by_age.json --output B01001_sex_by_age.csv
```
The script will save the raw CSV and, by default, also create `age_raw_depth_1.csv`, `age_raw_depth_2.csv`, etc... splitting columns by label depth.

## Setup

1. **Python 3** and the `pandas` package (install with pip):

```bash
pip install pandas
```

2. **Census API key**
- Sign up for a free key at [https://api.census.gov/data/key_signup.html](https://api.census.gov/data/key_signup.html).
- Set it as an environment variable:
```bash
export CENSUS_API_KEY="your_key_here"
```
- If not set, the scripts will prompt you securely (input hidden).

3. **Data availability**
- The default dataset is `acs/acs5` (5‑year estimates). Use `--dataset acs/acs1` for 1‑year estimates.
- Not all tables are populated in every release. Use `census_table_dump.py` to browse variables; test a small API call to confirm data exists.

## Example: Age distribution by state
```bash
    # 1. Dump the "Sex by Age" table to a JSON column definition
    python census_table_dump.py --table B01001 --output-folder ./json_tables

    # 2. Download raw data (all variables)
    python census_simple_download.py --input ./json_tables/B01001_sex_by_age.json --output age_raw.csv

    # This produces age_raw.csv (full table) and age_raw_depth_*.csv (split by label depth)
```

## Notes

- Column labels are cleaned: `Estimate!!Total:!!Male:!!Under 5 years` becomes `Total//Male//Under 5 years`.
- The depth split uses `//` as separator; leaf columns that end before a certain depth are carried forward to deeper tables.
- For large tables (>50 variables), the download script automatically batches API requests.