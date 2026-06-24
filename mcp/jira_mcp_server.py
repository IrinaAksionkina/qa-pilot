import os
import requests
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize FastMCP Jira server
mcp = FastMCP("Jira")

# Retrieve Atlassian credentials
SITE_URL = os.getenv("ATLASSIAN_SITE_URL")
EMAIL = os.getenv("ATLASSIAN_USER_EMAIL")
API_TOKEN = os.getenv("ATLASSIAN_API_TOKEN")
PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY")

@mcp.tool()
def get_issue(issue_key: str) -> str:
    """
    Fetches the details (summary, description, etc.) of a Jira issue by its key.
    """
    url = f"{SITE_URL.rstrip('/')}/rest/api/3/issue/{issue_key}"
    res = requests.get(url, auth=(EMAIL, API_TOKEN), headers={"Accept": "application/json"})
    if res.status_code != 200:
        return f"Error: Failed to fetch issue {issue_key}. Status: {res.status_code}. Response: {res.text}"
    
    data = res.json()
    fields = data.get("fields", {})
    summary = fields.get("summary", "")
    description = fields.get("description", "")
    if isinstance(description, dict):
        import json
        description = json.dumps(description, indent=2)
        
    return f"Issue Key: {issue_key}\nSummary: {summary}\nDescription:\n{description}"

@mcp.tool()
def create_issue(summary: str, description: any, issue_type: str = "Story", labels: list[str] = None) -> str:
    """
    Creates a new issue in the configured Jira project. Description can be a string or a structured ADF dictionary.
    Labels is an optional list of strings.
    Returns a message containing the new issue key.
    """
    url = f"{SITE_URL.rstrip('/')}/rest/api/3/issue"
    
    # If description is a plain string, convert it to a valid ADF representation
    if isinstance(description, str):
        description = {
            "version": 1,
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": description
                        }
                    ]
                }
            ]
        }
        
    payload = {
        "fields": {
            "project": {
                "key": PROJECT_KEY
            },
            "summary": summary,
            "description": description,
            "issuetype": {
                "name": issue_type
            }
        }
    }
    if labels:
        payload["fields"]["labels"] = labels
        
    res = requests.post(url, auth=(EMAIL, API_TOKEN), headers={"Content-Type": "application/json"}, json=payload)
    if res.status_code not in [200, 201]:
        # Fallback to Task if Story/Test fails
        if issue_type != "Task":
            payload["fields"]["issuetype"]["name"] = "Task"
            res = requests.post(url, auth=(EMAIL, API_TOKEN), headers={"Content-Type": "application/json"}, json=payload)
        
        if res.status_code not in [200, 201]:
            return f"Error: Failed to create issue. Status: {res.status_code}. Response: {res.text}"
            
    data = res.json()
    return f"Success: Created issue {data.get('key')} of type {payload['fields']['issuetype']['name']}."

@mcp.tool()
def link_issues(inward_key: str, outward_key: str, link_type_name: str = "Test") -> str:
    """
    Links two Jira issues using the specified link type (e.g. 'Test' or 'Relates').
    """
    url = f"{SITE_URL.rstrip('/')}/rest/api/2/issueLink"
    payload = {
        "type": {
            "name": link_type_name
        },
        "inwardIssue": {
            "key": inward_key
        },
        "outwardIssue": {
            "key": outward_key
        }
    }
    res = requests.post(url, auth=(EMAIL, API_TOKEN), headers={"Content-Type": "application/json"}, json=payload)
    if res.status_code not in [200, 201, 204]:
        # Retry with 'Relates'
        if link_type_name != "Relates":
            payload["type"]["name"] = "Relates"
            res = requests.post(url, auth=(EMAIL, API_TOKEN), headers={"Content-Type": "application/json"}, json=payload)
            if res.status_code in [200, 201, 204]:
                return f"Success: Linked {outward_key} to {inward_key} as 'Relates' (fallback)."
        return f"Error: Failed to link issues. Status: {res.status_code}. Response: {res.text}"
        
    return f"Success: Linked {outward_key} to {inward_key} as '{link_type_name}'."

@mcp.tool()
def add_comment(issue_key: str, comment_body: str) -> str:
    """
    Adds a comment to a Jira issue.
    """
    url = f"{SITE_URL.rstrip('/')}/rest/api/2/issue/{issue_key}/comment"
    payload = {
        "body": comment_body
    }
    res = requests.post(url, auth=(EMAIL, API_TOKEN), headers={"Content-Type": "application/json"}, json=payload)
    if res.status_code not in [200, 201]:
        return f"Error: Failed to add comment. Status: {res.status_code}. Response: {res.text}"
    return f"Success: Added comment to {issue_key}."

if __name__ == "__main__":
    mcp.run()
