# SDLC Automation Blueprint v3: The Team Edition
**(Last Updated: 2025-07-03 01:46:31 by @regnaer)**

This document outlines a guided, integrated, and automated Software Development Lifecycle (SDLC) process designed for a full agile delivery team. It functions as a "project-in-a-box" template repository, leveraging reusable scripts and GitHub Copilot to create a unified workflow and single source of truth.

**Target Audience:** This framework is for the entire delivery team.
*   **Product Owner (PO):** To define vision, manage the backlog, and ensure business value is delivered.
*   **Developers (Devs):** To build and implement high-quality, context-aware code efficiently.
*   **Testers (QA):** To ensure quality and automate testing based on clear requirements.
*   **Scrum Master/Project Manager (SM/PM):** To facilitate the process, track progress, and remove impediments.
*   **Subject Matter Experts (SMEs):** To inject critical domain knowledge directly into the workflow.

---

## Phase 1: Project Kick-off & Automated Setup

**Goal:** Go from a raw idea to a fully structured repository with a populated README and initial backlog, ensuring universal team alignment from day one.

**Key Automation: The `project_setup_wizard.py` script**

**Workflow:**
1.  **Initiation (PO, SME, SM/PM):** The PO and SME run the wizard together. The SM/PM facilitates.
2.  **The Wizard Asks:** The script prompts for core project information (problem statement, goals, scope, stakeholders, etc.). The SME provides definitions for the glossary.
3.  **Automation in Action:** The script commits the following to the repository:
    *   **`README.md`**: The single source of truth for project vision and goals.
    *   **`docs/reinsurance_terms_glossary.md`**: A centralized glossary, seeded by the SME.
    *   **`docs/persona_card.md`**: A clear definition of the target user.
    *   **GitHub Epics**: Automatically creates issues in the repo for each "IN SCOPE" item, labeled as `epic`. This instantly populates the high-level backlog for the PO.

**How Each Role Benefits:**
*   **PO:** Gets an immediate, structured backlog of epics to begin planning.
*   **SME:** Their knowledge is captured and codified from the very beginning.
*   **SM/PM:** The project starts with clear artifacts, reducing ambiguity.
*   **Devs/QA:** Can immediately understand the project's vision, scope, and key terminology.

---

## Phase 2: Requirement Breakdown & Visual Design

**Goal:** Collaboratively refine epics into actionable user stories and create simple design mockups.

**Workflow:**
1.  **Backlog Refinement (PO, Devs, QA):** In a backlog refinement session, the team uses Copilot Chat to break down an epic.
    *   **Prompt (led by PO):** `"I am breaking down the epic titled: '[Paste Epic Title Here]'. Using our `reinsurance_terms_glossary.md` for correct terminology, generate user stories with Gherkin-style acceptance criteria for the 'Junior Actuarial Analyst' persona."`
    *   The team discusses the output, and the PO creates the stories as new issues in the repo.

2.  **Architectural & UI/UX Design (Devs, PO, QA):**
    *   **Architecture (Devs):** Generate Mermaid diagrams in markdown to propose and discuss technical approaches.
    *   **Mockups (Devs/PO):** Use Copilot to quickly generate simple HTML mockups of the UI. This gives the PO and QA a tangible preview to validate the user experience before any complex code is written.
        *   **Prompt:** `"Generate a simple HTML page using Pico.css with a title, a file input, a 'Run Calculation' button, and a placeholder for a results table."`

**How Each Role Benefits:**
*   **PO:** Can clearly articulate requirements and validate UI concepts early.
*   **Devs:** Get clear, visual guidance and well-defined acceptance criteria.
*   **QA:** The Gherkin acceptance criteria become the direct blueprint for their test cases.

---

## Phase 3: Guided, Domain-Aware Coding

**Goal:** Write high-quality code that is deeply integrated with the project's business logic.

**Workflow:**
1.  **Context-Primed Development (Devs):** Before starting a user story, the developer has the user story issue, the glossary, and related code files open. This "primes" Copilot with the necessary context.
2.  **Pair Programming with AI (Devs, SME):** A developer can pair with an SME. The SME explains the complex business logic (e.g., "now we need to apply the loss development factor"), and the developer translates that into a descriptive comment for Copilot to generate the code.
3.  **Step-by-Step Guided Coding:** Developers use prompts like `"What's the first step to implement the calculation from user story #25?"` to have Copilot guide them through the implementation, ensuring best practices.

**How Each Role Benefits:**
*   **Devs:** Accelerate development and reduce the mental load of recalling specific business rules.
*   **SME:** Can directly influence the code's logic without needing to write it themselves.
*   **PO/QA:** The resulting code is more likely to be correct from the start, reducing bugs and rework.

---

## Phase 4: Context-Aware Testing

**Goal:** Tightly couple testing with development, using the user stories as the source of truth for test cases.

**Workflow:**
1.  **BDD in Practice (Devs, QA):**
    *   **Devs:** As part of the user story, they are responsible for writing the automated unit tests. They use Copilot to generate tests that directly correspond to the acceptance criteria.
        *   **Prompt:** `"Write a pytest unit test for the function I just created. Use the acceptance criteria from user story #25 as the basis for the test cases."`
    *   **QA:** Reviews the automated tests to ensure all acceptance criteria are covered. They can focus their manual and exploratory testing on more complex, edge-case scenarios.

**How Each Role Benefits:**
*   **QA:** Can trust that the core logic is covered by automation, freeing them up for higher-value testing activities. Traceability from requirement to test is guaranteed.
*   **Devs:** Fulfill "definition of done" criteria more easily by generating tests as they code.
*   **SM/PM:** The passing of these tests is a clear, objective measure of progress for a user story.

---

## Phase 5: Simple, Extendable Deployment

**Goal:** Implement a foundational CI/CD pipeline that proves the concept of automated builds and testing, with a clear path to production-grade deployment.

**Workflow:**
1.  **CI Pipeline (Devs):** Use Copilot to generate a simple GitHub Actions workflow that runs the linter and the automated tests on every push to the `main` branch. This provides immediate feedback on code quality.
2.  **Documenting the Future (Devs, PO):** The `README.md`'s "Future Deployment Strategy" section is updated. The PO can contribute user-facing release considerations, while Devs outline the technical path to a full production environment (Docker, cloud services, etc.).

**How Each Role Benefits:**
*   **Devs:** Get instant feedback on their commits.
*   **Everyone:** Has visibility into the health of the codebase. A green checkmark on a commit is a universal sign of quality.

---

## Phase 6: Automated Documentation Hub

**Goal:** Create a "living" documentation site that is automatically generated from the team's work, requiring minimal manual effort.

**Key Automation: The "Generate Docs" GitHub Action**

**Workflow:**
1.  **Manual Trigger (PO/SM/PM):** After a sprint or before a release, the PO or SM/PM can manually trigger the "Generate Docs" workflow in GitHub Actions.
2.  **The Action Runs:** The workflow executes a script that:
    *   Generates API docs from code comments (for Devs).
    *   Generates a draft User Guide from all user stories marked as 'done' (for POs and end-users).
    *   Generates a `KNOWN_ISSUES.md` file from all open `bug` reports (for everyone).
    *   Collates the math libraries, design decisions, and other key artifacts.
    *   Publishes everything to a clean, searchable GitHub Pages website.

**How Each Role Benefits:**
*   **PO:** Gets an auto-generated draft of release notes and user guides.
*   **SM/PM:** Has a central place to point stakeholders for project status and documentation.
*   **Devs:** Never have to worry about outdated API documentation again.
*   **New Team Members:** Have a comprehensive, up-to-date site to learn everything about the project.
