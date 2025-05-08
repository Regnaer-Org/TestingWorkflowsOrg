import os
import requests
import json
import csv
from datetime import datetime
from zoneinfo import ZoneInfo
import sys
import time

# --- Configuration ---
PROJECT_ID = os.environ.get("PROJECT_ID")  # Must be set in environment/secrets
GRAPHQL_API_URL = "https://api.github.com/graphql"
OUTPUT_DIR = "agilereporting"
TOKEN = os.environ.get("MILESTONE_SYNC_TOKEN")

if not TOKEN:
    print("Error: MILESTONE_SYNC_TOKEN environment variable not set.", file=sys.stderr)
    sys.exit(1)
if not PROJECT_ID or PROJECT_ID.strip() == "":
    print("Error: PROJECT_ID environment variable not set.", file=sys.stderr)
    sys.exit(1)

# --- Generate Filename (Central Time, YYYY.MM.DD) ---
snapshot_date = datetime.now(ZoneInfo("America/Chicago")).strftime('%Y.%m.%d')

SNAPSHOT_FILENAME = f"project.issues_{snapshot_date}.csv"
OUTPUT_PATH = os.path.join(OUTPUT_DIR, SNAPSHOT_FILENAME)
LATEST_SNAPSHOT_FILENAME = "latest_snapshot.csv"
LATEST_OUTPUT_PATH = os.path.join(OUTPUT_DIR, LATEST_SNAPSHOT_FILENAME)

# --- GraphQL Query (Includes labels, assignees nodes, and issueType) ---
graphql_query = f"""
query GetProjectV2Items($cursor: String) {{
  node(id: "{PROJECT_ID}") {{
    ... on ProjectV2 {{
      id
      title
      number
      items(first: 100, after: $cursor, orderBy: {{field: POSITION, direction: ASC}}) {{
        totalCount
        nodes {{
          id
          createdAt
          updatedAt
          isArchived
          type
          fieldValues(first: 100) {{
            nodes {{
              ... on ProjectV2ItemFieldTextValue {{
                text
                field {{ ...ProjectV2FieldCommon }}
              }}
              ... on ProjectV2ItemFieldDateValue {{
                date
                field {{ ...ProjectV2FieldCommon }}
              }}
              ... on ProjectV2ItemFieldNumberValue {{
                number
                field {{ ...ProjectV2FieldCommon }}
              }}
              ... on ProjectV2ItemFieldSingleSelectValue {{
                name
                field {{ ...ProjectV2FieldCommon }}
              }}
              ... on ProjectV2ItemFieldIterationValue {{
                title
                startDate
                duration
                field {{ ...ProjectV2FieldCommon }}
              }}
            }}
          }}
          content {{
            ... on DraftIssue {{
              id
              title
              body
              creator {{ login }}
            }}
            ... on PullRequest {{
              id
              number
              title
              state
              url
              createdAt
              updatedAt
              closedAt
              mergedAt
              author {{ login }}
              repository {{ nameWithOwner owner {{ login }} name }}
              assignees(first: 10) {{ nodes {{ login }} }}
              labels(first: 20) {{ nodes {{ name }} }}
              milestone {{ title number state }}
            }}
            ... on Issue {{
              id
              number
              title
              state
              url
              createdAt
              updatedAt
              closedAt
              author {{ login }}
              repository {{ nameWithOwner owner {{ login }} name }}
              assignees(first: 10) {{ nodes {{ login }} }}
              labels(first: 20) {{ nodes {{ name }} }}
              milestone {{ title number state }}
              issueType {{
                id
                name
              }}
            }}
          }}
        }}
        pageInfo {{
          endCursor
          hasNextPage
        }}
      }}
    }}
  }}
}}

fragment ProjectV2FieldCommon on ProjectV2FieldCommon {{
    ... on ProjectV2Field {{ name id }}
    ... on ProjectV2IterationField {{ name id }}
    ... on ProjectV2SingleSelectField {{ name id }}
}}
"""

def get_value(data, keys, default=""):
    current = data
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        else:
            return default
        if current is None:
            return default
    return str(current) if current is not None else default

# --- Fetch All Items via Pagination ---
all_items = []
has_next_page = True
cursor = None
item_count = 0
print(f"Fetching items for Project ID: {PROJECT_ID}...")

while has_next_page:
    variables = {"cursor": cursor}
    payload = {"query": graphql_query, "variables": variables}
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    try:
        response = requests.post(GRAPHQL_API_URL, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()
        if 'errors' in data:
            print("Error: GraphQL API returned errors:", file=sys.stderr)
            print(json.dumps(data['errors'], indent=2), file=sys.stderr)
            project_data = data.get('data', {}).get('node', {})
            if not project_data:
                print("Error: No project data node found in response with errors.", file=sys.stderr)
                sys.exit(1)
        else:
            project_data = data.get('data', {}).get('node', {})
        if not project_data:
            print("Error: Could not find project node in response.", file=sys.stderr)
            print(json.dumps(data, indent=2), file=sys.stderr)
            sys.exit(1)
        items_data = project_data.get('items', {})
        nodes = items_data.get('nodes', [])
        page_info = items_data.get('pageInfo', {})
        if nodes:
            all_items.extend(nodes)
            item_count += len(nodes)
            total_project_items = items_data.get('totalCount', item_count)
            print(f"Fetched {len(nodes)} items (Total processed: {item_count} / {total_project_items or 'unknown'})...")
        has_next_page = page_info.get('hasNextPage', False)
        cursor = page_info.get('endCursor')
        if has_next_page:
            time.sleep(0.2)
    except requests.exceptions.Timeout:
        print(f"Error: Request timed out connecting to {GRAPHQL_API_URL}", file=sys.stderr)
        sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data from GraphQL API: {e}", file=sys.stderr)
        if 'response' in locals() and response is not None:
            print(f"Response status code: {response.status_code}", file=sys.stderr)
            print(f"Response body: {response.text}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON response: {e}", file=sys.stderr)
        if 'response' in locals() and response is not None:
            print(f"Response status code: {response.status_code}", file=sys.stderr)
            print(f"Response body (first 500 chars): {response.text[:500]}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred during fetching: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)

print(f"Finished fetching. Total items retrieved: {len(all_items)}")
