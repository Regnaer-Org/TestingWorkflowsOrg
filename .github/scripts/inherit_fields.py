import os
import requests
import json
import sys
import time

# --- Configuration ---
TOKEN = os.environ.get("GITHUB_TOKEN")
PROJECT_ID = os.environ.get("PROJECT_ID") # ProjectV2 Node ID (e.g., from vars)
REPO_OWNER = os.environ.get("REPO_OWNER")
REPO_NAME = os.environ.get("REPO_NAME")
NEW_ISSUE_NODE_ID = os.environ.get("NEW_ISSUE_NODE_ID") # The triggering issue
NEW_ISSUE_NUMBER = os.environ.get("NEW_ISSUE_NUMBER") # The triggering issue number

# --- API Setup ---
GRAPHQL_API_URL = "https://api.github.com/graphql"
REST_API_URL_BASE = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}"
HEADERS_GRAPHQL = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
    "Accept": "application/json",
    "GraphQL-Features": "sub_issues" # Ensure sub_issues feature is enabled
}
HEADERS_REST = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github.v3+json",
    "X-GitHub-Api-Version": "2022-11-28"
}

# --- Constants ---
TARGET_SPRINT_FIELD_NAME = "Sprint"
TARGET_TEAM_FIELD_NAME = "Team"

# --- Validate Environment Variables ---
if not all([TOKEN, PROJECT_ID, REPO_OWNER, REPO_NAME, NEW_ISSUE_NODE_ID, NEW_ISSUE_NUMBER]):
    print("Error: Missing one or more required environment variables.", file=sys.stderr)
    print(f"TOKEN: {'Set' if TOKEN else 'Missing'}", file=sys.stderr)
    print(f"PROJECT_ID: {PROJECT_ID}", file=sys.stderr)
    print(f"REPO_OWNER: {REPO_OWNER}", file=sys.stderr)
    print(f"REPO_NAME: {REPO_NAME}", file=sys.stderr)
    print(f"NEW_ISSUE_NODE_ID: {NEW_ISSUE_NODE_ID}", file=sys.stderr)
    print(f"NEW_ISSUE_NUMBER: {NEW_ISSUE_NUMBER}", file=sys.stderr)
    sys.exit(1)

try:
    NEW_ISSUE_NUMBER = int(NEW_ISSUE_NUMBER)
except ValueError:
    print(f"Error: NEW_ISSUE_NUMBER ('{NEW_ISSUE_NUMBER}') is not a valid integer.", file=sys.stderr)
    sys.exit(1)

# --- Helper Functions (Consider moving to github_utils.py later) ---
def graphql_request(query, variables=None):
    """Makes a GraphQL request and handles basic error checking."""
    try:
        response = requests.post(GRAPHQL_API_URL, headers=HEADERS_GRAPHQL, json={"query": query, "variables": variables or {}}, timeout=30)
        response.raise_for_status()
        data = response.json()
        if "errors" in data:
            print(f"GraphQL Error: {json.dumps(data['errors'])}", file=sys.stderr)
            # Check for specific project access error
            if any("Could not resolve to a ProjectV2 with the number" in e.get("message", "") for e in data["errors"]):
                 print("Hint: Ensure the token has access to the specified ProjectV2.", file=sys.stderr)
            return None
        return data.get("data")
    except requests.exceptions.RequestException as e:
        print(f"GraphQL Request failed: {e}", file=sys.stderr)
        if e.response is not None:
            print(f"Response Status: {e.response.status_code}", file=sys.stderr)
            print(f"Response Text: {e.response.text[:500]}...", file=sys.stderr) # Print beginning of error response
        return None
    except Exception as e:
        print(f"An unexpected error occurred during GraphQL request: {e}", file=sys.stderr)
        return None

