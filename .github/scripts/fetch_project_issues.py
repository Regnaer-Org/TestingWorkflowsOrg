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
utc_now = datetime.now(timezone.utc)
try:
    # Use zoneinfo if available (Python 3.9+) for better timezone handling
    from zoneinfo import ZoneInfo
    chicago_tz = ZoneInfo("America/Chicago")
    chicago_now = utc_now.astimezone(chicago_tz)
    snapshot_date = chicago_now.strftime('%Y.%m.%d')
except ImportError:
    # Fallback for older Python versions (less accurate DST handling)
    print("Warning: zoneinfo module not found. Approximating Chicago time offset.", file=sys.stderr)
    chicago_offset = timedelta(hours=-5) # Manual offset (CDT approximation)
    chicago_now = utc_now + chicago_offset
    snapshot_date = chicago_now.strftime('%Y.%m.%d')
except Exception as e:
     # General fallback if timezone lookup fails
     print(f"Warning: Could not determine Chicago time precisely ({e}). Using UTC date.", file=sys.stderr)
     snapshot_date = utc_now.strftime('%Y.%m.%d')

SNAPSHOT_FILENAME = f"project.issues_{snapshot_date}.csv"
OUTPUT_PATH = os.path.join(OUTPUT_DIR, SNAPSHOT_FILENAME)

