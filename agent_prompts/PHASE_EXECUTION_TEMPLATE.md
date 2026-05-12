# Phase Execution Template for Coding Agent

Use this template when asking an agent to implement a phase.

```text
You are working on the Investment Analysis MVP repository.

Read these files first:
- README.md
- docs/00_PROJECT_BRIEF.md
- docs/01_ARCHITECTURE.md
- docs/02_REPOSITORY_STRUCTURE.md
- docs/[PHASE_FILE].md
- agent_prompts/AGENT_MASTER_PROMPT.md

Implement only [PHASE_NAME].

Constraints:
- Do not implement later phases.
- Do not add real API keys or secrets.
- Use clear, typed Python.
- Add or update tests.
- Keep provider calls behind connector classes.
- Store raw data before normalisation when applicable.
- Make the implementation robust to missing data.

Before finishing:
- Run tests.
- Confirm acceptance criteria.
- Summarise files changed.
- List any assumptions and next recommended phase.
```
