# QA Pilot Analysis Report for Ticket SCRUM-147

## Ticket Details
* **Summary:** As a user, I can update my email in profile
* **Description:** As a registered user, I want to update my email address associated with my profile so that I can keep my account information current and receive important notifications.

---

## 1. Gherkin / BDD Cucumber Scenarios

**Feature: User Email Update in Profile**

  As a registered user,
  I want to update my email address associated with my profile,
  So that I can keep my account information current and receive important notifications.

  Background:
    Given the user is logged into the application
    And the user is on the profile settings page of their account
    And their current registered email is "current_user@example.com"

  ### Scenario: Successfully request email update (Happy Path with Re-authentication)
    Given the user enters a valid new email address "updated_user@example.com"
    When the user submits the email update form
    Then a secure authentication modal should be displayed prompting for the user's current password
    When the user enters their valid password "SecurePassword123"
    And confirms the password authentication
    Then the profile page should display a message: "An email verification link has been sent to updated_user@example.com. Please verify to complete the update."
    And a secure verification email should be dispatched to "updated_user@example.com" containing a dynamic verification link
    And the registered email in the system database should remain "current_user@example.com" pending verification

  ### Scenario: Successfully complete email update via Verification Link
    Given a verification email token has been successfully sent to "updated_user@example.com"
    When the user accesses the dynamic verification link from their inbox
    Then the user should be redirected to the secure verification page
    And a success banner should display: "Thank you! Your email has been successfully updated to updated_user@example.com."
    And the system backend data store should be updated with the new email "updated_user@example.com"
    And any subsequent notification should be delivered to "updated_user@example.com"
    And a notification alert of the email change should be sent to the old address "current_user@example.com" for security purposes

  ### Scenario Outline: Attempt to update with invalid email format (Validation Failures)
    When the user enters an invalid email format "<invalid_email>"
    And the user submits the email update form
    Then an inline form validation error should appear: "Please enter a valid email address."
    And the submit button should remain disabled or the request aborted
    And the email address on the user profile must not be updated in the system datastore

    Examples:
      | invalid_email               | validation_notes                         |
      | plainaddress                | No '@' character                          |
      | @missing-username.com       | Missing local part                        |
      | user@.com                   | Missing domain name                       |
      | user@domain..com            | Double dot in domain structure           |
      | user@domain.com (Joe)       | Trailing characters/parenthesis           |
      | user name@domain.com        | Space inside local part                  |
      | user@domain with spaces.com | Space inside domain name                 |
      | abc#@gmail.com              | Special character in local part          |

  ### Scenario: Attempt to update with an already registered email
    When the user enters an email address "already_taken@example.com"
    And the email "already_taken@example.com" is already registered to another active profile in the database
    And the user submits the email update form
    Then the application should prompt the user for password verification (or display the duplicate warning directly)
    And upon authentication submission, an error banner should display: "This email address is already registered to another account."
    And the email address on the user profile must not be updated in the system datastore

  ### Scenario: Security Timeout of verification link
    Given a verification email token has been sent to "updated_user@example.com"
    And 24 hours have passed making the token expired
    When the user clicks the expired dynamic verification link
    Then the verification landing page should display an error: "This verification link has expired. Please request a new email update request."
    And the user's email address in the system datastore must remain "current_user@example.com"

---

## 2. API Specifications & Test Stubs

The user profile email change involves two core REST API endpoints:
1. `PUT /api/v1/profile/email` — Requests an email update (triggers re-authentication and verification email dispatch).
2. `POST /api/v1/profile/email/confirm` — Completes modification using the token from the verification link.

### Endpoint 1: Request Email Update

* **HTTP Method:** `PUT`
* **Path:** `/api/v1/profile/email`
* **Headers:**
  - `Content-Type: application/json`
  - `Authorization: Bearer <JWT_ACCESS_TOKEN>`

#### Request Payload:
```json
{
  "new_email": "updated_user@example.com",
  "password": "SecurePassword123"
}
```

