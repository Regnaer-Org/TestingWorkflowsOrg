import os
import textwrap
import subprocess
import tempfile
from datetime import datetime
import re
import sys
import json
from pathlib import Path

try:
    from github import Github, GithubException
except ImportError:
    print(
        "ERROR: PyGithub is not installed. "
        "Please ensure your Codespace has run 'pip install -r requirements.txt'."
    )
    sys.exit(1)

# --- Configurable constants ---
PERSONA_DIR = "personas"
INITIATIVE_DIR = "initiatives"
LOG_PATH = ".project_framework/wizard_log.jsonl"
README = "README.md"
INITIATIVES_SECTION_TITLE = "## Initiatives"
EPIC_TEMPLATE_NAME = "epic"  # No extension; we'll resolve it
TEMPLATES_DIR = ".github/ISSUE_TEMPLATE"

# --- Utility Functions ---

def sanitize_for_filename(name):
    s = name.strip().lower()
    s = re.sub(r'\s+', '-', s)
    s = re.sub(r'[^a-z0-9-]', '', s)
    return s

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
        content = re.sub(r'^#.*# Please enter your text below this line.\n?', '', content, flags=re.MULTILINE).strip()
    os.remove(temp_filename)
    return content

def print_step_header(title, description):
    print("\n" + "="*60)
    print(f"STEP: {title}")
    print(textwrap.fill(description, 60))
    print("="*60)

def print_copilot_pro_tip(prompt_example):
    print("\n--- [ Copilot Pro-Tip ] ---")
    print("Use Copilot Chat to help you generate detailed content.")
    print("Try a prompt like this, then paste the entire output into the editor:")
    print("\n" + textwrap.fill(f'"{prompt_example}"', 58, initial_indent="  ", subsequent_indent="  "))
    print("---------------------------\n")

def ensure_dir_exists(dirpath):
    Path(dirpath).mkdir(parents=True, exist_ok=True)

def log_action(action, data):
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "user": os.environ.get("USER") or os.environ.get("USERNAME") or "",
        "action": action,
        "data": data
    }
    ensure_dir_exists(os.path.dirname(LOG_PATH))
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(log_entry) + "\n")

def get_github_token():
    token = os.environ.get("ISSUE_WIZARD_PAT")
    if not token:
        print(
            "\nERROR: GitHub token not found!\n"
            "A repository admin must set a Codespaces secret named 'ISSUE_WIZARD_PAT' with a PAT for issue creation.\n"
            "Go to repo Settings → Secrets and variables → Codespaces → New repository secret."
        )
        return None
    return token

def get_repo_slug():
    # Trust GITHUB_REPOSITORY var in Codespaces/GitHub Actions, fallback to local
    return os.environ.get('GITHUB_REPOSITORY') or get_repo_slug_from_git() or "owner/repo"

def get_repo_slug_from_git():
    try:
        remote_url = subprocess.check_output(["git", "remote", "get-url", "origin"], encoding="utf-8").strip()
        m = re.match(r"(?:https:\/\/github\.com\/|git@github\.com:)([^\/]+)\/(.+?)(?:\.git)?$", remote_url)
        if m:
            return f"{m.group(1)}/{m.group(2)}"
    except Exception:
        return None

# --- Persona Selection ---

def persona_exists(persona_title):
    filename = sanitize_for_filename(persona_title) + ".md"
    filepath = os.path.join(PERSONA_DIR, filename)
    return os.path.isfile(filepath)

def handle_persona_selection():
    ensure_dir_exists(PERSONA_DIR)
    existing_personas = [f for f in os.listdir(PERSONA_DIR) if f.endswith('.md')]
    selected = []

    while True:
        persona_title = input("Enter the title of a user persona (e.g., 'Mid-level Reinsurance Actuary'): ").strip()
        filename = sanitize_for_filename(persona_title) + ".md"
        filepath = os.path.join(PERSONA_DIR, filename)
        if persona_exists(persona_title):
            print(f"A persona named '{persona_title}' already exists.")
            use_existing = input(f"Use existing '{persona_title}'? (Y/n): ").strip().lower()
            if use_existing in ("", "y", "yes"):
                selected.append(filepath)
            else:
                continue  # Ask again
        else:
            print_step_header("Create New Persona", "A great persona is the foundation of a great project. Generate a detailed persona and paste the entire thing here.")
            print_copilot_pro_tip("Create a detailed user persona card for a [persona title, e.g., 'Mid-level Reinsurance Actuary']. Include their goals, skills, daily tasks, and frustrations in Markdown form.")
            persona_content = get_multiline_input_from_editor(f"Paste the full persona card for '{persona_title}'")
            with open(filepath, 'w') as f:
                f.write(f"# Persona: {persona_title}\n\n{persona_content}")
            print(f"\nPersona created and saved to: {filepath}")
            log_action("create_persona", {"persona_title": persona_title, "file": filepath})
            selected.append(filepath)
        add_another = input("Add another persona? (y/N): ").strip().lower()
        if add_another not in ("y", "yes"):
            break
    return selected

