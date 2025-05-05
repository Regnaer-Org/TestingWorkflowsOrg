import os
import requests
import json
import csv
from datetime import datetime, timedelta, timezone
import sys
import time

# --- Configuration ---
PROJECT_ID = os.environ.get("PROJECT_ID", "PVT_kwDODH0FwM4A3yi4") # Get from env var or use default
GRAPHQL_API_URL = "https://api.github.com/graphql"
OUTPUT_DIR = "agilereporting"
TOKEN = os.environ.get("MILESTONE_SYNC_TOKEN")

if not TOKEN:
    print("Error: MILESTONE_SYNC_TOKEN environment variable not set.", file=sys.stderr)
    sys.exit(1)
if not PROJECT_ID:
    print("Error: PROJECT_ID environment variable not set.", file=sys.stderr)
    sys.exit(1)

# --- Generate Filename (Central Time, YYYY.MM.DD) ---
# Define Central Time Zone (approximated, consider using pytz for perfect DST handling if needed)
# UTC-6 (CST), UTC-5 (CDT)
# Let's use a fixed offset for simplicity, or rely on runner's timezone setting if appropriate.
# Using America/Chicago requires the runner to have tzdata installed.
# A simpler approach for Actions runner: Get UTC and format.
utc_now = datetime.now(timezone.utc)
# If you absolutely need Chicago time formatted *exactly* like before:
try:
    # This relies on the runner having tzdata available
    # Correct approximation for Chicago time considering DST possibilities
    # This is still an approximation, pytz is better for accuracy
    # Let's try fetching the zone info if available
    from zoneinfo import ZoneInfo
    chicago_tz = ZoneInfo("America/Chicago")
    chicago_now = utc_now.astimezone(chicago_tz)
    snapshot_date = chicago_now.strftime('%Y.%m.%d')
except ImportError: # Fallback if zoneinfo is not available (older Python?)
    print("Warning: zoneinfo module not found. Approximating Chicago time offset. Consider using pytz or ensuring tzdata is available.", file=sys.stderr)
    # Manual offset approximation (less reliable for DST)
    chicago_offset = timedelta(hours=-5) # Assume CDT for summer, adjust if needed
    chicago_now = utc_now + chicago_offset
    snapshot_date = chicago_now.strftime('%Y.%m.%d')
except Exception as e: # Fallback if timezone info is unavailable or other error
     print(f"Warning: Could not determine Chicago time precisely ({e}). Using UTC date.", file=sys.stderr)
     snapshot_date = utc_now.strftime('%Y.%m.%d')


SNAPSHOT_FILENAME = f"project.issues_{snapshot_date}.csv"
OUTPUT_PATH = os.path.join(OUTPUT_DIR, SNAPSHOT_FILENAME)

