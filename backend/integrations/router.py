# ARIS/integrations/router.py
# Natural language intent router — detects what the user wants and calls the right integration
# Uses Gemini function calling to classify intent and extract parameters
# Phase 4: Extended with PC control, file, system, browser, clipboard, notification intents

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
                    "unread_only": types.Schema(type=types.Type.BOOLEAN,  description="Only unread emails"),
                    "category":    types.Schema(type=types.Type.STRING,   description="Email category: primary, promotions, social, all"),
                },
            )
        ),

        types.FunctionDeclaration(
            name="search_emails",
            description="User wants to search for specific emails by keyword, sender, or subject",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "query":       types.Schema(type=types.Type.STRING,  description="Search query e.g. 'from:raj@gmail.com' or 'invoice'"),
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
                    "content":    types.Schema(type=types.Type.STRING,  description="Task title/content"),
                    "due_string": types.Schema(type=types.Type.STRING,  description="Due date in natural language e.g. 'tomorrow', 'next Monday'"),
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

        # ── PC Control ─────────────────────────────────────────────────────────
        types.FunctionDeclaration(
            name="open_application",
            description="User wants to open, launch, or start an application or program on their PC",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "app": types.Schema(type=types.Type.STRING, description="App name e.g. 'Spotify', 'Chrome', 'Notepad', 'VS Code'"),
                },
                required=["app"]
            )
        ),

        types.FunctionDeclaration(
            name="close_application",
            description="User wants to close, quit, or exit a window or application",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "title": types.Schema(type=types.Type.STRING, description="Window title or app name to close"),
                },
                required=["title"]
            )
        ),

        types.FunctionDeclaration(
            name="take_screenshot",
            description="User wants to take a screenshot or capture their screen",
            parameters=types.Schema(type=types.Type.OBJECT, properties={})
        ),

        types.FunctionDeclaration(
            name="type_text",
            description="User wants ARIS to type text or write something on screen",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "text": types.Schema(type=types.Type.STRING, description="Text to type"),
                },
                required=["text"]
            )
        ),

        types.FunctionDeclaration(
            name="press_hotkey",
            description="User wants to press a keyboard shortcut like Ctrl+C, Alt+Tab, Win+D",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "keys": types.Schema(type=types.Type.STRING, description="Key combo e.g. 'ctrl+c', 'alt+tab', 'win+d'"),
                },
                required=["keys"]
            )
        ),

        types.FunctionDeclaration(
            name="clipboard_write",
            description="User wants to copy text to clipboard",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "text": types.Schema(type=types.Type.STRING, description="Text to copy to clipboard"),
                },
                required=["text"]
            )
        ),

        types.FunctionDeclaration(
            name="clipboard_read",
            description="User wants to read or see what's currently in the clipboard",
            parameters=types.Schema(type=types.Type.OBJECT, properties={})
        ),

        # ── System Monitoring ──────────────────────────────────────────────────
        types.FunctionDeclaration(
            name="get_system_stats",
            description="User asks about system health: CPU usage, RAM, battery, disk space, performance",
            parameters=types.Schema(type=types.Type.OBJECT, properties={})
        ),

        types.FunctionDeclaration(
            name="list_processes",
            description="User wants to see running processes, apps, or what's using CPU/RAM",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "sort_by": types.Schema(type=types.Type.STRING, description="Sort by: cpu, ram, or name"),
                    "limit":   types.Schema(type=types.Type.INTEGER, description="How many to show, default 10"),
                }
            )
        ),

        types.FunctionDeclaration(
            name="kill_process",
            description="User wants to kill, stop, or force quit a process or app",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "name": types.Schema(type=types.Type.STRING, description="Process name to kill e.g. 'chrome', 'notepad'"),
                },
                required=["name"]
            )
        ),

        # ── File Management ────────────────────────────────────────────────────
        types.FunctionDeclaration(
            name="list_files",
            description="User wants to list, browse, or see files in a folder or directory",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "path": types.Schema(type=types.Type.STRING, description="Directory path, default ~ for home"),
                }
            )
        ),

        types.FunctionDeclaration(
            name="create_file",
            description="User wants to create a new file, possibly with content",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "path":    types.Schema(type=types.Type.STRING, description="Full file path e.g. ~/Desktop/notes.txt"),
                    "content": types.Schema(type=types.Type.STRING, description="Optional content to write"),
                },
                required=["path"]
            )
        ),

        types.FunctionDeclaration(
            name="read_file",
            description="User wants to read, open, or see the contents of a file",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "path": types.Schema(type=types.Type.STRING, description="File path to read"),
                },
                required=["path"]
            )
        ),

        types.FunctionDeclaration(
            name="search_files",
            description="User wants to find or search for files by name or extension",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "query":       types.Schema(type=types.Type.STRING, description="File name or keyword to search for"),
                    "search_path": types.Schema(type=types.Type.STRING, description="Where to search, default ~"),
                    "extension":   types.Schema(type=types.Type.STRING, description="File extension filter e.g. .txt .py .pdf"),
                },
                required=["query"]
            )
        ),

        # ── Browser ────────────────────────────────────────────────────────────
        types.FunctionDeclaration(
            name="browser_open",
            description="User wants to open a website or URL in the browser",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "url": types.Schema(type=types.Type.STRING, description="URL to open e.g. 'youtube.com' or 'https://github.com'"),
                },
                required=["url"]
            )
        ),

        types.FunctionDeclaration(
            name="browser_search",
            description="User wants to search the web or Google for something",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "query": types.Schema(type=types.Type.STRING, description="Search query"),
                    "max_results": types.Schema(type=types.Type.INTEGER, description="Number of results, default 5"),
                },
                required=["query"]
            )
        ),

        # ── Notifications ──────────────────────────────────────────────────────
        types.FunctionDeclaration(
            name="send_notification",
            description="User wants ARIS to send a desktop notification or reminder popup",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "title":   types.Schema(type=types.Type.STRING, description="Notification title"),
                    "message": types.Schema(type=types.Type.STRING, description="Notification message body"),
                },
                required=["title", "message"]
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


