import os
import textwrap
import subprocess
import tempfile
from datetime import datetime
import re

def get_multiline_input_from_editor(prompt):
    """Opens a command-line editor (nano) to get multi-line input from the user."""
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
        # Remove the placeholder prompt if it's still there
        content = re.sub(r'^#.*# Please enter your text below this line.\n?', '', content, flags=re.MULTILINE).strip()
    os.remove(temp_filename)
    return content

def print_step_header(title, description):
    """Prints a formatted header for each step."""
    print("\n" + "="*60)
    print(f"STEP: {title}")
    print(textwrap.fill(description, 60))
    print("="*60)

def print_copilot_pro_tip(prompt_example):
    """Prints the Copilot Pro-Tip box."""
    print("\n--- [ Copilot Pro-Tip ] ---")
    print("Use Copilot Chat to help you generate detailed content.")
    print("Try a prompt like this, then paste the entire output into the editor:")
    print("\n" + textwrap.fill(f'"{prompt_example}"', 58, initial_indent="  ", subsequent_indent="  "))
    print("---------------------------\n")

def sanitize_for_directory_name(name):
    """Converts a project name into a filesystem-safe directory name."""
    s = name.strip().lower()
    s = re.sub(r'\s+', '-', s)
    s = re.sub(r'[^a-z0-9-]', '', s)
    return s

def main():
    """Main function to run the project setup wizard."""
    current_time_utc = "2025-07-03 02:52:35"
    current_user = "regnaer"

    print("="*60)
    print("        Welcome to the Initiative Brief Wizard!")
    print("="*60)
    print("This wizard helps you document a new project or feature")
    print("within this existing repository.")
    
    initiative_name = input("\nWhat is the name of this new initiative or feature?: ")
    dir_name = sanitize_for_directory_name(initiative_name)
    initiative_path = os.path.join("initiatives", dir_name)

    os.makedirs(initiative_path, exist_ok=True)
    print(f"\nGreat! We will create all documentation in: {initiative_path}/")

    # --- Persona ---
    print_step_header("Define the User Persona", "A great persona is the foundation of a great project. Generate a detailed persona and paste the entire thing here.")
    print_copilot_pro_tip(f"I'm working on a '{initiative_name}' initiative. Can you create a detailed user persona card for a 'Mid-level Reinsurance Actuary'? Include their goals, skills, daily tasks, and frustrations in Markdown format.")
    persona = get_multiline_input_from_editor(f"Paste the full User Persona for {initiative_name}")

    # --- Problem Statement ---
    print_step_header("Define the Problem", "Use Copilot to help you draft a clear and compelling problem statement, then paste the full text here.")
    print_copilot_pro_tip(f"Based on the persona of a Mid-level Reinsurance Actuary, help me write a detailed problem statement about the challenges they face that our '{initiative_name}' initiative will solve. Use Markdown to structure it.")
    problem = get_multiline_input_from_editor("Paste the full Problem Statement")

    # --- Business Case ---
    print_step_header("Build the Business Case", "This justifies the project's existence. Generate a comprehensive business case and paste the entire text here.")
    print_copilot_pro_tip(f"Given the problem statement for the '{initiative_name}' initiative, help me build a business case. Focus on metrics like efficiency gains, error reduction, and competitive advantage. Format it in Markdown.")
    business_case = get_multiline_input_from_editor("Paste the full Business Case")

    # --- Epics ---
    print_step_header("List the Epic Titles", "Finally, list the titles of the major epics for this initiative. Enter one epic title per line. The issue bodies will link back to the brief you're creating now.")
    print_copilot_pro_tip(f"Based on the business case for '{initiative_name}', suggest 3-5 high-level epic titles that would form the core of the MVP.")
    epics_raw = get_multiline_input_from_editor("List the Epic Titles (one per line)")

    # --- Processing and File Generation ---
    print("\n" + "="*60)
    print(f"Processing your inputs and generating files in {initiative_path}...")
    
    epic_titles = [line.strip() for line in epics_raw.splitlines() if line.strip()]

    # Create the main brief document (BRIEF.md)
    brief_content = f"""
# Initiative Brief: {initiative_name}
**(Last Updated: {current_time_utc} by @{current_user})**

---

## Primary User Persona
{persona}

---

## Problem Statement
{problem}

---

## Business Case
{business_case}

---

## Proposed Epics
The following epics represent the high-level scope for this initiative. See the corresponding GitHub Issues for detailed user stories and tasks.
"""
    for title in epic_titles:
        brief_content += f"\n- {title}"

    with open(os.path.join(initiative_path, 'BRIEF.md'), 'w') as f:
        f.write(textwrap.dedent(brief_content).strip())
    print(f"- Generated {os.path.join(initiative_path, 'BRIEF.md')}")

    # Create the epic generation script
    script_content = f"#!/bin/sh\n# This script uses the GitHub CLI to create your epics as issues for the '{initiative_name}' initiative.\n\n"
    brief_url = f"https://github.com/Regnaer-Org/TestingWorkflowsOrg/blob/main/{initiative_path}/BRIEF.md"
    
    for title in epic_titles:
        safe_title = title.replace("'", "'\\''")
        body_content = f"This epic is part of the **{initiative_name}** initiative.\\n\\nSee the full Initiative Brief for context: {brief_url}"
        title_prefix = f"[{initiative_name}] Epic:"
        
        script_content += f"gh issue create --title '{title_prefix} {safe_title}' --body '{body_content}' --label '{dir_name}'\n"
    
    script_path = os.path.join(initiative_path, 'create_epics.sh')
    with open(script_path, 'w') as f:
        f.write(script_content)
    os.chmod(script_path, 0o755)
    print(f"- Generated {script_path}")

    print("\n--- Setup Complete! ---")
    print("Your initiative brief has been created in your Codespace.\n")
    print("--- YOUR NEXT STEP ---")
    print("A script to create these epics in GitHub Issues has been generated.")
    print("\nIn your terminal, run the following command:")
    print(f"sh {script_path}\n")
    print("After that, commit the new 'initiatives/' directory to save your work.")

if __name__ == '__main__':
    main()
