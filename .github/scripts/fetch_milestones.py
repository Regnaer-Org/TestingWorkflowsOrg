import os
import requests
import csv
import sys
from datetime import datetime, timezone

# --- Configuration ---
TOKEN = os.environ.get("MILESTONE_SYNC_TOKEN")
REPO_OWNER = os.environ.get("REPO_OWNER")
REPO_NAME = os.environ.get("REPO_NAME")
PROJECT_ID = os.environ.get("PROJECT_ID")  # Use if needed for future queries or logging
OUTPUT_DIR = "agilereportingmetadata"
SNAPSHOT_FILENAME = "milestone_metadata.csv"  # Fixed filename for workflow simplicity
OUTPUT_PATH = os.path.join(OUTPUT_DIR, SNAPSHOT_FILENAME)
API_BASE_URL = "https://api.github.com"

# --- Validate Environment Variables ---
if not TOKEN:
    print("Error: MILESTONE_SYNC_TOKEN environment variable not set.", file=sys.stderr)
    sys.exit(1)
if not REPO_OWNER:
    print("Error: REPO_OWNER environment variable not set.", file=sys.stderr)
    sys.exit(1)
if not REPO_NAME:
    print("Error: REPO_NAME environment variable not set.", file=sys.stderr)
    sys.exit(1)
if not PROJECT_ID:
    print("Warning: PROJECT_ID environment variable not set. Proceeding anyway.")

print(f"Output file path set to: {OUTPUT_PATH}")

# --- Fetch All Milestones (Handles Pagination) ---
all_milestones = []
page = 1
per_page = 100  # Max allowed by GitHub API

print(f"Fetching milestones for repository: {REPO_OWNER}/{REPO_NAME}...")
while True:
    milestones_url = f"{API_BASE_URL}/repos/{REPO_OWNER}/{REPO_NAME}/milestones"
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    params = {
        "state": "all",  # Fetch both open and closed milestones
        "sort": "due_on",
        "direction": "asc",
        "per_page": per_page,
        "page": page
    }
    try:
        response = requests.get(milestones_url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        milestones_page = response.json()
        if not milestones_page:
            print("No more milestones found.")
            break
        all_milestones.extend(milestones_page)
        print(f"Fetched page {page} ({len(milestones_page)} milestones)...")
        if len(milestones_page) < per_page:
            print("Last page reached.")
            break
        page += 1
    except requests.exceptions.Timeout:
        print(f"Error: Request timed out connecting to {milestones_url}", file=sys.stderr)
        sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"Error fetching milestones: {e}", file=sys.stderr)
        sys.exit(1)

# --- Prepare Data and Write to CSV ---
if not all_milestones:
    print("No milestones found to write to CSV. Writing header only for consistency.")

print(f"Writing {len(all_milestones)} milestones to {OUTPUT_PATH}...")

headers = [
    'number', 'id', 'node_id', 'title', 'state', 'description',
    'creator_login', 'creator_id',
    'open_issues', 'closed_issues',
    'created_at', 'updated_at', 'closed_at', 'due_on',
    'url', 'html_url', 'labels_url'
]

try:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_PATH, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=headers, restval='', extrasaction='ignore')
        writer.writeheader()
        for milestone in all_milestones:
            row = {
                'number': milestone.get('number'),
                'id': milestone.get('id'),
                'node_id': milestone.get('node_id'),
                'title': milestone.get('title'),
                'state': milestone.get('state'),
                'description': milestone.get('description'),
                'creator_login': milestone.get('creator', {}).get('login'),
                'creator_id': milestone.get('creator', {}).get('id'),
                'open_issues': milestone.get('open_issues'),
                'closed_issues': milestone.get('closed_issues'),
                'created_at': milestone.get('created_at'),
                'updated_at': milestone.get('updated_at'),
                'closed_at': milestone.get('closed_at'),
                'due_on': milestone.get('due_on'),
                'url': milestone.get('url'),
                'html_url': milestone.get('html_url'),
                'labels_url': milestone.get('labels_url')
            }
            # Convert None to empty string and ensure all are strings
            for key, value in row.items():
                row[key] = str(value) if value is not None else ''
            writer.writerow(row)
except IOError as e:
    print(f"Error writing to {OUTPUT_PATH}: {e}", file=sys.stderr)
    sys.exit(1)
