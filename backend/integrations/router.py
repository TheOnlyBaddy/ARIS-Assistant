# ARIS/integrations/router.py
# Natural language intent router — detects what the user wants and calls the right integration
# Uses Gemini function calling to classify intent and extract parameters

import os
import json
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
gemini_client  = genai.Client(api_key=GEMINI_API_KEY)
ROUTER_MODEL   = "gemini-2.5-flash"

# ─── INTENT DEFINITIONS ────────────────────────────────────────────────────────
# These tell Gemini what intents exist and what parameters to extract

INTENT_TOOLS = [
    types.Tool(function_declarations=[

        # ── Gmail ──────────────────────────────────────────────────────────────
        types.FunctionDeclaration(
            name="read_inbox",
            description="User wants to read, check, or see their emails or inbox",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "max_results": types.Schema(type=types.Type.INTEGER, description="How many emails to fetch, default 5"),
                    "unread_only": types.Schema(type=types.Type.BOOLEAN, description="Only unread emails"),
                    "category":    types.Schema(type=types.Type.STRING,  description="Email category: primary, promotions, social, all"),
                },
            )
        ),

        types.FunctionDeclaration(
            name="search_emails",
            description="User wants to search for specific emails by keyword, sender, or subject",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "query": types.Schema(type=types.Type.STRING, description="Search query e.g. 'from:raj@gmail.com' or 'invoice'"),
                    "max_results": types.Schema(type=types.Type.INTEGER, description="How many results, default 5"),
                },
                required=["query"]
            )
        ),

        types.FunctionDeclaration(
            name="send_email",
            description="User wants to send or write an email to someone",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "to":      types.Schema(type=types.Type.STRING, description="Recipient email address"),
                    "subject": types.Schema(type=types.Type.STRING, description="Email subject"),
                    "body":    types.Schema(type=types.Type.STRING, description="Email body content"),
                },
                required=["to", "subject", "body"]
            )
        ),

        # ── Calendar ───────────────────────────────────────────────────────────
        types.FunctionDeclaration(
            name="get_today_events",
            description="User wants to know what's on their calendar today or their schedule for today",
            parameters=types.Schema(type=types.Type.OBJECT, properties={})
        ),

        types.FunctionDeclaration(
            name="get_week_events",
            description="User wants to see their calendar for this week or upcoming events",
            parameters=types.Schema(type=types.Type.OBJECT, properties={})
        ),

        types.FunctionDeclaration(
            name="create_event",
            description="User wants to schedule, create, or add a meeting or event to their calendar",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "title":       types.Schema(type=types.Type.STRING, description="Event title"),
                    "start_time":  types.Schema(type=types.Type.STRING, description="Start time in ISO 8601 format with IST offset +05:30"),
                    "end_time":    types.Schema(type=types.Type.STRING, description="End time in ISO 8601 format with IST offset +05:30"),
                    "description": types.Schema(type=types.Type.STRING, description="Optional event description"),
                    "location":    types.Schema(type=types.Type.STRING, description="Optional location"),
                    "attendees":   types.Schema(type=types.Type.STRING, description="Comma separated email addresses of attendees"),
                },
                required=["title", "start_time", "end_time"]
            )
        ),

        # ── Tasks ──────────────────────────────────────────────────────────────
        types.FunctionDeclaration(
            name="get_tasks",
            description="User wants to see, list, or check their tasks or to-do list",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "filter": types.Schema(type=types.Type.STRING, description="Filter: today, overdue, p1, p2, or leave empty for all"),
                }
            )
        ),

        types.FunctionDeclaration(
            name="create_task",
            description="User wants to add, create, or remember a task or to-do item",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "content":    types.Schema(type=types.Type.STRING, description="Task title/content"),
                    "due_string": types.Schema(type=types.Type.STRING, description="Due date in natural language e.g. 'tomorrow', 'next Monday'"),
                    "priority":   types.Schema(type=types.Type.INTEGER, description="Priority: 1=normal, 2=medium, 3=high, 4=urgent"),
                },
                required=["content"]
            )
        ),

        types.FunctionDeclaration(
            name="complete_task",
            description="User wants to mark a task as done or complete",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "task_id": types.Schema(type=types.Type.STRING, description="Task ID to complete"),
                },
                required=["task_id"]
            )
        ),

        # ── Relationships ──────────────────────────────────────────────────────
        types.FunctionDeclaration(
            name="get_person",
            description="User asks about a specific person ARIS knows — their info, history, birthday, preferences",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "name": types.Schema(type=types.Type.STRING, description="Person's full name"),
                },
                required=["name"]
            )
        ),

        types.FunctionDeclaration(
            name="get_neglected_contacts",
            description="User wants to know who they haven't talked to in a while or who to reach out to",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "days": types.Schema(type=types.Type.INTEGER, description="Days threshold, default 14"),
                }
            )
        ),

        types.FunctionDeclaration(
            name="get_upcoming_birthdays",
            description="User wants to know about upcoming birthdays",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "days_ahead": types.Schema(type=types.Type.INTEGER, description="How many days ahead to look, default 30"),
                }
            )
        ),

        # ── General ────────────────────────────────────────────────────────────
        types.FunctionDeclaration(
            name="general_chat",
            description="User is just chatting, asking a general question, or the message doesn't match any specific integration",
            parameters=types.Schema(type=types.Type.OBJECT, properties={})
        ),

    ])
]


