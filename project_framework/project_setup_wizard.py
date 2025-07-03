import os
import textwrap
import subprocess
import tempfile
from datetime import datetime

def get_multiline_input_from_editor(prompt):
    """
    Opens a command-line editor (nano) to get multi-line input from the user.
    This allows for easy pasting of paragraphs from other documents.
    """
    print(f"\n--- {prompt} ---")
    print("A text editor will now open. Please enter or paste your text.")
    print("When you are finished, save the file and exit:")
    print("  1. Press 'Ctrl+O' (Write Out), then 'Enter' to save.")
    print("  2. Press 'Ctrl+X' to exit the editor.")
    input("Press Enter to continue...")

    editor = os.environ.get('EDITOR', 'nano')
    with tempfile.NamedTemporaryFile(mode='w+', delete=False) as tf:
        tf.write(f"# {prompt}\n# Please enter your text below this line.\n")
        temp_filename = tf.name

    subprocess.run([editor, temp_filename])

    with open(temp_filename, 'r') as tf:
        # Read all lines and filter out the comment lines at the top
        content = [line for line in tf.readlines() if not line.strip().startswith('#')]
        
    os.remove(temp_filename) # Clean up the temporary file
    
    # Join the lines back into a single string
    return "".join(content).strip()

def main():
    """Main function to run the project setup wizard."""
    # --- Get metadata ---
    current_time_utc = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    current_user = "regnaer" # Hardcoded based on user login context

    print("\n--- Project Setup Wizard ---")
    print("This wizard will help you create the foundational documents for your project.")

    # --- Gather Information ---
    project_name = input("\nEnter the project name (e.g., 'Reinsurance Pricing Engine'): ")
    persona = get_multiline_input_from_editor("Primary User Persona")
    problem = get_multiline_input_from_editor("Core Problem Statement")
    business_case = get_multiline_input_from_editor("Business Case")
    goals = get_multiline_input_from_editor("Project Goals (as a bulleted list)")
    stakeholders = get_multiline_input_from_editor("Key Stakeholders (as a bulleted list)")
    glossary_input = get_multiline_input_from_editor("Glossary Terms (format: TERM: Definition, one per line)")
    epics = get_multiline_input_from_editor("Epics / In-Scope Features (as a bulleted list)")
    
    # --- Process list-based inputs ---
    goal_list = [line.strip().lstrip('-* ').capitalize() for line in goals.splitlines() if line.strip()]
    stakeholder_list = [line.strip().lstrip('-* ').capitalize() for line in stakeholders.splitlines() if line.strip()]
    epic_list = [line.strip().lstrip('-* ').capitalize() for line in epics.splitlines() if line.strip()]
    
    glossary = {}
    for line in glossary_input.splitlines():
        if ':' in line:
            term, definition = line.split(':', 1)
            glossary[term.strip()] = definition.strip()

    # --- Generate Files ---
    print("\nProcessing...")

    if not os.path.exists('docs'):
        os.makedirs('docs')
        print("- Creating docs/ directory")

    # 1. README.md
    print("- Generating README.md")
    readme_content = f"""
    # {project_name}
    **(Last Updated: {current_time_utc} by @{current_user})**

    ## 1. Executive Summary

    ### Problem
    {problem}

    ### Solution
    This project aims to deliver a solution that addresses the core problem by focusing on the goals outlined below. The primary user for this solution is the **{persona}**.

    ### Business Case
    {business_case}

    ## 2. Project Goals

    The primary objectives for this project are:
    {''.join([f'- {goal}\\n' for goal in goal_list])}
    ## 3. Stakeholders

    The key stakeholders for this project are:
    {''.join([f'- {stakeholder}\\n' for stakeholder in stakeholder_list])}
    """
    with open('README.md', 'w') as f:
        f.write(textwrap.dedent(readme_content).strip())

    # 2. Persona Card
    print("- Generating docs/persona_card.md")
    persona_content = f"""
    # Persona Card: {persona}

    *(This is a placeholder. The Product Owner should expand this with more details about the user's goals, frustrations, and daily tasks.)*
    """
    with open('docs/persona_card.md', 'w') as f:
        f.write(textwrap.dedent(persona_content).strip())

    # 3. Glossary
    print("- Generating docs/reinsurance_terms_glossary.md")
    glossary_content = "# Reinsurance Terms Glossary\n\n"
    for term, definition in glossary.items():
        glossary_content += f"### {term}\n{definition}\n\n"
    with open('docs/reinsurance_terms_glossary.md', 'w') as f:
        f.write(glossary_content.strip())

    # 4. Epic Creation Script
    print("- Generating create_epics.sh to create your issues in GitHub")
    script_content = "#!/bin/sh\n"
    for epic in epic_list:
        safe_epic_title = epic.replace("'", "'\\''")
        script_content += f"gh issue create --title 'Epic: {safe_epic_title}' --body 'This is an epic. It should be broken down into user stories.' --label 'epic'\n"

    with open('create_epics.sh', 'w') as f:
        f.write(script_content)
    os.chmod('create_epics.sh', 0o755)

    print("\n--- Setup Complete! ---")
    print("Your project foundation has been created.\n")
    print("NEXT STEP: To create your initial epics in GitHub, run the following command:")
    print("sh create_epics.sh\n")
    print("After that, commit and push your newly generated files.")

if __name__ == '__main__':
    main()
