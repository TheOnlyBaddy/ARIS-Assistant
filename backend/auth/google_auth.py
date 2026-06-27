# ARIS/auth/google_auth.py
import os
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow, Flow
from googleapiclient.discovery import build
from fastapi import APIRouter
from fastapi.responses import RedirectResponse

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"
REDIRECT_URI = "http://localhost:8000/auth/google/callback"
FRONTEND_URL = "http://localhost:5173"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
]

# ✅ FIX: Store flow between /login and /callback
# PKCE requires the same flow object — we keep it in memory
_pending_flow: Flow | None = None

# ── FastAPI Router ────────────────────────────────────────────────────────────
auth_router = APIRouter(prefix="/auth", tags=["auth"])


@auth_router.get("/google/login")
def google_login():
    """
    Starts OAuth flow. Stores the flow object so /callback can reuse it
    (required to satisfy PKCE code verifier check).
    """
    global _pending_flow

    _pending_flow = Flow.from_client_secrets_file(
        CREDENTIALS_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )

    auth_url, _ = _pending_flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )

    return RedirectResponse(auth_url)


@auth_router.get("/google/callback")
def google_callback(code: str, state: str = None):
    """
    Google redirects here after user approves.
    Reuses the same flow object from /login to exchange code for tokens.
    """
    global _pending_flow

    if _pending_flow is None:
        # Fallback: rebuild flow without PKCE if session was lost
        _pending_flow = Flow.from_client_secrets_file(
            CREDENTIALS_FILE,
            scopes=SCOPES,
            redirect_uri=REDIRECT_URI,
        )

    _pending_flow.fetch_token(code=code)
    creds = _pending_flow.credentials
    save_credentials(creds)
    _pending_flow = None  # clear after use
    print("[Auth] Token saved via web OAuth flow.")

    return RedirectResponse(f"{FRONTEND_URL}?google_auth=success")


@auth_router.get("/google/status")
def google_status():
    """Check if Google is connected. Auto-refreshes expired token silently."""
    return {"connected": is_authenticated()}


@auth_router.post("/google/logout")
def google_logout():
    """Delete token.json to disconnect Google account."""
    if os.path.exists(TOKEN_FILE):
        os.remove(TOKEN_FILE)
        print("[Auth] Token deleted — Google disconnected.")
    return {"disconnected": True}


# ── Core Auth Functions ───────────────────────────────────────────────────────

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
    """Fallback: CLI OAuth flow for manual testing only."""
    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
    creds = flow.run_local_server(port=8080, prompt="consent", authorization_prompt_message="")
    save_credentials(creds)
    return creds


def get_gmail_service():
    """Returns an authenticated Gmail API client."""
    creds = get_credentials()
    if not creds:
        raise Exception("Not authenticated. Connect Google via the ARIS UI first.")
    return build("gmail", "v1", credentials=creds)


def get_calendar_service():
    """Returns an authenticated Google Calendar API client."""
    creds = get_credentials()
    if not creds:
        raise Exception("Not authenticated. Connect Google via the ARIS UI first.")
    return build("calendar", "v3", credentials=creds)