# --- Epic Template Logic ---

def get_epic_template():
    if not os.path.isdir(TEMPLATES_DIR):
        return None
    for file in os.listdir(TEMPLATES_DIR):
        if sanitize_for_filename(file.split(".")[0]) == EPIC_TEMPLATE_NAME:
            return os.path.join(TEMPLATES_DIR, file)
    return None

def read_epic_template():
    path = get_epic_template()
    if not path:
        return None
    with open(path, "r") as f:
        return f.read()

def create_github_epic_issues(epic_titles, repo_slug, brief_url, use_template=False):
    token = get_github_token()
    if not token:
        print("Skipping GitHub epic issue creation due to missing token.")
        return []
    g = Github(token)
    try:
        repo = g.get_repo(repo_slug)
    except GithubException as e:
        print(f"ERROR: Unable to access repository '{repo_slug}': {e}")
        return []

    epic_issue_links = []
    epic_template_content = read_epic_template() if use_template else None
    for title in epic_titles:
        issue_title = f"[Epic] {title}"
        if epic_template_content:
            body = epic_template_content.replace("{{epic_title}}", title).replace("{{initiative_url}}", brief_url)
        else:
            body = (
                f"### Description\n"
                f"*See the full context in the [**Initiative File**]({brief_url}).*\n\n"
                f"---\n\n"
                f"### Decomposition Guidance\n\n"
                f"This epic may have sub-issues created later. When using this epic as input for Copilot or other tooling, "
                f"**assume all sub-issues linked to this epic are part of the initiative, even if not all are listed here.**\n"
            )
        try:
            issue = repo.create_issue(title=issue_title, body=body)
            print(f"Created epic issue: {issue.html_url}")
            epic_issue_links.append(issue.html_url)
            log_action("create_epic_issue", {"title": issue_title, "url": issue.html_url})
        except GithubException as e:
            print(f"ERROR: Unable to create epic issue '{issue_title}': {e}")
    return epic_issue_links

# --- README Writeback ---

def append_initiative_to_readme(initiative_name, initiative_path):
    link = f"- [{initiative_name}]({initiative_path})\n"
    readme_path = README
    if not os.path.exists(readme_path):
        with open(readme_path, "w") as f:
            f.write(f"# Project README\n\n{INITIATIVES_SECTION_TITLE}\n\n{link}")
        return
    with open(readme_path, "r") as f:
        content = f.read()
    if INITIATIVES_SECTION_TITLE not in content:
        content += f"\n\n{INITIATIVES_SECTION_TITLE}\n\n"
    # Insert after the "Initiatives" section title
    lines = content.splitlines()
    out_lines = []
    in_section = False
    inserted = False
    for line in lines:
        out_lines.append(line)
        if line.strip() == INITIATIVES_SECTION_TITLE and not inserted:
            in_section = True
            out_lines.append("") # blank line after header
            out_lines.append(link.strip())
            inserted = True
        elif in_section and (line.startswith("#") and line != INITIATIVES_SECTION_TITLE):
            in_section = False  # End of section
    if not inserted:
        out_lines.append(INITIATIVES_SECTION_TITLE)
        out_lines.append("")
        out_lines.append(link.strip())
    new_content = "\n".join(out_lines) + "\n"
    with open(readme_path, "w") as f:
        f.write(new_content)

# --- Main Wizard Flow ---

