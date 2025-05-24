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

# Query all fields for this project so we can find the "Status" field and its options
graphql_query = """
query GetProjectV2Items($projectId: ID!, $cursor: String) {
  node(id: $projectId) {
    ... on ProjectV2 {
      fields(first: 50) {
        nodes {
          ... on ProjectV2SingleSelectField {
            id
            name
            options {
              id
              name
            }
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
              trackedByIssues(first: 1) {
                nodes {
                  id
                  number
                  title
                  url
                }
              }
              trackedIssues(first: 20) {
                nodes {
                  id
                  number
                  title
                  url
                }
              }
            }
          }
          fieldValues(first: 20) {
            nodes {
              ... on ProjectV2ItemFieldSingleSelectValue {
                field {
                  ... on ProjectV2SingleSelectField {
                    id
                    name
                  }
                }
                name
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
            # Only need to get fields once
            fields = project_node.get("fields", {}).get("nodes", [])
        items = (
            project_node
            .get('items', {})
            .get('nodes', [])
        )
        all_items.extend(items)
        # Extract issue content for our main list
        for item in items:
            issue = item.get("content")
            if not issue or issue.get("__typename", "Issue") != "Issue":
                continue
            # Save the project item id for lookup
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
            time.sleep(0.25)
    except Exception as e:
        print(f"Error fetching data: {e}", file=sys.stderr)
        sys.exit(1)

print(f"Fetched {len(all_issues)} issues from project.")

# Find the ID of the Status field
status_field_id = None
for f in fields:
    if f.get("name", "").lower() == "status":
        status_field_id = f["id"]
        break
if not status_field_id:
    print("Could not find 'Status' single-select field for this project.", file=sys.stderr)
    sys.exit(1)

def extract_status(field_values, status_field_id):
    for fv in field_values:
        field = fv.get("field", {})
        if field.get("id") == status_field_id:
            return fv.get("name")
    return None

# Map from Issue ID to {status, etc.} for lookup by parent/sub-issue
issue_id_to_iteminfo = {}
for item in all_items:
    issue = item.get("content")
    if not issue or issue.get("__typename", "Issue") != "Issue":
        continue
    field_values = item.get("fieldValues", {}).get("nodes", [])
    status_val = extract_status(field_values, status_field_id)
    issue_id_to_iteminfo[issue["id"]] = {
        "status": status_val
    }

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

    # Main issue status
    project_item_status = issue_id_to_iteminfo.get(issue["id"], {}).get("status")

    # Parent info (first trackedByIssues node, if any)
    parent = None
    parent_nodes = issue.get('trackedByIssues', {}).get('nodes', [])
    if parent_nodes:
        parent = parent_nodes[0]
        parent_id = parent.get('id')
        parent_number = parent.get('number')
        parent_title = parent.get('title')
        parent_url = parent.get('url')
        parent_status = issue_id_to_iteminfo.get(parent_id, {}).get("status")
    else:
        parent_id = parent_number = parent_title = parent_url = parent_status = None

    # Sub-issues (all trackedIssues nodes)
    sub_issues = []
    for sub in issue.get('trackedIssues', {}).get('nodes', []):
        sub_id = sub.get('id')
        sub_issues.append({
            'id': sub_id,
            'number': sub.get('number'),
            'title': sub.get('title'),
            'url': sub.get('url'),
            'status': issue_id_to_iteminfo.get(sub_id, {}).get("status"),
        })

    # Compose final output for the issue
    output_issue = dict(issue)  # shallow copy
    output_issue["status"] = project_item_status
    output_issue["parent_id"] = parent_id
    output_issue["parent_number"] = parent_number
    output_issue["parent_title"] = parent_title
    output_issue["parent_url"] = parent_url
    output_issue["parent_status"] = parent_status
    output_issue["sub_issues"] = sub_issues
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
