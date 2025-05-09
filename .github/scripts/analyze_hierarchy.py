import csv
import os
from collections import defaultdict

input_file = "agilereporting/latest_snapshot.csv"
output_folder = "backloghealth"
os.makedirs(output_folder, exist_ok=True)
output_file = os.path.join(output_folder, "hierarchy_violations.csv")

# Define allowed children by parent type
allowed_children = {
    "epic": {"feature"},
    "feature": {"story", "bug"},
    "story": {"task"},
    "bug": {"task"},
    "task": set(),
}

hierarchy_values = {"epic", "feature", "story", "bug", "task"}

def detect_hierarchy_col(rows):
    if not rows:
        return None
    columns = rows[0].keys()
    for col in columns:
        for row in rows:
            v = (row.get(col) or '').strip().lower()
            if v in hierarchy_values:
                return col
    return None

def detect_column_by_header(headers, candidates):
    for c in candidates:
        for h in headers:
            if c.lower() == h.lower() or c.lower() in h.lower():
                return h
    return None

with open(input_file, newline='', encoding="utf-8") as csvfile:
    reader = csv.DictReader(csvfile)
    all_rows = list(reader)
    headers = reader.fieldnames

hierarchy_col = detect_hierarchy_col(all_rows[:50])
parent_type_col = detect_column_by_header(headers, ["parent_issue_type", "parent type"])
parent_id_col = detect_column_by_header(headers, ["parent_id", "parent id"])
id_col = detect_column_by_header(headers, ["content_id", "issue_id", "id", "number"])
title_col = detect_column_by_header(headers, ["content_title", "title"])
parent_title_col = detect_column_by_header(headers, ["parent_title", "parent title"])
content_url_col = detect_column_by_header(headers, ["content_url", "url"])
parent_url_col = detect_column_by_header(headers, ["parent_url", "parent url"])
team_col = detect_column_by_header(headers, ["team"])

# Build maps
id_to_issue = {}
parent_to_children = defaultdict(list)

for row in all_rows:
    issue_id = (row.get(id_col) or '').strip()
    parent_id = (row.get(parent_id_col) or '').strip() if parent_id_col else ''
    row_type = (row.get(hierarchy_col) or '').strip().lower() if hierarchy_col else ''
    parent_type = (row.get(parent_type_col) or '').strip().lower() if parent_type_col else ''
    row['__id'] = issue_id
    row['__parent_id'] = parent_id
    row['__type'] = row_type
    row['__parent_type'] = parent_type
    id_to_issue[issue_id] = row
    if parent_id:
        parent_to_children[parent_id].append(row)

violations = []

# 1. For all parents, check for improper sub-issues
for parent_id, children in parent_to_children.items():
    parent = id_to_issue.get(parent_id)
    if not parent:
        continue
    parent_type = parent.get('__type')
    parent_url = parent.get(content_url_col, '')
    parent_title = parent.get(title_col, '')
    parent_team = parent.get(team_col, '')
    allowed = allowed_children.get(parent_type, set())
    for child in children:
        child_type = child.get('__type')
        child_url = child.get(content_url_col, '')
        child_title = child.get(title_col, '')
        child_team = child.get(team_col, '')
        # Flag if child_type not allowed as a sub-issue of parent_type
        if allowed and child_type not in allowed:
            violations.append({
                "parent_id": parent_id,
                "parent_title": parent_title,
                "parent_issue_type_name": parent_type,
                "parent_url": parent_url,
                "parent_team": parent_team,
                "child_id": child.get('__id'),
                "child_title": child_title,
                "child_issue_type_name": child_type,
                "child_url": child_url,
                "child_team": child_team,
                "violation": f"{parent_type.title()} cannot have {child_type.title()} as a sub-issue"
            })

# 2. Tasks with no parent
for row in all_rows:
    if row.get('__type') == "task" and not row.get('__parent_id'):
        violations.append({
            "parent_id": "",
            "parent_title": "",
            "parent_issue_type_name": "",
            "parent_url": "",
            "parent_team": "",
            "child_id": row.get('__id'),
            "child_title": row.get(title_col, ''),
            "child_issue_type_name": "task",
            "child_url": row.get(content_url_col, ''),
            "child_team": row.get(team_col, ''),
            "violation": "Task is missing a parent"
        })

with open(output_file, "w", newline='', encoding="utf-8") as outfile:
    fieldnames = [
        "parent_id", "parent_title", "parent_issue_type_name", "parent_url", "parent_team",
        "child_id", "child_title", "child_issue_type_name", "child_url", "child_team",
        "violation"
    ]
    writer = csv.DictWriter(outfile, fieldnames=fieldnames)
    writer.writeheader()
    for v in violations:
        writer.writerow(v)
