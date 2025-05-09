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
try:
    snapshot_date = datetime.now(ZoneInfo("America/Chicago")).strftime('%Y.%m.%d')
except Exception as e:
    print(f"Warning: Could not determine Chicago time ({e}), falling back to UTC.", file=sys.stderr)
    snapshot_date = datetime.utcnow().strftime('%Y.%m.%d')

SNAPSHOT_FILENAME = f"project.issues_{snapshot_date}.csv"
OUTPUT_PATH = os.path.join(OUTPUT_DIR, SNAPSHOT_FILENAME)
LATEST_SNAPSHOT_FILENAME = "latest_snapshot.csv"
LATEST_OUTPUT_PATH = os.path.join(OUTPUT_DIR, LATEST_SNAPSHOT_FILENAME)

# --- GraphQL Query (updated to include parent issue fields) ---
graphql_query = """
query GetProjectV2Items($projectId: ID!, $cursor: String) {
  node(id: $projectId) {
    ... on ProjectV2 {
      id
      title
      number
      items(first: 100, after: $cursor, orderBy: {field: POSITION, direction: ASC}) {
        totalCount
        nodes {
          id
          createdAt
          updatedAt
          isArchived
          type
          fieldValues(first: 100) {
            nodes {
              ... on ProjectV2ItemFieldTextValue {
                text
                field { ...ProjectV2FieldCommon }
              }
              ... on ProjectV2ItemFieldDateValue {
                date
                field { ...ProjectV2FieldCommon }
              }
              ... on ProjectV2ItemFieldNumberValue {
                number
                field { ...ProjectV2FieldCommon }
              }
              ... on ProjectV2ItemFieldSingleSelectValue {
                name
                field { ...ProjectV2FieldCommon }
              }
              ... on ProjectV2ItemFieldIterationValue {
                title
                startDate
                duration
                field { ...ProjectV2FieldCommon }
              }
            }
          }
          content {
            ... on DraftIssue {
              id
              title
              body
              creator { login }
            }
            ... on PullRequest {
              id
              number
              title
              state
              url
              createdAt
              updatedAt
              closedAt
              mergedAt
              author { login }
              repository { nameWithOwner owner { login } name }
              assignees(first: 10) { nodes { login } }
              labels(first: 20) { nodes { name } }
              milestone { title number state }
            }
            ... on Issue {
              id
              number
              title
              state
              url
              createdAt
              updatedAt
              closedAt
              author { login }
              repository { nameWithOwner owner { login } name }
              assignees(first: 10) { nodes { login } }
              labels(first: 20) { nodes { name } }
              milestone { title number state }
              issueType {
                id
                name
              }
              parent {
                ... on Issue { id number title url issueType { id name } }
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

fragment ProjectV2FieldCommon on ProjectV2FieldCommon {
    ... on ProjectV2Field { name id }
    ... on ProjectV2IterationField { name id }
    ... on ProjectV2SingleSelectField { name id }
}
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

# --- Process Data and Prepare for CSV ---
processed_data = []
all_field_names = set()

core_headers = [
    'project_item_id', 'project_item_type', 'project_item_created_at', 'project_item_updated_at', 'project_item_is_archived',
    'content_id', 'content_type', 'content_number', 'content_title', 'content_state', 'content_url',
    'content_created_at', 'content_updated_at', 'content_closed_at', 'content_merged_at',
    'author', 'repository', 'repository_owner', 'repository_name',
    'assignees', 'labels',
    'milestone_title', 'milestone_number', 'milestone_state',
    'issue_type_id', 'issue_type_name',
    'parent_id', 'parent_number', 'parent_title', 'parent_url', 'parent_issue_type_id', 'parent_issue_type_name'
]
for header in core_headers:
    all_field_names.add(header)

print("Processing items for CSV conversion...")
for item in all_items:
    row = {}

    row['project_item_id'] = item.get('id', '')
    row['project_item_type'] = item.get('type', '')
    row['project_item_created_at'] = item.get('createdAt', '')
    row['project_item_updated_at'] = item.get('updatedAt', '')
    row['project_item_is_archived'] = str(item.get('isArchived', ''))

    content = item.get('content')
    row['issue_type_id'] = ''
    row['issue_type_name'] = ''
    # Default parent fields to blank
    row['parent_id'] = ''
    row['parent_number'] = ''
    row['parent_title'] = ''
    row['parent_url'] = ''
    row['parent_issue_type_id'] = ''
    row['parent_issue_type_name'] = ''

    if content:
        if 'repository' in content:
            if 'mergedAt' in content or content.get('state') == 'MERGED':
                row['content_type'] = 'PullRequest'
            else:
                row['content_type'] = 'Issue'
        elif 'body' in content and ('creator' in content or 'author' in content):
            row['content_type'] = 'DraftIssue'
        else:
            row['content_type'] = 'Unknown'

        row['content_id'] = content.get('id', '')
        row['content_number'] = str(content.get('number', ''))
        row['content_title'] = content.get('title', '')
        row['content_state'] = content.get('state', '')
        row['content_url'] = content.get('url', '')
        row['content_created_at'] = content.get('createdAt', '')
        row['content_updated_at'] = content.get('updatedAt', '')
        row['content_closed_at'] = content.get('closedAt', '')
        row['content_merged_at'] = content.get('mergedAt', '')
        row['author'] = get_value(content, ['author', 'login'], get_value(content, ['creator', 'login']))
        row['repository'] = get_value(content, ['repository', 'nameWithOwner'])
        row['repository_owner'] = get_value(content, ['repository', 'owner', 'login'])
        row['repository_name'] = get_value(content, ['repository', 'name'])

        assignees_nodes = content.get('assignees', {}).get('nodes', [])
        if isinstance(assignees_nodes, list):
            assignees_logins = [a.get('login', '') for a in assignees_nodes if a and isinstance(a, dict)]
            row['assignees'] = ";".join(filter(None, assignees_logins))
        else:
            row['assignees'] = ""

        labels_nodes = content.get('labels', {}).get('nodes', [])
        if isinstance(labels_nodes, list):
            label_names = [lbl.get('name', '') for lbl in labels_nodes if lbl and isinstance(lbl, dict)]
            row['labels'] = ";".join(filter(None, label_names))
        else:
            row['labels'] = ""

        row['milestone_title'] = get_value(content, ['milestone', 'title'])
        row['milestone_number'] = str(get_value(content, ['milestone', 'number']))
        row['milestone_state'] = get_value(content, ['milestone', 'state'])

        # Extract issueType if present
        if row['content_type'] == 'Issue':
            issue_type = content.get('issueType')
            if issue_type:
                row['issue_type_id'] = issue_type.get('id', '')
                row['issue_type_name'] = issue_type.get('name', '')
            # --- Extract parent issue fields if present ---
            parent = content.get('parent', {}) if 'parent' in content else {}
            row['parent_id'] = parent.get('id', '')
            row['parent_number'] = parent.get('number', '')
            row['parent_title'] = parent.get('title', '')
            row['parent_url'] = parent.get('url', '')
            parent_issue_type = parent.get('issueType', {}) if parent else {}
            row['parent_issue_type_id'] = parent_issue_type.get('id', '')
            row['parent_issue_type_name'] = parent_issue_type.get('name', '')

    else:
        row['content_type'] = 'No Content'
        for key in core_headers:
            if key.startswith('content_') or key in ['author','repository','repository_owner','repository_name','assignees','labels','milestone_title','milestone_number','milestone_state','issue_type_id','issue_type_name','parent_id','parent_number','parent_title','parent_url','parent_issue_type_id','parent_issue_type_name']:
                row[key] = ''

    field_values = item.get('fieldValues', {}).get('nodes', [])
    for fv in field_values:
        if not fv or not fv.get('field'): continue
        field_name = fv['field'].get('name')
        if not field_name: continue
        sanitized_name = ''.join(c if c.isalnum() else '_' for c in field_name.lower())
        header_name = '_'.join(filter(None, sanitized_name.split('_')))
        if not header_name: continue
        all_field_names.add(header_name)
        value = None
        if 'text' in fv: value = fv['text']
        elif 'number' in fv: value = fv['number']
        elif 'date' in fv: value = fv['date']
        elif 'name' in fv: value = fv['name']
        elif 'title' in fv: value = fv['title']
        row[header_name] = str(value) if value is not None else ''

    processed_data.append(row)

def write_csv(file_path, data_to_write, headers_list):
    print(f"Writing {len(data_to_write)} processed items to {file_path}...")
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=headers_list, restval='', extrasaction='ignore')
            writer.writeheader()
            writer.writerows(data_to_write)
        print(f"CSV file '{file_path}' written successfully.")
    except IOError as e:
        print(f"Error writing CSV file '{file_path}': {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred during CSV writing for '{file_path}': {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)

print(f"Preparing to write CSV files...")

final_headers = core_headers + sorted([h for h in all_field_names if h not in core_headers])

write_csv(OUTPUT_PATH, processed_data, final_headers)
write_csv(LATEST_OUTPUT_PATH, processed_data, final_headers)

print("All CSV files written successfully.")
