import os
import textwrap
import subprocess
import tempfile
from datetime import datetime

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

def main():
    """Main function to run the project setup wizard."""
    current_time_utc = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    current_user = "regnaer"

    print("="*60)
    print("        Welcome to the Project Setup Wizard!")
    print("="*60)
    print("This wizard will guide you through creating the foundational")
    print("documents for your project, using Copilot as your partner.")
    
    project_name = input("\nFirst, what is the official project name?: ")

    # --- Persona ---
    print_step_header("Define the User Persona", "Who are we building this for? A good persona helps us focus on user needs.")
    print_copilot_pro_tip("I'm building a reinsurance pricing tool. Can you help me create a detailed user persona for a 'Mid-level Reinsurance Actuary'? Include their goals, daily tasks, and frustrations with current tools like Excel.")
    print_future_vision("In the future, Copilot could analyze your project description and automatically suggest a detailed persona for you.")
    persona = get_multiline_input_from_editor(f"Describe the Primary User Persona for {project_name}")

    # --- Problem Statement ---
    print_step_header("Define the Problem", "What specific problem are we solving? A clear problem statement is critical for success.")
    print_copilot_pro_tip(f"Based on the persona of a '{persona}', help me write a clear and concise problem statement about the challenges they face with the current, Excel-based reinsurance pricing process.")
    print_future_vision("In the future, Copilot could analyze a business requirements document and draft the problem statement for your approval.")
    problem = get_multiline_input_from_editor("Describe the Core Problem this project solves")

    # --- Business Case ---
    print_step_header("Build the Business Case", "Why should the business invest in this? This justifies the project's existence.")
    print_copilot_pro_tip(f"Given this problem statement: '{problem[:100]}...', help me build a business case. Focus on metrics like efficiency gains, error reduction, and competitive advantage.")
    print_future_vision("In the future, Copilot could analyze the problem statement and market data to generate a business case with ROI estimates.")
    business_case = get_multiline_input_from_editor("Describe the Business Case (Why we should build this)")

    # --- Goals ---
    print_step_header("List the Project Goals", "What does success look like? Goals should be clear and measurable.")
    print_copilot_pro_tip(f"Based on the business case for '{project_name}', suggest 3-5 high-level project goals. Frame them as measurable outcomes (e.g., 'Reduce X by Y%').")
    goals = get_multiline_input_from_editor("List the Project Goals (as a bulleted list)")

    # --- Glossary ---
    print_step_header("Create a Glossary", "What key terms will we use? A shared vocabulary prevents confusion.")
    print_copilot_pro_tip(f"I'm building a '{project_name}'. Can you generate a list of 10-15 key technical and business terms that a new team member would need to know? Format them as TERM: Definition.")
    glossary_input = get_multiline_input_from_editor("List Glossary Terms (format: TERM: Definition, one per line)")

    # --- Epics ---
    print_step_header("Define the Initial Epics", "What are the major pieces of work? These will become the top-level items in your backlog.")
    print_copilot_pro_tip(f"Based on the goals for '{project_name}', suggest 3-5 initial epics that would form the core of the Minimum Viable Product (MVP).")
    print_future_vision("This is the most exciting opportunity for direct integration. In the future, Copilot will analyze everything you've entered and generate a full, proposed epic backlog for you to approve, edit, or discard.")
    epics = get_multiline_input_from_editor("List the Epics / In-Scope Features (as a bulleted list)")

    # --- Processing and File Generation ---
    print("\n" + "="*60)
    print("Processing your inputs and generating files...")
    goal_list = [line.strip().lstrip('-* ') for line in goals.splitlines() if line.strip()]
    epic_list = [line.strip().lstrip('-* ') for line in epics.splitlines() if line.strip()]
    glossary = {term.strip(): definition.strip() for line in glossary_input.splitlines() if ':' in line for term, definition in [line.split(':', 1)]}

    if not os.path.exists('docs'):
        os.makedirs('docs')
    
    with open('README.md', 'w') as f:
        f.write(f"# {project_name}\n**(Last Updated: {current_time_utc} by @{current_user})**\n\n"
                f"## 1. Executive Summary\n\n### Problem\n{problem}\n\n### Business Case\n{business_case}\n\n"
                f"## 2. Project Goals\nThe primary objectives are:\n" + ''.join([f'- {g}\n' for g in goal_list]))
    print("- Generated README.md")

    with open('docs/persona_card.md', 'w') as f: f.write(f"# Persona Card\n\n## {persona}\n\n*(This is a placeholder...)*")
    print("- Generated docs/persona_card.md")

    with open('docs/glossary.md', 'w') as f:
        f.write("# Project Glossary\n\n" + ''.join([f"### {term}\n{definition}\n\n" for term, definition in glossary.items()]))
    print("- Generated docs/glossary.md")

    script_content = "#!/bin/sh\n# This script uses the GitHub CLI to create your epics as issues.\n"
    for epic in epic_list:
        safe_epic = epic.replace("'", "'\\''")
        script_content += f"gh issue create --title 'Epic: {safe_epic}' --body 'This is an epic. It should be broken down into user stories.' --label 'epic'\n"
    with open('create_epics.sh', 'w') as f: f.write(script_content)
    os.chmod('create_epics.sh', 0o755)
    print("- Generated create_epics.sh")

    print("\n--- Setup Complete! ---")
    print("Your project foundation has been created in your Codespace.\n")
    print("--- YOUR NEXT STEP ---")
    print("The 'create_epics.sh' script has been generated. This script")
    print("is a simple automation that will create your epics in GitHub.")
    print("\nIn your terminal, run the following command:")
    print("sh create_epics.sh\n")
    print("After that, commit and push your new files to save them.")

if __name__ == '__main__':
    main()
