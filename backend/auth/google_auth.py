# ARIS/auth/google_auth.py
import os
import json
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Allow HTTP for local development
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
]


def get_credentials() -> Credentials | None:
    """Load saved credentials, refreshing if expired."""
    if not os.path.exists(TOKEN_FILE):
        return None
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            save_credentials(creds)
        except Exception as e:
            print(f"[Auth] Token refresh failed: {e}")
            return None
    return creds if creds.valid else None


def save_credentials(creds: Credentials):
    """Save credentials to token.json."""
    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())


def is_authenticated() -> bool:
    """Check if Google account is connected and token is valid."""
    creds = get_credentials()
    return creds is not None and creds.valid


def run_auth_flow():
    """
    Run the OAuth flow using a local server (most reliable method).
    This opens a browser tab automatically and handles the callback internally.
    """
    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
    # run_local_server handles everything — opens browser, catches callback, saves token
    creds = flow.run_local_server(port=8080, prompt="consent", authorization_prompt_message="")
    save_credentials(creds)
    return creds


def get_gmail_service():
    """Returns an authenticated Gmail API client."""
    creds = get_credentials()
    if not creds:
        raise Exception("Not authenticated. Run /auth/google/login first.")
    return build("gmail", "v1", credentials=creds)


def get_calendar_service():
    """Returns an authenticated Google Calendar API client."""
    creds = get_credentials()
    if not creds:
        raise Exception("Not authenticated. Run /auth/google/login first.")
    return build("calendar", "v3", credentials=creds)