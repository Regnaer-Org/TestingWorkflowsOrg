import csv
import os

input_file = "agilereporting/latest_snapshot.csv"
output_folder = "backloghealth"
os.makedirs(output_folder, exist_ok=True)
base_output_file = os.path.join(output_folder, "hierarchy_violations")

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
    ("Task", "Bug"),
}

def normalize(val):
    if val is None or str(val).strip() == "":
        return "null"
    return str(val).strip()

def markdown_link(url, text=None):
    if url is None or str(url).strip() == "" or url == "null":
        return "null"
    url = str(url).strip()
    if not text or str(text).strip() == "" or text == "null": # Ensure text for link is not null/empty
        text = url # Default to URL if text is not meaningful
    return f"[{text}]({url})"

# Define output columns
fieldnames = [
    "content_number", "content_title", "content_url", "issue_type_name",
    "author", "assignees", "team",
    "project_item_type",
    "parent_title", "parent_issue_type_name", "parent_url",
    "violation_explanation"
]

violations = []

# Read and filter violations first
with open(input_file, newline='', encoding="utf-8") as infile:
    reader = csv.DictReader(infile)
    if not reader.fieldnames: # Check if file is empty or not a CSV
        print(f"Warning: Input file {input_file} is empty or not a valid CSV.")
    elif "project_item_is_archived" not in reader.fieldnames:
        print(f"Warning: 'project_item_is_archived' column not found in {input_file}. Cannot filter archived items.")
        # Decide if you want to proceed without filtering or stop
        # For now, it will proceed and not filter if the column is missing.

    for row in reader:
        # Skip archived items
        project_item_is_archived = normalize(row.get("project_item_is_archived")).lower()
        if project_item_is_archived == "true":
            continue

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
            violations.append({
                "content_number": row.get("content_number"),
                "content_title": row.get("content_title"),
                "content_url": row.get("content_url") or "null",
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

# Write CSV output (no link formatting)
with open(base_output_file + ".csv", "w", newline='', encoding="utf-8") as outfile:
    writer = csv.DictWriter(outfile, fieldnames=fieldnames)
    writer.writeheader()
    for v in violations:
        writer.writerow(v)

# Write Markdown output (with link formatting)
with open(base_output_file + ".md", "w", encoding="utf-8") as mdfile:
    # Header row
    mdfile.write("| " + " | ".join(fieldnames) + " |\n")
    mdfile.write("|" + "|".join(["---"] * len(fieldnames)) + "|\n")
    for v in violations:
        parent_link_text = v["parent_title"]
        if normalize(parent_link_text) == "null":
            parent_link_text = "Parent" # Use "Parent" if title is null

        md_row_data = {
            "content_number": str(v["content_number"]),
            "content_title": str(v["content_title"]),
            "content_url": markdown_link(v["content_url"], v["content_number"]),
            "issue_type_name": str(v["issue_type_name"]),
            "author": str(v["author"]),
            "assignees": str(v["assignees"]),
            "team": str(v["team"]),
            "project_item_type": str(v["project_item_type"]),
            "parent_title": str(v["parent_title"]),
            "parent_issue_type_name": str(v["parent_issue_type_name"]),
            "parent_url": markdown_link(v["parent_url"], parent_link_text),
            "violation_explanation": str(v["violation_explanation"])
        }
        md_row_values = [md_row_data[fieldname] for fieldname in fieldnames]
        mdfile.write("| " + " | ".join(md_row_values) + " |\n")

print(f"Processed {len(violations)} violations.")
