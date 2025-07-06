import os
import textwrap
import subprocess
import tempfile
from datetime import datetime
import re
import sys

INITIATIVE_AUTOGEN_START = "<!-- INITIATIVE-AUTO-GENERATED-START -->"
INITIATIVE_AUTOGEN_END = "<!-- INITIATIVE-AUTO-GENERATED-END -->"

def get_multiline_input_from_editor(prompt):
    print("\nA text editor will now open. Markdown formatting is encouraged!")
    print("When you are finished, save the file and exit:")
    print("  1. Press 'Ctrl+O' (Write Out), then 'Enter' to save.")
    print("  2. Press 'Ctrl+X' to exit the editor.")
    input("Press Enter to continue...")

    editor = os.environ.get('EDITOR', 'nano')
    try:
        with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix=".md") as tf:
            tf.write(f"# {prompt}\n# Please enter your text below this line.\n")
            temp_filename = tf.name
        subprocess.run([editor, temp_filename])
        with open(temp_filename, 'r') as tf:
            content = tf.read().strip()
            content = re.sub(r'^#.*# Please enter your text below this line.\n?', '', content, flags=re.MULTILINE).strip()
        os.remove(temp_filename)
        return content
    except Exception as e:
        print(f"Error during editor input: {e}")
        if os.path.exists(temp_filename):
            os.remove(temp_filename)
        sys.exit(1)

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

def sanitize_for_filename(name):
    s = name.strip().lower()
    s = re.sub(r'\s+', '-', s)
    s = re.sub(r'[^a-z0-9-]', '', s)
    return s

def handle_persona_selection():
    persona_dir = "personas"
    os.makedirs(persona_dir, exist_ok=True)
    existing_personas = [f for f in os.listdir(persona_dir) if f.endswith('.md')]
    if not existing_personas:
        print("No existing personas found. Let's create the first one.")
        return [create_new_persona(persona_dir)]
    print("Found existing personas:")
    for i, p_file in enumerate(existing_personas):
        display_name = os.path.splitext(p_file)[0].replace('-', ' ').title()
        print(f"  {i + 1}: {display_name}")
    print(f"  {len(existing_personas) + 1}: Create a new persona")
    selected = []
    print("Select persona numbers separated by commas (e.g. 1,3) or type just the new option to add a new one.")
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
            else:
                print(f"Invalid selection: {choice}")
        except ValueError:
            print(f"Invalid input (not a number): {choice}")
    if not selected:
        print("No personas selected. Exiting.")
        sys.exit(1)
    return selected

def create_new_persona(persona_dir):
    print_step_header("Create a New User Persona", "A great persona is the foundation of a great project. Generate a detailed persona and paste the entire thing here.")
    print_copilot_pro_tip("Create a detailed user persona card for a [persona title, e.g., 'Mid-level Reinsurance Actuary']. Include their goals, skills, daily tasks, and frustrations in Markdown format.")
    persona_title = input("What is the title of this new persona? (e.g., Mid-level Reinsurance Actuary): ")
    if not persona_title.strip():
        print("Persona title cannot be empty. Exiting.")
        sys.exit(1)
    filename = sanitize_for_filename(persona_title) + ".md"
    filepath = os.path.join(persona_dir, filename)
    persona_content = get_multiline_input_from_editor(f"Paste the full persona card for '{persona_title}'")
    if not persona_content.strip():
        print("Persona content is empty. Exiting.")
        sys.exit(1)
    try:
        with open(filepath, 'w') as f:
            f.write(f"# Persona: {persona_title}\n\n{persona_content}")
        print(f"\nPersona created and saved to: {filepath}")
        return filepath
    except Exception as e:
        print(f"Error writing persona file: {e}")
        sys.exit(1)

def collect_existing_issues():
    print_step_header("Link Existing Relevant Issues", "You may want to reference existing issues that provide context for this initiative (e.g., bugs, feedback, dependencies, etc).")
    print_copilot_pro_tip("Which existing issues in this repo are relevant to this initiative? Copy their GitHub URLs here (one per line).")
    issues_raw = get_multiline_input_from_editor("Paste one or more GitHub issue URLs (or leave blank):")
    issue_links = [line.strip() for line in issues_raw.splitlines() if line.strip()]
    return issue_links

