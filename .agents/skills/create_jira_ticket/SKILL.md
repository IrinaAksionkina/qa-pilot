---
name: create_jira_ticket
description: Generates a Jira user story from a feature request, formats it into Atlassian Document Format (ADF), validates inputs, and registers the ticket in the Jira issue tracker.
---

# Jira Story Ticket Creation Skill

This skill allows the QA Orchestration agent to automatically process a raw feature description and convert it into a structured, single-focus Jira user story.

## Capabilities

1. **Feature Input Validation**: Rejects input names that are generic, empty, or represent potential prompt injections.
2. **ADF Formatting**: Builds Atlassian Document Format JSON trees containing:
   - "Story Description" heading.
   - Gherkin format paragraphs.
   - Ordered/unordered lists for developers and acceptance criteria.
3. **Jira Registration**: Creates the Story issue directly using the Jira MCP server `create_issue` tool.

## Structure Details
The skill functions by executing python logic defined in `agent/skills/create_jira_ticket.py` utilizing the Jira MCP Server.
