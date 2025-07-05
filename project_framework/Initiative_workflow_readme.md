# Initiative Workflow Solution (Docs & Wizard)

This solution provides a repeatable, product-owner/BA-friendly workflow for defining, documenting, and refining initiatives using Markdown files, linked issues, personas, and assistive Copilot prompts.

## What It Does

- Guides the user through a series of questions to capture all key initiative info.
- Generates a Markdown file (`initiative.md`) for each new initiative under `initiatives/{initiative-name}`.
- Links to all involved personas, epics, and any related issues.
- Provides a safe, non-destructive file structure—manual edits are allowed and only auto-generated sections are updated by the wizard.
- Scaffolds Mermaid diagrams based on user description.
- Embeds Copilot/LLM prompt snippets for quality-of-life improvement.
- Outputs a shell script to create epic issues, with Copilot guidance in each epic.

## Key Features

- Supports selection/creation of one or more personas per initiative.
- Allows linking of existing GitHub issues.
- Adds quick prompts for Copilot and LLMs to help with further refinement.
- Encourages but does not require diagrams; rough Mermaid scaffolds are auto-generated if a description is provided.
- Initiative file is designed to be the authoritative source for all future documentation, release notes, and refinement prompts.

## Getting Started

1. Run the wizard:
   ```
   python project_framework/project_setup_wizard.py
   ```
2. Follow the prompts to fill in details.
3. Run the generated `create_epics.sh` to create your initial epic issues.
4. Manually refine `initiative.md` as the project evolves.

## Next Steps

- Action-based maintenance (auto-sync, drift detection, release note generation) to be added after initial testing.
- See `project_framework/copilot_prompt_guide.md` for more Copilot usage ideas.

---