# ─── ROUTER ────────────────────────────────────────────────────────────────────
def _keyword_fallback(message: str) -> dict:
    """
    Simple keyword-based intent detection when Gemini is unavailable.
    Not as smart as Gemini but handles the most common cases.
    """
    msg = message.lower()

    # Gmail
    if any(w in msg for w in ["email", "inbox", "mail", "emails"]):
        return {"intent": "read_inbox", "params": {"max_results": 5, "category": "primary"}}
    if any(w in msg for w in ["send email", "write email", "email to"]):
        return {"intent": "send_email", "params": {}}

    # Calendar
    if any(w in msg for w in ["today", "schedule", "calendar", "agenda"]):
        return {"intent": "get_today_events", "params": {}}
    if any(w in msg for w in ["this week", "week", "upcoming"]):
        return {"intent": "get_week_events", "params": {}}
    if any(w in msg for w in ["schedule", "create event", "add event", "meeting"]):
        return {"intent": "create_event", "params": {}}

    # Tasks
    if any(w in msg for w in ["task", "tasks", "todo", "to-do", "to do"]):
        return {"intent": "get_tasks", "params": {}}
    if any(w in msg for w in ["add task", "create task", "remind me", "remember to"]):
        return {"intent": "create_task", "params": {}}

    # Relationships
    if any(w in msg for w in ["haven't talked", "haven't spoken", "reach out", "contact", "neglected"]):
        return {"intent": "get_neglected_contacts", "params": {}}
    if any(w in msg for w in ["birthday", "birthdays"]):
        return {"intent": "get_upcoming_birthdays", "params": {}}

    return {"intent": "general_chat", "params": {}}
    
async def route_message(message: str) -> dict:
    """
    Detect intent from a natural language message.
    Returns: { "intent": "function_name", "params": { ... } }
    Falls back to general_chat if Gemini is unavailable.
    """
    try:
        response = gemini_client.models.generate_content(
            model=ROUTER_MODEL,
            contents=[types.Content(
                role="user",
                parts=[types.Part(text=message)]
            )],
            config=types.GenerateContentConfig(
                system_instruction=(
                    "You are an intent classifier for ARIS, a personal AI assistant. "
                    "Given the user's message, call the most appropriate function. "
                    "Always extract parameters from the message when possible. "
                    "For dates/times, use ISO 8601 format with India timezone offset +05:30. "
                    "If the message is just conversation or doesn't match any integration, call general_chat."
                ),
                tools=INTENT_TOOLS,
                temperature=0.1,
            )
        )

        for part in response.candidates[0].content.parts:
            if part.function_call:
                fc = part.function_call
                return {
                    "intent": fc.name,
                    "params": dict(fc.args) if fc.args else {}
                }

        return {"intent": "general_chat", "params": {}}

    except Exception as e:
        print(f"[Router] Gemini unavailable: {e}. Using keyword fallback.")
        return _keyword_fallback(message)


