import requests
import csv
import os
import sys

# Replace this with your Personal Access Token
GITHUB_PAT = "YOUR_PERSONAL_ACCESS_TOKEN"  # <-- Add your PAT here
PROJECT_ID = "PVT_kwDODH0FwM4A3yi4"  # Replace with your Project ID

# Output file paths
desktop = os.path.join(os.path.expanduser("~"), "Desktop")
OUTPUT_CSV = os.path.join(desktop, "output.csv")
OUTPUT_META = os.path.join(desktop, "field_metadata.csv")


def fetch_project_fields(project_id, token):
    """Fetch all fields from a GitHub ProjectV2."""
    query = '''
    query($project: ID!, $cursor: String) {
      node(id: $project) {
        ... on ProjectV2 {
          fields(first: 100, after: $cursor) {
            nodes {
              id
              name
              dataType
              ... on ProjectV2SingleSelectField {
                options {
                  id
                  name
                  description
                  color
                }
              }
              ... on ProjectV2IterationField {
                configuration {
                  iterations {
                    id
                    title
                    startDate
                    duration
                  }
                }
              }
            }
            pageInfo { endCursor hasNextPage }
          }
        }
      }
    }
    '''
    fields = []
    cursor = None
    while True:
        variables = {"project": project_id, "cursor": cursor}
        resp = requests.post(
            "https://api.github.com/graphql",
            json={"query": query, "variables": variables},
            headers={"Authorization": f"Bearer {token}"}
        )
        resp.raise_for_status()
        data = resp.json()
        if "errors" in data:
            print("GraphQL API error:", data["errors"], file=sys.stderr)
            sys.exit(1)
        if "data" not in data or data["data"]["node"] is None:
            print("GraphQL response error:", data, file=sys.stderr)
            sys.exit(1)
        nodes = data["data"]["node"]["fields"]["nodes"]
        fields.extend(nodes)
        page_info = data["data"]["node"]["fields"]["pageInfo"]
        if not page_info["hasNextPage"]:
            break
        cursor = page_info["endCursor"]
    return fields


def fetch_project_items(project_id, token):
    """Fetch all items from a GitHub ProjectV2."""
    query = '''
    query($project: ID!, $cursor: String) {
      node(id: $project) {
        ... on ProjectV2 {
          items(first: 100, after: $cursor) {
            nodes {
              id
              fieldValues(first: 100) {
                nodes {
                  ... on ProjectV2ItemFieldTextValue {
                    text
                    field { id name }
                  }
                  ... on ProjectV2ItemFieldDateValue {
                    date
                    field { id name }
                  }
                  ... on ProjectV2ItemFieldNumberValue {
                    number
                    field { id name }
                  }
                  ... on ProjectV2ItemFieldSingleSelectValue {
                    name
                    field { id name }
                  }
                  ... on ProjectV2ItemFieldIterationValue {
                    title
                    field { id name }
                  }
                }
              }
              content {
                ... on Issue {
                  id
                  number
                  title
                  state
                  createdAt
                  updatedAt
                  url
                  author { login }
                  closedAt
                  milestone { title number state }
                  issueType { name }
                  labels(first: 100) { nodes { name color } }
                  assignees(first: 100) { nodes { login } }
                  parent {
                    ... on Issue { title number url id issueType { name } }
                  }
                  repository { nameWithOwner }
                }
              }
            }
            pageInfo { endCursor hasNextPage }
          }
        }
      }
    }
    '''
    items = []
    cursor = None
    while True:
        variables = {"project": project_id, "cursor": cursor}
        resp = requests.post(
            "https://api.github.com/graphql",
            json={"query": query, "variables": variables},
            headers={"Authorization": f"Bearer {token}"}
        )
        resp.raise_for_status()
        data = resp.json()
        if "errors" in data:
            print("GraphQL API error:", data["errors"], file=sys.stderr)
            sys.exit(1)
        if "data" not in data or data["data"]["node"] is None:
            print("GraphQL response error:", data, file=sys.stderr)
            sys.exit(1)
        nodes = data["data"]["node"]["items"]["nodes"]
        items.extend(nodes)
        page_info = data["data"]["node"]["items"]["pageInfo"]
        if not page_info["hasNextPage"]:
            break
        cursor = page_info["endCursor"]
    return items


def main():
    # Fetch fields and items
    print("Fetching project fields...")
    fields = fetch_project_fields(PROJECT_ID, GITHUB_PAT)
    print(f"Fetched {len(fields)} fields.")

    print("Fetching project items...")
    items = fetch_project_items(PROJECT_ID, GITHUB_PAT)
    print(f"Fetched {len(items)} items.")

    # Save output
    print(f"Writing items to {OUTPUT_CSV}...")
    with open(OUTPUT_CSV, "w", newline='', encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["ID", "Title", "State", "Created At", "Updated At", "URL"])
        for item in items:
            content = item.get("content", {})
            writer.writerow([
                content.get("id", ""),
                content.get("title", ""),
                content.get("state", ""),
                content.get("createdAt", ""),
                content.get("updatedAt", ""),
                content.get("url", "")
            ])
    print("Items written successfully.")

    print(f"Writing field metadata to {OUTPUT_META}...")
    with open(OUTPUT_META, "w", newline='', encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Field ID", "Field Name", "Field Type"])
        for field in fields:
            writer.writerow([
                field.get("id", ""),
                field.get("name", ""),
                field.get("dataType", "")
            ])
    print("Field metadata written successfully.")


if __name__ == "__main__":
    main()
