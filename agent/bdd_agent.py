"""
File: agent/bdd_agent.py
Description: BDD Agent sub-agent component of the QA Pilot system. Responsible for analyzing Jira user story descriptions and generating structured Gherkin scenario definitions (Given/When/Then).
Role in Architecture: Orchestrated by QAOrchestrator to construct the happy-path behavior specifications for the feature under test.
"""

import os
from google.antigravity import Agent, LocalAgentConfig
from google.antigravity.hooks import policy
from dotenv import load_dotenv

# Load env variables
load_dotenv()

class BDDAgent:
    """
    An ADK sub-agent that receives ticket content and generates Gherkin BDD scenarios
    in Given/When/Then format covering happy path and main workflows.
    """
    def __init__(self):
        """
        Initializes the BDDAgent with appropriate Gemini LLM model and system instructions.
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
                "You are an expert QA Engineer. Analyze the given Jira ticket details and generate Gherkin/BDD scenarios "
                "covering the happy path and main workflows. Use standard Given/When/Then formatting. "
                "Do NOT write any files or use any tools to edit files."
            )
        )

    async def generate_bdd(self, ticket_content: str) -> str:
        """
        Generates structured BDD Gherkin scenarios from the retrieved Jira ticket contents.

        Parameters:
            ticket_content (str): The summary and description text of the target Jira user story.

        Returns:
            str: The generated Gherkin test scenarios content.
        """
        try:
            async with Agent(config=self.config) as agent:
                response = await agent.chat(f"Analyze this ticket and generate Gherkin/BDD scenarios:\n{ticket_content}")
                return await response.text()
        except Exception as e:
            return f"Error generating BDD scenarios: {str(e)}"

