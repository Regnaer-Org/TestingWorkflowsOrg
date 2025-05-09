import csv
import os

input_file = "agilereporting/latest_snapshot.csv"
output_folder = "backloghealth"
os.makedirs(output_folder, exist_ok=True)
output_file = os.path.join(output_folder, "hierarchy_violations.csv")

# All valid (issue_type_name, parent_issue_type_name) pairs (with "null" for None/empty)
valid_pairs = {
    ("Epic", "null"),
    ("Feature", "null"),
    ("Feature", "Epic"),
    ("Story", "null"),
    ("Story", "Feature"),
    ("Bug", "null"),
    ("Bug", "Feature"),
    ("Task", "Story"),
    ("Task", "Bug"),      # Added
    # ("Task", "Feature"),  # Removed
}

def normalize(val):
    if val is None or str(val).strip() == "":
        return "null"
    return str(val).strip()

with open(input_file, newline='', encoding="utf-8") as infile, open(output_file, "w", newline='', encoding="utf-8") as outfile:
    reader = csv.DictReader(infile)
    fieldnames = [
        "content_number", "content_title", "content_url", "issue_type_name",
        "author", "assignees", "team",
        "project_item_type",
        "parent_title", "parent_issue_type_name", "parent_url",
        "violation_explanation"
    ]
    writer = csv.DictWriter(outfile, fieldnames=fieldnames)
    writer.writeheader()

    for row in reader:
        project_item_type = normalize(row.get("project_item_type"))
        issue_type = normalize(row.get("issue_type_name"))
        parent_type = normalize(row.get("parent_issue_type_name"))

        # Only include rows where project_item_type is 'ISSUE'
        if project_item_type != "ISSUE":
            continue

        # Exclude issues of type 'Impediment' (case-insensitive)
        if issue_type.lower() == "impediment":
            continue

        violation = None

        # Check if valid
        if (issue_type, parent_type) not in valid_pairs:
            if issue_type == "Task" and parent_type == "null":
                violation = "Task is missing a parent issue"
            else:
                violation = "issue has an improper parent"

        if violation:
            writer.writerow({
                "content_number": row.get("content_number"),
                "content_title": row.get("content_title"),
                "content_url": row.get("content_url"),
                "issue_type_name": row.get("issue_type_name"),
                "author": row.get("author") or "null",
                "assignees": row.get("assignees") or "null",
                "team": row.get("team") or "null",
                "project_item_type": row.get("project_item_type") or "null",
                "parent_title": row.get("parent_title") or "null",
                "parent_issue_type_name": row.get("parent_issue_type_name") or "null",
                "parent_url": row.get("parent_url") or "null",
                "violation_explanation": violation
            })
