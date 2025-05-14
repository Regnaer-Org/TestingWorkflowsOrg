import os
import csv
import re
from collections import defaultdict

# --- CONFIGURATION ---
SNAPSHOT_DIR = "agilereporting"
SNAPSHOT_PATTERN = re.compile(r"project\.issues_(\d{4}\.\d{2}\.\d{2})\.csv")
CHANGELOG_PATH = "agilereportingmetadata/issue_changelog.csv"
FIELDS_TO_TRACK = [
    "content_title",
    "content_state",
    "content_closed_at",
    "milestone_title",
    "issue_type_name",
    "parent_id",
    "escalate",
    "sprint",
    "status",
    "team"
]
CONTEXT_FIELDS = [
    "content_title",
    "issue_type_name",
    "team",
    "status",
    "sprint",
    "parent_id",
    "escalate",
    "content_state",
    "content_closed_at",
    "milestone_title"
]

def list_snapshots(directory):
    files = []
    for fname in os.listdir(directory):
        match = SNAPSHOT_PATTERN.match(fname)
        if match:
            files.append((match.group(1), fname))
    files.sort()  # Sort by date string
    return [fname for _, fname in files]

def load_snapshot(filepath):
    issues = {}
    with open(filepath, newline='', encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (row.get("content_id") or row.get("content.id"), row.get("content_number") or row.get("content.number"))
            if key[0] and key[1]:
                issues[key] = row
    return issues

def main():
    if not os.path.exists("agilereportingmetadata"):
        os.makedirs("agilereportingmetadata")
    snapshots = list_snapshots(SNAPSHOT_DIR)
    if len(snapshots) < 2:
        print("Not enough snapshots to generate changelog.")
        return

    changelog_rows = []
    prev_issues = {}
    prev_date = None

    for snap_fname in snapshots:
        date = SNAPSHOT_PATTERN.match(snap_fname).group(1)
        snap_path = os.path.join(SNAPSHOT_DIR, snap_fname)
        issues = load_snapshot(snap_path)

        if prev_issues:
            # Compare this snapshot to previous
            all_keys = set(issues.keys()) | set(prev_issues.keys())
            for key in all_keys:
                curr = issues.get(key)
                prev = prev_issues.get(key)
                content_id, issue_number = key
                if not curr:
                    continue  # Issue disappeared, likely closed (could log if desired)
                if not prev:
                    # New issue appeared, record initial state for all tracked fields
                    for f in FIELDS_TO_TRACK:
                        changelog_rows.append({
                            "date": date,
                            "issue_number": issue_number,
                            "content_id": content_id,
                            "field": f,
                            "old_value": "",
                            "new_value": curr.get(f, ""),
                            **{cf: curr.get(cf, "") for cf in CONTEXT_FIELDS}
                        })
                else:
                    for f in FIELDS_TO_TRACK:
                        if curr.get(f, "") != prev.get(f, ""):
                            changelog_rows.append({
                                "date": date,
                                "issue_number": issue_number,
                                "content_id": content_id,
                                "field": f,
                                "old_value": prev.get(f, ""),
                                "new_value": curr.get(f, ""),
                                **{cf: curr.get(cf, "") for cf in CONTEXT_FIELDS}
                            })
        prev_issues = issues
        prev_date = date

    # Write changelog
    if changelog_rows:
        with open(CHANGELOG_PATH, "w", newline='', encoding="utf-8") as out:
            writer = csv.DictWriter(out, fieldnames=[
                "date",
                "issue_number",
                "content_id",
                "field",
                "old_value",
                "new_value"
            ] + CONTEXT_FIELDS)
            writer.writeheader()
            writer.writerows(changelog_rows)
        print(f"Wrote changelog: {CHANGELOG_PATH} ({len(changelog_rows)} changes detected)")
    else:
        print("No changes detected across snapshots.")

if __name__ == "__main__":
    main()
