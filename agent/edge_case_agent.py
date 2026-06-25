"""
File: agent/edge_case_agent.py
Description: Edge Case Agent sub-agent component of the QA Pilot system. Responsible for analyzing target Jira ticket parameters to extract negative flows, boundary values, validation tests, and non-happy path conditions.
Role in Architecture: Orchestrated by QAOrchestrator to produce structured markdown test verification suites.
"""

import os
from google.antigravity import Agent, LocalAgentConfig
from google.antigravity.hooks import policy
from dotenv import load_dotenv

# Load env variables
load_dotenv()

class EdgeCaseAgent:
    """
    An ADK sub-agent that receives ticket content and generates edge case and negative
    test scenarios in a structured table format with columns: Test Case, Steps, Expected Result.
    """
    def __init__(self):
        """
        Initializes the EdgeCaseAgent with Gemini config and negative testing prompt instructions.
        """
        self.config = LocalAgentConfig(
            model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite"),
            policies=[
                policy.deny("create_file"),
                policy.deny("edit_file"),
                policy.deny("run_command"),
                policy.allow("*")
            ],
            system_instructions=(
                "You are an expert QA Architect. Analyze the given Jira ticket details and generate edge case and negative "
                "test scenarios in a structured Markdown table format with exactly three columns: | Test Case | Steps | Expected Result |. "
                "Do NOT write any files or use any tools to edit files."
            )
        )

    async def generate_edge_cases(self, ticket_content: str) -> str:
        """
        Generates edge case and negative test scenarios from ticket content.

        Parameters:
            ticket_content (str): Text details of the Jira User Story to analyze.

        Returns:
            str: Generated Markdown table containing negative test cases.
        """
        try:
            async with Agent(config=self.config) as agent:
                response = await agent.chat(f"Analyze this ticket and generate edge cases and negative test scenarios:\n{ticket_content}")
                return await response.text()
        except Exception as e:
            return f"Error generating edge cases: {str(e)}"