# ─── KEYWORD FALLBACK ──────────────────────────────────────────────────────────

def _keyword_fallback(message: str) -> dict:
    msg = message.lower()

    # Gmail
    if any(w in msg for w in ["email", "emails", "inbox", "mail", "unread"]):
        return {"intent": "read_inbox", "params": {"max_results": 5, "category": "primary"}}
    if "send" in msg and "email" in msg:
        return {"intent": "send_email", "params": {}}

    # Calendar
    if any(w in msg for w in ["calendar", "schedule", "agenda"]):
        return {"intent": "get_today_events", "params": {}}
    if any(w in msg for w in ["this week", "week events"]):
        return {"intent": "get_week_events", "params": {}}
    if any(w in msg for w in ["create event", "add event", "new meeting"]):
        return {"intent": "create_event", "params": {}}

    # Tasks
    if any(w in msg for w in ["task", "tasks", "todo", "to-do"]):
        return {"intent": "get_tasks", "params": {}}
    if any(w in msg for w in ["add task", "create task", "remind me"]):
        return {"intent": "create_task", "params": {}}

    # System
    if any(w in msg for w in ["cpu", "ram", "memory", "battery", "disk", "system"]):
        return {"intent": "get_system_stats", "params": {}}
    if any(w in msg for w in ["processes", "running apps"]):
        return {"intent": "list_processes", "params": {"sort_by": "cpu", "limit": 10}}

    # PC control
    if any(w in msg for w in ["screenshot", "capture screen"]):
        return {"intent": "take_screenshot", "params": {}}
    if msg.startswith("open ") or "launch " in msg:
        app = msg.replace("open ", "").replace("launch ", "").strip()
        return {"intent": "open_application", "params": {"app": app}}

    # Files
    if any(w in msg for w in ["list files", "show files", "what files", "my files"]):
        return {"intent": "list_files", "params": {"path": "~"}}

    # Browser
    if any(w in msg for w in ["search web", "search for", "google", "look up"]):
        query = msg.split("for ")[-1] if "for " in msg else msg
        return {"intent": "browser_search", "params": {"query": query}}
    if any(w in msg for w in ["open website", "go to", "visit"]):
        return {"intent": "browser_open", "params": {"url": ""}}

    # Relationships
    if any(w in msg for w in ["birthday", "birthdays"]):
        return {"intent": "get_upcoming_birthdays", "params": {}}
    if any(w in msg for w in ["haven't talked", "reach out", "neglected"]):
        return {"intent": "get_neglected_contacts", "params": {}}

    return {"intent": "general_chat", "params": {}}


# ─── ROUTER ────────────────────────────────────────────────────────────────────

async def route_message(message: str) -> dict:
    return _keyword_fallback(message)  # ← ADD THIS LINE TEMPORARILY

    try:
        response = gemini_client.models.generate_content(
            model=ROUTER_MODEL,
            contents=[types.Content(
                role="user",
                parts=[types.Part(text=message)]
            )],
            config=types.GenerateContentConfig(
                system_instruction=(
                    "You are an intent classifier for ARIS, a personal AI assistant with full PC control. "
                    "Given the user's message, call the most appropriate function and extract all parameters. "
                    "For dates/times, use ISO 8601 with India timezone offset +05:30. "
                    "For PC control commands (open app, screenshot, system stats, file ops, browser), "
                    "always extract the app name, path, or query from the message. "
                    "If the message is conversation or doesn't match any integration, call general_chat."
                ),
                tools=INTENT_TOOLS,
                temperature=0.1,
            )
        )

        candidates = response.candidates
        if not candidates:
            return {"intent": "general_chat", "params": {}}

        parts = candidates[0].content.parts if candidates[0].content else []
        if not parts:
            return {"intent": "general_chat", "params": {}}

        for part in parts:
            if hasattr(part, 'function_call') and part.function_call:
                fc = part.function_call
                return {
                    "intent": fc.name,
                    "params": dict(fc.args) if fc.args else {}
                }

        return {"intent": "general_chat", "params": {}}

    except Exception as e:
        import traceback
        print(f"[Router] Gemini error: {e}")
        print(f"[Router] Traceback: {traceback.format_exc()}")
        return _keyword_fallback(message)


