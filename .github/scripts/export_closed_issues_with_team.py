import os
import requests
import json

GITHUB_API_URL = "https://api.github.com/graphql"

GH_TOKEN = os.environ["GH_TOKEN"]
PROJECT_ID = os.environ["PROJECT_ID"]
TEAM_VALUE = os.environ["TEAM_VALUE"]
SINCE = os.environ["SINCE"]
OWNER = os.environ["OWNER"]
REPO = os.environ["REPO"]
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
      orderBy: {field: CLOSED_AT, direction: DESC}
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
        issues = data["data"]["repository"]["issues"]["nodes"]
        all_issues.extend(issues)
        page_info = data["data"]["repository"]["issues"]["pageInfo"]
        if page_info["hasNextPage"]:
            after = page_info["endCursor"]
        else:
            break
    return all_issues

def filter_issues_by_team(issues, project_id, team_value):
    filtered = []
    for issue in issues:
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
    filtered = filter_issues_by_team(issues, PROJECT_ID, TEAM_VALUE)
    filename = f"closed_issues_with_team.json"
    # Save with the team and date in the filename as well for clarity if needed
    if TEAM_SAFE and FILE_SUFFIX:
        filename = f"{TEAM_SAFE}_monthlyreport_{FILE_SUFFIX}.json"
    with open("closed_issues_with_team.json", "w", encoding="utf-8") as f:
        json.dump(filtered, f, indent=2, ensure_ascii=False)
    # Also save with the dynamic filename for easy copying
    if TEAM_SAFE and FILE_SUFFIX:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(filtered, f, indent=2, ensure_ascii=False)
    print(f"Exported {len(filtered)} issues to {filename}")

if __name__ == "__main__":
    main()
