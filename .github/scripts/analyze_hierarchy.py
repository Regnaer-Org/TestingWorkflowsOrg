import csv
import os

input_file = "agilereporting/latest_snapshot.csv"
output_folder = "backloghealth"
os.makedirs(output_folder, exist_ok=True)
output_file = os.path.join(output_folder, "hierarchy_violations.csv")

# Define hierarchy
hierarchy = {
    "Epic": 1,
    "Feature": 2,
    "Story": 3,
    "Bug": 3,
    "Task": 4,
}

with open(input_file, newline='', encoding="utf-8") as csvfile, open(output_file, "w", newline='', encoding="utf-8") as outfile:
    reader = csv.DictReader(csvfile)
    fieldnames = [
        "content_id", "content_title", "issue_type_name", "content_url", "Team",
        "parent_id", "parent_title", "parent_issue_type_name", "parent_url",
        "violation"
    ]
    writer = csv.DictWriter(outfile, fieldnames=fieldnames)
    writer.writeheader()

    for row in reader:
        issue_type = row.get("issue_type_name")
        parent_type = row.get("parent_issue_type_name")
        parent_id = row.get("parent_id")
        violation = ""

        # Task rules
        if issue_type == "Task":
            if not parent_id:
                violation = "Task is missing a parent"
            elif parent_type not in ("Story", "Bug"):
                violation = "Task parent is not Story or Bug"

        # Story/Bug rules
        elif issue_type in ("Story", "Bug"):
            if parent_id and parent_type != "Feature":
                violation = "Story/Bug parent is not Feature"

        # Feature rules
        elif issue_type == "Feature":
            if parent_id and parent_type != "Epic":
                violation = "Feature parent is not Epic"

        # Epic rules
        elif issue_type == "Epic":
            if parent_id:
                violation = "Epic should not have a parent"

        if violation:
            writer.writerow({
                "content_id": row.get("content_id"),
                "content_title": row.get("content_title"),
                "issue_type_name": issue_type,
                "content_url": row.get("content_url"),
                "Team": row.get("Team"),
                "parent_id": parent_id,
                "parent_title": row.get("parent_title"),
                "parent_issue_type_name": parent_type,
                "parent_url": row.get("parent_url"),
                "violation": violation,
            })
