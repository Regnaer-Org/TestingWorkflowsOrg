import os
import requests
import json
import csv
from datetime import datetime, timedelta
import sys

# --- Configuration ---
PROJECT_ID = os.environ.get("PROJECT_ID")  # Must be set in environment/secrets
GRAPHQL_API_URL = "https://api.github.com/graphql"
OUTPUT_DIR = "agilereportingmetadata"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "SprintMetaData.csv")
TOKEN = os.environ.get("MILESTONE_SYNC_TOKEN")  # Get token from environment variable

# --- Check for Token and Project ID ---
if not TOKEN:
    print("Error: MILESTONE_SYNC_TOKEN environment variable not set.", file=sys.stderr)
    sys.exit(1)
if not PROJECT_ID or PROJECT_ID.strip() == "":
    print("Error: PROJECT_ID variable is not set or is empty.", file=sys.stderr)
    sys.exit(1)

# --- GraphQL Query ---
# Using an f-string to easily embed the project ID
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

# --- Prepare API Request ---
headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
    "Accept": "application/json",
}
payload = {'query': query}

# --- Fetch Data from GitHub GraphQL API ---
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

# Check for GraphQL errors in the response body
if 'errors' in data:
    print("Error: GraphQL API returned errors:", file=sys.stderr)
    print(json.dumps(data['errors'], indent=2), file=sys.stderr)
    sys.exit(1)

# --- Process Data and Write CSV ---
print(f"Processing data and writing to {OUTPUT_FILE}...")
os.makedirs(OUTPUT_DIR, exist_ok=True)

processed_count = 0
try:
    with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as outfile:
        writer = csv.writer(outfile)
        writer.writerow(['id', 'title', 'startDate', 'endDate', 'duration'])

        # Safely navigate the potentially complex JSON structure
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

        if not sprint_field:
            print("Warning: Could not find 'Sprint' field in the GraphQL response.", file=sys.stderr)
        elif not iterations:
            print("Warning: Found 'Sprint' field, but it contains no iterations.", file=sys.stderr)
        else:
            print(f"Found {len(iterations)} iterations.")
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

                writer.writerow([id_, title, start, end, duration_str if duration_str is not None else ""])
                processed_count += 1

except IOError as e:
    print(f"Error writing CSV file '{OUTPUT_FILE}': {e}", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f"An unexpected error occurred during CSV processing: {e}", file=sys.stderr)
    import traceback
    traceback.print_exc(file=sys.stderr)
    sys.exit(1)

print(f"Processed {processed_count} iterations.")
print(f"Python script finished successfully. Output written to {OUTPUT_FILE}")
