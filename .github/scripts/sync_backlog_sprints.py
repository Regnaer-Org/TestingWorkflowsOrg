import os
import requests
import json
import sys
import time

# --- Configuration ---
TOKEN = os.environ.get("MILESTONE_SYNC_TOKEN")
PROJECT_ID = os.environ.get("PROJECT_ID") # ProjectV2 Node ID (e.g., PVT_...)
REPO_OWNER = os.environ.get("REPO_OWNER")
REPO_NAME = os.environ.get("REPO_NAME")
API_URL = "https://api.github.com/graphql"
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
    "Accept": "application/json",
    # Required headers for specific features
    "GraphQL-Features": "issue_types, sub_issues"
}

# --- Validate Environment Variables ---
# (No changes needed here)
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
# (No changes needed here)
SEARCH_ISSUES_QUERY = """
query SearchOpenIssues($searchQuery: String!, $cursor: String) {
  search(query: $searchQuery, type: ISSUE, first: 50, after: $cursor) { # Fetch parents in batches of 50
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
        # Get project items to find the sprint field value for the target project
        projectItems(first: 10) { # Assume parent issue is in < 10 projects
          nodes {
            id # Project item ID
            project { id }
            # Get iteration field value (Sprint)
            fieldValues(first: 20) { # Assume < 20 fields per project item
              nodes {
                ... on ProjectV2ItemFieldIterationValue {
                  iterationId
                  title
                  field {
                    ... on ProjectV2IterationField {
                      id # Sprint Field ID
                      name
                    }
                  }
                }
              }
            }
          }
        }
        # Get sub-issues
        subIssues(first: 50) { # Fetch up to 50 sub-issues (sufficient based on user info)
          nodes {
            id # Sub-issue Node ID
            number
            state
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
      id # Returns the Project Item ID
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
    projectV2Item { id } # Confirmation
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
    projectV2Item { id } # Confirmation
  }
}
"""

# --- Helper Function for GraphQL Requests ---
# (No changes needed here)
def graphql_request(query, variables=None):
    """Makes a GraphQL request and handles basic error checking."""
    try:
        response = requests.post(API_URL, headers=HEADERS, json={"query": query, "variables": variables or {}}, timeout=60)
        response.raise_for_status()
        data = response.json()
        if "errors" in data:
            print(f"GraphQL Error: {json.dumps(data['errors'])}", file=sys.stderr)
            return None
        return data.get("data")
    except requests.exceptions.RequestException as e:
        print(f"HTTP Request failed: {e}", file=sys.stderr)
        if 'response' in locals() and response is not None:
            print(f"Response Status: {response.status_code}", file=sys.stderr)
            print(f"Response Body: {response.text[:500]}...", file=sys.stderr)
        return None
    except Exception as e:
        print(f"An unexpected error occurred during GraphQL request: {e}", file=sys.stderr)
        return None

# --- Main Logic ---
processed_parents = 0
updated_sub_issues = 0
cleared_sub_issues = 0
skipped_sub_issues = 0
# ** NEW: Variable to store the discovered Sprint Field ID **
discovered_sprint_field_id = None