# --- GraphQL Query (Includes labels, assignees nodes) ---
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
                name # Option selected
                field { ...ProjectV2FieldCommon }
              }
              ... on ProjectV2ItemFieldIterationValue {
                title # Iteration title
                startDate
                duration
                field { ...ProjectV2FieldCommon }
              }
              # Add fragments for other field types if needed
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
              state # OPEN, CLOSED, MERGED
              url
              createdAt
              updatedAt
              closedAt
              mergedAt
              author { login }
              repository { nameWithOwner owner { login } name }
              assignees(first: 10) { nodes { login } } # Request assignees
              labels(first: 20) { nodes { name } }     # Request labels
              milestone { title number state }
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
              assignees(first: 10) { nodes { login } } # Request assignees
              labels(first: 20) { nodes { name } }     # Request labels
              milestone { title number state }
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
    # Add other field types here if you add fragments for them above
}
"""

# --- Helper Function to Safely Get Nested Values (for single values) ---
def get_value(data, keys, default=""):
    """Safely retrieve nested dictionary values."""
    current = data
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        else: # Not a dictionary, cannot proceed
            return default
        if current is None: # Key not found or value is None
            return default
    # Convert final result to string for CSV consistency
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
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        data = response.json()

        # Check for GraphQL errors in the response body
        if 'errors' in data:
            print("Error: GraphQL API returned errors:", file=sys.stderr)
            print(json.dumps(data['errors'], indent=2), file=sys.stderr)
            # Attempt to process partial data if available, but exit if node is missing
            project_data = data.get('data', {}).get('node', {})
            if not project_data:
                 print("Error: No project data node found in response with errors.", file=sys.stderr)
                 sys.exit(1)
        else: # No GraphQL errors
             project_data = data.get('data', {}).get('node', {})

        # Ensure project data node exists
        if not project_data:
            print("Error: Could not find project node in response.", file=sys.stderr)
            print(json.dumps(data, indent=2), file=sys.stderr) # Print full response for debug
            sys.exit(1)

        # Extract items data
        items_data = project_data.get('items', {})
        nodes = items_data.get('nodes', [])
        page_info = items_data.get('pageInfo', {})

        if nodes:
            all_items.extend(nodes)
            item_count += len(nodes)
            total_project_items = items_data.get('totalCount', item_count) # Get total if available
            print(f"Fetched {len(nodes)} items (Total processed: {item_count} / {total_project_items or 'unknown'})...")

        # Update pagination info
        has_next_page = page_info.get('hasNextPage', False)
        cursor = page_info.get('endCursor')

        # Optional delay to avoid secondary rate limits
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
        # Determine content type
        if 'repository' in content: # Issue or PR
             if 'mergedAt' in content or content.get('state') == 'MERGED':
                  row['content_type'] = 'PullRequest'
             else:
                  row['content_type'] = 'Issue'
        elif 'body' in content and ('creator' in content or 'author' in content): # DraftIssue might use 'author' now
            row['content_type'] = 'DraftIssue'
        else:
            row['content_type'] = 'Unknown' # Should not happen often

        # Basic content fields (using get_value where appropriate for single values)
        row['content_id'] = content.get('id', '') # Direct get is fine
        row['content_number'] = str(content.get('number', '')) # Direct get, ensure string
        row['content_title'] = content.get('title', '') # Direct get
        row['content_state'] = content.get('state', '') # Direct get
        row['content_url'] = content.get('url', '') # Direct get
        row['content_created_at'] = content.get('createdAt', '') # Direct get
        row['content_updated_at'] = content.get('updatedAt', '') # Direct get
        row['content_closed_at'] = content.get('closedAt', '') # Direct get
        row['content_merged_at'] = content.get('mergedAt', '') # Direct get
        row['author'] = get_value(content, ['author', 'login'], get_value(content, ['creator', 'login'])) # Use helper for nested optional author/creator
        row['repository'] = get_value(content, ['repository', 'nameWithOwner']) # Use helper
        row['repository_owner'] = get_value(content, ['repository', 'owner', 'login']) # Use helper
        row['repository_name'] = get_value(content, ['repository', 'name']) # Use helper

        # --- Assignees (Corrected - Direct Access for List) ---
        assignees_nodes = content.get('assignees', {}).get('nodes', [])
        if isinstance(assignees_nodes, list):
             assignees_logins = [a.get('login', '') for a in assignees_nodes if a and isinstance(a, dict)]
             row['assignees'] = ";".join(filter(None, assignees_logins))
        else:
             row['assignees'] = "" # Default to empty if structure is unexpected

        # --- Labels (Corrected - Direct Access for List) ---
        labels_nodes = content.get('labels', {}).get('nodes', [])
        if isinstance(labels_nodes, list):
            label_names = [lbl.get('name', '') for lbl in labels_nodes if lbl and isinstance(lbl, dict)]
            row['labels'] = ";".join(filter(None, label_names))
        else:
            row['labels'] = "" # Default to empty if structure is unexpected

        # --- Milestone (using get_value for single nested fields) ---
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
        if not fv or not fv.get('field'): continue # Skip empty/invalid field values

        field_name = fv['field'].get('name')
        if not field_name: continue # Skip if field name is missing

        # Sanitize field name for CSV header
        sanitized_name = ''.join(c if c.isalnum() else '_' for c in field_name.lower())
        header_name = '_'.join(filter(None, sanitized_name.split('_'))) # Collapse underscores

        if not header_name: continue # Skip if sanitized name is empty

        all_field_names.add(header_name) # Add to our dynamic set of all headers
        custom_fields_processed_this_item.add(header_name) # Mark as processed for this specific item

        # Extract the value based on type
        value = None # Initialize value
        if 'text' in fv: value = fv['text']
        elif 'number' in fv: value = fv['number']
        elif 'date' in fv: value = fv['date']
        elif 'name' in fv: value = fv['name'] # SingleSelect option name
        elif 'title' in fv: value = fv['title'] # Iteration title
        # Add other types like User, Labels if needed in the GraphQL query and here

        # Store the extracted value in the row dictionary, ensure string
        row[header_name] = str(value) if value is not None else ''

    # Ensure all dynamically found custom fields exist in the row dictionary for DictWriter
    # This step might be redundant if restval='' is used in DictWriter, but can be explicit
    # for dynamic_header in all_field_names:
    #     if dynamic_header not in core_headers and dynamic_header not in row:
    #          row[dynamic_header] = '' # Set default empty for fields not present on this item


    processed_data.append(row)

# --- Write CSV File ---
print(f"Writing {len(processed_data)} processed items to {OUTPUT_PATH}...")

# Define the final header order: start with core fields, then add sorted custom fields
final_headers = core_headers + sorted([h for h in all_field_names if h not in core_headers])

try:
    os.makedirs(OUTPUT_DIR, exist_ok=True) # Ensure output directory exists
    with open(OUTPUT_PATH, 'w', newline='', encoding='utf-8') as csvfile:
        # Use DictWriter for robustness.
        # `restval=''` ensures that if a row dict is missing a key from final_headers, it writes an empty string.
        # `extrasaction='ignore'` prevents errors if a row dict somehow has more keys than final_headers.
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

# --- Set output for workflow using environment file ---
output_env_file = os.environ.get("GITHUB_OUTPUT")

if output_env_file:
    print(f"Setting output 'snapshot_filename' in {output_env_file}")
    try:
        with open(output_env_file, "a") as f:
            f.write(f"snapshot_filename={OUTPUT_PATH}\n")
        print("Output set successfully.")
    except Exception as e:
        print(f"Error writing to GITHUB_OUTPUT file '{output_env_file}': {e}", file=sys.stderr)
else:
    print("Warning: GITHUB_OUTPUT environment variable not set. Cannot pass output to subsequent steps.", file=sys.stderr)
