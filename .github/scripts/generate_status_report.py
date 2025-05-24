import os
import json
import openai

# Load issues JSON
with open('monthly_report/latest_snapshot.JSON', 'r') as f:
    issues = json.load(f)

# Concise reporting prompt
PROMPT = """You are an expert project delivery assistant with deep knowledge of GitHub's issue hierarchy and Agile methodology.

Your task: Generate a concise, business-focused monthly status report from a JSON export of closed issues from a GitHub Project.

Reminders:
- GitHub supports issue hierarchies: Epic > Feature > Story > Task (Bug is like Story unless it's a sub-task).
- Epics = business goals; Features = major functionalities; Stories = deliverable units of work; Tasks = steps to complete a Story.
- Milestones represent releases and can include target dates/outstanding issues.
- Team field shows which agile team delivered each item.
- The most important reporting level is Story; fall back to Task if needed.
- Bugs should be grouped with Stories if they're sub-issues.
- Bodies and titles may be sparse; infer context from parents/titles if needed.
- Not all issues will have parents; infer value from what’s provided.
- Multiple teams may collaborate, but group by Team.
- Audience: project managers and delivery leads.

Instructions:
- Group deliverables by Team.
- For each Team, create a bulleted list of what was accomplished this month.
    - Each bullet should be one sentence, concise, and business-focused.
    - Summarize the business value and parent feature/epic if possible.
    - Only mention Tasks if no Stories were delivered.
- Use plain English.
- Omit empty sections/teams.

Input: JSON list of closed issues with fields: id, number, title, state, url, createdAt, closedAt, body, labels, issueType, parent (id, title), issue_type, parent_id, parent_title, team, sprint, priority, etc.

Output: For each Team, a bulleted list of one-line accomplishments for the month.
"""

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise EnvironmentError("OPENAI_API_KEY not set in environment.")

messages = [
    {"role": "system", "content": PROMPT},
    {"role": "user", "content": f"Here is the closed issues JSON:\n{json.dumps(issues)}"},
]

response = openai.ChatCompletion.create(
    model="gpt-4-1106-preview",
    messages=messages,
    temperature=0.3,
)

report = response['choices'][0]['message']['content']

os.makedirs('monthly_report', exist_ok=True)
with open('monthly_report/status_report.md', 'w') as f:
    f.write(report)

print("Status report generated and saved to monthly_report/status_report.md")
