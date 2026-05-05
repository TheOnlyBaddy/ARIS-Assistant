# ARIS/integrations/gmail.py
# Gmail integration — read, search, send, summarize emails

import base64
import re
from email.mime.text import MIMEText
from auth.google_auth import get_gmail_service


# ─── HELPERS ───────────────────────────────────────────────────────────────────

def _decode_body(payload: dict) -> str:
    """Extract and decode the plain-text body from a Gmail message payload."""
    body = ""
    if "parts" in payload:
        for part in payload["parts"]:
            if part.get("mimeType") == "text/plain":
                data = part["body"].get("data", "")
                if data:
                    body = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                    break
            # Handle nested parts (multipart/alternative inside multipart/mixed)
            elif "parts" in part:
                for subpart in part["parts"]:
                    if subpart.get("mimeType") == "text/plain":
                        data = subpart["body"].get("data", "")
                        if data:
                            body = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                            break
    else:
        # Single-part message
        data = payload.get("body", {}).get("data", "")
        if data:
            body = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
    return body.strip()


def _parse_message(msg: dict, include_body: bool = False) -> dict:
    """Convert raw Gmail API message into a clean dict."""
    headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
    result = {
        "id":      msg["id"],
        "from":    headers.get("From", "Unknown"),
        "to":      headers.get("To", ""),
        "subject": headers.get("Subject", "(no subject)"),
        "date":    headers.get("Date", ""),
        "snippet": msg.get("snippet", ""),
    }
    if include_body:
        result["body"] = _decode_body(msg["payload"])
    return result


# ─── READ INBOX ────────────────────────────────────────────────────────────────

# Gmail category labels for filtering
CATEGORY_MAP = {
    "primary":    "category:primary",
    "promotions": "category:promotions",
    "social":     "category:social",
    "updates":    "category:updates",
    "forums":     "category:forums",
    "all":        "in:inbox"          # everything including all tabs
}

def read_inbox(max_results: int = 10, unread_only: bool = False, category: str = "primary") -> list[dict]:
    """
    Fetch the latest emails from inbox.
    Args:
        max_results: How many emails to return (default 10)
        unread_only: If True, only return unread emails
        category:    "primary", "promotions", "social", "updates", "forums", "all"
                     Defaults to "primary" so ARIS only reads important emails
    Returns:
        List of email dicts with sender, subject, snippet, date
    """
    service = get_gmail_service()

    # Build query — default to primary tab only
    category_filter = CATEGORY_MAP.get(category.lower(), "category:primary")
    query = category_filter
    if unread_only:
        query += " is:unread"

    results = service.users().messages().list(
        userId="me",
        q=query,
        maxResults=max_results
    ).execute()

    messages = results.get("messages", [])
    emails = []
    for msg_ref in messages:
        msg = service.users().messages().get(
            userId="me",
            id=msg_ref["id"],
            format="full"
        ).execute()
        emails.append(_parse_message(msg))

    return emails


# ─── SEARCH EMAILS ─────────────────────────────────────────────────────────────

def search_emails(query: str, max_results: int = 5) -> list[dict]:
    """
    Search emails by keyword, sender, subject etc.
    Supports Gmail search syntax e.g. "from:raj@gmail.com" or "subject:invoice"
    """
    service = get_gmail_service()
    results = service.users().messages().list(
        userId="me",
        q=query,
        maxResults=max_results
    ).execute()

    messages = results.get("messages", [])
    emails = []
    for msg_ref in messages:
        msg = service.users().messages().get(
            userId="me",
            id=msg_ref["id"],
            format="full"
        ).execute()
        emails.append(_parse_message(msg, include_body=True))

    return emails


# ─── GET SINGLE EMAIL ──────────────────────────────────────────────────────────

def get_email(message_id: str) -> dict:
    """Fetch a single email by its ID, including full body."""
    service = get_gmail_service()
    msg = service.users().messages().get(
        userId="me",
        id=message_id,
        format="full"
    ).execute()
    return _parse_message(msg, include_body=True)


# ─── SEND EMAIL ────────────────────────────────────────────────────────────────

def send_email(to: str, subject: str, body: str) -> dict:
    """
    Send an email on behalf of the user.
    Args:
        to:      Recipient email address
        subject: Email subject line
        body:    Plain text email body
    Returns:
        Dict with message ID and status
    """
    service = get_gmail_service()

    mime_msg = MIMEText(body)
    mime_msg["to"]      = to
    mime_msg["subject"] = subject

    raw = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode()
    sent = service.users().messages().send(
        userId="me",
        body={"raw": raw}
    ).execute()

    return {"status": "sent", "message_id": sent["id"], "to": to, "subject": subject}


# ─── DRAFT EMAIL ───────────────────────────────────────────────────────────────

def create_draft(to: str, subject: str, body: str) -> dict:
    """Create a draft email without sending it."""
    service = get_gmail_service()

    mime_msg = MIMEText(body)
    mime_msg["to"]      = to
    mime_msg["subject"] = subject

    raw = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode()
    draft = service.users().drafts().create(
        userId="me",
        body={"message": {"raw": raw}}
    ).execute()

    return {"status": "drafted", "draft_id": draft["id"], "to": to, "subject": subject}


# ─── SUMMARIZE INBOX ───────────────────────────────────────────────────────────

def get_inbox_summary(max_results: int = 5) -> dict:
    """
    Get inbox emails formatted for Gemini to summarize.
    Returns structured data ready to pass to the AI.
    """
    emails = read_inbox(max_results=max_results)
    return {
        "email_count": len(emails),
        "emails": emails
    }