# ─── EXECUTOR ──────────────────────────────────────────────────────────────────

async def execute_intent(intent: str, params: dict) -> dict:
    """
    Execute the detected intent by calling the right integration function.
    Returns structured result data.
    """
    try:
        # ── Gmail ──────────────────────────────────────────────────────────────
        if intent == "read_inbox":
            from integrations.gmail import read_inbox
            emails = read_inbox(
                max_results=int(params.get("max_results", 5)),
                unread_only=bool(params.get("unread_only", False)),
                category=params.get("category", "primary")
            )
            return {"type": "emails", "data": emails}

        elif intent == "search_emails":
            from integrations.gmail import search_emails
            emails = search_emails(
                query=params.get("query", ""),
                max_results=int(params.get("max_results", 5))
            )
            return {"type": "emails", "data": emails}

        elif intent == "send_email":
            from integrations.gmail import send_email
            result = send_email(
                to=params.get("to", ""),
                subject=params.get("subject", ""),
                body=params.get("body", "")
            )
            return {"type": "email_sent", "data": result}

        # ── Calendar ───────────────────────────────────────────────────────────
        elif intent == "get_today_events":
            from integrations.calendar import get_today_events
            events = get_today_events()
            return {"type": "events", "data": events}

        elif intent == "get_week_events":
            from integrations.calendar import get_week_events
            events = get_week_events()
            return {"type": "events", "data": events}

        elif intent == "create_event":
            from integrations.calendar import create_event
            attendees = []
            if params.get("attendees"):
                attendees = [e.strip() for e in params["attendees"].split(",")]
            result = create_event(
                title=params.get("title", ""),
                start_time=params.get("start_time", ""),
                end_time=params.get("end_time", ""),
                description=params.get("description", ""),
                location=params.get("location", ""),
                attendees=attendees
            )
            return {"type": "event_created", "data": result}

        # ── Tasks ──────────────────────────────────────────────────────────────
        elif intent == "get_tasks":
            from integrations.tasks import get_all_tasks
            tasks = get_all_tasks(filter_str=params.get("filter"))
            return {"type": "tasks", "data": tasks}

        elif intent == "create_task":
            from integrations.tasks import create_task
            result = create_task(
                content=params.get("content", ""),
                due_string=params.get("due_string"),
                priority=int(params.get("priority", 1))
            )
            return {"type": "task_created", "data": result}

        elif intent == "complete_task":
            from integrations.tasks import complete_task
            result = complete_task(task_id=params.get("task_id", ""))
            return {"type": "task_completed", "data": result}

        # ── Relationships ──────────────────────────────────────────────────────
        elif intent == "get_person":
            from integrations.relationships import get_person
            person = get_person(params.get("name", ""))
            return {"type": "person", "data": person}

        elif intent == "get_neglected_contacts":
            from integrations.relationships import get_neglected_contacts
            people = get_neglected_contacts(days_threshold=int(params.get("days", 14)))
            return {"type": "people", "data": people}

        elif intent == "get_upcoming_birthdays":
            from integrations.relationships import get_upcoming_birthdays
            birthdays = get_upcoming_birthdays(days_ahead=int(params.get("days_ahead", 30)))
            return {"type": "birthdays", "data": birthdays}

        # ── Fallback ───────────────────────────────────────────────────────────
        else:
            return {"type": "general_chat", "data": None}

    except Exception as e:
        return {"type": "error", "data": str(e)}