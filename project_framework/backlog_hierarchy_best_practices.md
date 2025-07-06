# Backlog Hierarchy & Best Practices

## Native GitHub Functionality

- **Epics, Features, Stories, and Tasks can all be represented as GitHub Issues.**
- **Epic**: Use the "Epic" issue type or label. An Epic is a large body of work that can be broken down into Features and Stories. Link Features and Stories as sub-issues to the Epic.
- **Feature**: Use the "Feature" issue type or label. A Feature is a service or function that delivers business value, broken down into Stories and Tasks.
- **Story**: Use the "Story" issue type or label. Stories represent vertical slices of functionality with clear acceptance criteria.
- **Task**: Use the "Task" issue type or label. Tasks are small units of work, typically technical or supporting a Story.

**Sub-issues**:  
GitHub supports linking issues using the "linked issues" feature. Use "is blocked by", "blocks", or "relates to" to define relationships.  
You can also use checklists in the parent Epic or Feature to track progress on sub-issues.

---

## Hierarchy Structure

- **Epic**
  - Feature 1
    - Story 1.1
      - Task 1.1.1
      - Task 1.1.2
    - Story 1.2
  - Feature 2
    - Story 2.1

---

## Agile Delivery Principles

- **INVEST** for Stories:
  - **I**ndependent
  - **N**egotiable
  - **V**aluable
  - **E**stimable
  - **S**mall
  - **T**estable

- **The 3 C’s** for User Stories:
  - **Card**: Short description (title + summary)
  - **Conversation**: Details discussed between team and stakeholders
  - **Confirmation**: Acceptance criteria are defined and agreed

- **DEEP** for Product Backlogs:
  - **D**etailed appropriately
  - **E**stimable
  - **E**mergent (evolving)
  - **P**rioritized

---

## Issue Types & Labels

- Use GitHub's "Issue Type" if enabled (Epic, Feature, Story, Task).
- Otherwise, use standardized labels:  
  - `type: epic`
  - `type: feature`
  - `type: story`
  - `type: task`

---

## Tips for Managing the Backlog

- Always link sub-issues to their parent Epic/Feature using GitHub’s linking/relationship features.
- Use checklists in Epic/Feature issue bodies to track progress on sub-issues.
- Regularly groom and prioritize the backlog to keep it actionable and DEEP.
- Ensure each Story meets INVEST and has clear acceptance criteria (confirmation).

---

## Example: Epic Issue Body

```markdown
## Epic: Automated Pricing Workflow

### Features
- [ ] [Feature: Dynamic Rate Calculation](#123)
- [ ] [Feature: Real-time Reporting](#124)

### Stories & Tasks
- [ ] [Story: As a user, I want to upload data...](#125)
    - [ ] [Task: Implement file upload endpoint](#126)
    - [ ] [Task: Validate data format](#127)
```

---
