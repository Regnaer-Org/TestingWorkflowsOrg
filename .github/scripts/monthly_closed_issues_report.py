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
              parent {
                ... on Issue { id title }
              }
            }
          }
          fieldValues(first: 30) {
            nodes {
              __typename
              ... on ProjectV2ItemFieldSingleSelectValue {
                name
                field {
                  ... on ProjectV2SingleSelectFieldConfiguration { name }
                }
              }
              ... on ProjectV2ItemFieldIterationValue {
                title
                field {
                  ... on ProjectV2IterationFieldConfiguration { name }
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

def extract_project_fields(field_values):
    result = {"team": None, "sprint": None, "priority": None}
    for fv in field_values or []:
        field_type = fv.get("__typename")
        field = fv.get("field") or {}
        # Team (single select)
        if field_type == "ProjectV2ItemFieldSingleSelectValue" and field.get("name", "").lower() == "team":
            result["team"] = fv.get("name")
        # Priority (single select)
        if field_type == "ProjectV2ItemFieldSingleSelectValue" and field.get("name", "").lower() == "priority":
            result["priority"] = fv.get("name")
        # Sprint (iteration)
        if field_type == "ProjectV2ItemFieldIterationValue" and field.get("name", "").lower() == "sprint":
            result["sprint"] = fv.get("title")
    return result

all_issues = []
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
        items = (
            data.get('data', {})
            .get('node', {})
            .get('items', {})
            .get('nodes', [])
        )
        for item in items:
            issue = item.get("content")
            if not issue or issue.get("__typename", "Issue") != "Issue":
                continue
            field_values = item.get("fieldValues", {}).get("nodes", [])
            issue["_fieldValues"] = field_values
            all_issues.append(issue)
        page_info = (
            data.get('data', {})
            .get('node', {})
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

    output_issue = dict(issue)
    # Add the issue type (if present)
    output_issue["issue_type"] = issue.get("issueType", {}).get("name")
    # Add parent id and title (if present)
    parent = issue.get("parent")
    output_issue["parent_id"] = parent.get("id") if parent else None
    output_issue["parent_title"] = parent.get("title") if parent else None
    # Add project custom fields
    proj_fields = extract_project_fields(issue.get("_fieldValues", []))
    output_issue["team"] = proj_fields.get("team")
    output_issue["sprint"] = proj_fields.get("sprint")
    output_issue["priority"] = proj_fields.get("priority")
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
