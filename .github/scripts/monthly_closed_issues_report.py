import os
import requests
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

PROJECT_ID = os.environ.get("PROJECT_ID")
GRAPHQL_API_URL = "https://api.github.com/graphql"
OUTPUT_DIR = "monthly_report"
TOKEN = os.environ.get("MILESTONE_SYNC")

if not TOKEN:
    print("Error: MILESTONE_SYNC environment variable not set.", file=sys.stderr)
    sys.exit(1)
if not PROJECT_ID or PROJECT_ID.strip() == "":
    print("Error: PROJECT_ID environment variable not set.", file=sys.stderr)
    sys.exit(1)

try:
    snapshot_date = datetime.now(ZoneInfo("America/Chicago")).strftime('%Y%m%d')
except Exception as e:
    print(f"Warning: Could not determine Chicago time ({e}), falling back to UTC.", file=sys.stderr)
    snapshot_date = datetime.utcnow().strftime('%Y%m%d')

SNAPSHOT_FILENAME = f"{snapshot_date}_monthlyreport.JSON"
OUTPUT_PATH = os.path.join(OUTPUT_DIR, SNAPSHOT_FILENAME)
LATEST_SNAPSHOT_FILENAME = "latest_snapshot.JSON"
LATEST_OUTPUT_PATH = os.path.join(OUTPUT_DIR, LATEST_SNAPSHOT_FILENAME)

graphql_query = """
query GetProjectV2Items($projectId: ID!, $cursor: String) {
  node(id: $projectId) {
    ... on ProjectV2 {
      fields(first: 50) {
        nodes {
          ... on ProjectV2Field {
            id
            name
          }
        }
      }
      items(first: 100, after: $cursor, orderBy: {field: POSITION, direction: ASC}) {
        nodes {
          id
          content {
            ... on Issue {
              id
              number
              title
              state
              url
              createdAt
              closedAt
              body
              labels(first: 20) { nodes { name } }
              issueType { id name }
            }
          }
          fieldValues(first: 20) {
            nodes {
              ... on ProjectV2ItemFieldIssueValue {
                field {
                  ... on ProjectV2Field {
                    id
                    name
                  }
                }
                issue {
                  id
                  number
                  title
                  url
                }
              }
            }
          }
        }
        pageInfo {
          endCursor
          hasNextPage
        }
      }
    }
  }
}
"""

all_items = []
all_issues = []
fields = []
has_next_page = True
cursor = None
print(f"Fetching items for Project ID: {PROJECT_ID}...")

while has_next_page:
    variables = {"projectId": PROJECT_ID, "cursor": cursor}
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
            sys.exit(1)
        project_node = data.get("data", {}).get("node", {})
        if not fields:
            fields = project_node.get("fields", {}).get("nodes", [])
        items = (
            project_node
            .get('items', {})
            .get('nodes', [])
        )
        all_items.extend(items)
        for item in items:
            issue = item.get("content")
            if not issue or issue.get("__typename", "Issue") != "Issue":
                continue
            # Attach the field values to the issue for later processing
            issue["_project_item_id"] = item["id"]
            issue["_fieldValues"] = item.get("fieldValues", {}).get("nodes", [])
            all_issues.append(issue)
        page_info = (
            project_node
            .get('items', {})
            .get('pageInfo', {})
        )
        has_next_page = page_info.get('hasNextPage', False)
        cursor = page_info.get('endCursor')
        if has_next_page:
            time.sleep(0.2)
    except Exception as e:
        print(f"Error fetching data: {e}", file=sys.stderr)
        sys.exit(1)

print(f"Fetched {len(all_issues)} issues from project.")

# Find the ID of the "Parent issue" field
parent_field_id = None
for f in fields:
    if f.get("name", "").lower() == "parent issue":
        parent_field_id = f["id"]
        break

def extract_parent(field_values, parent_field_id):
    if not parent_field_id:
        return None, None, None, None
    for fv in field_values:
        field = fv.get("field", {})
        if field.get("id") == parent_field_id:
            parent_issue = fv.get("issue")
            if parent_issue:
                return (
                    parent_issue.get("id"),
                    parent_issue.get("number"),
                    parent_issue.get("title"),
                    parent_issue.get("url")
                )
    return None, None, None, None

now = datetime.now(timezone.utc)
window_start = now - timedelta(days=30)
filtered_issues = []
for issue in all_issues:
    if issue.get('state') != 'CLOSED':
        continue
    closed_at = issue.get('closedAt')
    if not closed_at:
        continue
    try:
        closed_at_dt = datetime.fromisoformat(closed_at.replace('Z', '+00:00'))
    except Exception:
        continue
    if closed_at_dt < window_start:
        continue
    labels = [lbl['name'].strip().lower() for lbl in (issue.get('labels', {}).get('nodes') or []) if 'name' in lbl]
    if any(lbl in ['duplicate', 'not planned'] for lbl in labels):
        continue

    # Extract parent issue info via fieldValues
    parent_id, parent_number, parent_title, parent_url = extract_parent(issue.get("_fieldValues", []), parent_field_id)
    output_issue = dict(issue)
    output_issue["issue_type"] = issue.get("issueType", {}).get("name")
    output_issue["parent_id"] = parent_id
    output_issue["parent_number"] = parent_number
    output_issue["parent_title"] = parent_title
    output_issue["parent_url"] = parent_url
    filtered_issues.append(output_issue)

print(f"Returning {len(filtered_issues)} issues closed in last 30 days (excluding 'duplicate' and 'not planned').")
if len(filtered_issues) < len(all_issues):
    print("Note: Exclusion is based on the labels 'duplicate' or 'not planned'. The true close 'reason' is not available from the ProjectV2 API. "
          "In the future, update logic here to use close_reason if you label issues or fetch close reason via REST API.")

def write_json(file_path, data_to_write):
    print(f"Writing {len(data_to_write)} issues to {file_path}...")
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data_to_write, f, indent=2, ensure_ascii=False)
        print(f"JSON file '{file_path}' written successfully.")
    except Exception as e:
        print(f"Error writing JSON file '{file_path}': {e}", file=sys.stderr)
        sys.exit(1)

write_json(OUTPUT_PATH, filtered_issues)
write_json(LATEST_OUTPUT_PATH, filtered_issues)
print("All JSON files written successfully.")
