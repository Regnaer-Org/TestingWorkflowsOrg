import os
import textwrap
import subprocess
import tempfile
from datetime import datetime
import re

def get_multiline_input_from_editor(prompt):
    """Opens a command-line editor (nano) to get multi-line input from the user."""
    print("\nA text editor will now open. Please enter or paste your text.")
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
        content = [line for line in tf.readlines() if not line.strip().startswith('#')]
    os.remove(temp_filename)
    return "".join(content).strip()

def print_step_header(title, description):
    """Prints a formatted header for each step."""
    print("\n" + "="*60)
    print(f"STEP: {title}")
    print(textwrap.fill(description, 60))
    print("="*60)

def print_copilot_pro_tip(prompt_example):
    """Prints the Copilot Pro-Tip box."""
    print("\n--- [ Copilot Pro-Tip ] ---")
    print("Stuck? Use Copilot Chat to help you brainstorm!")
    print("Try a prompt like this:")
    print("\n" + textwrap.fill(f'"{prompt_example}"', 58, initial_indent="  ", subsequent_indent="  "))
    print("---------------------------\n")

def print_future_vision(vision_description):
    """Prints the Future Vision box."""
    print("--- [ Future Vision: Direct Integration ] ---")
    print(textwrap.fill(vision_description, 58, initial_indent="  "))
    print("-------------------------------------------\n")

def sanitize_for_directory_name(name):
    """Converts a project name into a filesystem-safe directory name."""
    s = name.strip().lower()
    s = re.sub(r'\s+', '-', s)
    s = re.sub(r'[^a-z0-9-]', '', s)
    return s

def main():
    """Main function to run the project setup wizard."""
    current_time_utc = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    current_user = "regnaer"

    print("="*60)
    print("        Welcome to the Initiative Brief Wizard!")
    print("="*60)
    print("This wizard helps you document a new project or feature")
    print("within this existing repository.")
    
    initiative_name = input("\nWhat is the name of this new initiative or feature?: ")
    dir_name = sanitize_for_directory_name(initiative_name)
    initiative_path = os.path.join("initiatives", dir_name)

    if os.path.exists(initiative_path):
        print(f"\nWarning: An initiative named '{dir_name}' already exists.")
        if input("Do you want to overwrite it? (y/n): ").lower() != 'y':
            print("Aborting.")
            return
    else:
        os.makedirs(initiative_path, exist_ok=True)

    print(f"\nGreat! We will create all documentation in: {initiative_path}/")

    # --- Persona ---
    print_step_header("Define the User Persona", "Who are we building this for? A good persona helps us focus on user needs.")
    print_copilot_pro_tip(f"I'm working on a '{initiative_name}' initiative. Can you help me create a detailed user persona for a 'Mid-level Reinsurance Actuary'? Include their goals, daily tasks, and frustrations.")
    persona = get_multiline_input_from_editor(f"Describe the Primary User Persona for {initiative_name}")

    # --- Problem Statement ---
    print_step_header("Define the Problem", "What specific problem are we solving? A clear problem statement is critical for success.")
    print_copilot_pro_tip(f"Based on the persona of a '{persona}', help me write a clear and concise problem statement about the challenges they face that our '{initiative_name}' initiative will solve.")
    problem = get_multiline_input_from_editor("Describe the Core Problem this initiative solves")

    # --- Business Case ---
    print_step_header("Build the Business Case", "Why should the business invest in this? This justifies the project's existence.")
    print_copilot_pro_tip(f"Given this problem statement: '{problem[:100]}...', help me build a business case for our '{initiative_name}' initiative. Focus on metrics like efficiency gains, error reduction, and competitive advantage.")
    business_case = get_multiline_input_from_editor("Describe the Business Case (Why we should build this)")

    # --- Epics ---
    print_step_header("Define the Initial Epics", "What are the major pieces of work? These will become the top-level items in your backlog.")
    print_copilot_pro_tip(f"Based on the goals for '{initiative_name}', suggest 3-5 initial epics that would form the core of the Minimum Viable Product (MVP).")
    print_future_vision("This is the most exciting opportunity for direct integration. In the future, Copilot will analyze everything you've entered and generate a full, proposed epic backlog for you to approve, edit, or discard.")
    epics = get_multiline_input_from_editor("List the Epics / In-Scope Features (as a bulleted list)")

    # --- Processing and File Generation ---
    print("\n" + "="*60)
    print(f"Processing your inputs and generating files in {initiative_path}...")
    epic_list = [line.strip().lstrip('-* ') for line in epics.splitlines() if line.strip()]

    # Create the main brief document
    brief_content = f"""
    # Initiative Brief: {initiative_name}
    **(Last Updated: {current_time_utc} by @{current_user})**

    ## 1. Executive Summary

    ### Primary Persona
    {persona}

    ### Problem Statement
    {problem}

    ### Business Case
    {business_case}

    ## 2. Proposed Epics
    The following epics represent the high-level scope for this initiative:
    """ + ''.join([f'- {e}\n' for e in epic_list])

    with open(os.path.join(initiative_path, 'BRIEF.md'), 'w') as f:
        f.write(textwrap.dedent(brief_content).strip())
    print(f"- Generated {os.path.join(initiative_path, 'BRIEF.md')}")

    # Create the epic generation script
    script_content = f"#!/bin/sh\n# This script uses the GitHub CLI to create your epics as issues for the '{initiative_name}' initiative.\n"
    for epic in epic_list:
        safe_epic = epic.replace("'", "'\\''")
        script_content += f"gh issue create --title '[{initiative_name}] Epic: {safe_epic}' --body 'This is an epic for the {initiative_name} initiative. It should be broken down into user stories.' --label 'epic,{dir_name}'\n"
    
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