# ─── EXECUTOR ──────────────────────────────────────────────────────────────────

async def execute_intent(intent: str, params: dict) -> dict:
    """
    Execute the detected intent by calling the right integration or control function.
    Returns structured result data for the AI to narrate.
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
            return {"type": "events", "data": get_today_events()}

        elif intent == "get_week_events":
            from integrations.calendar import get_week_events
            return {"type": "events", "data": get_week_events()}

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
            return {"type": "tasks", "data": get_all_tasks(filter_str=params.get("filter"))}

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
            return {"type": "task_completed", "data": complete_task(task_id=params.get("task_id", ""))}

        # ── Relationships ──────────────────────────────────────────────────────
        elif intent == "get_person":
            from integrations.relationships import get_person
            return {"type": "person", "data": get_person(params.get("name", ""))}

        elif intent == "get_neglected_contacts":
            from integrations.relationships import get_neglected_contacts
            return {"type": "people", "data": get_neglected_contacts(days_threshold=int(params.get("days", 14)))}

        elif intent == "get_upcoming_birthdays":
            from integrations.relationships import get_upcoming_birthdays
            return {"type": "birthdays", "data": get_upcoming_birthdays(days_ahead=int(params.get("days_ahead", 30)))}

        # ── PC Control ─────────────────────────────────────────────────────────
        elif intent == "open_application":
            from control.pc import open_app
            return {"type": "pc_action", "data": open_app(params.get("app", ""))}

        elif intent == "close_application":
            from control.pc import close_window
            return {"type": "pc_action", "data": close_window(params.get("title", ""))}

        elif intent == "take_screenshot":
            from control.pc import take_screenshot
            return {"type": "pc_action", "data": take_screenshot()}

        elif intent == "type_text":
            from control.pc import type_text
            return {"type": "pc_action", "data": type_text(params.get("text", ""))}

        elif intent == "press_hotkey":
            from control.pc import hotkey
            keys = [k.strip() for k in params.get("keys", "").replace("+", " ").split()]
            return {"type": "pc_action", "data": hotkey(*keys)}

        elif intent == "clipboard_write":
            from control.pc import clipboard_write
            return {"type": "pc_action", "data": clipboard_write(params.get("text", ""))}

        elif intent == "clipboard_read":
            from control.pc import clipboard_read
            return {"type": "pc_action", "data": clipboard_read()}

        # ── System Monitoring ──────────────────────────────────────────────────
        elif intent == "get_system_stats":
            from control.system import get_stats
            return {"type": "system_stats", "data": get_stats()}

        elif intent == "list_processes":
            from control.system import list_processes
            return {"type": "system_stats", "data": list_processes(
                sort_by=params.get("sort_by", "cpu"),
                limit=int(params.get("limit", 10))
            )}

        elif intent == "kill_process":
            from control.system import kill_process
            # Safety: always require confirmation via chat
            return {"type": "needs_confirmation", "data": {
                "action" : "kill_process",
                "name"   : params.get("name", ""),
                "message": f"Are you sure you want to kill '{params.get('name')}'? Reply 'yes kill it' to confirm."
            }}

        # ── File Management ────────────────────────────────────────────────────
        elif intent == "list_files":
            from control.files import list_directory
            return {"type": "files", "data": list_directory(params.get("path", "~"))}

        elif intent == "create_file":
            from control.files import create_file
            return {"type": "files", "data": create_file(
                path=params.get("path", ""),
                content=params.get("content", "")
            )}

        elif intent == "read_file":
            from control.files import read_file
            return {"type": "files", "data": read_file(params.get("path", ""))}

        elif intent == "search_files":
            from control.files import search_files
            return {"type": "files", "data": search_files(
                query=params.get("query", ""),
                search_path=params.get("search_path", "~"),
                extension=params.get("extension")
            )}

        # ── Browser ────────────────────────────────────────────────────────────
        elif intent == "browser_open":
            from control.browser import open_url
            return {"type": "browser", "data": open_url(params.get("url", ""))}

        elif intent == "browser_search":
            from control.browser import search_google
            return {"type": "browser", "data": search_google(
                query=params.get("query", ""),
                max_results=int(params.get("max_results", 5))
            )}

        # ── Notifications ──────────────────────────────────────────────────────
        elif intent == "send_notification":
            from control.notify import send_notification
            return {"type": "pc_action", "data": send_notification(
                title=params.get("title", "ARIS"),
                message=params.get("message", "")
            )}

        # ── Fallback ───────────────────────────────────────────────────────────
        else:
            return {"type": "general_chat", "data": None}

    except Exception as e:
        return {"type": "error", "data": str(e)}