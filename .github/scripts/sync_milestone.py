import os
import requests
import json
import sys
import time

# --- Configuration ---
TOKEN = os.environ.get("GITHUB_TOKEN")
PROJECT_ID = os.environ.get("PROJECT_ID") # ProjectV2 Node ID
REPO_OWNER = os.environ.get("REPO_OWNER")
REPO_NAME = os.environ.get("REPO_NAME")
PARENT_ISSUE_NODE_ID = os.environ.get("PARENT_ISSUE_NODE_ID")
PARENT_MILESTONE_NUMBER = os.environ.get("PARENT_MILESTONE_NUMBER") # String representation or empty string
GRAPHQL_API_URL = "https://api.github.com/graphql"
REST_API_URL_BASE = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}"
HEADERS_GRAPHQL = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
    "Accept": "application/json",
    # Required headers for specific features
    "GraphQL-Features": "issue_types, sub_issues"
}
HEADERS_REST = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github.v3+json",
    "X-GitHub-Api-Version": "2022-11-28"
}
# --- Allowed Parent Issue Types ---
ALLOWED_PARENT_TYPES = ["Bug", "Story", "Feature"]

# --- Validate Environment Variables ---
# (Token, Project ID, Owner, Repo checks remain the same)
if not TOKEN:
    print("Error: GITHUB_TOKEN environment variable not set.", file=sys.stderr)
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
if not PARENT_ISSUE_NODE_ID:
    print("Error: PARENT_ISSUE_NODE_ID environment variable not set.", file=sys.stderr)
    sys.exit(1)

# --- MODIFIED: Validate PARENT_MILESTONE_NUMBER ---
if PARENT_MILESTONE_NUMBER is None:
    # Handles case where env var might be truly absent (unlikely with current YAML)
    print("Warning: PARENT_MILESTONE_NUMBER environment variable was not found. Assuming unmilestoned.", file=sys.stderr)
    PARENT_MILESTONE_NUMBER = "" # Treat as empty string for consistent handling
elif PARENT_MILESTONE_NUMBER == "":
    # This is the expected path for the 'unmilestoned' event trigger
    print("Info: PARENT_MILESTONE_NUMBER is empty (unmilestoned event).")
    # Let the script proceed
elif not PARENT_MILESTONE_NUMBER.isdigit():
    # This catches non-empty strings that aren't valid numbers
    print(f"Error: PARENT_MILESTONE_NUMBER ('{PARENT_MILESTONE_NUMBER}') is not a valid digit sequence.", file=sys.stderr)
    sys.exit(1)
# If it's a digit string, validation passes silently.


