import os
import textwrap
import subprocess
import tempfile
from datetime import datetime
import re
import requests

INITIATIVE_AUTOGEN_START = "<!-- INITIATIVE-AUTO-GENERATED-START -->"
INITIATIVE_AUTOGEN_END = "<!-- INITIATIVE-AUTO-GENERATED-END -->"


def get_multiline_input_from_editor(prompt):
    print("\nA text editor will now open. Markdown formatting is encouraged!")
    print("When you are finished, save the file and exit:")
    print("  1. Press 'Ctrl+O' (Write Out), then 'Enter' to save.")
    print("  2. Press 'Ctrl+X' to exit the editor.")
    input("Press Enter to continue...")

    editor = os.environ.get('EDITOR', 'nano')
    with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix=".md") as tf:
        tf.write(f"# {prompt}\n# Please enter your text below this line.\n")
        temp_filename = tf.name
    subprocess.run([editor, temp_filename])
    with open(temp_filename, 'r') as tf:
        content = tf.read().strip()
        # Remove all lines starting with "#" (prompt and Copilot tips)
        content = "\n".join(
            [line for line in content.splitlines() if not line.strip().startswith("#")]
        ).strip()
    os.remove(temp_filename)
    return content


def print_step_header(title, description):
    print("\n" + "=" * 60)
    print(f"STEP: {title}")
    print(textwrap.fill(description, 60))
    print("=" * 60)


def print_copilot_pro_tip(prompt_example):
    print("\n--- [ Copilot Pro-Tip ] ---")
    print("Use Copilot Chat to help you generate detailed content.")
    print("Try a prompt like this, then paste the entire output into the editor:")
    print(
        "\n"
        + textwrap.fill(
            f'"{prompt_example}"', 58, initial_indent="  ", subsequent_indent="  "
        )
    )
    print("---------------------------\n")


def sanitize_for_filename(name):
    s = name.strip().lower()
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"[^a-z0-9-]", "", s)
    while "--" in s:
        s = s.replace("--", "-")
    return s


def write_initiative_file(initiative_name, content):
    os.makedirs("initiatives", exist_ok=True)
    filename = f"initiatives/{sanitize_for_filename(initiative_name)}.md"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)
    return filename


def handle_persona_selection():
    persona_dir = "personas"
    os.makedirs(persona_dir, exist_ok=True)
    existing_personas = [f for f in os.listdir(persona_dir) if f.endswith(".md")]
    if not existing_personas:
        print("No existing personas found. Let's create the first one.")
        return [create_new_persona(persona_dir)]
    print("Found existing personas:")
    for i, p_file in enumerate(existing_personas):
        display_name = os.path.splitext(p_file)[0].replace("-", " ").title()
        print(f"  {i + 1}: {display_name}")
    print(f"  {len(existing_personas) + 1}: Create a new persona")
    selected = []
    print(
        "Select persona numbers separated by commas (e.g. 1,3) or type just the new option to add a new one."
    )
    choices = input("Your selection: ").split(",")
    for choice in choices:
        choice = choice.strip()
        if not choice:
            continue
        try:
            idx = int(choice)
            if 1 <= idx <= len(existing_personas):
                selected.append(os.path.join(persona_dir, existing_personas[idx - 1]))
            elif idx == len(existing_personas) + 1:
                selected.append(create_new_persona(persona_dir))
        except ValueError:
            print(f"Invalid input: {choice}")
    return selected


def create_new_persona(persona_dir):
    print_step_header(
        "Create a New User Persona",
        "A great persona is the foundation of a great project. Generate a detailed persona and paste the entire thing here.",
    )
    print_copilot_pro_tip(
        "Create a detailed user persona card for a [persona title, e.g., 'Mid-level Reinsurance Actuary']. Include their goals, skills, daily tasks, and frustrations in Markdown form."
    )
    persona_title = input(
        "What is the title of this new persona? (e.g., Mid-level Reinsurance Actuary): "
    )
    filename = sanitize_for_filename(persona_title) + ".md"
    filepath = os.path.join(persona_dir, filename)
    persona_content = get_multiline_input_from_editor(
        f"Paste the full persona card for '{persona_title}'"
    )
    with open(filepath, "w") as f:
        f.write(f"# Persona: {persona_title}\n\n{persona_content}")
    print(f"\nPersona created and saved to: {filepath}")
    return filepath


