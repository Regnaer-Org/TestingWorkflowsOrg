import os
import requests
import json
import sys
import time

# --- Configuration ---
TOKEN = os.environ.get("GITHUB_TOKEN")
PROJECT_ID = os.environ.get("PROJECT_ID")  # ProjectV2 Node ID (e.g., from vars)
REPO_OWNER = os.environ.get("REPO_OWNER")
REPO_NAME = os.environ.get("REPO_NAME")
NEW_ISSUE_NODE_ID = os.environ.get("NEW_ISSUE_NODE_ID")  # The triggering issue
NEW_ISSUE_NUMBER = os.environ.get("NEW_ISSUE_NUMBER")  # The triggering issue number

# --- API Setup ---
GRAPHQL_API_URL = "https://api.github.com/graphql"
REST_API_URL_BASE = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}"
HEADERS_GRAPHQL = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
    "Accept": "application/json",
    "GraphQL-Features": "sub_issues"  # Ensure sub_issues feature is enabled
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
    sys.exit(1)

try:
    NEW_ISSUE_NUMBER = int(NEW_ISSUE_NUMBER)
except ValueError:
    print(f"Error: NEW_ISSUE_NUMBER ('{NEW_ISSUE_NUMBER}') is not a valid integer.", file=sys.stderr)
    sys.exit(1)


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


def rest_patch_request(endpoint, payload):
    """Makes a REST PATCH request."""
    url = f"{REST_API_URL_BASE}{endpoint}"
    try:
        response = requests.patch(url, headers=HEADERS_REST, json=payload, timeout=30)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        print(f"REST PATCH request to {url} failed: {e}", file=sys.stderr)
        return False


# --- Main Logic ---
print("Starting field inheritance process...")
print(f"Processing new issue: #{NEW_ISSUE_NUMBER} (Node ID: {NEW_ISSUE_NODE_ID})")
print(f"Target Project ID: {PROJECT_ID}")

# Query to get parent issue information
GET_PARENT_INFO_QUERY = """
query GetParentInfo($issueId: ID!) {
  node(id: $issueId) {
    ... on Issue {
      parent {
        id
        number
        milestone { number }
        labels(first: 100) { nodes { name } }
      }
    }
  }
}
"""

# Fetch parent issue information
parent_data = graphql_request(GET_PARENT_INFO_QUERY, {"issueId": NEW_ISSUE_NODE_ID})

if not parent_data or not parent_data.get("node", {}).get("parent"):
    print("No parent issue found or failed to fetch data. Exiting.")
    sys.exit(0)

parent_info = parent_data["node"]["parent"]
parent_milestone_number = parent_info.get("milestone", {}).get("number")
parent_labels = [label["name"] for label in parent_info.get("labels", {}).get("nodes", [])]

# Inherit Milestone (REST)
if parent_milestone_number is not None:
    print(f"Inheriting milestone: {parent_milestone_number}")
    payload = {"milestone": parent_milestone_number}
    if not rest_patch_request(f"/issues/{NEW_ISSUE_NUMBER}", payload):
        print(f"Warning: Failed to set milestone on issue #{NEW_ISSUE_NUMBER}.")
else:
    print("Parent has no milestone to inherit.")

# Inherit Labels (REST)
if parent_labels:
    print(f"Inheriting labels: {', '.join(parent_labels)}")
    payload = {"labels": parent_labels}
    if not rest_patch_request(f"/issues/{NEW_ISSUE_NUMBER}", payload):
        print(f"Warning: Failed to set labels on issue #{NEW_ISSUE_NUMBER}.")
else:
    print("Parent has no labels to inherit.")

print("Field inheritance process complete.")