# --- GraphQL Query and Mutation ---
# (No changes needed here)
GET_PARENT_TYPE_AND_SUBISSUES_QUERY = """
query GetParentTypeAndSubIssues($parentId: ID!) {
  node(id: $parentId) {
    ... on Issue {
      issueType { name }
      subIssues(first: 100) { # Fetch up to 100 sub-issues
        nodes {
          id     # Sub-issue Node ID
          number # Sub-issue Number
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

# --- Helper Functions ---
# (No changes needed here)
def graphql_request(query, variables=None):
    """Makes a GraphQL request and handles basic error checking."""
    try:
        response = requests.post(GRAPHQL_API_URL, headers=HEADERS_GRAPHQL, json={"query": query, "variables": variables or {}}, timeout=30)
        response.raise_for_status()
        data = response.json()
        if "errors" in data:
            print(f"GraphQL Error: {json.dumps(data['errors'])}", file=sys.stderr)
            return None
        return data.get("data")
    except requests.exceptions.RequestException as e:
        print(f"GraphQL Request failed: {e}", file=sys.stderr)
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
             print(f"Warning: REST PATCH request to {url} returned status {response.status_code}. Response: {response.text[:200]}...", file=sys.stderr)
             return False
        response.raise_for_status()
        print(f"  REST PATCH to {url} successful (Status: {response.status_code})")
        return True
    except requests.exceptions.RequestException as e:
        print(f"REST PATCH request to {url} failed: {e}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"An unexpected error occurred during REST PATCH request: {e}", file=sys.stderr)
        return False


# --- Main Logic ---
print("Starting milestone sync process...")
print(f"Parent Issue Node ID: {PARENT_ISSUE_NODE_ID}")
# Use the (potentially modified) PARENT_MILESTONE_NUMBER for logging
print(f"Parent Milestone Number: {PARENT_MILESTONE_NUMBER if PARENT_MILESTONE_NUMBER else 'None (Unmilestoned)'}")
print(f"Target Project ID: {PROJECT_ID}")
print(f"Allowed Parent Types: {ALLOWED_PARENT_TYPES}")

# 1. Get Parent Type and Sub-issues
print("Fetching parent issue type and sub-issues...")
gql_vars = {"parentId": PARENT_ISSUE_NODE_ID}
gql_data = graphql_request(GET_PARENT_TYPE_AND_SUBISSUES_QUERY, gql_vars)

if not gql_data or not gql_data.get("node"):
    print("Error: Failed to fetch parent issue data via GraphQL. Exiting.", file=sys.stderr)
    sys.exit(1)

parent_data = gql_data["node"]
parent_type = parent_data.get("issueType", {}).get("name")
sub_issues = parent_data.get("subIssues", {}).get("nodes", [])

print(f"Parent Issue Type: {parent_type}")

# 2. Check Parent Type
if not parent_type or parent_type not in ALLOWED_PARENT_TYPES:
    print(f"Parent issue type '{parent_type}' is not in the allowed list ({ALLOWED_PARENT_TYPES}). Skipping sync.")
    sys.exit(0)

# 3. Check for Sub-issues
if not sub_issues:
    print("No sub-issues found for the parent issue. Exiting.")
    sys.exit(0)

print(f"Found {len(sub_issues)} sub-issue(s). Processing...")

# 4. Process Sub-issues
updated_count = 0
project_added_count = 0 # Note: This count isn't accurately tracked currently
error_count = 0

# --- MODIFIED: Determine milestone value for REST API ---
# Treat empty string the same as None for the purpose of clearing the milestone
# Send integer if it's a valid digit string, otherwise send null
milestone_payload_value = int(PARENT_MILESTONE_NUMBER) if PARENT_MILESTONE_NUMBER and PARENT_MILESTONE_NUMBER.isdigit() else None

print(f"Determined Milestone Payload for Sub-issues: {milestone_payload_value}") # Added log

for sub in sub_issues:
    sub_issue_node_id = sub.get("id")
    sub_issue_number = sub.get("number")

    if not sub_issue_node_id or not sub_issue_number:
        print("Warning: Skipping sub-issue with missing ID or number.", file=sys.stderr)
        error_count += 1
        continue

    print(f"\nProcessing sub-issue #{sub_issue_number} (Node ID: {sub_issue_node_id})")

    # a. Update Milestone via REST API
    print(f"  Setting milestone to: {milestone_payload_value}")
    rest_endpoint = f"/issues/{sub_issue_number}"
    rest_payload = {"milestone": milestone_payload_value} # Use the determined value
    if rest_patch_request(rest_endpoint, rest_payload):
        updated_count += 1
    else:
        print(f"  Failed to update milestone for sub-issue #{sub_issue_number}.")
        error_count += 1
        # Continue to next step even if milestone update fails

    # b. Add to Project via GraphQL API
    # (This part remains unchanged, may still show warnings if token lacks permission)
    print(f"  Ensuring sub-issue is in project {PROJECT_ID}...")
    add_vars = {"projectId": PROJECT_ID, "contentId": sub_issue_node_id}
    add_data = graphql_request(ADD_TO_PROJECT_MUTATION, add_vars)
    if add_data and add_data.get("addProjectV2ItemById", {}).get("item"):
        print(f"    Successfully added/confirmed sub-issue #{sub_issue_number} in project.")
    else:
        print(f"    Warning: Failed to add/confirm sub-issue #{sub_issue_number} in project {PROJECT_ID}.")

    time.sleep(0.1) # Small delay between processing sub-issues

# --- Summary ---
# (Summary print statements remain the same)
print("\n--- Milestone Sync Summary ---")
print(f"Processed Parent Issue Type: {parent_type}")
print(f"Sub-issues Found: {len(sub_issues)}")
print(f"Sub-issues Milestone Update Attempted/Succeeded: {updated_count}")
print(f"Sub-issues Add-to-Project Attempted (Success/Already Present): {len(sub_issues)}") # Still an approximation
print(f"Errors during processing (Milestone Update): {error_count}")
print("Milestone synchronization complete.")

if error_count > 0:
    sys.exit(1) # Exit with error code if any milestone updates failed
