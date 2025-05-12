import os
import requests
import json
import sys
import time

# --- Configuration ---
TOKEN = os.environ.get("MILESTONE_SYNC_TOKEN")
PROJECT_ID = os.environ.get("PROJECT_ID")
REPO_OWNER = os.environ.get("REPO_OWNER")
REPO_NAME = os.environ.get("REPO_NAME")
API_URL = "https://api.github.com/graphql"
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
    "Accept": "application/json",
    "GraphQL-Features": "issue_types, sub_issues" # Ensure this feature flag is supported if sub-issue types are recent
}

# --- Validate Environment Variables ---
if not TOKEN:
    print("Error: MILESTONE_SYNC_TOKEN environment variable not set.", file=sys.stderr)
    sys.exit(1)
if not PROJECT_ID:
    print("Error: PROJECT_ID environment variable not set.", file=sys.stderr)
    sys.exit(1)
if not REPO_OWNER:
    print("Error: REPO_OWNER environment variable not set.", file=sys.stderr)
    sys.exit(1)
if not REPO_NAME:
    print("Error: REPO_NAME environment variable not set.", file=sys.stderr)
    sys.exit(1)

# --- GraphQL Queries and Mutations ---
SEARCH_ISSUES_QUERY = """
query SearchOpenIssues($searchQuery: String!, $cursor: String) {
  search(query: $searchQuery, type: ISSUE, first: 50, after: $cursor) {
    pageInfo {
      hasNextPage
      endCursor
    }
    nodes {
      ... on Issue {
        id
        number
        title
        state
        issueType { name }
        projectItems(first: 10) {
          nodes {
            id
            project { id }
            fieldValues(first: 20) {
              nodes {
                ... on ProjectV2ItemFieldIterationValue {
                  iterationId
                  title
                  field {
                    ... on ProjectV2IterationField {
                      id
                      name
                    }
                  }
                }
              }
            }
          }
        }
        subIssues(first: 50) {
          nodes {
            # Ensure this is the Issue object for sub-issues to get its type
            ... on Issue {
              id
              number
              state
              issueType { name } # <<< Added to get sub-issue type
            }
          }
        }
      }
    }
  }
}
"""
ADD_TO_PROJECT_MUTATION = """
mutation AddItemToProject($projectId: ID!, $contentId: ID!) {
  addProjectV2ItemById(input: {projectId: $projectId, contentId: $contentId}) {
    item {
      id
    }
  }
}
"""
UPDATE_SPRINT_MUTATION = """
mutation UpdateSprint($projectId: ID!, $itemId: ID!, $fieldId: ID!, $iterationId: String!) {
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
CLEAR_SPRINT_MUTATION = """
mutation ClearSprint($projectId: ID!, $itemId: ID!, $fieldId: ID!) {
  clearProjectV2ItemFieldValue(input: {
    projectId: $projectId,
    itemId: $itemId,
    fieldId: $fieldId
  }) {
    projectV2Item { id }
  }
}
"""

# --- Helper Function for GraphQL Requests ---
def graphql_request(query, variables=None):
    """Makes a GraphQL request and handles basic error checking."""
    try:
        response = requests.post(API_URL, headers=HEADERS, json={"query": query, "variables": variables or {}}, timeout=60)
        response.raise_for_status()
        data = response.json()
        if "errors" in data:
            print(f"GraphQL Error: {json.dumps(data['errors'])}", file=sys.stderr)
            # Check for specific errors like "Field 'issueType' doesn't exist on type 'PullRequest'" if subIssues can include PRs
            for error in data['errors']:
                if "locations" in error and "message" in error: # Basic check
                     print(f"  Message: {error['message']}")
            return None
        return data.get("data")
    except requests.exceptions.RequestException as e:
        print(f"HTTP Request failed: {e}", file=sys.stderr)
        if 'response' in locals() and response is not None:
            print(f"Response Status: {response.status_code}", file=sys.stderr)
            print(f"Response Body: {response.text[:500]}...", file=sys.stderr)
        return None
    except json.JSONDecodeError as e:
        print(f"JSON Decode Error: {e}. Response text: {response.text[:500]}...", file=sys.stderr)
        return None
    except Exception as e:
        print(f"An unexpected error occurred during GraphQL request: {e}", file=sys.stderr)
        return None

# --- Main Logic ---
processed_parents = 0
updated_sub_issues = 0
cleared_sub_issues = 0
skipped_sub_issues_error = 0
skipped_sub_issues_type = 0
discovered_sprint_field_id = None

print(f"Starting Sprint sync for project {PROJECT_ID} in repo {REPO_OWNER}/{REPO_NAME}")
print(f"Run initiated by user: {os.environ.get('GITHUB_ACTOR', 'Unknown')} at {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
print("Fetching open issues...")

has_next_page = True
cursor = None
search_query = f"repo:{REPO_OWNER}/{REPO_NAME} is:open is:issue"

while has_next_page:
    variables = {"searchQuery": search_query, "cursor": cursor}
    data = graphql_request(SEARCH_ISSUES_QUERY, variables)

    if not data or not data.get("search"):
        print("Error fetching issues or empty search result. Aborting.", file=sys.stderr)
        break

    search_result = data["search"]
    issues = search_result.get("nodes", [])
    page_info = search_result.get("pageInfo", {})
    has_next_page = page_info.get("hasNextPage", False)
    cursor = page_info.get("endCursor")

    print(f"Processing batch of {len(issues)} issues...")

    for issue in issues:
        if not issue:
            continue

        issue_number = issue.get("number")
        issue_node_id = issue.get("id")
        # Ensure issueType is a dictionary before accessing 'name'
        issue_type_info = issue.get("issueType")
        issue_type = issue_type_info.get("name") if isinstance(issue_type_info, dict) else None
        issue_state = issue.get("state")

        if issue_state != "OPEN" or issue_type not in ["Bug", "Story"]:
            continue

        print(f"\nProcessing Parent Issue #{issue_number} (Type: {issue_type}, ID: {issue_node_id})")
        processed_parents += 1

        parent_sprint_id = None
        parent_sprint_name = None
        current_sprint_field_id = None
        parent_project_item_node_id = None
        sprint_value_node_found = False

        project_items = issue.get("projectItems", {}).get("nodes", [])
        for item in project_items:
            if item and item.get("project", {}).get("id") == PROJECT_ID:
                parent_project_item_node_id = item.get("id")
                field_values = item.get("fieldValues", {}).get("nodes", [])
                for fv in field_values:
                    if fv and "iterationId" in fv and fv.get("field"): # iterationId implies it's a ProjectV2ItemFieldIterationValue
                        sprint_value_node_found = True
                        parent_sprint_id = fv.get("iterationId")
                        parent_sprint_name = fv.get("title")
                        current_sprint_field_id = fv.get("field", {}).get("id")
                        if discovered_sprint_field_id is None and current_sprint_field_id:
                            discovered_sprint_field_id = current_sprint_field_id
                            print(f"  Discovered Sprint Field ID: {discovered_sprint_field_id}")
                        print(f"  Parent Sprint Value Found: '{parent_sprint_name}' (ID: {parent_sprint_id}, FieldID: {current_sprint_field_id})")
                        break # Found sprint for this project item
                if sprint_value_node_found:
                    break # Found sprint for this parent in the target project

        final_sprint_field_id_to_use = None
        if parent_project_item_node_id: # Parent is in the target project
            if sprint_value_node_found: # And its sprint value node was found (even if sprint is null)
                final_sprint_field_id_to_use = current_sprint_field_id
            else: # Parent in project, but no sprint value node (sprint never set/field not present on item)
                print(f"  Parent issue #{issue_number} is in project {PROJECT_ID} but no Sprint iteration field value was found. Will use discovered Sprint Field ID if available to clear/set.")
                parent_sprint_id = None # Ensure this is None if no explicit sprint value node
                parent_sprint_name = None
                final_sprint_field_id_to_use = discovered_sprint_field_id
        else:
            print(f"  INFO: Parent issue #{issue_number} not found in project {PROJECT_ID}. Sub-issues cannot be synced to this project's sprints based on this parent.")
            continue # Skip to next parent issue

        if not final_sprint_field_id_to_use:
            print(f"  WARNING: Could not determine the Sprint Field ID for project {PROJECT_ID} needed for operations related to parent issue #{issue_number}. This might happen if no item in the project has ever had its Sprint field set. Skipping sub-issue sync for this parent.", file=sys.stderr)
            continue # Skip to next parent issue

        sub_issues_nodes = issue.get("subIssues", {}).get("nodes", [])
        if not sub_issues_nodes:
            print("  No sub-issues found for this parent.")
            continue
        
        print(f"  Found {len(sub_issues_nodes)} potential sub-issue(s). Processing using Field ID: {final_sprint_field_id_to_use}")

        for sub_issue_data in sub_issues_nodes:
            if not sub_issue_data: # Should not happen if GraphQL returns valid nodes
                continue

            sub_issue_node_id = sub_issue_data.get("id")
            sub_issue_number = sub_issue_data.get("number", "N/A")
            sub_issue_state = sub_issue_data.get("state")
            
            # Ensure sub_issue_type_info is a dictionary before accessing 'name'
            sub_issue_type_info = sub_issue_data.get("issueType")
            sub_issue_type = sub_issue_type_info.get("name") if isinstance(sub_issue_type_info, dict) else "Unknown"


            if sub_issue_state != "OPEN":
                print(f"    Skipping sub-issue #{sub_issue_number} as it is not OPEN (State: {sub_issue_state}).")
                continue

            if sub_issue_type != "Task":
                print(f"    Skipping sub-issue #{sub_issue_number} (Type: {sub_issue_type}). Not a 'Task'.")
                skipped_sub_issues_type += 1
                continue

            print(f"    Processing OPEN 'Task' sub-issue #{sub_issue_number} (Node ID: {sub_issue_node_id})")

            add_vars = {"projectId": PROJECT_ID, "contentId": sub_issue_node_id}
            add_data = graphql_request(ADD_TO_PROJECT_MUTATION, add_vars)

            if not add_data or not add_data.get("addProjectV2ItemById", {}).get("item"):
                print(f"    ERROR: Failed to add/find sub-issue #{sub_issue_number} in project {PROJECT_ID}. Skipping update.")
                skipped_sub_issues_error += 1
                continue
            
            sub_project_item_id = add_data["addProjectV2ItemById"]["item"]["id"]
            print(f"      Sub-issue Project Item ID: {sub_project_item_id}")

            if parent_sprint_id:
                print(f"      Updating Sprint to '{parent_sprint_name}' (ID: {parent_sprint_id})")
                update_vars = {
                    "projectId": PROJECT_ID,
                    "itemId": sub_project_item_id,
                    "fieldId": final_sprint_field_id_to_use,
                    "iterationId": parent_sprint_id
                }
                update_result = graphql_request(UPDATE_SPRINT_MUTATION, update_vars)
                if update_result:
                    updated_sub_issues += 1
                    print("        Update successful.")
                else:
                    print("        ERROR: Update failed.")
                    skipped_sub_issues_error += 1
            else:
                print(f"      Parent Sprint for issue #{issue_number} is empty/not set. Clearing Sprint for sub-issue #{sub_issue_number}.")
                clear_vars = {
                    "projectId": PROJECT_ID,
                    "itemId": sub_project_item_id,
                    "fieldId": final_sprint_field_id_to_use
                }
                clear_result = graphql_request(CLEAR_SPRINT_MUTATION, clear_vars)
                if clear_result:
                    cleared_sub_issues += 1
                    print("        Clear successful.")
                else:
                    print("        ERROR: Clear failed.")
                    skipped_sub_issues_error += 1
            
            time.sleep(0.2) # Slightly increased delay

    if has_next_page:
        print(f"Fetching next page of issues (cursor: {cursor})...")
        time.sleep(1) 
    else:
        print("All pages processed.")

print("\n--- Sync Summary ---")
print(f"Run initiated by user: {os.environ.get('GITHUB_ACTOR', 'Unknown')} at {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
print(f"Processed Parent Issues (Open Bug/Story): {processed_parents}")
print(f"Sub-issues Sprints Updated: {updated_sub_issues}")
print(f"Sub-issues Sprints Cleared: {cleared_sub_issues}")
print(f"Sub-issues Skipped (Type Mismatch): {skipped_sub_issues_type}")
print(f"Sub-issues Skipped (Errors during add/update): {skipped_sub_issues_error}")
print("Sprint synchronization complete.")