def collect_existing_issues():
    print_step_header(
        "Link Existing Relevant Issues",
        "You may want to reference existing issues that provide context for this initiative (e.g., bugs, feedback, dependencies, etc).",
    )
    print_copilot_pro_tip(
        "Which existing issues in this repo are relevant to this initiative? Copy their GitHub URLs here (one per line)."
    )
    issues_raw = get_multiline_input_from_editor(
        "Paste one or more GitHub issue URLs (or leave blank):"
    )
    issue_links = [line.strip() for line in issues_raw.splitlines() if line.strip()]
    return issue_links


def parse_epic_titles(epic_lines):
    """
    Filter epic titles: Ignore lines that are empty or start with '#'.
    """
    return [
        line.strip()
        for line in epic_lines
        if line.strip() and not line.strip().startswith("#")
    ]


def create_github_issue(
    repo_owner,
    repo_name,
    title,
    body,
    github_pat,
    issue_type_name=None,
    labels=None,
    assignees=None,
    milestone=None,
):
    """
    Create a new issue with GitHub native type if available. If not, fallback to regular issue (no label!).
    """
    url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/issues"
    headers = {
        "Authorization": f"token {github_pat}",
        "Accept": "application/vnd.github+json",
    }
    data = {
        "title": title,
        "body": body,
    }
    if assignees:
        data["assignees"] = assignees
    if milestone:
        data["milestone"] = milestone
    if labels:
        data["labels"] = labels
    tried_type = False
    if issue_type_name:
        data["issue_type"] = issue_type_name
        tried_type = True
    resp = requests.post(url, headers=headers, json=data)
    if resp.status_code == 201:
        return resp.json()
    elif tried_type and resp.status_code == 422:
        # Remove issue_type and try again (type not supported)
        del data["issue_type"]
        resp = requests.post(url, headers=headers, json=data)
        if resp.status_code == 201:
            return resp.json()
        else:
            print(f"Failed to create issue (fallback): {resp.status_code} {resp.text}")
            return None
    else:
        print(f"Failed to create issue: {resp.status_code} {resp.text}")
        return None