def rest_patch_request(endpoint, payload):
    """Makes a REST PATCH request."""
    url = f"{REST_API_URL_BASE}{endpoint}"
    try:
        response = requests.patch(url, headers=HEADERS_REST, json=payload, timeout=30)
        if 400 <= response.status_code < 500:
             print(f"Warning: REST PATCH request to {url} returned status {response.status_code}. Payload: {json.dumps(payload)}. Response: {response.text[:200]}...", file=sys.stderr)
             return False # Indicate non-fatal failure
        response.raise_for_status() # Raise for 5xx or other non-4xx client errors
        print(f"  REST PATCH to {url} successful (Status: {response.status_code})")
        return True
    except requests.exceptions.RequestException as e:
        print(f"REST PATCH request to {url} failed: {e}", file=sys.stderr)
        if e.response is not None:
            print(f"Response Status: {e.response.status_code}", file=sys.stderr)
            print(f"Response Text: {e.response.text[:500]}...", file=sys.stderr)
        return False
    except Exception as e:
        print(f"An unexpected error occurred during REST PATCH request: {e}", file=sys.stderr)
        return False

# --- GraphQL Queries & Mutations ---
GET_PARENT_INFO_QUERY = """
query GetParentInfo($issueId: ID!) {
  node(id: $issueId) {
    ... on Issue {
      parent {
        id
        number
        milestone { number }
        labels(first: 100) { nodes { name } }
        # Get project items to find Sprint/Team values
        projectItems(first: 10) {
          nodes {
            project { id } # Project ID the parent is in
            fieldValues(first: 20) {
              nodes {
                __typename
                ... on ProjectV2ItemFieldSingleSelectValue {
                  field { ... on ProjectV2SingleSelectField { name id } }
                  name # Team Name
                  optionId # Team Option ID
                }
                ... on ProjectV2ItemFieldIterationValue {
                  field { ... on ProjectV2IterationField { name id } }
                  title # Sprint Title
                  iterationId # Sprint Iteration ID
                }
              }
            }
          }
        }
      }
    }
  }
}
"""

GET_PROJECT_FIELDS_QUERY = """
query GetProjectFields($projectId: ID!) {
  node(id: $projectId) {
    ... on ProjectV2 {
      fields(first: 50) {
        nodes {
          __typename
          ... on ProjectV2SingleSelectField {
            id
            name
            options { id name }
          }
          ... on ProjectV2IterationField {
            id
            name
            configuration {
              iterations { id title }
            }
          }
        }
      }
    }
  }
}
"""

ADD_ITEM_TO_PROJECT_MUTATION = """
mutation AddItemToProject($projectId: ID!, $contentId: ID!) {
  addProjectV2ItemById(input: {projectId: $projectId, contentId: $contentId}) {
    item { id } # Returns the Project Item ID
  }
}
"""

UPDATE_ITERATION_FIELD_MUTATION = """
mutation UpdateIterationField($projectId: ID!, $itemId: ID!, $fieldId: ID!, $iterationId: String!) {
  updateProjectV2ItemFieldValue(input: {
    projectId: $projectId,
    itemId: $itemId,
    fieldId: $fieldId,
    value: { iterationId: $iterationId }
  }) {
    projectV2Item { id }
  }
}
"""

UPDATE_SINGLE_SELECT_FIELD_MUTATION = """
mutation UpdateSingleSelectField($projectId: ID!, $itemId: ID!, $fieldId: ID!, $optionId: String!) {
  updateProjectV2ItemFieldValue(input: {
    projectId: $projectId,
    itemId: $itemId,
    fieldId: $fieldId,
    value: { singleSelectOptionId: $optionId }
  }) {
    projectV2Item { id }
  }
}
"""

# --- Main Logic ---
print("Starting field inheritance process...")
print(f"Processing new issue: #{NEW_ISSUE_NUMBER} (Node ID: {NEW_ISSUE_NODE_ID})")
print(f"Target Project ID: {PROJECT_ID}")

# 1. Get Parent Issue Info
print("Fetching parent issue information...")
parent_data = graphql_request(GET_PARENT_INFO_QUERY, {"issueId": NEW_ISSUE_NODE_ID})

if not parent_data or not parent_data.get("node", {}).get("parent"):
    print("No parent issue found or failed to fetch data. Exiting.")
    sys.exit(0) # Not an error, just no parent

parent_info = parent_data["node"]["parent"]
parent_number = parent_info.get("number")
parent_milestone_number = parent_info.get("milestone", {}).get("number")
parent_labels = [label["name"] for label in parent_info.get("labels", {}).get("nodes", [])]
parent_project_items = parent_info.get("projectItems", {}).get("nodes", [])