def main():
    print("="*60)
    print("        Welcome to the Initiative Brief Wizard!")
    print("="*60)

    persona_paths = handle_persona_selection()
    persona_links = []
    for p in persona_paths:
        display = os.path.splitext(os.path.basename(p))[0].replace('-', ' ').title()
        rel_path = os.path.join("..", "..", p).replace(os.path.sep, '/')
        persona_links.append(f"[{display}]({rel_path})")

    try:
        initiative_name = input("\nWhat is the name of this new initiative or feature?: ")
        if not initiative_name.strip():
            print("Initiative name cannot be empty. Exiting.")
            sys.exit(1)
        dir_name = sanitize_for_filename(initiative_name)
        initiative_path = os.path.join("initiatives", dir_name)
        os.makedirs(initiative_path, exist_ok=True)
        print(f"\nWe will create all documentation in: {initiative_path}/")
    except Exception as e:
        print(f"Error creating initiative directory: {e}")
        sys.exit(1)

    print_step_header("Define the Problem", "Draft a clear and compelling problem statement.")
    print_copilot_pro_tip(f"Based on the selected personas, help me write a detailed problem statement about the challenges they face that the '{initiative_name}' initiative will solve. Use Markdown to structure it.")
    problem = get_multiline_input_from_editor("Paste the full Problem Statement")
    if not problem.strip():
        print("Problem statement cannot be empty. Exiting.")
        sys.exit(1)

    print_step_header("Build the Business Case", "This justifies the project's existence. Generate a comprehensive business case and paste the entire text here.")
    print_copilot_pro_tip(f"Given the problem statement for the '{initiative_name}' initiative, help me build a business case. Focus on metrics like efficiency gains, error reduction, and competitive advantage. Format it in Markdown.")
    business_case = get_multiline_input_from_editor("Paste the full Business Case")
    if not business_case.strip():
        print("Business case cannot be empty. Exiting.")
        sys.exit(1)

    print_step_header("List the Epic Titles", "List the titles of the major epics for this initiative. Enter one epic title per line.")
    print_copilot_pro_tip(f"Based on the business case for '{initiative_name}', suggest 3-5 high-level epic titles that form the core of the MVP.")
    epics_raw = get_multiline_input_from_editor("List the Epic Titles (one per line)")
    epic_titles = [line.strip() for line in epics_raw.splitlines() if line.strip()]
    if not epic_titles:
        print("At least one epic title is required. Exiting.")
        sys.exit(1)

    existing_issues = collect_existing_issues()

    repo_slug = os.environ.get('GITHUB_REPOSITORY', 'owner/repo-name')
    brief_url = f"https://github.com/{repo_slug}/blob/main/{initiative_path}/initiative.md"
    hierarchy_url = f"https://github.com/{repo_slug}/blob/main/.project_framework/backlog_hierarchy_best_practices.md"

    # --- Mermaid ETL/Cloud Diagram Scaffolding ---
    print_step_header("OPTIONAL: Describe a high-level process for a data/ETL or cloud architecture diagram.", "This description will be used to generate a rough Mermaid.js diagram for the initiative file. (You can edit it later.)")
    print_copilot_pro_tip("Summarize the main data flows, ETL steps, or cloud components for this initiative, as a list or short description.")
    diagram_desc = get_multiline_input_from_editor("Describe the process (optional):")
    diagram_mermaid = ""
    if diagram_desc:
        steps = [s.strip("-•> ").capitalize() for s in diagram_desc.splitlines() if s.strip()]
        if len(steps) >= 2:
            nodes = [chr(ord('A')+i) for i in range(len(steps))]
            mermaid_lines = [f"{nodes[i]}[{steps[i]}] --> {nodes[i+1]}[{steps[i+1]}]" for i in range(len(steps)-1)]
            diagram_mermaid = "```mermaid\nflowchart TD\n    " + "\n    ".join(mermaid_lines) + "\n```"

    # --- Epic Issue Creation Script ---
    script_content = "#!/bin/sh\n"
    epic_links = []
    for title in epic_titles:
        safe_title = title.replace("'", "'\\''")
        title_prefix = f"[{initiative_name}] Epic:"
        # Issue body
        body_template = f"""
### Description
*See the full context in the [**Initiative File**]({brief_url}).*

---

### Decomposition Guidance

This epic may have sub-issues created later. When using this epic as input for Copilot or other tooling, **assume all sub-issues linked to this epic are part of the initiative, even if not all are listed here**.

**Quick Copilot Prompt:**  
Copy the following into Copilot Chat to begin requirement refinement:

Given the epic "{title}", the initiative details in [this file]({brief_url}), and the [backlog hierarchy guide]({hierarchy_url}), help me break down this epic into features and user stories. Assume all sub-issues of this epic are included. Ask clarifying questions if needed.
"""
        safe_body = textwrap.dedent(body_template).replace("'", "'\\''").replace("\n", "\\n")
        script_content += f"gh issue create --title '{title_prefix} {safe_title}' --body '{safe_body}' --label '{dir_name},epic'\n"
        epic_links.append(f"- [ ] (TBD) Epic: {title}")

    script_path = os.path.join(initiative_path, 'create_epics.sh')
    try:
        with open(script_path, 'w') as f:
            f.write(script_content)
        os.chmod(script_path, 0o755)
        print(f"- Generated {script_path}")
    except Exception as e:
        print(f"Error writing epic creation script: {e}")

    # --- Initiative File Creation ---
    initiative_md_path = os.path.join(initiative_path, 'initiative.md')
    old_manual = ""
    if os.path.exists(initiative_md_path):
        try:
            with open(initiative_md_path, "r") as f:
                content = f.read()
            parts = content.split(INITIATIVE_AUTOGEN_START)
            if len(parts) > 1:
                old_manual = parts[0]
        except Exception as e:
            print(f"Error reading existing initiative.md: {e}")

    auto_section = f"""{INITIATIVE_AUTOGEN_START}
# Initiative: {initiative_name}

## Overview
_TODO: Add a summary of the initiative._

## Personas Involved
""" + '\n'.join(f"- {link}" for link in persona_links) + """

## Problem Statement
""" + problem + """

## Business Case
""" + business_case + """

## Epics

The following epics are linked to this initiative.  
**Note:** Each epic may have sub-issues/features which are considered part of this initiative even if not listed here.

""" + '\n'.join(epic_links) + """

## Related Issues

Link any issues that provide additional context (e.g., bugs, dependencies, customer feedback, compliance).  
**Prompt:** "What kinds of issues should be linked here for full context?"

""" + ('\n'.join(f"- [ ] {url}" for url in existing_issues) if existing_issues else "_None linked yet._") + """

## Diagrams

""" + (diagram_mermaid if diagram_mermaid else "_Add diagrams here. Use Mermaid for ETL/process/architecture diagrams._") + """

## Release Notes

_To be filled during or after delivery._

## User Guides

_Links or embedded guides go here._

---
### Copilot/LLM Prompt Snippets

> Copy and use these prompts in Copilot Chat or another LLM agent to jumpstart requirement writing, decomposition, or documentation.

- "Given this initiative file, what requirements are missing or unclear?"
- "Summarize the business case and personas for a user guide introduction."
- "Break down all linked epics into feature and story issues."
- "Draft release notes based on completed issues linked to this initiative."
- "Generate a Mermaid diagram showing the high-level process described above."

{INITIATIVE_AUTOGEN_END}
"""

    try:
        with open(initiative_md_path, "w") as f:
            f.write((old_manual or "") + "\n" + auto_section)
        print(f"- Generated {initiative_md_path}")
    except Exception as e:
        print(f"Error writing initiative.md: {e}")

    print("\n--- Setup Complete! ---")
    print("Your initiative file and epic creation script have been generated.")
    print("\n--- NEXT STEP ---")
    print(f"Run the following command to create your epic issues:\nsh {script_path}\n")
    print("Then, manually update initiative.md as you refine details, add links, or edit sections.")
    print("Commit the new 'initiatives/' and 'personas/' directories to save your work.")

if __name__ == '__main__':
    main()
