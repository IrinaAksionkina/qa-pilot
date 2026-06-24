"""
File: agent/skills/create_jira_ticket.py
Description: Story Creation Skill module. Implements user story generation with ADF formatting rules and validations.
Role in Architecture: Regsiters as an ADK tool/skill in the QAOrchestrator context to process clean Jira User Story tickets.
"""

import os
import re
import asyncio
from google.antigravity import Agent, LocalAgentConfig, types
from dotenv import load_dotenv
from agent.guardrails import validate_feature_input

# Load env variables
load_dotenv()

async def create_jira_ticket(feature_name: str) -> str:
    """
    An ADK skill (tool) that generates a realistic Jira user story from a feature name,
    validates the input, creates the ticket in Jira, and links it.

    Parameters:
        feature_name (str): The name/concept of the feature.

    Returns:
        str: Status response indicating success message or validation error.
    """
    # Security Guardrail Check 2: Validate feature input name size, prompt injections & vagueness
    is_valid, err_msg = validate_feature_input(feature_name)
    if not is_valid:
        return f"Validation Error: {err_msg}"

    # Configure the standard Jira MCP server in the current virtual environment
    python_bin = os.path.join(os.getcwd(), ".venv", "bin", "python3")
    mcp_servers = [
        types.McpStdioServer(
            name="jira",
            command=python_bin,
            args=["mcp/jira_mcp_server.py"]
        )
    ]
    
    # Precise rules for validation, formatting, and issue creation
    system_instructions = (
        "You are an expert product manager. Your task is to process a feature request and create a Jira ticket.\n"
        "Follow these strict steps and constraints:\n"
        "1. Validate the feature_name. If the feature name is too vague, broad, or generic (e.g. 'database', 'app', 'website', 'AI', 'test'), "
        "you MUST immediately return a validation error starting with: 'Validation Error: [reason]. Please be more specific.'\n"
        "2. If valid, generate a user story covering ONE functionality only.\n"
        "3. Title: Maximum 10 words.\n"
        "4. Construct the description field exactly as a valid Jira Atlassian Document Format (ADF) JSON dictionary. "
        "The ADF structure must have exactly these three sections in content:\n"
        "   - A Heading 2 with text 'Story Description'\n"
        "   - A Paragraph with text formatted exactly as: 'As a [user], I want to [action] so that [benefit]'\n"
        "   - A Heading 2 with text 'Scope of Work'\n"
        "   - A Bullet List (bulletList) containing a maximum of 5 developer-focused list items (each containing a paragraph with plain text)\n"
        "   - A Heading 2 with text 'Acceptance Criteria'\n"
        "   - ONE Ordered List (orderedList) node for the scenarios (min 2, max 4 scenarios), where each listItem contains:\n"
        "     * A first paragraph with the Scenario title only (e.g. 'Scenario: Successful login with valid credentials') having the 'strong' mark (bold) applied.\n"
        "     * Following that paragraph inside the same listItem, each Gherkin step (Given, When, And, Then) as a separate, plain text paragraph (no bold, not a nested list) with the 'indent' attribute set to 1 (attrs: { 'indent': 1 }).\n"
        "5. Call the `create_issue` tool on the Jira MCP server passing the generated title as 'summary', the ADF JSON dictionary as 'description', and 'Story' as 'issue_type'.\n"
        "6. On success, return exactly: 'Success: Created issue [ticket ID] with title: [Generated Title]'.\n"
        "7. CRITICAL: Do NOT write or edit any local files, and do NOT run shell commands."
    )
    
    config = LocalAgentConfig(
        model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        mcp_servers=mcp_servers,
        system_instructions=system_instructions
    )
    
    async with Agent(config=config) as agent:
        response = await agent.chat(f"Process and create a Jira user story for the feature: {feature_name}")
        return await response.text()
