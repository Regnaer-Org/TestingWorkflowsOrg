import argparse
import requests
import csv
import sys
from collections import OrderedDict

def get_all_project_fields(project_id, token):
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
        data = resp.json()
        nodes = data["data"]["node"]["fields"]["nodes"]
        fields.extend(nodes)
        page_info = data["data"]["node"]["fields"]["pageInfo"]
        if not page_info["hasNextPage"]:
            break
        cursor = page_info["endCursor"]
    return fields

def get_all_project_items(project_id, token):
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
        data = resp.json()
        nodes = data["data"]["node"]["items"]["nodes"]
        items.extend(nodes)
        page_info = data["data"]["node"]["items"]["pageInfo"]
        if not page_info["hasNextPage"]:
            break
        cursor = page_info["endCursor"]
    return items

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--out-csv", required=True)
    parser.add_argument("--out-meta", required=True)
    args = parser.parse_args()

    fields = get_all_project_fields(args.project_id, args.token)
    items = get_all_project_items(args.project_id, args.token)

    # Prepare standard GitHub issue fields
    standard_fields = [
        "id", "content_id", "number", "title", "state", "createdAt", "updatedAt", "url",
        "author", "closedAt", "milestone_title", "milestone_number", "milestone_state",
        "issueType", "labels", "assignees",
        "parent_title", "parent_number", "parent_url", "parent_id", "parent_issueType",
        "repository"
    ]

    # Prepare dynamic custom fields (in order as shown in ProjectV2)
    custom_fields = [f["name"] for f in fields if f["name"] not in ("Title", "Status")] # Exclude default fields if you wish

    # Compose CSV header
    csv_header = standard_fields + custom_fields

    with open(args.out_csv, "w", newline='', encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(csv_header)
        for item in items:
            issue = item.get("content", {})
            # Standard fields
            row = [
                item.get("id", ""),
                issue.get("id", ""),
                issue.get("number", ""),
                issue.get("title", ""),
                issue.get("state", ""),
                issue.get("createdAt", ""),
                issue.get("updatedAt", ""),
                issue.get("url", ""),
                (issue.get("author") or {}).get("login", ""),
                issue.get("closedAt", ""),
                ((issue.get("milestone") or {}).get("title", "") if issue.get("milestone") else ""),
                ((issue.get("milestone") or {}).get("number", "") if issue.get("milestone") else ""),
                ((issue.get("milestone") or {}).get("state", "") if issue.get("milestone") else ""),
                ((issue.get("issueType") or {}).get("name", "") if issue.get("issueType") else ""),
                ";".join(l["name"] for l in ((issue.get("labels") or {}).get("nodes") or [])),
                ";".join(a["login"] for a in ((issue.get("assignees") or {}).get("nodes") or [])),
                ((issue.get("parent") or {}).get("title", "") if issue.get("parent") else ""),
                ((issue.get("parent") or {}).get("number", "") if issue.get("parent") else ""),
                ((issue.get("parent") or {}).get("url", "") if issue.get("parent") else ""),
                ((issue.get("parent") or {}).get("id", "") if issue.get("parent") else ""),
                (((issue.get("parent") or {}).get("issueType") or {}).get("name", "") if issue.get("parent") and issue["parent"].get("issueType") else ""),
                ((issue.get("repository") or {}).get("nameWithOwner", "") if issue.get("repository") else "")
            ]
            # Collect field values into a dict by name for easy lookup
            fieldvals = {}
            for fv in (item.get("fieldValues", {}).get("nodes") or []):
                val = fv.get("text") or fv.get("date") or fv.get("number") or fv.get("name") or fv.get("title") or ""
                fname = fv.get("field", {}).get("name")
                if fname:
                    fieldvals[fname] = val
            # Dynamic fields, in order
            for cf in custom_fields:
                row.append(fieldvals.get(cf, ""))
            writer.writerow(row)

    # Write field metadata
    with open(args.out_meta, "w", newline='', encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "name", "dataType", "options/iterations"])
        for fmeta in fields:
            extra = ""
            if fmeta.get("options"):
                extra = "|".join(
                    f"{o['id']}::{o['name']}" for o in (fmeta["options"] or [])
                )
            elif fmeta.get("configuration"):
                extra = "|".join(
                    f"{i['id']}::{i['title']}::{i['startDate']}::{i['duration']}" for i in (fmeta["configuration"]["iterations"] or [])
                )
            writer.writerow([fmeta["id"], fmeta["name"], fmeta["dataType"], extra])

if __name__ == "__main__":
    main()