def main():
    print("="*60)
    print("        Welcome to the Initiative Brief Wizard!")
    print("="*60)

    # 1. Persona selection (with existence check)
    persona_paths = handle_persona_selection()
    persona_links = []
    for p in persona_paths:
        display = os.path.splitext(os.path.basename(p))[0].replace('-', ' ').title()
        rel_path = os.path.relpath(p, start=".").replace(os.path.sep, '/')
        persona_links.append(f"[{display}]({rel_path})")

    # 2. Initiative info
    initiative_name = input("\nWhat is the name of this new initiative or feature?: ").strip()
    dir_name = sanitize_for_filename(initiative_name)
    initiative_path = os.path.join(INITIATIVE_DIR, dir_name)
    ensure_dir_exists(initiative_path)
    print(f"\nWe will create all documentation in: {initiative_path}/")

    # 3. Problem statement, business case, epics
    print_step_header("Define the Problem", "Draft a clear and compelling problem statement.")
    print_copilot_pro_tip(f"Based on the selected personas, help me write a detailed problem statement about the challenges they face that the '{initiative_name}' initiative will solve. Use Markdown to format.")
    problem = get_multiline_input_from_editor("Paste the full Problem Statement")

    print_step_header("Build the Business Case", "This justifies the project's existence. Generate a comprehensive business case and paste the entire text here.")
    print_copilot_pro_tip(f"Given the problem statement for the '{initiative_name}' initiative, help me build a business case. Focus on metrics like efficiency gains, error reduction, and competitive advantage.")
    business_case = get_multiline_input_from_editor("Paste the full Business Case")

    print_step_header("List the Epic Titles", "List the titles of the major epics for this initiative. Enter one epic title per line.")
    print_copilot_pro_tip(f"Based on the business case for '{initiative_name}', suggest 3-5 high-level epic titles that form the core of the MVP.")
    epics_raw = get_multiline_input_from_editor("List the Epic Titles (one per line)")
    epic_titles = [line.strip() for line in epics_raw.splitlines() if line.strip()]

    print_step_header("Link Existing Relevant Issues", "You may want to reference existing issues that provide context for this initiative (e.g., bugs, feedback, dependencies, etc).")
    print_copilot_pro_tip("Which existing issues in this repo are relevant to this initiative? Copy their GitHub URLs here (one per line).")
    issues_raw = get_multiline_input_from_editor("Paste one or more GitHub issue URLs (or leave blank):")
    existing_issues = [line.strip() for line in issues_raw.splitlines() if line.strip()]

    repo_slug = get_repo_slug()
    brief_url = f"https://github.com/{repo_slug}/blob/main/{initiative_path}/initiative.md"
    hierarchy_url = f"https://github.com/{repo_slug}/blob/main/.project_framework/backlog_hierarchy_best_practices.md"

    # Mermaid diagram
    print_step_header(
        "OPTIONAL: Describe a high-level process for a data/ETL or cloud architecture diagram.",
        "This description will be used to generate a rough Mermaid.js diagram for the initiative."
    )
    print_copilot_pro_tip("Summarize the main data flows, ETL steps, or cloud components for this initiative, as a list or short description.")
    diagram_desc = get_multiline_input_from_editor("Describe the process (optional):")
    diagram_mermaid = ""
    if diagram_desc:
        steps = [s.strip("-•> ").capitalize() for s in diagram_desc.splitlines() if s.strip()]
        if len(steps) >= 2:
            nodes = [chr(ord('A')+i) for i in range(len(steps))]
            mermaid_lines = [f"{nodes[i]}[{steps[i]}] --> {nodes[i+1]}[{steps[i+1]}]" for i in range(len(steps)-1)]
            diagram_mermaid = "```mermaid\nflowchart TD\n    " + "\n    ".join(mermaid_lines) + "\n```"

    # Save initiative brief
    brief_path = os.path.join(initiative_path, "initiative.md")
    with open(brief_path, "w") as f:
        f.write(f"# Initiative: {initiative_name}\n\n")
        f.write("## Personas\n" + "\n".join(persona_links) + "\n\n")
        f.write("## Problem Statement\n" + problem + "\n\n")
        f.write("## Business Case\n" + business_case + "\n\n")
        f.write("## Epics\n")
        for epic in epic_titles:
            f.write(f"- {epic}\n")
        f.write("\n## Relevant Issues\n")
        for link in existing_issues:
            f.write(f"- {link}\n")
        if diagram_mermaid:
            f.write("\n## Architecture Diagram\n" + diagram_mermaid + "\n")
    print(f"\nInitiative brief saved to: {brief_path}")
    log_action("create_initiative", {
        "initiative_name": initiative_name,
        "initiative_file": brief_path,
        "personas": persona_links,
        "epics": epic_titles,
        "issues": existing_issues
    })

    # Append to README
    append_initiative_to_readme(initiative_name, brief_path)
    print(f"Initiative '{initiative_name}' has been added to the README under '## Initiatives'.")

    # Offer to create epic issues on GitHub
    print("\nWould you like to create epic issues for these epics on GitHub now?")
    print("This requires the repo admin to have set the Codespaces secret ISSUE_WIZARD_PAT.")
    # Check if template is required
    require_template = False
    config_path = ".github/.github-config.yml"
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            if "blank_issues_enabled: false" in f.read():
                require_template = True
    use_template = require_template and get_epic_template() is not None
    if require_template and not use_template:
        print("WARNING: Your repo requires issue templates but no 'epic' template was found. Epic issue creation may fail.")

    choice = input("Type Y to create the epics now, or any other key to skip: ").strip().lower()
    epic_links = []
    if choice == "y":
        epic_links = create_github_epic_issues(epic_titles, repo_slug, brief_url, use_template=use_template)
        # Add epic links to initiative file
        if epic_links:
            with open(brief_path, "a") as f:
                f.write("\n## Epic Issue Links\n")
                for url in epic_links:
                    f.write(f"- {url}\n")
            print("Epic issue links appended to initiative file.")
    else:
        print("Skipping GitHub epic issue creation. You can run this wizard again to create them later.")

    # Post-creation guidance
    print("\n=== Initiative and Epic Creation Complete ===")
    print(f"- Initiative file: {brief_path}")
    if epic_links:
        print("Created Epic Issues:")
        for url in epic_links:
            print(f"  - {url}")
        print("Next steps:")
        print("  - Refine the epic issues with additional details or link sub-issues as needed.")
        print("  - Optionally, add these epics to your GitHub Project board for tracking.")
    else:
        print("No epic issues were created in this run.")
        print("You may run the wizard again to create them later.")

    print("\nAll actions are logged for audit purposes in .project_framework/wizard_log.jsonl.")

if __name__ == "__main__":
    main()
