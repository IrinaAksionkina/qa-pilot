"""
File: agent/guardrails.py
Description: Security and validation guardrails module. Performs sanitization of outputs and filters inputs for path traversal, project isolation, prompt injection vectors, and schema errors.
Role in Architecture: Ensures the master orchestrator and story creator skills process untrusted data safely.
"""

import re

def validate_ticket_id(ticket_id: str) -> tuple[bool, str]:
    """
    Validates the ticket ID to protect against unauthorized project access, SQL injection,
    and path traversal style key spoofing.
    
    Checks:
    - Must not be empty or None.
    - Must match the regex pattern: ^SCRUM-\\d+$ representing only the SCRUM project key and its index.

    Parameters:
        ticket_id (str): The raw Jira issue key identifier.

    Returns:
        tuple[bool, str]: Success boolean state, and error text description if invalid.
    """
    if not ticket_id:
        return False, "Ticket ID cannot be empty."
    
    # Strictly match SCRUM- followed by digits only
    pattern = r"^SCRUM-\d+$"
    if not re.match(pattern, ticket_id):
        return False, f"Invalid ticket ID format '{ticket_id}'. Must be in the format 'SCRUM-[digits]'."
        
    return True, ""

def validate_feature_input(feature_name: str) -> tuple[bool, str]:
    """
    Validates input features to protect against prompt injection, jailbreaking, Denial of Service (DoS) 
    through abnormally long inputs, and low-quality generation due to vague features.
    
    Checks:
    - Reject if empty or less than 5 characters.
    - Reject if longer than 100 characters.
    - Check for prompt injection payloads (e.g. ignore previous instructions, jailbreak).
    - Reject vague, single-word prompts.
    """
    if not feature_name:
        return False, "Feature name cannot be empty."
        
    trimmed = feature_name.strip()
    if len(trimmed) < 5:
        return False, "Feature name is too short. Must be at least 5 characters."
        
    if len(trimmed) > 100:
        return False, "Feature name is too long. Must be 100 characters or less."
        
    # Check for prompt injection signatures
    injection_patterns = [
        "ignore previous instructions",
        "you are now",
        "forget everything",
        "act as",
        "jailbreak"
    ]
    for pattern in injection_patterns:
        if pattern in trimmed.lower():
            return False, "Input rejected due to detected security violation (prompt injection attempt)."

    # Reject if it's too vague (e.g., single word)
    if " " not in trimmed:
        return False, f"Feature name '{trimmed}' is too vague. Please provide a more descriptive feature name."
        
    return True, ""

def validate_jira_response(response: dict) -> tuple[bool, str]:
    """
    Validates Jira API responses to protect against empty responses, service failures,
    and schema drift that could lead to AttributeError/KeyError down the line.
    
    Checks:
    - Verifies response dictionary is not empty.
    - Ensures critical keys like summary and description are present.
    """
    if not response:
        return False, "Jira response is empty or None."
        
    if "summary" not in response or "description" not in response:
        return False, "Jira response format is invalid. Missing required fields: 'summary' or 'description'."
        
    return True, ""

def sanitize_output(text: str) -> str:
    """
    Sanitizes output text to prevent leaks of API tokens, basic auth credentials,
    internal workspace directory structures, or server paths in client-facing documents.
    
    Sanitizations:
    - Removes basic authorization strings / API token signatures.
    - Replaces internal workspace folders or system paths with generic names.
    """
    if not text:
        return ""
        
    sanitized = text
    
    # 1. Regex to match Atlassian API tokens (ATATT...) or generic JWTs and API key prefixes
    # e.g., ATATT3xFf... or raw base64 tokens
    token_pattern = r"(ATATT[a-zA-Z0-9_\-\=]{50,250}|Bearer\s+[a-zA-Z0-9_\-\.\=]{20,250}|XRAY_[A-Z_]+=[a-zA-Z0-9]{16,64})"
    sanitized = re.sub(token_pattern, "[REDACTED_CREDENTIAL]", sanitized)
    
    # 2. Replaces system paths (e.g., /Users/irina/...)
    path_pattern = r"(/Users/[a-zA-Z0-9_\.\-]+/Projects/[a-zA-Z0-9_\-\./]+|/Users/[a-zA-Z0-9_\.\-]+/\.gemini/[a-zA-Z0-9_\-\./]+)"
    sanitized = re.sub(path_pattern, "[SYSTEM_PATH]", sanitized)
    
    return sanitized