print(f"Starting Sprint sync for project {PROJECT_ID} in repo {REPO_OWNER}/{REPO_NAME}")
print(f"Run initiated by user: {os.environ.get('GITHUB_ACTOR', 'Unknown')}")
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
        if not issue: continue

        issue_number = issue.get("number")
        issue_node_id = issue.get("id")
        issue_type = issue.get("issueType", {}).get("name")
        issue_state = issue.get("state")

        if issue_state != "OPEN" or issue_type not in ["Bug", "Story"]:
            continue

        print(f"\nProcessing Parent Issue #{issue_number} (Type: {issue_type}, ID: {issue_node_id})")
        processed_parents += 1

        # --- Find Parent's Sprint in the target Project ---
        parent_sprint_id = None
        parent_sprint_name = None
        # ** MODIFIED: Use a local variable first **
        current_sprint_field_id = None
        parent_project_item_node_id = None
        sprint_value_node_found = False # Flag to check if we found the specific value node

        project_items = issue.get("projectItems", {}).get("nodes", [])
        for item in project_items:
            if item and item.get("project", {}).get("id") == PROJECT_ID:
                parent_project_item_node_id = item.get("id")
                field_values = item.get("fieldValues", {}).get("nodes", [])
                for fv in field_values:
                    if fv and "iterationId" in fv and fv.get("field"):
                        # Found the Sprint Iteration Value node
                        sprint_value_node_found = True
                        parent_sprint_id = fv.get("iterationId") # Might be null if set then cleared, but node exists
                        parent_sprint_name = fv.get("title")
                        current_sprint_field_id = fv.get("field", {}).get("id")

                        # ** NEW: Learn the Sprint Field ID if we haven't already **
                        if discovered_sprint_field_id is None and current_sprint_field_id:
                            discovered_sprint_field_id = current_sprint_field_id
                            print(f"  Discovered Sprint Field ID: {discovered_sprint_field_id}")

                        print(f"  Parent Sprint Value Found: '{parent_sprint_name}' (ID: {parent_sprint_id}, FieldID: {current_sprint_field_id})")
                        break # Found the Sprint value node, no need to check other fields
                # ** MODIFIED: Only break outer loop if we found the value node **
                if sprint_value_node_found:
                    break # Found the value node in the correct project item

        # --- Determine Sprint status and required Field ID ---
        # ** NEW: Logic to handle cases where the value node wasn't found **
        final_sprint_field_id_to_use = None
        if parent_project_item_node_id:
            if sprint_value_node_found:
                # We found the value node, use the ID from it
                final_sprint_field_id_to_use = current_sprint_field_id
            else:
                # Parent is in project, but value node wasn't found. Assume Sprint is empty.
                print(f"  Parent Sprint Value Node not found (likely empty). Assuming Sprint is empty.")
                parent_sprint_id = None # Ensure it's None
                parent_sprint_name = None
                # Use the globally discovered ID if available
                final_sprint_field_id_to_use = discovered_sprint_field_id
        else:
            # Parent issue is not in the target project at all
             print(f"  WARNING: Parent issue #{issue_number} not found in project {PROJECT_ID}. Skipping sub-issue sync.")
             continue # Skip to next parent issue

        # ** NEW: Check if we have a Field ID to work with **
        if not final_sprint_field_id_to_use:
            print(f"  WARNING: Could not determine the Sprint Field ID for project {PROJECT_ID} needed for issue #{issue_number}. Ensure at least one item in the project has had its Sprint field set at some point, or manually provide the Field ID.")
            continue # Skip processing sub-issues for this parent

        # --- Get Open Sub-issues ---
        sub_issues = issue.get("subIssues", {}).get("nodes", [])
        open_sub_issues_data = [
             {"id": sub["id"], "number": sub.get("number", "N/A")}
             for sub in sub_issues if sub and sub.get("state") == "OPEN"
        ]

        if not open_sub_issues_data:
            print("  No open sub-issues found.")
            continue

        print(f"  Found {len(open_sub_issues_data)} open sub-issue(s). Processing using Field ID: {final_sprint_field_id_to_use}")

        # --- Process Each Open Sub-issue ---
        for sub_data in open_sub_issues_data:
            sub_issue_node_id = sub_data["id"]
            sub_issue_number = sub_data["number"]
            print(f"    Processing sub-issue #{sub_issue_number} (Node ID: {sub_issue_node_id})")

            # 1. Ensure sub-issue is in the project, get its Item ID
            add_vars = {"projectId": PROJECT_ID, "contentId": sub_issue_node_id}
            add_data = graphql_request(ADD_TO_PROJECT_MUTATION, add_vars)

            if not add_data or not add_data.get("addProjectV2ItemById", {}).get("item"):
                print(f"    ERROR: Failed to add/find sub-issue #{sub_issue_number} in project {PROJECT_ID}. Skipping.")
                skipped_sub_issues += 1
                continue

            sub_project_item_id = add_data["addProjectV2ItemById"]["item"]["id"]
            print(f"      Sub-issue Project Item ID: {sub_project_item_id}")

            # 2. Update or Clear Sprint based on parent
            if parent_sprint_id:
                # Update Sprint
                print(f"      Updating Sprint to '{parent_sprint_name}' ({parent_sprint_id})")
                update_vars = {
                    "projectId": PROJECT_ID,
                    "itemId": sub_project_item_id,
                    "fieldId": final_sprint_field_id_to_use, # Use the determined ID
                    "iterationId": parent_sprint_id
                }
                update_result = graphql_request(UPDATE_SPRINT_MUTATION, update_vars)
                if update_result:
                    updated_sub_issues += 1
                    print("        Update successful.")
                else:
                    print("        ERROR: Update failed.")
                    skipped_sub_issues += 1
            else:
                # Clear Sprint
                print("      Parent Sprint is empty. Clearing Sprint.")
                clear_vars = {
                    "projectId": PROJECT_ID,
                    "itemId": sub_project_item_id,
                    "fieldId": final_sprint_field_id_to_use # Use the determined ID
                }
                clear_result = graphql_request(CLEAR_SPRINT_MUTATION, clear_vars)
                if clear_result:
                    cleared_sub_issues += 1
                    print("        Clear successful.")
                else:
                    print("        ERROR: Clear failed.")
                    skipped_sub_issues += 1

            time.sleep(0.1) # 100ms delay between processing each sub-issue

    if has_next_page:
        print(f"Fetching next page of issues (cursor: {cursor})...")
        time.sleep(1) # 1 second delay between fetching pages of parent issues
    else:
        print("All pages processed.")

# --- Print Summary ---
# (No changes needed here)
print("\n--- Sync Summary ---")
print(f"Run initiated by user: {os.environ.get('GITHUB_ACTOR', 'Unknown')}")
print(f"Processed Parent Issues (Open Bug/Story): {processed_parents}")
print(f"Sub-issues Updated: {updated_sub_issues}")
print(f"Sub-issues Cleared: {cleared_sub_issues}")
print(f"Sub-issues Skipped (Errors): {skipped_sub_issues}")
print("Sprint synchronization complete.")
