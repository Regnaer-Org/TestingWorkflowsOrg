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
  search(query: $searchQuery, type: ISSUE, first: 50, after: $cursor) { # Number of parent issues per page
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
        projectItems(first: 5) { # For parent issue's project items
          nodes {
            id # ProjectV2Item ID
            project {
              id
              title # For logging
            }
            fieldValues(first: 15) { # For parent's sprint field
              nodes {
                __typename # Crucial for identifying field type
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
                # We might want to log other field types too for debugging
                ... on ProjectV2ItemFieldSingleSelectValue {
                  name # Option name
                  field { ... on ProjectV2SingleSelectField { id name } }
                }
                ... on ProjectV2ItemFieldTextValue {
                  text
                  field { ... on ProjectV2Field { id name } }
                }
              }
            }
          }
        }
        subIssues(first: 25) { # Number of sub-issues per parent
          nodes {
            ... on Issue {
              id
              number
              state
              issueType { name }
              projectItems(first: 5) { # For sub-issue's project items
                nodes {
                  id
                  project { id title }
                  fieldValues(first: 15) { # For sub-issue's team field
                    nodes {
                      __typename
                      ... on ProjectV2ItemFieldSingleSelectValue {
                        name
                        optionId
                        field {
                          ... on ProjectV2SingleSelectField {
                            id
                            name
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
            for error_detail in data['errors']: # Renamed from 'error' to 'error_detail'
                if "locations" in error_detail and "message" in error_detail:
                     print(f"  Message: {error_detail['message']}")
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
skipped_sub_issues_team_mismatch = 0
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

        print(f"\nProcessing Parent Issue #{issue_number} (Type: {issue_type}, NodeID: {issue_node_id})")
        processed_parents += 1

        parent_sprint_id = None
        parent_sprint_name = None
        current_sprint_field_id = None # Specific to the iteration field found on current parent
        parent_project_item_node_id = None # Item ID of the parent in the target project
        sprint_value_node_found_for_current_parent = False # Reset for each parent

        # --- DETAILED LOGGING FOR PARENT'S PROJECT ITEMS AND FIELDS ---
        print(f"  Parent Issue #{issue_number} - Examining its projectItems (max {SEARCH_ISSUES_QUERY.count('projectItems(first: 5)')*5} items):")
        parent_project_items_data = issue.get("projectItems", {}).get("nodes", [])
        if not parent_project_items_data:
            print(f"    No projectItems nodes found for parent #{issue_number}.")
        
        for item_idx, item_data in enumerate(parent_project_items_data):
            if not item_data:
                print(f"    ProjectItem {item_idx}: null")
                continue

            item_project_details = item_data.get("project", {})
            item_project_id = item_project_details.get("id")
            item_project_title = item_project_details.get("title", "N/A")
            item_node_id = item_data.get("id") # This is the ProjectV2Item ID

            print(f"    Item {item_idx} (NodeID: {item_node_id}): ProjectID='{item_project_id}', ProjectTitle='{item_project_title}'")

            if item_project_id == PROJECT_ID:
                print(f"      >>> This item is in TARGET PROJECT ({PROJECT_ID}). Examining its fieldValues (max {SEARCH_ISSUES_QUERY.count('fieldValues(first: 15)')*15} values):")
                parent_project_item_node_id = item_node_id # Found the parent's item in the target project

                field_values_data = item_data.get("fieldValues", {}).get("nodes", [])
                if not field_values_data:
                    print(f"        No fieldValues nodes found for this item in the target project.")
                
                for fv_idx, fv_data in enumerate(field_values_data):
                    if not fv_data:
                        print(f"        FV {fv_idx}: null")
                        continue
                    
                    fv_typename = fv_data.get("__typename")
                    fv_field_details = fv_data.get("field", {})
                    fv_field_name = fv_field_details.get("name", "N/A") if fv_field_details else "N/A"
                    fv_field_id = fv_field_details.get("id", "N/A") if fv_field_details else "N/A"
                    
                    # Log basic info for all fields
                    print(f"        FV {fv_idx}: Type='{fv_typename}', FieldName='{fv_field_name}', FieldID='{fv_field_id}'")

                    if fv_typename == "ProjectV2ItemFieldIterationValue":
                        sprint_value_node_found_for_current_parent = True
                        parent_sprint_id = fv_data.get("iterationId")
                        parent_sprint_name = fv_data.get("title")
                        current_sprint_field_id = fv_field_id # Use the ID from the actual field node
                        print(f"          FOUND ITERATION: Name='{parent_sprint_name}', IterationNodeID='{parent_sprint_id}', FieldID='{current_sprint_field_id}'")
                        
                        if discovered_sprint_field_id is None and current_sprint_field_id != "N/A":
                            discovered_sprint_field_id = current_sprint_field_id
                            print(f"            >>> Globally Discovered Sprint Field ID set to: {discovered_sprint_field_id}")
                        break # Found the iteration field for this project item
                
                if sprint_value_node_found_for_current_parent:
                    print(f"      Iteration field value processing complete for this item in target project.")
                    break # Found parent in target project and processed its iteration field
                else:
                    print(f"      No Iteration field value found for this item in target project after checking all its fieldValues.")
            else:
                print(f"      This item is NOT in the target project.")
        # --- END OF DETAILED LOGGING ---

        final_sprint_field_id_to_use = None
        if parent_project_item_node_id: # If parent was found in the target project
            if sprint_value_node_found_for_current_parent and current_sprint_field_id and current_sprint_field_id != "N/A":
                final_sprint_field_id_to_use = current_sprint_field_id
                print(f"  Using Sprint Field ID from current parent: {final_sprint_field_id_to_use}")
            elif discovered_sprint_field_id: # Fallback to globally discovered ID
                final_sprint_field_id_to_use = discovered_sprint_field_id
                print(f"  Using GLOBALLY discovered Sprint Field ID: {final_sprint_field_id_to_use} (Parent #{issue_number} either had no sprint set or its field ID was not found directly).")
            else:
                print(f"  Parent issue #{issue_number} is in project {PROJECT_ID}, but no Sprint Field ID could be determined (neither directly nor globally).")
        else:
            print(f"  INFO: Parent issue #{issue_number} was NOT found in project {PROJECT_ID}. Sub-issues cannot be synced based on this parent.")
            continue

        if not final_sprint_field_id_to_use:
            print(f"  WARNING: Could not determine the Sprint Field ID for project {PROJECT_ID} to use for operations related to parent #{issue_number}. Skipping sub-issue sync for this parent.", file=sys.stderr)
            continue
        
        # ... (rest of the sub-issue processing logic remains the same) ...
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

            perform_update_based_on_team = False
            if TARGET_TEAM.upper() == "ALL":
                perform_update_based_on_team = True
            else:
                sub_issue_actual_team_name = None
                sub_project_items_nodes = sub_issue_data.get("projectItems", {}).get("nodes", [])
                for item_node in sub_project_items_nodes:
                    if item_node and item_node.get("project", {}).get("id") == PROJECT_ID:
                        field_values_nodes = item_node.get("fieldValues", {}).get("nodes", [])
                        for fv_node in field_values_nodes:
                            if fv_node and fv_node.get("__typename") == "ProjectV2ItemFieldSingleSelectValue" and \
                               fv_node.get("field", {}).get("name", "").lower() == "team":
                                sub_issue_actual_team_name = fv_node.get("name")
                                break
                        if sub_issue_actual_team_name:
                            break 
                
                if sub_issue_actual_team_name and sub_issue_actual_team_name.lower() == TARGET_TEAM.lower():
                    perform_update_based_on_team = True
                    print(f"      Sub-issue #{sub_issue_number} Team '{sub_issue_actual_team_name}' matches Target Team '{TARGET_TEAM}'.")
                else:
                    print(f"      Skipping sub-issue #{sub_issue_number}. Team '{sub_issue_actual_team_name if sub_issue_actual_team_name else 'Not Set or Not in Project'}' does not match Target Team '{TARGET_TEAM}'.")
                    skipped_sub_issues_team_mismatch += 1
            
            if not perform_update_based_on_team:
                continue

            add_vars = {"projectId": PROJECT_ID, "contentId": sub_issue_node_id}
            add_data = graphql_request(ADD_TO_PROJECT_MUTATION, add_vars)

            if not add_data or not add_data.get("addProjectV2ItemById", {}).get("item"):
                print(f"    ERROR: Failed to add/find sub-issue #{sub_issue_number} in project {PROJECT_ID}. Skipping update.")
                skipped_sub_issues_error += 1
                continue
            
            sub_project_item_id = add_data["addProjectV2ItemById"]["item"]["id"]
            print(f"      Sub-issue Project Item ID: {sub_project_item_id}")

            if parent_sprint_id: # This relies on parent_sprint_id being correctly set when sprint_value_node_found_for_current_parent is true
                print(f"      Updating Sprint to '{parent_sprint_name}' (ID: {parent_sprint_id}) for sub-issue #{sub_issue_number}")
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
            else: # Parent's sprint is not set (parent_sprint_id is None)
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
            
            time.sleep(0.2) # Be mindful of rate limits

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
