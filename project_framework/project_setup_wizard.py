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

def sanitize_for_filename(name):
    """Converts a name into a filesystem-safe filename."""
    s = name.strip().lower()
    s = re.sub(r'\s+', '-', s)
    s = re.sub(r'[^a-z0-9-]', '', s)
    return s

def handle_persona_selection():
    """Manages the creation or selection of a user persona."""
    persona_dir = "personas"
    os.makedirs(persona_dir, exist_ok=True)
    
    existing_personas = [f for f in os.listdir(persona_dir) if f.endswith('.md')]
    
    if not existing_personas:
        print("No existing personas found. Let's create the first one.")
        return create_new_persona(persona_dir)

    print("Found existing personas:")
    for i, p_file in enumerate(existing_personas):
        display_name = os.path.splitext(p_file)[0].replace('-', ' ').title()
        print(f"  {i + 1}: {display_name}")
    
    print(f"  {len(existing_personas) + 1}: Create a new persona")

    while True:
        try:
            choice = int(input("Choose an option: "))
            if 1 <= choice <= len(existing_personas):
                return os.path.join(persona_dir, existing_personas[choice - 1])
            elif choice == len(existing_personas) + 1:
                return create_new_persona(persona_dir)
            else:
                print("Invalid choice. Please try again.")
        except ValueError:
            print("Invalid input. Please enter a number.")

def create_new_persona(persona_dir):
    """Guides the user to create a new persona file."""
    print_step_header("Create a New User Persona", "A great persona is the foundation of a great project. Generate a detailed persona and paste the entire thing here.")
    print_copilot_pro_tip("Create a detailed user persona card for a [persona title, e.g., 'Mid-level Reinsurance Actuary']. Include their goals, skills, daily tasks, and frustrations in Markdown format.")
    
    persona_title = input("What is the title of this new persona? (e.g., Mid-level Reinsurance Actuary): ")
    filename = sanitize_for_filename(persona_title) + ".md"
    filepath = os.path.join(persona_dir, filename)
    
    persona_content = get_multiline_input_from_editor(f"Paste the full persona card for '{persona_title}'")
    
    with open(filepath, 'w') as f:
        f.write(f"# Persona: {persona_title}\n\n{persona_content}")
    
    print(f"\nPersona created and saved to: {filepath}")
    return filepath

def main():
    """Main function to run the project setup wizard."""
    current_time_utc = "2025-07-03 03:28:11"
    current_user = "regnaer"

    print("="*60)
    print("        Welcome to the Initiative Brief Wizard!")
    print("="*60)
    
    persona_path = handle_persona_selection()
    
    initiative_name = input("\nWhat is the name of this new initiative or feature?: ")
    dir_name = sanitize_for_filename(initiative_name)
    initiative_path = os.path.join("initiatives", dir_name)

    os.makedirs(initiative_path, exist_ok=True)
    print(f"\nGreat! We will create all documentation in: {initiative_path}/")

    print_step_header("Define the Problem", "Use Copilot to help you draft a clear and compelling problem statement, then paste the full text here.")
    print_copilot_pro_tip(f"Based on our selected persona, help me write a detailed problem statement about the challenges they face that our '{initiative_name}' initiative will solve. Use Markdown to structure it.")
    problem = get_multiline_input_from_editor("Paste the full Problem Statement")

    print_step_header("Build the Business Case", "This justifies the project's existence. Generate a comprehensive business case and paste the entire text here.")
    print_copilot_pro_tip(f"Given the problem statement for the '{initiative_name}' initiative, help me build a business case. Focus on metrics like efficiency gains, error reduction, and competitive advantage. Format it in Markdown.")
    business_case = get_multiline_input_from_editor("Paste the full Business Case")

    print_step_header("List the Epic Titles", "Finally, list the titles of the major epics for this initiative. Enter one epic title per line.")
    print_copilot_pro_tip(f"Based on the business case for '{initiative_name}', suggest 3-5 high-level epic titles that would form the core of the MVP.")
    epics_raw = get_multiline_input_from_editor("List the Epic Titles (one per line)")

    print("\n" + "="*60)
    print(f"Processing your inputs and generating files in {initiative_path}...")
    
    epic_titles = [line.strip() for line in epics_raw.splitlines() if line.strip()]

    repo_slug = os.environ.get('GITHUB_REPOSITORY', 'owner/repo-name')
    brief_url = f"https://github.com/{repo_slug}/blob/main/{initiative_path}/BRIEF.md"
    hierarchy_url = f"https://github.com/{repo_slug}/blob/main/backlog_hierarchy_best_practices.md"
    
    relative_persona_path = os.path.join("..", "..", persona_path).replace(os.path.sep, '/')
    brief_content = f"""
# Initiative Brief: {initiative_name}
**(Last Updated: {current_time_utc} by @{current_user})**
---
##
