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
TARGET_TEAM = os.environ.get("TARGET_TEAM", "ALL").strip() # Default to "ALL"
RUN_INITIATOR = os.environ.get("RUN_INITIATOR", "Unknown")
RUN_TIMESTAMP_UTC_ISO = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


API_URL = "https://api.github.com/graphql"
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
    "Accept": "application/json",
    "GraphQL-Features": "issue_types, sub_issues"
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
        projectItems(first: 10) { # For parent issue
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
            ... on Issue {
              id
              number
              state
              issueType { name }
              projectItems(first: 10) { # For sub-issue, to get its Team field
                nodes {
                  id # ProjectV2Item ID for the sub-issue
                  project { id } # Project this item is in
                  fieldValues(first: 20) {
                    nodes {
                      __typename
                      ... on ProjectV2ItemFieldSingleSelectValue {
                        name # This is the selected option's name, e.g., "Frontend Team"
                        optionId # ID of the selected option
                        field {
                          ... on ProjectV2SingleSelectField {
                            id # Field ID
                            name # Field name, e.g., "Team"
                          }
                        }
                      }
                    }
                  }
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
            for error in data['errors']:
                if "locations" in error and "message" in error:
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
skipped_sub_issues_team_mismatch = 0 # New counter
discovered_sprint_field_id = None

print(f"Starting Sprint sync for project {PROJECT_ID} in repo {REPO_OWNER}/{REPO_NAME}")
print(f"Run initiated by user: {RUN_INITIATOR} at {RUN_TIMESTAMP_UTC_ISO}")
print(f"Target Team for sub-issue sync: '{TARGET_TEAM}'")
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
        issue_type_info = issue.get("issueType")
        issue_type = issue_type_info.get("name") if isinstance(issue_type_info, dict) else None
        issue_state = issue.get("state")

        if issue_state != "OPEN" or issue_type not in ["Bug", "Story"]:
            continue

        print(f"\nProcessing Parent Issue #{issue_number} (Type: {issue_type}, ID: {issue_node_id})")
        processed_parents += 1

        parent_sprint_id = None
        parent_sprint_name = None
        current_sprint_field_id = None # Sprint field ID from parent's project item
        parent_project_item_node_id = None # Parent's item ID in the target project
        sprint_value_node_found = False # If parent had a sprint value node (even if null)

        project_items = issue.get("projectItems", {}).get("nodes", [])
        for item in project_items:
            if item and item.get("project", {}).get("id") == PROJECT_ID:
                parent_project_item_node_id = item.get("id")
                field_values = item.get("fieldValues", {}).get("nodes", [])
                for fv in field_values:
                    if fv and fv.get("__typename") == "ProjectV2ItemFieldIterationValue" and fv.get("field"):
                        sprint_value_node_found = True # A sprint field value exists for this item
                        parent_sprint_id = fv.get("iterationId") # Could be null if sprint is cleared
                        parent_sprint_name = fv.get("title")    # Could be null
                        current_sprint_field_id = fv.get("field", {}).get("id")
                        if discovered_sprint_field_id is None and current_sprint_field_id:
                            discovered_sprint_field_id = current_sprint_field_id
                            print(f"  Discovered Sprint Field ID from parent: {discovered_sprint_field_id}")
                        print(f"  Parent's Project Item ID: {parent_project_item_node_id}, Sprint: '{parent_sprint_name}' (ID: {parent_sprint_id}), FieldID: {current_sprint_field_id}")
                        break # Found sprint value for this project item
                if sprint_value_node_found: # Found the sprint value for the parent in the target project
                    break

        final_sprint_field_id_to_use = None
        if parent_project_item_node_id: # Parent is in the target project
            if sprint_value_node_found and current_sprint_field_id:
                final_sprint_field_id_to_use = current_sprint_field_id
            else: # Parent in project, but no sprint value node or field ID found. Use discovered.
                print(f"  Parent issue #{issue_number} is in project {PROJECT_ID} but its specific Sprint field or value node was not found. Will use globally discovered Sprint Field ID if available.")
                final_sprint_field_id_to_use = discovered_sprint_field_id
                # parent_sprint_id and parent_sprint_name remain as they were (None if not found)
        else:
            print(f"  INFO: Parent issue #{issue_number} not found in project {PROJECT_ID}. Sub-issues cannot be synced to this project's sprints based on this parent.")
            continue

        if not final_sprint_field_id_to_use:
            print(f"  WARNING: Could not determine the Sprint Field ID for project {PROJECT_ID} (operations for parent #{issue_number}). Ensure project has a Sprint field, and at least one item has had its Sprint set to discover the field ID. Skipping sub-issue sync for this parent.", file=sys.stderr)
            continue

        sub_issues_nodes = issue.get("subIssues", {}).get("nodes", [])
        if not sub_issues_nodes:
            print("  No sub-issues found for this parent.")
            continue
        
        print(f"  Found {len(sub_issues_nodes)} potential sub-issue(s). Processing using Sprint Field ID: {final_sprint_field_id_to_use}")

        for sub_issue_data in sub_issues_nodes:
            if not sub_issue_data:
                continue

            sub_issue_node_id = sub_issue_data.get("id")
            sub_issue_number = sub_issue_data.get("number", "N/A")
            sub_issue_state = sub_issue_data.get("state")
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

            # --- Team Filtering Logic ---
            perform_update_based_on_team = False
            if TARGET_TEAM.upper() == "ALL":
                perform_update_based_on_team = True
            else:
                sub_issue_actual_team_name = None
                # Find the "Team" field for the sub-issue within the target project
                sub_project_items_nodes = sub_issue_data.get("projectItems", {}).get("nodes", [])
                for item_node in sub_project_items_nodes:
                    # Check if this project item is for the *target project*
                    if item_node and item_node.get("project", {}).get("id") == PROJECT_ID:
                        field_values_nodes = item_node.get("fieldValues", {}).get("nodes", [])
                        for fv_node in field_values_nodes:
                            if fv_node and fv_node.get("__typename") == "ProjectV2ItemFieldSingleSelectValue" and \
                               fv_node.get("field", {}).get("name", "").lower() == "team": # Case-insensitive field name check
                                sub_issue_actual_team_name = fv_node.get("name") # This is the selected team name
                                break # Found Team field for this project item
                        if sub_issue_actual_team_name: # If team found in this project item, no need to check others
                            break 
                
                if sub_issue_actual_team_name and sub_issue_actual_team_name.lower() == TARGET_TEAM.lower():
                    perform_update_based_on_team = True
                    print(f"      Sub-issue #{sub_issue_number} Team '{sub_issue_actual_team_name}' matches Target Team '{TARGET_TEAM}'.")
                else:
                    print(f"      Skipping sub-issue #{sub_issue_number}. Team '{sub_issue_actual_team_name if sub_issue_actual_team_name else 'Not Set or Not in Project'}' does not match Target Team '{TARGET_TEAM}'.")
                    skipped_sub_issues_team_mismatch += 1
            
            if not perform_update_based_on_team:
                continue # Skip to the next sub-issue

            # --- Add sub-issue to project (if not already there) and get its project item ID ---
            add_vars = {"projectId": PROJECT_ID, "contentId": sub_issue_node_id}
            add_data = graphql_request(ADD_TO_PROJECT_MUTATION, add_vars)

            if not add_data or not add_data.get("addProjectV2ItemById", {}).get("item"):
                print(f"    ERROR: Failed to add/find sub-issue #{sub_issue_number} in project {PROJECT_ID}. Skipping update.")
                skipped_sub_issues_error += 1
                continue
            
            sub_project_item_id = add_data["addProjectV2ItemById"]["item"]["id"]
            print(f"      Sub-issue Project Item ID: {sub_project_item_id}")

            # --- Update or Clear Sprint based on parent ---
            if parent_sprint_id: # Parent has a specific sprint set
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
            else: # Parent's sprint is not set (or parent not in project with sprint)
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
            
            time.sleep(0.2)

    if has_next_page:
        print(f"Fetching next page of issues (cursor: {cursor})...")
        time.sleep(1) 
    else:
        print("All pages processed.")

print("\n--- Sync Summary ---")
print(f"Run initiated by user: {RUN_INITIATOR} at {RUN_TIMESTAMP_UTC_ISO}")
print(f"Target Team: '{TARGET_TEAM}'")
print(f"Processed Parent Issues (Open Bug/Story): {processed_parents}")
print(f"Sub-issues Sprints Updated: {updated_sub_issues}")
print(f"Sub-issues Sprints Cleared: {cleared_sub_issues}")
print(f"Sub-issues Skipped (Type Mismatch): {skipped_sub_issues_type}")
print(f"Sub-issues Skipped (Team Mismatch): {skipped_sub_issues_team_mismatch}")
print(f"Sub-issues Skipped (Errors during add/update): {skipped_sub_issues_error}")
print("Sprint synchronization complete.")

