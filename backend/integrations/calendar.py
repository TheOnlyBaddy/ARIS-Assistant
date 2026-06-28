# ARIS/integrations/calendar.py
# Google Calendar integration — fetch events, create events, detect conflicts

from datetime import datetime, timedelta, timezone
import re
from auth.google_auth import get_calendar_service
from user_profile import load_profile


# ─── HELPERS ───────────────────────────────────────────────────────────────────

def _format_event(event: dict) -> dict:
    """Convert raw Google Calendar event into a clean dict."""
    start = event.get("start", {})
    end   = event.get("end", {})

    # Events can be all-day (date) or timed (dateTime)
    start_str = start.get("dateTime", start.get("date", ""))
    end_str   = end.get("dateTime",   end.get("date",   ""))

    return {
        "id":          event.get("id", ""),
        "title":       event.get("summary", "(no title)"),
        "start":       start_str,
        "end":         end_str,
        "location":    event.get("location", ""),
        "description": event.get("description", ""),
        "attendees":   [a.get("email", "") for a in event.get("attendees", [])],
        "meet_link":   event.get("hangoutLink", ""),
        "all_day":     "date" in start and "dateTime" not in start,
    }


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _end_of_day_utc() -> datetime:
    now = _now_utc()
    return now.replace(hour=23, minute=59, second=59)


# ─── FETCH EVENTS ──────────────────────────────────────────────────────────────

def get_events(time_min: datetime = None, time_max: datetime = None, max_results: int = 10) -> list[dict]:
    """
    Fetch calendar events between two times.
    Defaults to now → 7 days from now if not specified.
    """
    service = get_calendar_service()

    if time_min is None:
        time_min = _now_utc()
    if time_max is None:
        time_max = time_min + timedelta(days=7)

    results = service.events().list(
        calendarId="primary",
        timeMin=time_min.isoformat(),
        timeMax=time_max.isoformat(),
        maxResults=max_results,
        singleEvents=True,
        orderBy="startTime"
    ).execute()

    return [_format_event(e) for e in results.get("items", [])]


def get_today_events() -> list[dict]:
    """Fetch all events happening today."""
    now     = _now_utc()
    end_day = _end_of_day_utc()
    return get_events(time_min=now, time_max=end_day, max_results=20)


def get_week_events() -> list[dict]:
    """Fetch all events for the next 7 days."""
    now      = _now_utc()
    end_week = now + timedelta(days=7)
    return get_events(time_min=now, time_max=end_week, max_results=50)


# ─── CREATE EVENT ──────────────────────────────────────────────────────────────

def create_event(
    title: str,
    start_time: str,
    end_time: str,
    description: str = "",
    location: str = "",
    attendees: list[str] = None,
    add_meet: bool = False
) -> dict:
    """
    Create a new Google Calendar event.
    Args:
        title:       Event title/summary
        start_time:  ISO 8601 string e.g. "2026-05-05T14:00:00+05:30"
        end_time:    ISO 8601 string e.g. "2026-05-05T15:00:00+05:30"
        description: Optional event description
        location:    Optional location string
        attendees:   Optional list of email addresses to invite
        add_meet:    If True, adds a Google Meet link
    """
    service = get_calendar_service()

    try:
        profile = load_profile()
        tz = profile.get("timezone", "Asia/Kolkata")
    except Exception:
        tz = "Asia/Kolkata"

    event_body = {
        "summary":     title,
        "description": description,
        "location":    location,
        "start": {
            "dateTime": start_time,
            "timeZone": tz,
        },
        "end": {
            "dateTime": end_time,
            "timeZone": tz,
        },
    }

    if attendees:
        event_body["attendees"] = [{"email": e} for e in attendees]

    if add_meet:
        event_body["conferenceData"] = {
            "createRequest": {"requestId": f"aris-{title[:10]}-meet"}
        }

    created = service.events().insert(
        calendarId="primary",
        body=event_body,
        conferenceDataVersion=1 if add_meet else 0,
        sendUpdates="all" if attendees else "none"
    ).execute()

    return {
        "status":   "created",
        "event":    _format_event(created),
        "link":     created.get("htmlLink", ""),
    }


# ─── DELETE EVENT ──────────────────────────────────────────────────────────────

def delete_event(event_id: str) -> dict:
    """Delete a calendar event by ID."""
    service = get_calendar_service()
    service.events().delete(calendarId="primary", eventId=event_id).execute()
    return {"status": "deleted", "event_id": event_id}


# ─── CONFLICT DETECTION ────────────────────────────────────────────────────────

def check_conflicts(start_time: str, end_time: str) -> dict:
    """
    Check if any existing events overlap with a proposed time slot.
    Returns conflicts list and whether the slot is free.
    """
    start_dt = datetime.fromisoformat(start_time)
    end_dt   = datetime.fromisoformat(end_time)

    # Make timezone-aware if naive
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=timezone.utc)
    if end_dt.tzinfo is None:
        end_dt = end_dt.replace(tzinfo=timezone.utc)

    existing = get_events(time_min=start_dt, time_max=end_dt)

    return {
        "is_free":   len(existing) == 0,
        "conflicts": existing,
        "conflict_count": len(existing)
    }


# ─── TODAY'S BRIEFING ──────────────────────────────────────────────────────────

def get_agenda_summary() -> dict:
    """
    Get today's events formatted for ARIS morning briefing.
    Returns structured data ready to pass to Gemini.
    """
    today  = get_today_events()
    week   = get_week_events()

    return {
        "today_count":  len(today),
        "today_events": today,
        "week_count":   len(week),
        "week_events":  week,
    }