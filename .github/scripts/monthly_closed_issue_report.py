import os
import sys
import requests
import json
from datetime import datetime, timedelta, timezone

# --- CONFIGURATION ---
TOKEN = os.environ.get("MILESTONE_SYNC_TOKEN")
PROJECT_ID = os.environ.get("PROJECT_ID")
TEAM_INPUT = sys.argv[1] if len(sys.argv) > 1 else "ALL"
VALID_ISSUETYPES = {"Bug", "Story"}
OUTPUT_PATH = "agilereporting/filtered_issues.json"

if not TOKEN:
    print("Error: MILESTONE_SYNC_TOKEN is not set.", file=sys.stderr)
    sys.exit(1)
if not PROJECT_ID:
    print("Error: PROJECT_ID is not set.", file=sys.stderr)
    sys.exit(1)

GRAPHQL_API_URL = "https://api.github.com/graphql"

# --- Fetch the Team field id from ProjectV2 ---
def get_team_field_id():
    query = '''
    query($projectId:ID!) {
      node(id: $projectId) {
        ... on ProjectV2 {
          fields(first: 50) {
            nodes {
              ... on ProjectV2SingleSelectField {
                id
                name
                options { id name }
              }
            }
          }
        }
      }
    }
    '''
    variables = {"projectId": PROJECT_ID}
    headers = {"Authorization": f"Bearer {TOKEN}"}
    resp = requests.post(GRAPHQL_API_URL, headers=headers, json={"query": query, "variables": variables})
    if resp.status_code != 200:
        raise Exception(f"Failed to fetch fields: {resp.status_code} {resp.text}")
    data = resp.json()
    fields = data["data"]["node"]["fields"]["nodes"]
    for f in fields:
        if f and f.get("name", "").lower() == "team":
            return f["id"], {opt["name"]: opt["id"] for opt in f.get("options", [])}
    raise Exception("No ProjectV2 field named 'Team' found.")

team_field_id, team_options = get_team_field_id()
# If user requests a specific team, map to option ID (for safety, but script uses name matching)
if TEAM_INPUT != "ALL" and TEAM_INPUT not in team_options:
    print(f"Error: Team value '{TEAM_INPUT}' not found in project options: {list(team_options.keys())}", file=sys.stderr)
    sys.exit(1)

# --- Date window ---
now = datetime.now(timezone.utc)
window_start = now - timedelta(days=30)

def parse_dt(s):
    if not s:
        return None
    try:
        # Handles Z or +00:00
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None

# --- Main query loop ---
all_issues = []
cursor = None
has_next_page = True

while has_next_page:
    query = '''
    query($projectId:ID!, $cursor:String) {
      node(id: $projectId) {
        ... on ProjectV2 {
          items(first: 50, after: $cursor) {
            pageInfo { endCursor hasNextPage }
            nodes {
              id
              fieldValues(first: 20) {
                nodes {
                  ... on ProjectV2ItemFieldSingleSelectValue {
                    field { id }
                    name
                  }
                }
              }
              content {
                ... on Issue {
                  id
                  number
                  title
                  body
                  state
                  url
                  createdAt
                  updatedAt
                  closedAt
                  author { login }
                  issueType { name }
                }
              }
            }
          }
        }
      }
    }
    '''
    variables = {"projectId": PROJECT_ID, "cursor": cursor}
    headers = {"Authorization": f"Bearer {TOKEN}"}
    resp = requests.post(GRAPHQL_API_URL, json={"query": query, "variables": variables}, headers=headers)
    if resp.status_code != 200:
        print(f"Error from GitHub API: {resp.text}", file=sys.stderr)
        sys.exit(1)
    data = resp.json()
    items = data["data"]["node"]["items"]["nodes"]
    page_info = data["data"]["node"]["items"]["pageInfo"]
    cursor = page_info["endCursor"]
    has_next_page = page_info["hasNextPage"]

    for item in items:
        content = item.get("content")
        if not content or content.get("state", "").lower() != "closed":
            continue
        # Closed date check
        closed_at = parse_dt(content.get("closedAt"))
        if not closed_at or closed_at < window_start:
            continue
        # Issue type check
        issue_type = (content.get("issueType") or {}).get("name", "")
        if issue_type not in VALID_ISSUETYPES:
            continue
        # Team check
        team_val = None
        for fv in item.get("fieldValues", {}).get("nodes", []):
            if fv and fv.get("field", {}).get("id") == team_field_id:
                team_val = fv.get("name")
                break
        if TEAM_INPUT != "ALL":
            if team_val != TEAM_INPUT:
                continue
        # If ALL, include even if team_val is None
        all_issues.append({
            "id": content.get("id"),
            "number": content.get("number"),
            "title": content.get("title"),
            "body": content.get("body"),
            "url": content.get("url"),
            "state": content.get("state"),
            "createdAt": content.get("createdAt"),
            "closedAt": content.get("closedAt"),
            "author": (content.get("author") or {}).get("login"),
            "issueType": issue_type,
            "team": team_val,
        })

# Write output
os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    json.dump(all_issues, f, indent=2, ensure_ascii=False)

print(f"Wrote {len(all_issues)} issues to {OUTPUT_PATH}")
