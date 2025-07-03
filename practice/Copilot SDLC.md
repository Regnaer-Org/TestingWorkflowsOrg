# SDLC Automation Blueprint

This document outlines the phased approach to building an end-to-end, automated software development lifecycle (SDLC) in this repository. Each phase builds upon the last to create a robust, efficient, and repeatable process.

---

### **Phase 1: Initiative Definition & Setup (✅ Completed)**

This phase ensures every project starts with a clear, standardized, and well-documented foundation.

*   **Goal:** To automate the creation of project briefs, user personas, and initial work items (epics).
*   **Key Artifact:** The `project_setup_wizard.py` script located in the `.project_framework/` directory.
*   **Process:**
    1.  A team member runs the interactive wizard (`python .project_framework/project_setup_wizard.py`).
    2.  The wizard guides them to select a reusable persona from the central `/personas` library or create a new one.
    3.  The user provides the initiative name, problem statement, and business case, leveraging Copilot Chat for detailed content generation.
    4.  The user lists the high-level epic titles for the initiative.
*   **Outcome:**
    *   A reusable **Persona Library** is maintained in the `/personas` directory.
    *   A standardized **Initiative Brief** (`BRIEF.md`) is created in a new `/initiatives/{initiative-name}/` directory.
    *   A shell script (`create_epics.sh`) is generated to create the initial epics as GitHub Issues.
    *   The resulting GitHub Issues are automatically labeled and contain a link back to the `BRIEF.md` for full context.

---

### **Phase 2: Development & Continuous Integration (CI)**

This phase focuses on ensuring code quality and automating the testing process.

*   **Goal:** To automatically validate that new code contributions are safe and meet quality standards before they are merged.
*   **Key Artifact:** A GitHub Actions workflow file, e.g., `.github/workflows/ci.yml`.
*   **Process:**
    1.  A developer breaks down an Epic from Phase 1 into smaller user stories or tasks.
    2.  They create a feature branch from `main` to work on a specific task.
    3.  When the work is complete, they open a Pull Request (PR) to merge the feature branch back into `main`.
*   **Automation:**
    *   The `ci.yml` workflow is **triggered automatically** on every PR.
    *   The workflow builds the application, runs linters, and executes all automated tests (unit, integration, etc.).
    *   The PR is blocked from merging until all checks pass, ensuring the `main` branch is always stable.

---

### **Phase 3: Deployment & Release (CD)**

This phase automates the process of delivering the finished product to users.

*   **Goal:** To automatically deploy new versions of the application after they have passed all CI checks.
*   **Key Artifact:** A GitHub Actions workflow file, e.g., `.github/workflows/cd.yml`.
*   **Process:**
    1.  A Pull Request from Phase 2 is reviewed and approved.
    2.  The PR is merged into the `main` branch.
*   **Automation:**
    *   The `cd.yml` workflow is **triggered automatically** on every merge to `main`.
    *   The workflow builds the production version of the application (e.g., a Docker container).
    *   It then pushes the build to a registry (e.g., GitHub Container Registry) and deploys it to the target environment (e.g., a cloud service like Azure or AWS).

---

### **Phase 4: Project & Issue Management**

This phase adds automation to reduce the manual overhead of managing project boards and issues.

*   **Goal:** To keep project boards, labels, and assignments synchronized with the development workflow.
*   **Key Artifact:** One or more GitHub Actions workflow files, e.g., `.github/workflows/management.yml`.
*   **Process:**
    1.  An Epic issue is created (via the wizard or manually).
    2.  A developer links a Pull Request to an issue.
    3.  A Pull Request is merged.
*   **Automation Examples:**
    *   When a new issue with the "Epic" label is created, automatically add it to the "Epics" column of a project board.
    *   When a PR linked to an issue is opened, automatically move the issue to the "In Progress" column.
    *   When the PR is merged, automatically move the linked issue to the "Done" column.
