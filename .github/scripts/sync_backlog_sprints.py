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

# Query to search for open issues and get necessary fields
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
        # Get project items to find the sprint field value for the target project
        projectItems(first: 10) {
          nodes {
            id # Project item ID
            project { id }
            # Get iteration field value (Sprint)
            fieldValues(first: 20) {
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
        subIssues(first: 50) {
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

# Mutation to add an issue to a project
ADD_TO_PROJECT_MUTATION = """
mutation AddItemToProject($projectId: ID!, $contentId: ID!) {
  addProjectV2ItemById(input: {projectId: $projectId, contentId: $contentId}) {
    item {
      id # Returns the Project Item ID
    }
  }
}
"""

# Mutation to update the iteration (Sprint) field
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

# Mutation to clear the iteration (Sprint) field
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
def graphql_request(query, variables=None):
    """Makes a GraphQL request and handles basic error checking."""
    try:
        response = requests.post(API_URL, headers=HEADERS, json={"query": query, "variables": variables or {}}, timeout=60)
        response.raise_for_status()
        data = response.json()
        if "errors" in data:
            print(f"GraphQL Error: {json.dumps(data['errors'])}", file=sys.stderr)
            # Decide if error is fatal or can be skipped
            # For now, return None to indicate potential failure
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

print(f"Starting Sprint sync for project {PROJECT_ID} in repo {REPO_OWNER}/{REPO_NAME}")
print("Fetching open issues...")

has_next_page = True
cursor = None
search_query = f"repo:{REPO_OWNER}/{REPO_NAME} is:open is:issue" # Search all open issues

while has_next_page:
    variables = {"searchQuery": search_query, "cursor": cursor}
    data = graphql_request(SEARCH_ISSUES_QUERY, variables)

    if not data or not data.get("search"):
        print("Error fetching issues or empty search result. Aborting.", file=sys.stderr)
        break # Exit loop on fetch error

    search_result = data["search"]
    issues = search_result.get("nodes", [])
    page_info = search_result.get("pageInfo", {})
    has_next_page = page_info.get("hasNextPage", False)
    cursor = page_info.get("endCursor")

    print(f"Processing batch of {len(issues)} issues...")

    for issue in issues:
        if not issue: continue # Skip if node is null

        issue_number = issue.get("number")
        issue_node_id = issue.get("id")
        issue_type = issue.get("issueType", {}).get("name")
        issue_state = issue.get("state") # Should always be OPEN due to search query

        # --- Filter 1: Parent Issue Type and State (redundant state check) ---
        if issue_state != "OPEN" or issue_type not in ["Bug", "Story"]:
            # print(f"Skipping issue #{issue_number} (Type: {issue_type}, State: {issue_state})")
            continue

        print(f"\nProcessing Parent Issue #{issue_number} (Type: {issue_type}, ID: {issue_node_id})")
        processed_parents += 1

        # --- Find Parent's Sprint in the target Project ---
        parent_sprint_id = None
        parent_sprint_name = None
        sprint_field_id = None
        parent_project_item_node_id = None # Project Item ID of the parent issue itself

        project_items = issue.get("projectItems", {}).get("nodes", [])
        for item in project_items:
            if item and item.get("project", {}).get("id") == PROJECT_ID:
                parent_project_item_node_id = item.get("id") # Found parent's item ID
                field_values = item.get("fieldValues", {}).get("nodes", [])
                for fv in field_values:
                    # Check if it's the iteration field value
                    if fv and "iterationId" in fv and fv.get("field"):
                        parent_sprint_id = fv.get("iterationId") # Can be None if cleared
                        parent_sprint_name = fv.get("title")
                        sprint_field_id = fv.get("field", {}).get("id")
                        print(f"  Parent Sprint Found: '{parent_sprint_name}' (ID: {parent_sprint_id}, FieldID: {sprint_field_id})")
                        break # Found the Sprint field for this project item
                break # Found the correct project item for the parent

        if not parent_project_item_node_id:
             print(f"  WARNING: Parent issue #{issue_number} not found in project {PROJECT_ID}. Skipping sub-issue sync for this parent.")
             continue # Cannot sync if parent isn't in the project

        if not sprint_field_id:
             print(f"  WARNING: Could not find the 'Sprint' (Iteration) field for parent issue #{issue_number} in project {PROJECT_ID}. Ensure the field exists and the token has permissions.")
             continue # Cannot sync without the field ID

        # --- Get Open Sub-issues ---
        sub_issues = issue.get("subIssues", {}).get("nodes", [])
        open_sub_issue_ids = [sub["id"] for sub in sub_issues if sub and sub.get("state") == "OPEN"]

        if not open_sub_issue_ids:
            print("  No open sub-issues found.")
            continue

        print(f"  Found {len(open_sub_issue_ids)} open sub-issue(s). Processing...")

        # --- Process Each Open Sub-issue ---
        for sub_issue_node_id in open_sub_issue_ids:
            print(f"    Processing sub-issue Node ID: {sub_issue_node_id}")

            # 1. Ensure sub-issue is in the project, get its Item ID
            add_vars = {"projectId": PROJECT_ID, "contentId": sub_issue_node_id}
            add_data = graphql_request(ADD_TO_PROJECT_MUTATION, add_vars)

            if not add_data or not add_data.get("addProjectV2ItemById", {}).get("item"):
                print(f"    ERROR: Failed to add/find sub-issue {sub_issue_node_id} in project {PROJECT_ID}. Skipping.")
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
                    "fieldId": sprint_field_id,
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
                    "fieldId": sprint_field_id
                }
                clear_result = graphql_request(CLEAR_SPRINT_MUTATION, clear_vars)
                if clear_result:
                    cleared_sub_issues += 1
                    print("        Clear successful.")
                else:
                    print("        ERROR: Clear failed.")
                    skipped_sub_issues += 1

            # Optional short delay to avoid secondary rate limits if processing many sub-issues rapidly
            time.sleep(0.1)

    if has_next_page:
        print(f"Fetching next page of issues (cursor: {cursor})...")
        time.sleep(1) # Delay between fetching pages
    else:
        print("All pages processed.")

print("\n--- Sync Summary ---")
print(f"Processed Parent Issues (Open Bug/Story): {processed_parents}")
print(f"Sub-issues Updated: {updated_sub_issues}")
print(f"Sub-issues Cleared: {cleared_sub_issues}")
print(f"Sub-issues Skipped (Errors): {skipped_sub_issues}")
print("Sprint synchronization complete.")
