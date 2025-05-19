import os
import requests
import json
import csv
from datetime import datetime, timedelta
import sys

# --- Configuration ---
PROJECT_ID = os.environ.get("PROJECT_ID")
GRAPHQL_API_URL = "https://api.github.com/graphql"
OUTPUT_DIR = "agilereportingmetadata"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "SprintMetaData.csv")
TOKEN = os.environ.get("MILESTONE_SYNC_TOKEN")

if not TOKEN:
    print("Error: MILESTONE_SYNC_TOKEN environment variable not set.", file=sys.stderr)
    sys.exit(1)
if not PROJECT_ID or PROJECT_ID.strip() == "":
    print("Error: PROJECT_ID variable is not set or is empty.", file=sys.stderr)
    sys.exit(1)

query = f"""
query GetIterations {{
  node(id: "{PROJECT_ID}") {{
    ... on ProjectV2 {{
      fields(first: 50) {{
        nodes {{
          ... on ProjectV2IterationField {{
            name
            configuration {{
              iterations {{
                id
                title
                startDate
                duration
              }}
            }}
          }}
        }}
      }}
    }}
  }}
}}
"""

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
    "Accept": "application/json",
}
payload = {'query': query}

print("Fetching data from GitHub GraphQL API...")
try:
    response = requests.post(GRAPHQL_API_URL, headers=headers, json=payload, timeout=30)
    response.raise_for_status()
    data = response.json()
    print("Data fetched successfully.")
except requests.exceptions.Timeout:
    print(f"Error: Request timed out connecting to {GRAPHQL_API_URL}", file=sys.stderr)
    sys.exit(1)
except requests.exceptions.RequestException as e:
    print(f"Error fetching data from GraphQL API: {e}", file=sys.stderr)
    print(f"Response status code: {response.status_code if 'response' in locals() else 'N/A'}", file=sys.stderr)
    print(f"Response body: {response.text if 'response' in locals() else 'N/A'}", file=sys.stderr)
    sys.exit(1)
except json.JSONDecodeError as e:
    print(f"Error decoding JSON response: {e}", file=sys.stderr)
    print(f"Response status code: {response.status_code}", file=sys.stderr)
    print(f"Response body (first 500 chars): {response.text[:500]}", file=sys.stderr)
    sys.exit(1)

if 'errors' in data:
    print("Error: GraphQL API returned errors:", file=sys.stderr)
    print(json.dumps(data['errors'], indent=2), file=sys.stderr)
    sys.exit(1)

# --- Read existing CSV into a dict keyed by id ---
existing_sprints = {}
if os.path.exists(OUTPUT_FILE):
    with open(OUTPUT_FILE, newline='', encoding='utf-8') as infile:
        reader = csv.DictReader(infile)
        for row in reader:
            existing_sprints[row['id']] = row

# --- Process new data ---
print(f"Processing data and merging into {OUTPUT_FILE}...")
os.makedirs(OUTPUT_DIR, exist_ok=True)

processed_count = 0
try:
    # Find the 'Sprint' field and get its iterations
    sprint_field = None
    iterations = []
    try:
        nodes = data.get("data", {}).get("node", {}).get("fields", {}).get("nodes", [])
        for field in nodes:
            if field and field.get("name") == "Sprint":
                sprint_field = field
                iterations = field.get("configuration", {}).get("iterations", [])
                break
    except AttributeError as e:
        print(f"Warning: Issue navigating GraphQL response structure: {e}", file=sys.stderr)

    # Update or add sprints from API
    for iteration in iterations:
        id_ = iteration.get("id", "")
        title = iteration.get("title", "")
        start = iteration.get("startDate", "")
        duration_str = iteration.get("duration")
        end = ""

        try:
            if duration_str is not None:
                duration_days = int(duration_str)
            else:
                duration_days = 0

            if start and duration_days > 0:
                start_date_obj = datetime.strptime(start, '%Y-%m-%d')
                end_date_obj = start_date_obj + timedelta(days=duration_days - 1)
                end = end_date_obj.strftime('%Y-%m-%d')
        except (ValueError, TypeError) as e:
            print(f"Warning: Could not parse date/duration or calculate end date for iteration '{title}' (ID: {id_}). Start: '{start}', Duration: '{duration_str}'. Error: {e}", file=sys.stderr)
            # Keep end as ""

        # Update dict: if id exists, update; if not, add
        existing_sprints[id_] = {
            'id': id_,
            'title': title,
            'startDate': start,
            'endDate': end,
            'duration': duration_str if duration_str is not None else ""
        }
        processed_count += 1

    # Write merged sprints back to CSV (preserving manual entries for completed sprints)
    with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as outfile:
        writer = csv.DictWriter(outfile, fieldnames=['id', 'title', 'startDate', 'endDate', 'duration'])
        writer.writeheader()
        for sprint in existing_sprints.values():
            writer.writerow(sprint)

except IOError as e:
    print(f"Error writing CSV file '{OUTPUT_FILE}': {e}", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f"An unexpected error occurred during CSV processing: {e}", file=sys.stderr)
    import traceback
    traceback.print_exc(file=sys.stderr)
    sys.exit(1)

print(f"Merged/processed {processed_count} iterations from API.")
print(f"Python script finished successfully. Output written to {OUTPUT_FILE}")