# --- GraphQL Query (fetches all relevant fields) ---
# This query is designed to get core issue data and all types of ProjectV2 field values
# It relies on fragments to get the field name regardless of the value type.
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
          id # ProjectV2 Item ID
          createdAt
          updatedAt
          isArchived
          type # ISSUE, PULL_REQUEST, DRAFT_ISSUE
          fieldValues(first: 100) { # Get all custom fields for the item
            nodes {
              ... on ProjectV2ItemFieldTextValue {
                text
                field { ... on ProjectV2FieldCommon { name id } }
              }
              ... on ProjectV2ItemFieldDateValue {
                date
                field { ... on ProjectV2FieldCommon { name id } }
              }
              ... on ProjectV2ItemFieldNumberValue {
                number
                field { ... on ProjectV2FieldCommon { name id } }
              }
              ... on ProjectV2ItemFieldSingleSelectValue {
                name # Option selected
                field { ... on ProjectV2SingleSelectField { name id } }
              }
              ... on ProjectV2ItemFieldIterationValue {
                title # Iteration title
                startDate
                duration
                field { ... on ProjectV2IterationField { name id } }
              }
              # Add fragments for other field types if needed (e.g., User, Label)
              # ... on ProjectV2ItemFieldUserValue { users(first:10){nodes{login}} field { ... on ProjectV2FieldCommon { name id } } }
              # ... on ProjectV2ItemFieldLabelValue { labels(first:10){nodes{name}} field { ... on ProjectV2FieldCommon { name id } } }
            }
          }
          content {
            ... on DraftIssue {
              id
              title
              body
              creator: author { login }
            }
            ... on PullRequest {
              id
              number
              title
              state # OPEN, CLOSED, MERGED
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
              # Add other PR fields if needed
            }
            ... on Issue {
              id
              number
              title
              state # OPEN, CLOSED
              url
              createdAt
              updatedAt
              closedAt
              author { login }
              repository { nameWithOwner owner { login } name }
              assignees(first: 10) { nodes { login } }
              labels(first: 20) { nodes { name } }
              milestone { title number state }
              # parent issue for task lists - might need separate query for deep nesting
              # parent { ... on Issue { number title url } }
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

# --- Helper Function to Safely Get Nested Values ---
def get_value(data, keys, default=""):
    """Safely retrieve nested dictionary values."""
    current = data
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        # Removed list index access for simplicity, handle lists explicitly where needed
        # elif isinstance(current, list) and isinstance(key, int) and 0 <= key < len(current):
        #      current = current[key]
        else:
            return default
        if current is None:
            return default
    # Convert non-string results (like numbers) to string for CSV
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
            # Decide if partial data is acceptable or if we should exit
            project_data = data.get('data', {}).get('node', {})
            if not project_data: # If no data node at all, exit
                 sys.exit(1)
        else: # No GraphQL errors
             project_data = data.get('data', {}).get('node', {})

        if not project_data:
            print("Error: Could not find project node in response.", file=sys.stderr)
            print(json.dumps(data, indent=2), file=sys.stderr) # Print full response for debug
            sys.exit(1)

        items_data = project_data.get('items', {})
        nodes = items_data.get('nodes', [])
        page_info = items_data.get('pageInfo', {})

        if nodes:
            all_items.extend(nodes)
            item_count += len(nodes)
            total_project_items = items_data.get('totalCount', item_count) # Get total if available
            print(f"Fetched {len(nodes)} items (Total processed: {item_count} / {total_project_items or 'unknown'})...")

        has_next_page = page_info.get('hasNextPage', False)
        cursor = page_info.get('endCursor')

        # Optional: Add delay to avoid hitting secondary rate limits on very large projects
        if has_next_page:
             time.sleep(0.2) # Small delay between pages

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
all_field_names = set() # To dynamically collect all ProjectV2 field names

# Define core fields we always expect (order matters for initial set)
core_headers = [
    'project_item_id', 'project_item_type', 'project_item_created_at', 'project_item_updated_at', 'project_item_is_archived',
    'content_id', 'content_type', 'content_number', 'content_title', 'content_state', 'content_url',
    'content_created_at', 'content_updated_at', 'content_closed_at', 'content_merged_at',
    'author', 'repository', 'repository_owner', 'repository_name',
    'assignees', 'labels',
    'milestone_title', 'milestone_number', 'milestone_state'
]
# Add core headers to the dynamic set
for header in core_headers:
     all_field_names.add(header)


print("Processing items for CSV conversion...")
for item in all_items:
    row = {} # Initialize row dictionary for this item

    # --- Project Item Core Fields ---
    row['project_item_id'] = item.get('id', '')
    row['project_item_type'] = item.get('type', '')
    row['project_item_created_at'] = item.get('createdAt', '')
    row['project_item_updated_at'] = item.get('updatedAt', '')
    row['project_item_is_archived'] = str(item.get('isArchived', '')) # Ensure string

    # --- Content Fields (Issue, PR, DraftIssue) ---
    content = item.get('content')
    if content:
        # Determine content type based on available fields (GraphQL __typename is better if available)
        if 'repository' in content: # Issue or PR
             # PRs have specific fields like mergedAt or state MERGED
             if 'mergedAt' in content or content.get('state') == 'MERGED':
                  row['content_type'] = 'PullRequest'
             else:
                  row['content_type'] = 'Issue'
        elif 'body' in content and ('creator' in content or 'author' in content): # DraftIssue might use 'author' now
            row['content_type'] = 'DraftIssue'
        else:
            row['content_type'] = 'Unknown' # Should not happen often

        row['content_id'] = content.get('id', '')
        row['content_number'] = str(content.get('number', '')) # Ensure string
        row['content_title'] = content.get('title', '')
        row['content_state'] = content.get('state', '') # OPEN/CLOSED for Issue, OPEN/CLOSED/MERGED for PR
        row['content_url'] = content.get('url', '')
        row['content_created_at'] = content.get('createdAt', '')
        row['content_updated_at'] = content.get('updatedAt', '')
        row['content_closed_at'] = content.get('closedAt', '')
        row['content_merged_at'] = content.get('mergedAt', '') # PR specific
        row['author'] = get_value(content, ['author', 'login'], get_value(content, ['creator', 'login'])) # Handle PR/Issue author vs Draft creator
        row['repository'] = get_value(content, ['repository', 'nameWithOwner'])
        row['repository_owner'] = get_value(content, ['repository', 'owner', 'login'])
        row['repository_name'] = get_value(content, ['repository', 'name'])

        # Assignees (list, semicolon separated)
        assignees_nodes = get_value(content, ['assignees', 'nodes'], [])
        assignees = [a.get('login', '') for a in assignees_nodes if a] if isinstance(assignees_nodes, list) else []
        row['assignees'] = ";".join(filter(None, assignees))

        # Labels (list, semicolon separated)
        labels_nodes = get_value(content, ['labels', 'nodes'], [])
        labels = [lbl.get('name', '') for lbl in labels_nodes if lbl] if isinstance(labels_nodes, list) else []
        row['labels'] = ";".join(filter(None, labels))

        # Milestone
        row['milestone_title'] = get_value(content, ['milestone', 'title'])
        row['milestone_number'] = str(get_value(content, ['milestone', 'number'])) # Ensure string
        row['milestone_state'] = get_value(content, ['milestone', 'state'])

    else: # Item might be archived or have no linked content
         row['content_type'] = 'No Content'
         # Set default empty values for content-related core fields
         for key in core_headers:
              if key.startswith('content_') or key in ['author','repository','repository_owner','repository_name','assignees','labels','milestone_title','milestone_number','milestone_state']:
                   row[key] = ''

    # --- ProjectV2 Custom Fields ---
    field_values = item.get('fieldValues', {}).get('nodes', [])
    custom_fields_processed_this_item = set() # Track fields processed for this item

    for fv in field_values:
        if not fv or not fv.get('field'): continue # Skip empty field values or those missing field info

        field_name = fv['field'].get('name')
        if not field_name: continue # Skip if field name is missing

        # Sanitize field name for CSV header (lowercase, replace space/special chars with underscore)
        sanitized_name = ''.join(c if c.isalnum() else '_' for c in field_name.lower())
        # Remove leading/trailing underscores and collapse multiple underscores
        header_name = '_'.join(filter(None, sanitized_name.split('_')))

        if not header_name: continue # Skip if sanitized name is empty

        all_field_names.add(header_name) # Add to our dynamic set of headers
        custom_fields_processed_this_item.add(header_name) # Mark as processed for this item

        # Extract the value based on type
        value = ''
        if 'text' in fv: value = fv['text']
        elif 'number' in fv: value = fv['number'] # Keep as number for now, will be str in CSV
        elif 'date' in fv: value = fv['date']
        elif 'name' in fv: value = fv['name'] # SingleSelect
        elif 'title' in fv: value = fv['title'] # Iteration
        # Add other types if needed (User, Labels from Project Fields)
        # elif 'users' in fv: value = ";".join(u.get('login','') for u in fv.get('users',{}).get('nodes',[]) if u)
        # elif 'labels' in fv: value = ";".join(l.get('name','') for l in fv.get('labels',{}).get('nodes',[]) if l)

        # Store the extracted value in the row dictionary, ensure string
        row[header_name] = str(value) if value is not None else ''

    # Ensure all dynamically found custom fields exist in the row, even if null for this item
    # This prevents DictWriter errors if an item lacks a field another item had
    # for dynamic_header in all_field_names:
    #     if dynamic_header not in core_headers and dynamic_header not in custom_fields_processed_this_item:
    #         row[dynamic_header] = '' # Set default empty for fields not present on this item

    processed_data.append(row)

# --- Write CSV File ---
print(f"Writing {len(processed_data)} processed items to {OUTPUT_PATH}...")

# Define the final header order: start with core fields, then add sorted custom fields
# Use the dynamically collected set `all_field_names`
final_headers = core_headers + sorted([h for h in all_field_names if h not in core_headers])

try:
    os.makedirs(OUTPUT_DIR, exist_ok=True) # Ensure output directory exists
    with open(OUTPUT_PATH, 'w', newline='', encoding='utf-8') as csvfile:
        # Use DictWriter for robustness against missing fields in some rows
        # `restval=''` ensures that if a row dict is missing a key from final_headers, it writes an empty string
        writer = csv.DictWriter(csvfile, fieldnames=final_headers, restval='', extrasaction='ignore')

        writer.writeheader() # Write the header row
        writer.writerows(processed_data) # Write all data rows

except IOError as e:
    print(f"Error writing CSV file '{OUTPUT_PATH}': {e}", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f"An unexpected error occurred during CSV writing: {e}", file=sys.stderr)
    import traceback
    traceback.print_exc(file=sys.stderr)
    sys.exit(1)

print("CSV file written successfully.")
# --- Set output for workflow ---
# This allows the commit step to know the exact filename generated
# Ensure the output path is correctly formatted for the runner OS if needed, but typically works directly.
print(f"::set-output name=snapshot_filename::{OUTPUT_PATH}")