def main():
    print("=" * 60)
    print("        Welcome to the Initiative Brief Wizard!")
    print("=" * 60)

    persona_paths = handle_persona_selection()
    persona_links = []
    for p in persona_paths:
        display = os.path.splitext(os.path.basename(p))[0].replace("-", " ").title()
        rel_path = os.path.join("..", "..", p).replace(os.path.sep, "/")
        persona_links.append(f"[{display}]({rel_path})")

    initiative_name = input("\nWhat is the name of this new initiative or feature?: ")
    safe_name = sanitize_for_filename(initiative_name)
    initiative_path = f"initiatives/{safe_name}.md"
    print(f"\nWe will create all documentation in: {initiative_path}")

    print_step_header("Define the Problem", "Draft a clear and compelling problem statement.")
    print_copilot_pro_tip(
        f"Based on the selected personas, help me write a detailed problem statement about the challenges they face that the '{initiative_name}' initiative will solve. Use Markdown to format the statement."
    )
    problem = get_multiline_input_from_editor("Paste the full Problem Statement")

    print_step_header("Build the Business Case", "This justifies the project's existence. Generate a comprehensive business case and paste the entire text here.")
    print_copilot_pro_tip(
        f"Given the problem statement for the '{initiative_name}' initiative, help me build a business case. Focus on metrics like efficiency gains, error reduction, and competitive advantage. Use Markdown."
    )
    business_case = get_multiline_input_from_editor("Paste the full Business Case")

    print_step_header("List the Epic Titles", "List the titles of the major epics for this initiative. Enter one epic title per line.")
    print_copilot_pro_tip(
        f"Based on the business case for '{initiative_name}', suggest 3-5 high-level epic titles that form the core of the MVP."
    )
    epics_raw = get_multiline_input_from_editor("List the Epic Titles (one per line)")
    epic_input_lines = epics_raw.splitlines()
    epic_titles = parse_epic_titles(epic_input_lines)

    existing_issues = collect_existing_issues()

    # Fake repo_slug for testing; in real use, you would use os.environ.get('GITHUB_REPOSITORY', 'owner/repo')
    repo_slug = os.environ.get("GITHUB_REPOSITORY", "owner/repo-name")
    brief_url = f"https://github.com/{repo_slug}/blob/main/{initiative_path}"
    hierarchy_url = f"https://github.com/{repo_slug}/blob/main/.project_framework/backlog_hierarchy_best_practices.md"

    # --- Mermaid ETL/Cloud Diagram Scaffolding ---
    print_step_header(
        "OPTIONAL: Describe a high-level process for a data/ETL or cloud architecture diagram.",
        "This description will be used to generate a rough Mermaid.js diagram for the initiative.",
    )
    print_copilot_pro_tip(
        "Summarize the main data flows, ETL steps, or cloud components for this initiative, as a list or short description."
    )
    diagram_desc = get_multiline_input_from_editor("Describe the process (optional):")
    diagram_mermaid = ""
    if diagram_desc:
        # Simple heuristic to create a Mermaid flowchart scaffold from a list
        steps = [s.strip("-•> ").capitalize() for s in diagram_desc.splitlines() if s.strip()]
        if len(steps) >= 2:
            nodes = [chr(ord("A") + i) for i in range(len(steps))]
            mermaid_lines = [f"{nodes[i]}[{steps[i]}] --> {nodes[i+1]}[{steps[i+1]}]" for i in range(len(steps) - 1)]
            diagram_mermaid = "```mermaid\nflowchart TD\n    " + "\n    ".join(mermaid_lines) + "\n```"

    # --- Write initiative file ---
    initiative_content = f"# Initiative: {initiative_name}\n\n"
    initiative_content += f"## Personas\n" + "\n".join(persona_links) + "\n\n"
    initiative_content += f"## Problem Statement\n{problem}\n\n"
    initiative_content += f"## Business Case\n{business_case}\n\n"
    initiative_content += f"## Epics\n" + "\n".join(f"- {e}" for e in epic_titles) + "\n\n"
    if existing_issues:
        initiative_content += "## Relevant Issues\n" + "\n".join(f"- {url}" for url in existing_issues) + "\n\n"
    if diagram_mermaid:
        initiative_content += f"## Architecture Diagram\n{diagram_mermaid}\n\n"
    initiative_content += f"*Created on {datetime.utcnow().strftime('%Y-%m-%d')} by {os.environ.get('USER', 'the wizard')}*"

    filename = write_initiative_file(initiative_name, initiative_content)
    print(f"Wrote initiative file: {filename}")

    # --- Epic Issue Creation ---
    github_pat = os.environ.get("ISSUE_WIZARD_PAT")
    repo_owner, repo_name = repo_slug.split("/", 1)
    create_epics = input("\nWould you like to create epics on GitHub now? (Y/n): ").lower().strip() in ("", "y", "yes")
    epic_links = []
    if github_pat and create_epics:
        for epic_title in epic_titles:
            body = f"See the [initiative file]({brief_url}) for context.\n\n"
            issue = create_github_issue(
                repo_owner=repo_owner,
                repo_name=repo_name,
                title=epic_title,
                body=body,
                github_pat=github_pat,
                issue_type_name="Epic"
            )
            if issue:
                print(f"Created Epic Issue: {issue['html_url']}")
                epic_links.append(issue['html_url'])
    elif not github_pat and create_epics:
        print("ISSUE_WIZARD_PAT not set. Skipping GitHub Epic creation.")

    print("\n=== Initiative and Epic Creation Complete ===")
    print(f"- Initiative file: {filename}")
    if epic_links:
        print("Created Epic Issues:")
        for link in epic_links:
            print(f"  - {link}")

    print("Next steps:")
    print("  - Refine the epic issues with additional details or link sub-issues as needed.")
    print("  - Optionally, add these epics to your GitHub Project board for tracking.")


if __name__ == "__main__":
    main()
