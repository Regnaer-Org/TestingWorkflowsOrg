import os
import csv
import re

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

def list_snapshots():
    files = []
    for fname in os.listdir(SNAPSHOT_DIR):
        match = SNAPSHOT_PATTERN.match(fname)
        if match:
            files.append((match.group(1), fname))
    files.sort()
    return [fname for _, fname in files]

def load_snapshot(path):
    issues = {}
    if not os.path.exists(path):
        return issues
    with open(path, newline='', encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (row.get("content_id") or row.get("content.id"), row.get("content_number") or row.get("content.number"))
            if key[0] and key[1]:
                issues[key] = row
    return issues

def append_to_changelog(new_rows):
    file_exists = os.path.exists(CHANGELOG_PATH)
    mode = "a" if file_exists else "w"
    with open(CHANGELOG_PATH, mode, newline='', encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=[
            "date",
            "issue_number",
            "content_id",
            "field",
            "old_value",
            "new_value"
        ] + CONTEXT_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerows(new_rows)

def get_last_changelog_date():
    if not os.path.exists(CHANGELOG_PATH):
        return None
    with open(CHANGELOG_PATH, newline='', encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        if not rows:
            return None
        # Get the latest date in the changelog
        return max(row["date"] for row in rows if row.get("date"))

def main():
    if not os.path.exists("agilereportingmetadata"):
        os.makedirs("agilereportingmetadata")

    snapshots = list_snapshots()
    if len(snapshots) < 2:
        print("Not enough snapshots to update changelog.")
        return

    latest_snapshot = snapshots[-1]
    prev_snapshot = snapshots[-2]
    latest_date = SNAPSHOT_PATTERN.match(latest_snapshot).group(1)
    prev_date = SNAPSHOT_PATTERN.match(prev_snapshot).group(1)

    # If changelog already contains the latest snapshot date, don't reprocess
    last_changelog_date = get_last_changelog_date()
    if last_changelog_date and latest_date <= last_changelog_date:
        print(f"Changelog already up-to-date for snapshot {latest_snapshot}.")
        return

    latest_issues = load_snapshot(os.path.join(SNAPSHOT_DIR, latest_snapshot))
    prev_issues = load_snapshot(os.path.join(SNAPSHOT_DIR, prev_snapshot))

    changelog_rows = []
    all_keys = set(latest_issues.keys()) | set(prev_issues.keys())
    for key in all_keys:
        curr = latest_issues.get(key)
        prev = prev_issues.get(key)
        content_id, issue_number = key
        if not curr:
            continue  # Issue disappeared, likely closed (could log if desired)
        if not prev:
            # New issue appeared, record initial state for all tracked fields
            for f in FIELDS_TO_TRACK:
                changelog_rows.append({
                    "date": latest_date,
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
                        "date": latest_date,
                        "issue_number": issue_number,
                        "content_id": content_id,
                        "field": f,
                        "old_value": prev.get(f, ""),
                        "new_value": curr.get(f, ""),
                        **{cf: curr.get(cf, "") for cf in CONTEXT_FIELDS}
                    })

    if changelog_rows:
        append_to_changelog(changelog_rows)
        print(f"Appended {len(changelog_rows)} changes for {latest_snapshot} to {CHANGELOG_PATH}")
    else:
        print(f"No changes detected for {latest_snapshot}")

if __name__ == "__main__":
    main()