print(f"Found parent issue: #{parent_number}")

# 2. Inherit Milestone (REST)
if parent_milestone_number is not None:
    print(f"  Inheriting milestone: {parent_milestone_number}")
    payload = {"milestone": parent_milestone_number}
    if not rest_patch_request(f"/issues/{NEW_ISSUE_NUMBER}", payload):
        print(f"  Warning: Failed to set milestone on issue #{NEW_ISSUE_NUMBER}.")
else:
    print("  Parent has no milestone to inherit.")

# 3. Inherit Labels (REST)
if parent_labels:
    print(f"  Inheriting labels: {', '.join(parent_labels)}")
    payload = {"labels": parent_labels}
    # Use PATCH to add labels without removing existing ones if any were added manually very quickly
    # Note: GitHub API v3 PATCH for labels replaces all labels. Use POST to add if needed, but PATCH is simpler for inheritance.
    if not rest_patch_request(f"/issues/{NEW_ISSUE_NUMBER}", payload):
         print(f"  Warning: Failed to set labels on issue #{NEW_ISSUE_NUMBER}.")
else:
    print("  Parent has no labels to inherit.")

# 4. Inherit ProjectV2 Fields (Sprint, Team)
parent_sprint_iteration_id = None
parent_sprint_title = None
parent_team_option_id = None
parent_team_name = None

print("Searching parent's project items for Sprint and Team values...")
for item in parent_project_items:
    # Optional: Check if item.project.id matches our target PROJECT_ID if parent could be in multiple projects
    # if item.get("project", {}).get("id") != PROJECT_ID:
    #     continue

    for fv in item.get("fieldValues", {}).get("nodes", []):
        field_info = fv.get("field", {})
        field_name = field_info.get("name")

        # Find first valid Sprint value
        if field_name == TARGET_SPRINT_FIELD_NAME and fv.get("__typename") == "ProjectV2ItemFieldIterationValue" and not parent_sprint_iteration_id:
            parent_sprint_iteration_id = fv.get("iterationId")
            parent_sprint_title = fv.get("title")
            if parent_sprint_iteration_id:
                print(f"  Found parent Sprint value: '{parent_sprint_title}' ({parent_sprint_iteration_id})")

        # Find first valid Team value
        elif field_name == TARGET_TEAM_FIELD_NAME and fv.get("__typename") == "ProjectV2ItemFieldSingleSelectValue" and not parent_team_option_id:
            parent_team_option_id = fv.get("optionId")
            parent_team_name = fv.get("name")
            if parent_team_option_id:
                print(f"  Found parent Team value: '{parent_team_name}' ({parent_team_option_id})")

    # Stop searching if both found
    if parent_sprint_iteration_id and parent_team_option_id:
        break

if not parent_sprint_iteration_id and not parent_team_option_id:
    print("No Sprint or Team values found on parent's project items. Skipping ProjectV2 field inheritance.")
    sys.exit(0)

# 5. Get Project Field Definitions (IDs and valid options/iterations)
print(f"Fetching field definitions for Project: {PROJECT_ID}")
fields_data = graphql_request(GET_PROJECT_FIELDS_QUERY, {"projectId": PROJECT_ID})
if not fields_data or not fields_data.get("node"):
    print("Error: Failed to fetch project field definitions. Cannot verify or set Sprint/Team.", file=sys.stderr)
    sys.exit(1)

project_fields = fields_data["node"].get("fields", {}).get("nodes", [])
sprint_field_id = None
team_field_id = None
valid_sprint_iteration_ids = set()
valid_team_option_ids = set()

