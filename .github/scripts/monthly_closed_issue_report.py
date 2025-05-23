import sys
import pandas as pd
import json
from datetime import datetime, timedelta
import os

CSV_DIR = "agilereporting"
SNAPSHOT_FILE = "latest_snapshot.csv"
CSV_PATH = os.path.join(CSV_DIR, SNAPSHOT_FILE)
OUTPUT_PATH = os.path.join(CSV_DIR, "filtered_issues.json")

# --- Get team input (from CLI arg or env) ---
TEAM_INPUT = None
if len(sys.argv) > 1:
    TEAM_INPUT = sys.argv[1]
elif "TEAM_INPUT" in os.environ:
    TEAM_INPUT = os.environ["TEAM_INPUT"]
else:
    TEAM_INPUT = "ALL"

VALID_ISSUETYPES = {"Bug", "Story"}

try:
    df = pd.read_csv(CSV_PATH, dtype=str)
except Exception as e:
    print(f"Error loading {CSV_PATH}: {e}")
    sys.exit(1)

today = datetime.utcnow()
date_30_days_ago = today - timedelta(days=30)

def parse_date(date_str):
    if pd.isna(date_str) or not isinstance(date_str, str) or date_str.strip() == "":
        return None
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except Exception:
        return None

df['closed_dt'] = df['content_closed_at'].map(parse_date)
df = df[df['closed_dt'].notnull()]
df = df[df['closed_dt'] >= date_30_days_ago]

if 'issue_type_name' not in df.columns:
    print("Error: issue_type_name column missing from data.")
    sys.exit(1)
df = df[df['issue_type_name'].isin(VALID_ISSUETYPES)]

team_cols = [col for col in df.columns if col.lower() == "team"]
if not team_cols:
    print("Error: No column named 'Team' found in the CSV. Check your field names.")
    sys.exit(1)
team_col = team_cols[0]

if TEAM_INPUT != "ALL":
    df = df[df[team_col] == TEAM_INPUT]

output_cols = [
    "content_id", "content_number", "content_title", "content_state", "content_url",
    "content_created_at", "content_closed_at", "issue_type_name", team_col
]
output_cols = [col for col in output_cols if col in df.columns]

results = df[output_cols].to_dict(orient="records")

with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

print(f"Wrote {len(results)} issues to {OUTPUT_PATH}")
