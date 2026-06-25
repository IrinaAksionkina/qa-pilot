"""
File: agent/skills/create_jira_ticket.py
Description: Story Creation Skill module. Implements user story generation with ADF formatting rules and validations.
Role in Architecture: Regsiters as an ADK tool/skill in the QAOrchestrator context to process clean Jira User Story tickets.
"""

import os
import re
import asyncio
from google.antigravity import Agent, LocalAgentConfig, types
from typing import Annotated
from pydantic import SkipValidation
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
        "Follow these strict steps:\n"
        "1. Validate the feature_name. If the feature name is too vague (e.g. 'app', 'AI'), "
        "return 'Validation Error: [reason]. Please be more specific.'\n"
        "2. Otherwise, generate a user story title (maximum 10 words).\n"
        "3. Construct the description parameter strictly as a valid Jira Atlassian Document Format (ADF) JSON dictionary. "
        "The ADF structure must contain exactly: \n"
        "   - Heading 2 with text 'Story Description'\n"
        "   - Paragraph text matching: 'As a [user], I want to [action] so that [benefit]'\n"
        "   - Heading 2 with text 'Scope of Work'\n"
        "   - Bullet List (bulletList) containing 3 to 5 plain-text listItem nodes\n"
        "   - Heading 2 with text 'Acceptance Criteria'\n"
        "   - One Ordered List (orderedList) where each listItem contains a paragraph with the Scenario title only (having the strong mark applied), "
        "and Gherkin steps as separate plain-text paragraphs (no bold, and do NOT use the indent attribute as it is unsupported in this context).\n"
        "4. Immediately invoke the `create_issue` tool on the `jira` server transport, passing the generated title as 'summary', the structured ADF JSON dictionary object as 'description', and 'Story' as 'issue_type'.\n"
        "5. On success, return exactly: 'Success: Created issue [ticket ID] with title: [Generated Title]'."
    )
    
    config = LocalAgentConfig(
        model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        mcp_servers=mcp_servers,
        system_instructions=system_instructions
    )
    
    async with Agent(config=config) as agent:
        response = await agent.chat(f"Process and create a Jira user story for the feature: {feature_name}")
        return await response.text()
