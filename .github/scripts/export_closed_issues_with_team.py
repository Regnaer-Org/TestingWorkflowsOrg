import os
import requests
import json
import sys

GITHUB_API_URL = "https://api.github.com/graphql"

GH_TOKEN = os.environ.get("GH_TOKEN")
PROJECT_ID = os.environ.get("PROJECT_ID")
TEAM_VALUE = os.environ.get("TEAM_VALUE")
SINCE = os.environ.get("SINCE")
OWNER = os.environ.get("OWNER")
REPO = os.environ.get("REPO")
FILE_SUFFIX = os.environ.get("FILE_SUFFIX", "")
TEAM_SAFE = os.environ.get("TEAM_SAFE", "")

HEADERS = {"Authorization": f"bearer {GH_TOKEN}"}

QUERY = """
query($owner: String!, $name: String!, $since: DateTime!, $after: String) {
  repository(owner: $owner, name: $name) {
    issues(
      first: 100
      filterBy: {states: CLOSED, since: $since}
      after: $after
    ) {
      nodes {
        number
        title
        body
        closedAt
        issueType {
          id
          name
        }
        projectItems(first: 10, includeArchived: false) {
          nodes {
            project {
              id
            }
            fieldValueByName(name: "Team") {
              ... on ProjectV2ItemFieldSingleSelectValue {
                name
                optionId
              }
            }
          }
        }
      }
      pageInfo {
        hasNextPage
        endCursor
      }
    }
  }
}
"""

def get_issues():
    all_issues = []
    after = None
    while True:
        variables = {
            "owner": OWNER,
            "name": REPO,
            "since": SINCE,
            "after": after
        }
        response = requests.post(
            GITHUB_API_URL,
            json={"query": QUERY, "variables": variables},
            headers=HEADERS,
        )
        response.raise_for_status()
        data = response.json()
        if "errors" in data:
            print("GraphQL errors:", json.dumps(data["errors"], indent=2), file=sys.stderr)
            raise RuntimeError("GraphQL query failed. See errors above.")
        if "data" not in data or data["data"] is None:
            print("Full response for debugging:", json.dumps(data, indent=2), file=sys.stderr)
            raise RuntimeError("No 'data' in GraphQL response.")
        issues = data["data"]["repository"]["issues"]["nodes"]
        all_issues.extend(issues)
        page_info = data["data"]["repository"]["issues"]["pageInfo"]
        if page_info["hasNextPage"]:
            after = page_info["endCursor"]
        else:
            break
    return all_issues

def filter_issues_by_team_and_type(issues, project_id, team_value):
    filtered = []
    for issue in issues:
        # Only include issues where issueType.name is 'Story' or 'Bug'
        issue_type_name = (issue.get("issueType") or {}).get("name", "")
        if issue_type_name not in ("Story", "Bug"):
            continue
        for item in issue.get("projectItems", {}).get("nodes", []):
            if item["project"]["id"] == project_id:
                team_field = item.get("fieldValueByName")
                if team_field and team_field.get("name") == team_value:
                    issue_copy = issue.copy()
                    issue_copy["team"] = team_value
                    filtered.append(issue_copy)
                    break
    return filtered

def main():
    issues = get_issues()
    filtered = filter_issues_by_team_and_type(issues, PROJECT_ID, TEAM_VALUE)
    if TEAM_SAFE and FILE_SUFFIX:
        filename = f"{TEAM_SAFE}_monthlyreport_{FILE_SUFFIX}.json"
    else:
        filename = "closed_issues_with_team.json"
    # Always write to closed_issues_with_team.json for downstream steps
    with open("closed_issues_with_team.json", "w", encoding="utf-8") as f:
        json.dump(filtered, f, indent=2, ensure_ascii=False)
    # Also write to the descriptive filename for clarity or local debugging
    if filename != "closed_issues_with_team.json":
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(filtered, f, indent=2, ensure_ascii=False)
    print(f"Exported {len(filtered)} issues to {filename}")

if __name__ == "__main__":
    main()