#### Response (202 Accepted):
```json
{
  "status": "pending_verification",
  "message": "Verification link dispatched to updated_user@example.com. Link expires in 24 hours.",
  "requested_email": "updated_user@example.com"
}
```

#### Response (401 Unauthorized - Incorrect Current Password):
```json
{
  "status": "error",
  "code": "AUTH_FAILED",
  "message": "The password entered is incorrect. Action aborted."
}
```

#### Response (409 Conflict - Duplicate Email):
```json
{
  "status": "error",
  "code": "EMAIL_ALREADY_IN_USE",
  "message": "The email address updated_user@example.com is already registered to another user account."
}
```

---

### Endpoint 2: Confirm Email Update

* **HTTP Method:** `POST`
* **Path:** `/api/v1/profile/email/confirm`
* **Headers:**
  - `Content-Type: application/json`

#### Request Payload:
```json
{
  "token": "v3r1f1cat10n_t0k3n_bcd_987654"
}
```

#### Response (200 OK):
```json
{
  "status": "success",
  "message": "Your profile email has been updated successfully.",
  "updated_email": "updated_user@example.com"
}
```

#### Response (410 Gone - Expired Verification Token):
```json
{
  "status": "error",
  "code": "TOKEN_EXPIRED",
  "message": "The verification link has expired or has already been used."
}
```

---

## 3. Python Integration Tests (Stub execution)

The following python code tests these scenarios programmatically using `requests`:

```python
import requests
import unittest

BASE_URL = "http://localhost:8000/api/v1"

class TestEmailUpdateFlow(unittest.TestCase):
    
    def setUp(self):
        # Setup login authentication session
        self.headers = {
            "Authorization": "Bearer mock_jwt_access_token_xyz_123",
            "Content-Type": "application/json"
        }

    def test_request_email_update_success(self):
        payload = {
            "new_email": "updated_user@example.com",
            "password": "SecurePassword123"
        }
        response = requests.put(f"{BASE_URL}/profile/email", json=payload, headers=self.headers)
        self.assertEqual(response.status_code, 202)
        data = response.json()
        self.assertEqual(data["status"], "pending_verification")
        self.assertIn("dispatched", data["message"])

    def test_request_email_update_auth_failure(self):
        payload = {
            "new_email": "updated_user@example.com",
            "password": "WrongPassword456"
        }
        response = requests.put(f"{BASE_URL}/profile/email", json=payload, headers=self.headers)
        self.assertEqual(response.status_code, 401)
        data = response.json()
        self.assertEqual(data["code"], "AUTH_FAILED")

    def test_request_email_update_duplicate(self):
        payload = {
            "new_email": "already_taken@example.com",
            "password": "SecurePassword123"
        }
        response = requests.put(f"{BASE_URL}/profile/email", json=payload, headers=self.headers)
        self.assertEqual(response.status_code, 409)
        data = response.json()
        self.assertEqual(data["code"], "EMAIL_ALREADY_IN_USE")

    def test_confirm_email_update_success(self):
        payload = {
            "token": "valid_token_xyz"
        }
        response = requests.post(f"{BASE_URL}/profile/email/confirm", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["updated_email"], "updated_user@example.com")

if __name__ == "__main__":
    unittest.main()
```

---

## 4. Edge Cases & Security Guidelines Checklist

To guarantee robust quality, confirm that standard frontend/backend defenses are in place:
1. **Double-Channel Notification:** Ensure a notification email is dispatched to the **old** email inbox immediately after completion to alert the user of profile changes, helping counter account takeover attempts.
2. **Rate Limiting:** Protect the update request endpoint (`PUT /api/v1/profile/email`) with a strict rate limit (e.g., maximum 3 requests within 10 minutes) to prevent verification email flooding or security spoofing.
3. **Token Invalidation:** Explicitly revoke the confirmation token immediately on first-time use, or systematically discard it if the user places a separate email update request afterwards.
4. **Local Part Sanitization:** Trim trailing whitespaces and normalize domains into lowercase before processing or comparing database values.
