"""
File: agent/orchestrator.py
Description: Master QA Orchestrator agent. Fetches user stories, invokes BDD and Edge Case generation sub-agents, formats results, creates test tickets, and synchronizes test structures to Xray.
Role in Architecture: Orchestrates the multi-agent system workflow, links Jira issues, and maps results to structured tests.
"""

import os
import re
import requests
from google.antigravity import Agent, LocalAgentConfig, types
from dotenv import load_dotenv

# Import sub-agents
from agent.bdd_agent import BDDAgent
from agent.edge_case_agent import EdgeCaseAgent
from agent.skills.create_jira_ticket import create_jira_ticket
from agent.guardrails import validate_ticket_id, validate_jira_response, sanitize_output

# Load env variables
load_dotenv()

class QAOrchestrator:
    """
    An ADK orchestrator agent that fetches a Jira ticket, generates BDD and Edge Case test plans
    via sub-agents, and writes the combined test plan back to Jira as a new linked issue,
    now directly integrating with Jira Xray to store tests as structured Cucumber/Manual test cases.
    """
    def __init__(self):
        # Configure Jira MCP server stdio transport in the current virtual environment
        python_bin = os.path.join(os.getcwd(), ".venv", "bin", "python3")
        self.mcp_servers = [
            types.McpStdioServer(
                name="jira",
                command=python_bin,
                args=["mcp/jira_mcp_server.py"]
            )
        ]
        
        self.config = LocalAgentConfig(
            model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            mcp_servers=self.mcp_servers,
            tools=[create_jira_ticket],
            system_instructions=(
                "You are a master QA orchestrator. Your job is to fetch Jira ticket content using get_issue tool, "
                "then process it. You also have tools to create and link tickets, and the create_jira_ticket tool. "
                "CRITICAL: When creating new test issues using the create_issue tool, you MUST explicitly set the "
                "argument issue_type='Test'. Do NOT omit this parameter or default to Story. "
                "Do NOT write or edit any local files, and do NOT run shell commands."
            )
        )
        self.bdd_agent = BDDAgent()
        self.edge_case_agent = EdgeCaseAgent()

    def _get_xray_token(self) -> str:
        """
        Authenticates with Xray Cloud REST API and retrieves the JWT Bearer token using client credentials.

        Returns:
            str: JWT bearer authorization token string.
        """
        try:
            client_id = os.getenv("XRAY_CLIENT_ID")
            client_secret = os.getenv("XRAY_CLIENT_SECRET")
            if not client_id or not client_secret:
                raise ValueError("XRAY_CLIENT_ID or XRAY_CLIENT_SECRET is missing from the environment configuration.")
                
            url = "https://xray.cloud.getxray.app/api/v2/authenticate"
            payload = {
                "client_id": client_id,
                "client_secret": client_secret
            }
            resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"})
            if resp.status_code != 200:
                raise RuntimeError(f"Failed to authenticate with Xray Cloud: {resp.status_code} - {resp.text}")
            # The response is the token string itself in quotes or raw
            return resp.text.strip('"')
        except Exception as e:
            raise RuntimeError(f"Xray token authentication exception occurred: {str(e)}")

    def _execute_xray_graphql(self, token: str, query: str, variables: dict = None) -> dict:
        """
        Executes a GraphQL query or mutation against the Xray Cloud GraphQL endpoint.

        Parameters:
            token (str): Xray JWT authentication token.
            query (str): The GraphQL query or mutation structure string.
            variables (dict, optional): Dict parameters mapping to query variables.

        Returns:
            dict: The data payload returned by the GraphQL executor.
        """
        try:
            url = "https://xray.cloud.getxray.app/api/v2/graphql"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}"
            }
            payload = {"query": query}
            if variables:
                payload["variables"] = variables
                
            resp = requests.post(url, json=payload, headers=headers)
            if resp.status_code != 200:
                raise RuntimeError(f"GraphQL request failed: {resp.status_code} - {resp.text}")
            data = resp.json()
            if "errors" in data:
                raise RuntimeError(f"GraphQL returned errors: {data['errors']}")
            return data.get("data", {})
        except Exception as e:
            raise RuntimeError(f"GraphQL execution exception occurred: {str(e)}")

    def _get_jira_issue_id(self, issue_key: str) -> str:
        """
        Retrieves the internal numeric Jira issue ID for a given issue key using the Jira REST API.

        Parameters:
            issue_key (str): The Jira ticket key (e.g. SCRUM-12).

        Returns:
            str: The numeric database issue identifier.
        """
        try:
            site_url = os.getenv("ATLASSIAN_SITE_URL").rstrip("/")
            email = os.getenv("ATLASSIAN_USER_EMAIL")
            token = os.getenv("ATLASSIAN_API_TOKEN")
            url = f"{site_url}/rest/api/3/issue/{issue_key}?fields=key"
            resp = requests.get(url, auth=(email, token), headers={"Accept": "application/json"})
            if resp.status_code != 200:
                raise RuntimeError(f"Failed to fetch Jira issue ID for {issue_key}: {resp.status_code} - {resp.text}")
            return resp.json().get("id")
        except Exception as e:
            raise RuntimeError(f"Jira issue ID resolution exception: {str(e)}")

    def _parse_markdown_table_to_steps(self, markdown_table: str) -> list:
        """
        Parses a markdown table containing manual test cases into a structured list of steps.
        Expects columns: Test Case / Scenario / Steps / Expected Result.

        Parameters:
            markdown_table (str): Raw markdown string representing scenarios.

        Returns:
            list: List of parsed test steps dictionaries (keys: action, result).
        """
        steps = []
        lines = markdown_table.strip().split("\n")
        for line in lines:
            line = line.strip()
            if not line.startswith("|") or not line.endswith("|"):
                continue
            # Skip header indicator line (e.g. |---|---|)
            if re.match(r"^\|[\s\-:|]*\|$", line):
                continue
            parts = [p.strip() for p in line.split("|")[1:-1]]
            if not parts:
                continue
            # Skip the table header row
            if "test case" in parts[0].lower() or "steps" in parts[0].lower():
                continue
            
            # Map columns to Step action and Expected Result
            # Columns usually are: Test Case | Steps | Expected Result
            if len(parts) >= 3:
                action = f"{parts[0]} - {parts[1]}"
                result = parts[2]
            elif len(parts) == 2:
                action = parts[0]
                result = parts[1]
            else:
                action = parts[0]
                result = ""
            
            steps.append({
                "action": action,
                "result": result
            })
        return steps

    def _update_xray_manual_test(self, token: str, issue_id: str, steps: list):
        """
        Sets a Test issue type to Manual and populates its manual steps using the Xray GraphQL API.
        """
        # 1. Update Test type to Manual using inline mutation parameters
        type_mutation = f'mutation {{ updateTestType(issueId: "{issue_id}", testType: {{ name: "Manual" }}) {{ issueId }} }}'
        self._execute_xray_graphql(token, type_mutation)
        
        # 2. Clear existing test steps to avoid duplicating steps on update
        clear_mutation = f'mutation {{ removeAllTestSteps(issueId: "{issue_id}") {{ issueId }} }}'
        try:
            self._execute_xray_graphql(token, clear_mutation)
        except Exception:
            # Fallback if removeAllTestSteps is not supported or fails
            pass

        # 3. Add each step one by one
        for step in steps:
            # Clean step contents of quotes to avoid GraphQL syntax errors
            action_escaped = step["action"].replace('"', '\\"')
            result_escaped = step["result"].replace('"', '\\"')
            step_mutation = f'mutation {{ addTestStep(issueId: "{issue_id}", step: {{ action: "{action_escaped}", result: "{result_escaped}" }}) {{ id }} }}'
            self._execute_xray_graphql(token, step_mutation)

    def _update_xray_cucumber_test(self, token: str, issue_id: str, gherkin_scenario: str):
        """
        Sets a Test issue type to Cucumber and updates its Gherkin definition using the Xray GraphQL API.
        """
        # 1. Update Test type to Cucumber using inline mutation parameters
        type_mutation = f'mutation {{ updateTestType(issueId: "{issue_id}", testType: {{ name: "Cucumber" }}) {{ issueId }} }}'
        self._execute_xray_graphql(token, type_mutation)
        
        # 2. Update Gherkin definition
        # Clean Gherkin contents of quotes and newlines for safe GraphQL string literal insertion
        gherkin_escaped = gherkin_scenario.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        gherkin_mutation = f'mutation {{ updateGherkinTestDefinition(issueId: "{issue_id}", gherkin: "{gherkin_escaped}") {{ issueId }} }}'
        self._execute_xray_graphql(token, gherkin_mutation)

    async def run_orchestration(self, ticket_id: str) -> dict:
        """
        Runs the full orchestration: validates ticket ID, fetches ticket, validates schema, calls sub-agents,
        creates and links separate manual and cucumber test tickets in Jira, then invokes Xray's APIs.
        """
        # Security Guardrail Check 1: Validate Ticket ID pattern, project key & emptiness
        is_valid_id, err_id = validate_ticket_id(ticket_id)
        if not is_valid_id:
            raise ValueError(f"Security Validation Failure: {err_id}")

        async with Agent(config=self.config) as agent:
            # 1. Fetch the ticket details using the get_issue MCP tool
            response = await agent.chat(f"Fetch the Jira ticket details for {ticket_id} using the get_issue tool.")
            ticket_details = await response.text()
            
            # Extract summary/title for naming the test tickets
            summary_match = re.search(r"Summary:\s*(.*)", ticket_details)
            summary = summary_match.group(1).strip() if summary_match else f"Feature {ticket_id}"

            # Security Guardrail Check 3: Validate schema structure of get_issue response content
            desc_match = re.search(r"Description:\s*(.*)", ticket_details, re.DOTALL)
            desc_text = desc_match.group(1).strip() if desc_match else ""
            mock_jira_resp = {"summary": summary, "description": desc_text}
            is_valid_schema, err_schema = validate_jira_response(mock_jira_resp)
            if not is_valid_schema:
                raise ValueError(f"Security Validation Failure (Jira Data): {err_schema}")

            # 2. Call sub-agents to generate BDD scenarios and edge cases
            bdd_scenarios = await self.bdd_agent.generate_bdd(ticket_details)
            edge_cases = await self.edge_case_agent.generate_edge_cases(ticket_details)
            
            # Clean User Story narrative and Acceptance Criteria lists parsed from description field
            user_story_narrative = ""
            ac_list_content = ""
            
            try:
                # Retrieve raw Jira issue description fields directly from Jira API for precise ADF parsing
                site_url = os.getenv("ATLASSIAN_SITE_URL", "https://irinasha.atlassian.net").rstrip("/")
                email = os.getenv("ATLASSIAN_USER_EMAIL")
                token = os.getenv("ATLASSIAN_API_TOKEN")
                url = f"{site_url}/rest/api/3/issue/{ticket_id}"
                resp = requests.get(url, auth=(email, token), headers={"Accept": "application/json"})
                if resp.status_code == 200:
                    raw_desc = resp.json().get("fields", {}).get("description")
                    if raw_desc and isinstance(raw_desc, dict) and raw_desc.get("type") == "doc":
                        content_nodes = raw_desc.get("content", [])
                        
                        # Loop through nodes to parse sections
                        current_section = None
                        for node in content_nodes:
                            node_type = node.get("type")
                            
                            # Identify section headers
                            if node_type == "heading":
                                heading_text = "".join([t.get("text", "") for t in node.get("content", []) if t.get("type") == "text"]).strip().lower()
                                if "story description" in heading_text or "description" in heading_text:
                                    current_section = "story"
                                elif "acceptance criteria" in heading_text:
                                    current_section = "ac"
                                else:
                                    current_section = None
                            
                            # Parse content inside target sections
                            elif node_type == "paragraph" and current_section == "story":
                                text_val = "".join([t.get("text", "") for t in node.get("content", []) if t.get("type") == "text"]).strip()
                                if text_val:
                                    user_story_narrative = text_val
                                    
                            elif node_type == "orderedList" and current_section == "ac":
                                ac_items = []
                                idx = 1
                                for list_item in node.get("content", []):
                                    item_texts = []
                                    for paragraph in list_item.get("content", []):
                                        for text_node in paragraph.get("content", []):
                                            if text_node.get("type") == "text":
                                                text_txt = text_node.get("text", "").strip()
                                                if text_txt:
                                                    item_texts.append(text_txt)
                                    if item_texts:
                                        # Combine all text blocks under this list item, replace linebreaks with spaces for a single line view
                                        combined_text = " ".join(item_texts).replace("\n", " ").strip()
                                        ac_items.append(f"{idx}. {combined_text}")
                                        idx += 1
                                if ac_items:
                                    ac_list_content = "\n".join(ac_items)
            except Exception as parse_err:
                print(f"ADF description parsing failed fallback: {parse_err}")

            # Fallback string parsing if direct REST API ADF parsing failed
            if not user_story_narrative or not ac_list_content:
                if desc_text:
                    if not user_story_narrative:
                        story_match = re.search(r"As a.*?(?=\n\n|\n[A-Z]|\Z)", desc_text, re.DOTALL | re.IGNORECASE)
                        if story_match:
                            user_story_narrative = story_match.group(0).strip()
                        else:
                            desc_parts = re.split(r"Acceptance Criteria", desc_text, flags=re.IGNORECASE)
                            user_story_narrative = desc_parts[0].replace("Story Description", "").strip()
                    
                    if not ac_list_content:
                        ac_parts = re.split(r"Acceptance Criteria", desc_text, flags=re.IGNORECASE)
                        if len(ac_parts) > 1:
                            ac_raw = ac_parts[1].strip()
                            ac_lines = [line.strip() for line in ac_raw.split("\n") if line.strip()]
                            formatted_lines = []
                            idx = 1
                            for line in ac_lines:
                                if (re.search(r"please let me know", line, re.IGNORECASE) or 
                                    re.match(r"^\s*(Given|When|Then|And|But)\s+", line, re.IGNORECASE) or
                                    line.strip() == ":" or line.strip() == ":**"):
                                    continue
                                clean_line = re.sub(r"^(\d+\.|\*|-)\s*", "", line).strip()
                                if clean_line:
                                    formatted_lines.append(f"{idx}. {clean_line}")
                                    idx += 1
                            ac_list_content = "\n".join(formatted_lines)
            
            if not user_story_narrative:
                user_story_narrative = f"As a user, I want to view the details for {ticket_id}."
            if not ac_list_content:
                ac_list_content = "1. Verify functionality is working as described in the story."

            # Description shows source story context — test cases live in Xray fields only
            test_description = (
                f"h2. *User Story*\n"
                f"{user_story_narrative}\n\n"
                f"h2. *Acceptance Criteria*\n"
                f"{ac_list_content}"
            )

            # 3. Create Manual Test ticket in Jira containing the edge cases
            manual_summary = f"Manual Test: {summary}"
            if len(manual_summary) > 250:
                manual_summary = manual_summary[:245] + "..."
            
            create_manual_resp = await agent.chat(
                f"Create a new issue in the project with summary: '{manual_summary}', "
                f"description: '{test_description}', labels: ['manual'], and issue_type: 'Test' using the create_issue tool."
            )
            create_manual_text = await create_manual_resp.text()
            
            # Find the created key, making sure it's not the original ticket_id
            keys_manual = re.findall(r"SCRUM-\d+", create_manual_text)
            manual_test_key = None
            for k in keys_manual:
                if k != ticket_id:
                    manual_test_key = k
                    break
            if not manual_test_key:
                if keys_manual:
                    manual_test_key = keys_manual[0]
                else:
                    raise RuntimeError(f"Could not extract created manual test key from response: {create_manual_text}")

            # Link the manual test ticket to the story (inward: story, outward: test, so outward 'tests' inward story and inward is 'tested by' outward test)
            link_manual_resp = await agent.chat(
                f"Link the issues using the link_issues tool: inward_key: '{ticket_id}', outward_key: '{manual_test_key}', link_type_name: 'Test'."
            )
            await link_manual_resp.text()

            # 4. Create Cucumber Test ticket in Jira containing Gherkin scenarios
            cucumber_summary = f"Cucumber Test: {summary}"
            if len(cucumber_summary) > 250:
                cucumber_summary = cucumber_summary[:245] + "..."
                
            create_cuc_resp = await agent.chat(
                f"Create a new issue in the project with summary: '{cucumber_summary}', "
                f"description: '{test_description}', labels: ['cucumber'], and issue_type: 'Test' using the create_issue tool."
            )
            create_cuc_text = await create_cuc_resp.text()
            
            keys_cuc = re.findall(r"SCRUM-\d+", create_cuc_text)
            cucumber_test_key = None
            for k in keys_cuc:
                if k != ticket_id and k != manual_test_key:
                    cucumber_test_key = k
                    break
            if not cucumber_test_key:
                if keys_cuc:
                    cucumber_test_key = keys_cuc[0]
                else:
                    raise RuntimeError(f"Could not extract created cucumber test key from response: {create_cuc_text}")

            # Link the cucumber test ticket to the story
            link_cuc_resp = await agent.chat(
                f"Link the issues using the link_issues tool: inward_key: '{ticket_id}', outward_key: '{cucumber_test_key}', link_type_name: 'Test'."
            )
            await link_cuc_resp.text()

            # 5. Populate structured Xray test information using the GraphQL API
            try:
                xray_token = self._get_xray_token()
                
                # Fetch internal numeric IDs for both newly created Test issues
                manual_issue_id = self._get_jira_issue_id(manual_test_key)
                cucumber_issue_id = self._get_jira_issue_id(cucumber_test_key)
                
                # Parse manual edge cases table and upload steps to Xray
                parsed_steps = self._parse_markdown_table_to_steps(edge_cases)
                if parsed_steps:
                    self._update_xray_manual_test(xray_token, manual_issue_id, parsed_steps)
                
                # Update Cucumber Gherkin scenario
                # Clean up markdown formatting if any from BDD agent response
                clean_gherkin = bdd_scenarios.replace("```gherkin", "").replace("```", "").strip()
                self._update_xray_cucumber_test(xray_token, cucumber_issue_id, clean_gherkin)
                
            except Exception as xray_err:
                # Log error or append notification, but don't fail the Jira creation if Xray sync fails
                print(f"Xray sync error: {xray_err}")
            
            return {
                "ticket_details": sanitize_output(ticket_details),
                "bdd_scenarios": sanitize_output(bdd_scenarios),
                "edge_cases": sanitize_output(edge_cases),
                "manual_test_key": manual_test_key,
                "cucumber_test_key": cucumber_test_key
            }

    async def create_story_with_skill(self, feature_name: str) -> str:
        """
        Uses the registered create_jira_ticket tool/skill to validate, generate, and create a Jira Story.
        Returns the output text of the tool execution.
        """
        async with Agent(config=self.config) as agent:
            response = await agent.chat(
                f"Use the create_jira_ticket tool to validate and create a user story for the feature: '{feature_name}'"
            )
            return await response.text()


