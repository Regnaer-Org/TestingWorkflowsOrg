import pandas as pd
import glob
import re
import os

# --- CONFIGURATION ---
SNAPSHOT_FOLDER = "agilereporting"
SNAPSHOT_PATTERN = os.path.join(SNAPSHOT_FOLDER, "project.issues_*.csv")
OUTPUT_CSV = "burndown_facts.csv"

# --- Step 1: Find all snapshot files ---
all_files = glob.glob(SNAPSHOT_PATTERN)
# Filter out the 'latest_snapshot.csv' duplicate if present
all_files = [f for f in all_files if "latest_snapshot" not in f]

# --- Step 2: Extract snapshot date and combine ---
combined = []

for filepath in sorted(all_files):  # Sorted by date in filename
    # Extract date from filename (expects project.issues_YYYY.MM.DD.csv)
    m = re.search(r'project\.issues_(\d{4}\.\d{2}\.\d{2})\.csv', os.path.basename(filepath))
    if not m:
        print(f"Skipping file with unexpected name: {filepath}")
        continue
    snapshot_date = m.group(1).replace('.', '-')  # e.g., '2025-05-13'
    
    # Read CSV
    df = pd.read_csv(filepath)
    df['snapshot_date'] = snapshot_date

    # Standardize column names (strip whitespace)
    df.columns = [col.strip() for col in df.columns]
    
    combined.append(df)

# --- Step 3: Concatenate to single DataFrame ---
if not combined:
    raise RuntimeError("No snapshot files found or matched pattern.")
full_df = pd.concat(combined, ignore_index=True)

# --- Step 4: Save consolidated fact table ---
full_df.to_csv(OUTPUT_CSV, index=False)

print(f"Burndown fact table saved to: {OUTPUT_CSV}")