for field in project_fields:
    field_name = field.get("name")
    if field_name == TARGET_SPRINT_FIELD_NAME and field.get("__typename") == "ProjectV2IterationField":
        sprint_field_id = field.get("id")
        iterations = field.get("configuration", {}).get("iterations", [])
        valid_sprint_iteration_ids = {iter["id"] for iter in iterations}
        print(f"  Found Sprint field ID: {sprint_field_id}. Valid iterations: {len(valid_sprint_iteration_ids)}")
    elif field_name == TARGET_TEAM_FIELD_NAME and field.get("__typename") == "ProjectV2SingleSelectField":
        team_field_id = field.get("id")
        options = field.get("options", [])
        valid_team_option_ids = {opt["id"] for opt in options}
        print(f"  Found Team field ID: {team_field_id}. Valid options: {len(valid_team_option_ids)}")

if not sprint_field_id and parent_sprint_iteration_id:
     print(f"Warning: Parent has Sprint value, but no field named '{TARGET_SPRINT_FIELD_NAME}' found in project {PROJECT_ID}.", file=sys.stderr)
if not team_field_id and parent_team_option_id:
     print(f"Warning: Parent has Team value, but no field named '{TARGET_TEAM_FIELD_NAME}' found in project {PROJECT_ID}.", file=sys.stderr)

# 6. Add New Issue to Project and Update Fields
print(f"Adding issue #{NEW_ISSUE_NUMBER} to project {PROJECT_ID}...")
add_item_data = graphql_request(ADD_ITEM_TO_PROJECT_MUTATION, {"projectId": PROJECT_ID, "contentId": NEW_ISSUE_NODE_ID})

# Retry mechanism for adding item to project, as it can sometimes fail due to eventual consistency
retry_count = 0
max_retries = 3
while (not add_item_data or not add_item_data.get("addProjectV2ItemById", {}).get("item")) and retry_count < max_retries:
    retry_count += 1
    wait_time = 2**retry_count # Exponential backoff (2, 4, 8 seconds)
    print(f"Warning: Failed to add issue to project on attempt {retry_count}. Retrying in {wait_time} seconds...", file=sys.stderr)
    time.sleep(wait_time)
    add_item_data = graphql_request(ADD_ITEM_TO_PROJECT_MUTATION, {"projectId": PROJECT_ID, "contentId": NEW_ISSUE_NODE_ID})

if not add_item_data or not add_item_data.get("addProjectV2ItemById", {}).get("item"):
    print(f"Error: Failed to add issue #{NEW_ISSUE_NUMBER} to project {PROJECT_ID} after {max_retries} retries. Cannot set Sprint/Team fields.", file=sys.stderr)
    sys.exit(1) # Exit with error after retries fail

new_project_item_id = add_item_data["addProjectV2ItemById"]["item"]["id"]
print(f"  Successfully added issue to project. New Project Item ID: {new_project_item_id}")


# Update Sprint Field
if sprint_field_id and parent_sprint_iteration_id:
    if parent_sprint_iteration_id in valid_sprint_iteration_ids:
        print(f"  Setting Sprint field to '{parent_sprint_title}' ({parent_sprint_iteration_id})...")
        update_sprint_data = graphql_request(UPDATE_ITERATION_FIELD_MUTATION, {
            "projectId": PROJECT_ID,
            "itemId": new_project_item_id,
            "fieldId": sprint_field_id,
            "iterationId": parent_sprint_iteration_id
        })
        if not update_sprint_data:
            print(f"  Warning: Failed to update Sprint field for item {new_project_item_id}.")
    else:
        print(f"  Warning: Parent Sprint value '{parent_sprint_title}' ({parent_sprint_iteration_id}) is not a valid/current iteration in project {PROJECT_ID}. Skipping.")

# Update Team Field
if team_field_id and parent_team_option_id:
    if parent_team_option_id in valid_team_option_ids:
        print(f"  Setting Team field to '{parent_team_name}' ({parent_team_option_id})...")
        update_team_data = graphql_request(UPDATE_SINGLE_SELECT_FIELD_MUTATION, {
            "projectId": PROJECT_ID,
            "itemId": new_project_item_id,
            "fieldId": team_field_id,
            "optionId": parent_team_option_id
        })
        if not update_team_data:
            print(f"  Warning: Failed to update Team field for item {new_project_item_id}.")
    else:
        print(f"  Warning: Parent Team value '{parent_team_name}' ({parent_team_option_id}) is not a valid option in project {PROJECT_ID}. Skipping.")

print("Field inheritance process complete.")
