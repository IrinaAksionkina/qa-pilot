---
name: generate_test_cases
description: Fetches user stories, runs BDD and Edge Case generation agents, creates linked Manual and Cucumber Jira test tickets, and synchronizes test structures to Xray.
---

# QA Test Case Generation and Xray Synchronization Skill

This skill analyzes target Jira user stories, generates BDD happy-path workflows and negative boundary condition scenarios, and synchronizes the results to Jira Xray.

## Workflow

1. **Jira Story Parsing**: Fetches the user story and parses description fields for user narratives and acceptance criteria.
2. **BDD Scenario Generation**: Executes `BDDAgent` to produce Cucumber scenarios.
3. **Edge Case Analysis**: Executes `EdgeCaseAgent` to identify validation boundaries.
4. **Link Relationships**: Links newly generated "Test" type tickets directly to the story ("is tested by").
5. **Xray Synchronization**: Connects to the Xray Cloud GraphQL endpoint to write manual test steps and Cucumber definitions.
