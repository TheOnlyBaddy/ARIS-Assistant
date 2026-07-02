# ARIS/integrations/router.py
# Natural language intent router — detects what the user wants and calls the right integration
# Uses Gemini function calling to classify intent and extract parameters
# Phase 4: Extended with PC control, file, system, browser, clipboard, notification intents

import os
import json
import re
import httpx
from typing import Optional
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_CHAT_MODEL = os.getenv("OLLAMA_CHAT_MODEL", "qwen3:8b")

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

        # ── Media Control (New) ────────────────────────────────────────────────
        types.FunctionDeclaration(
            name="media_control",
            description="User wants to control volume or media playback (play, pause, next, prev, mute, volume up, volume down, set volume)",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "action": types.Schema(type=types.Type.STRING, description="Action: play, pause, next, prev, mute, vol_up, vol_down, set_volume"),
                    "level":  types.Schema(type=types.Type.INTEGER, description="Optional volume level between 0 and 100"),
                },
                required=["action"]
            )
        ),

        # ── Brightness Control (New) ───────────────────────────────────────────
        types.FunctionDeclaration(
            name="brightness_control",
            description="User wants to adjust screen brightness (dim screen, set brightness, make brighter)",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "level": types.Schema(type=types.Type.INTEGER, description="Brightness percentage level between 0 and 100"),
                },
                required=["level"]
            )
        ),

        # ── Power Control (New) ────────────────────────────────────────────────
        types.FunctionDeclaration(
            name="power_control",
            description="User wants to manage PC power state: lock screen, put to sleep, shut down, restart, cancel pending shutdown",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "action": types.Schema(type=types.Type.STRING, description="Action: lock, sleep, shutdown, restart, cancel"),
                },
                required=["action"]
            )
        ),

        # ── Window Snapping (New) ──────────────────────────────────────────────
        types.FunctionDeclaration(
            name="window_snap",
            description="User wants to snap or tile the active/current window to the left or right half of the screen",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "direction": types.Schema(type=types.Type.STRING, description="Direction to snap: left, right"),
                },
                required=["direction"]
            )
        ),

        # ── Network Diagnostics (New) ──────────────────────────────────────────
        types.FunctionDeclaration(
            name="network_diagnostics",
            description="User wants to check network connection signal, SSID, public IP, ping latency, internet status",
            parameters=types.Schema(type=types.Type.OBJECT, properties={})
        ),

        # ── Phase 5: Knowledge Base ────────────────────────────────────────────
        types.FunctionDeclaration(
            name="knowledge_store",
            description="User wants ARIS to remember a fact, note, or information permanently in the knowledge base",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "content": types.Schema(type=types.Type.STRING, description="Fact/note content to store"),
                    "title": types.Schema(type=types.Type.STRING, description="Optional title for the note"),
                },
                required=["content"]
            )
        ),
        types.FunctionDeclaration(
            name="knowledge_search",
            description="User asks a question or wants to search their personal knowledge base/notes/documents",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "query": types.Schema(type=types.Type.STRING, description="Search query"),
                },
                required=["query"]
            )
        ),

        # ── Phase 5: Code Assistant ────────────────────────────────────────────
        types.FunctionDeclaration(
            name="code_generate",
            description="User wants code written, generated, or completed in any programming language",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "description": types.Schema(type=types.Type.STRING, description="What the code should do"),
                    "language": types.Schema(type=types.Type.STRING, description="Programming language e.g. python, javascript, rust"),
                },
                required=["description"]
            )
        ),
        types.FunctionDeclaration(
            name="code_debug",
            description="User wants code debugged, corrected, or fixed",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "code": types.Schema(type=types.Type.STRING, description="Code content to debug"),
                    "error": types.Schema(type=types.Type.STRING, description="Optional error message or description of failure"),
                },
                required=["code"]
            )
        ),
        types.FunctionDeclaration(
            name="code_execute",
            description="User wants to run or execute Python code locally",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "code": types.Schema(type=types.Type.STRING, description="Python code to run"),
                },
                required=["code"]
            )
        ),

        # ── Phase 5: Habits & Goals ────────────────────────────────────────────
        types.FunctionDeclaration(
            name="habit_create",
            description="User wants to define a new daily habit or goal to track",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "name": types.Schema(type=types.Type.STRING, description="Habit/goal name"),
                    "description": types.Schema(type=types.Type.STRING, description="Optional description"),
                    "target": types.Schema(type=types.Type.STRING, description="Optional target metric e.g. 3L, 30 mins"),
                },
                required=["name"]
            )
        ),
        types.FunctionDeclaration(
            name="habit_log",
            description="User wants to log, complete, or check off a daily habit",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "habit_id": types.Schema(type=types.Type.INTEGER, description="Optional ID of the habit"),
                    "name": types.Schema(type=types.Type.STRING, description="Name of the habit e.g. exercise, water"),
                    "notes": types.Schema(type=types.Type.STRING, description="Optional completion notes"),
                }
            )
        ),
        types.FunctionDeclaration(
            name="habit_streaks",
            description="User wants to see their current habit streaks and completion status",
            parameters=types.Schema(type=types.Type.OBJECT, properties={})
        ),

        # ── Phase 5: Health & Wellbeing ────────────────────────────────────────
        types.FunctionDeclaration(
            name="health_log",
            description="User wants to log health metrics: sleep, mood, energy, water, or exercise",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "sleep_hours": types.Schema(type=types.Type.NUMBER, description="Hours of sleep"),
                    "mood": types.Schema(type=types.Type.STRING, description="User mood e.g. good, tired, great"),
                    "energy": types.Schema(type=types.Type.INTEGER, description="Energy level 1-10"),
                    "water_litres": types.Schema(type=types.Type.NUMBER, description="Water consumed in litres"),
                    "exercise_mins": types.Schema(type=types.Type.INTEGER, description="Exercise duration in minutes"),
                    "exercise_type": types.Schema(type=types.Type.STRING, description="Type of exercise e.g. running, gym"),
                    "notes": types.Schema(type=types.Type.STRING, description="Optional health notes"),
                }
            )
        ),
        types.FunctionDeclaration(
            name="health_trends",
            description="User wants to see a health summary, averages, or AI trend analysis",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "days": types.Schema(type=types.Type.INTEGER, description="Number of days to analyze, default 7"),
                }
            )
        ),

        # ── Phase 5: Finance Awareness ─────────────────────────────────────────
        types.FunctionDeclaration(
            name="finance_log",
            description="User wants to log an expense or income transaction in INR (₹)",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "amount": types.Schema(type=types.Type.NUMBER, description="Transaction amount in INR"),
                    "category": types.Schema(type=types.Type.STRING, description="Category: food, transport, entertainment, shopping, bills, etc."),
                    "description": types.Schema(type=types.Type.STRING, description="What the transaction was for"),
                    "type": types.Schema(type=types.Type.STRING, description="Type: expense or income"),
                },
                required=["amount"]
            )
        ),
        types.FunctionDeclaration(
            name="finance_summary",
            description="User wants to see budget status, monthly summary, or savings goals progress",
            parameters=types.Schema(type=types.Type.OBJECT, properties={})
        ),

        # ── Phase 5: Meal Planning ─────────────────────────────────────────────
        types.FunctionDeclaration(
            name="meal_plan",
            description="User wants to plan their meals, get meal suggestions, or log a meal they ate",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "action": types.Schema(type=types.Type.STRING, description="Action: plan (generate 7-day plan), suggest (suggest dinners/breakfasts), log (log a meal eaten)"),
                    "meal_type": types.Schema(type=types.Type.STRING, description="Meal type for suggestions e.g. breakfast, dinner"),
                    "meal_name": types.Schema(type=types.Type.STRING, description="Meal name for logging"),
                    "calories": types.Schema(type=types.Type.INTEGER, description="Calorie estimate for logging"),
                }
            )
        ),

        # ── Phase 5: Personal Tutor ────────────────────────────────────────────
        types.FunctionDeclaration(
            name="tutor_learn",
            description="User wants to learn about a topic, start a lesson, or study a subject",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "topic": types.Schema(type=types.Type.STRING, description="Subject or concept to learn about"),
                    "difficulty": types.Schema(type=types.Type.STRING, description="Target level: beginner, medium, hard"),
                },
                required=["topic"]
            )
        ),
        types.FunctionDeclaration(
            name="tutor_quiz",
            description="User wants to take a multiple-choice quiz to test their knowledge on a topic",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "topic": types.Schema(type=types.Type.STRING, description="Quiz topic"),
                    "difficulty": types.Schema(type=types.Type.STRING, description="Difficulty level"),
                },
                required=["topic"]
            )
        ),

        # ── Phase 5: Creative Writing & Images ────────────────────────────────
        types.FunctionDeclaration(
            name="creative_writing",
            description="User wants a blog post, essay, email, or LinkedIn post written in their voice/style",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "topic": types.Schema(type=types.Type.STRING, description="Topic or prompt to write about"),
                    "format": types.Schema(type=types.Type.STRING, description="Format: blog, essay, email, linkedin_post"),
                },
                required=["topic"]
            )
        ),
        types.FunctionDeclaration(
            name="generate_image",
            description="User wants an image generated from a text description using Gemini Imagen",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "prompt": types.Schema(type=types.Type.STRING, description="Image description"),
                },
                required=["prompt"]
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


# ─── LOCAL HEURISTICS / KEYWORDS ───────────────────────────────────────────────

def _local_heuristics(message: str) -> Optional[dict]:
    msg = message.lower().strip()

    # Intercept conceptual/informational questions to prevent them from misclassifying
    # into local system tools (e.g., matching "TCP/UDP" to "network_diagnostics")
    conceptual_triggers = [
        "explain the difference", "difference between", "what is the difference",
        "explain how", "how does", "what is tcp", "what is udp", "why is", "why does",
        "tell me about", "explain ", "what are ", "can you explain", "what is ",
        "write a", "write an", "generate", "create a story", "passage", "essay",
        "paragraph", "summarize", "summary", "compare", "analyze", "analyse",
        "help me understand", "elaborate", "pros and cons", "advantages", "disadvantages"
    ]
    if any(trigger in msg for trigger in conceptual_triggers):
        return {"intent": "general_chat", "params": {}}

    # ── PC Control ──
    if msg in ("take screenshot", "screenshot", "capture screen", "capture screenshot"):
        return {"intent": "take_screenshot", "params": {}}
    
    if msg.startswith("open ") or msg.startswith("launch ") or msg.startswith("start "):
        app = msg.replace("open ", "").replace("launch ", "").replace("start ", "").strip()
        return {"intent": "open_application", "params": {"app": app}}
        
    if msg.startswith("close ") or msg.startswith("quit ") or msg.startswith("exit "):
        title = msg.replace("close ", "").replace("quit ", "").replace("exit ", "").strip()
        return {"intent": "close_application", "params": {"title": title}}
        
    if msg.startswith("kill "):
        name = msg.replace("kill ", "").strip()
        return {"intent": "kill_process", "params": {"name": name}}
        
    if msg.startswith("type "):
        text = message[5:].strip()  # Preserve casing
        return {"intent": "type_text", "params": {"text": text}}
        
    if msg.startswith("press hotkey ") or msg.startswith("press key "):
        keys = msg.replace("press hotkey ", "").replace("press key ", "").strip()
        return {"intent": "press_hotkey", "params": {"keys": keys}}

    if msg.startswith("notify ") or msg.startswith("send notification "):
        notify_msg = message.replace("notify ", "").replace("send notification ", "").strip()
        return {"intent": "send_notification", "params": {"title": "ARIS", "message": notify_msg}}

    # ── Media & Volume ──
    if msg in ("mute", "mute system", "mute volume"):
        return {"intent": "media_control", "params": {"action": "mute"}}
    if msg in ("unmute", "unmute system", "unmute volume"):
        return {"intent": "media_control", "params": {"action": "unmute"}}
    if msg in ("toggle mute", "toggle sound", "toggle volume"):
        return {"intent": "media_control", "params": {"action": "toggle_mute"}}
    if msg in ("volume up", "louder", "increase volume", "raise volume"):
        return {"intent": "media_control", "params": {"action": "vol_up"}}
    if msg in ("volume down", "quieter", "decrease volume", "lower volume"):
        return {"intent": "media_control", "params": {"action": "vol_down"}}
    if msg in ("play", "pause", "play music", "pause music", "resume", "resume music"):
        return {"intent": "media_control", "params": {"action": "play"}}
    if msg in ("next", "next song", "next track", "skip song"):
        return {"intent": "media_control", "params": {"action": "next"}}
    if msg in ("previous", "prev", "previous song", "prev track"):
        return {"intent": "media_control", "params": {"action": "prev"}}
        
    # Regex set volume to X or volume X
    vol_match = re.search(r'(?:set\s+)?volume\s+(?:to\s+)?(\d+)', msg)
    if vol_match:
        try:
            level = int(vol_match.group(1))
            return {"intent": "media_control", "params": {"action": "set_volume", "level": level}}
        except ValueError:
            pass

    # ── Brightness ──
    bright_match = re.search(r'(?:set\s+)?brightness\s+(?:to\s+)?(\d+)', msg)
    if bright_match:
        try:
            level = int(bright_match.group(1))
            return {"intent": "brightness_control", "params": {"level": level}}
        except ValueError:
            pass
    if "dim screen" in msg or "lower brightness" in msg:
        return {"intent": "brightness_control", "params": {"level": 30}}
    if "brighten screen" in msg or "increase brightness" in msg:
        return {"intent": "brightness_control", "params": {"level": 80}}

    # ── Power ──
    if msg in ("lock pc", "lock screen", "lock computer"):
        return {"intent": "power_control", "params": {"action": "lock"}}
    if msg in ("sleep pc", "put to sleep", "sleep computer"):
        return {"intent": "power_control", "params": {"action": "sleep"}}
    if msg in ("shutdown pc", "turn off pc", "shutdown computer", "turn off computer"):
        return {"intent": "power_control", "params": {"action": "shutdown"}}
    if msg in ("restart pc", "reboot pc", "restart computer", "reboot computer"):
        return {"intent": "power_control", "params": {"action": "restart"}}
    if msg in ("cancel shutdown", "abort shutdown", "stop shutdown"):
        return {"intent": "power_control", "params": {"action": "cancel"}}

    # ── Window Snapping ──
    if msg in ("snap left", "tile left", "window left", "snap window left", "tile window left"):
        return {"intent": "window_snap", "params": {"direction": "left"}}
    if msg in ("snap right", "tile right", "window right", "snap window right", "tile window right"):
        return {"intent": "window_snap", "params": {"direction": "right"}}

    # ── Clipboard ──
    if msg in ("clipboard read", "get clipboard", "what's in clipboard", "read clipboard", "show clipboard"):
        return {"intent": "clipboard_read", "params": {}}
    if msg.startswith("clipboard write ") or msg.startswith("copy to clipboard "):
        clip_text = message.replace("clipboard write ", "").replace("copy to clipboard ", "").strip()
        return {"intent": "clipboard_write", "params": {"text": clip_text}}

    # ── System Stats ──
    if msg in ("cpu", "ram", "memory", "battery", "disk", "system stats", "system health", "get stats"):
        return {"intent": "get_system_stats", "params": {}}
    if msg in ("processes", "running apps", "show processes", "list processes"):
        return {"intent": "list_processes", "params": {"sort_by": "cpu", "limit": 10}}
    if msg in ("network ssid", "signal", "ping", "latency", "internet stats", "network diagnostics", "ping latency", "network signal"):
        return {"intent": "network_diagnostics", "params": {}}

    # ── Files ──
    if msg in ("list files", "show files", "what files", "my files"):
        return {"intent": "list_files", "params": {"path": "~"}}
    if msg.startswith("list files in ") or msg.startswith("show files in "):
        path = message.replace("list files in ", "").replace("show files in ", "").strip()
        return {"intent": "list_files", "params": {"path": path}}
    if msg.startswith("read file ") or msg.startswith("show file "):
        path = message.replace("read file ", "").replace("show file ", "").strip()
        return {"intent": "read_file", "params": {"path": path}}

    # ── Browser ──
    if msg.startswith("search for ") or msg.startswith("search web for ") or msg.startswith("google "):
        query = message.replace("search for ", "").replace("search web for ", "").replace("google ", "").strip()
        return {"intent": "browser_search", "params": {"query": query}}
    if msg.startswith("open website ") or msg.startswith("go to ") or msg.startswith("visit "):
        url = msg.replace("open website ", "").replace("go to ", "").replace("visit ", "").strip()
        return {"intent": "browser_open", "params": {"url": url}}

    # ── Phase 5 Heuristics ──
    if msg.startswith("remember this:") or msg.startswith("remember that:"):
        fact = message[14:].strip()
        return {"intent": "knowledge_store", "params": {"content": fact}}

    if msg.startswith("write code to ") or msg.startswith("generate code to ") or msg.startswith("write a function to "):
        desc = message.replace("write code to ", "").replace("generate code to ", "").replace("write a function to ", "").strip()
        return {"intent": "code_generate", "params": {"description": desc}}

    if msg.startswith("log my habit: ") or msg.startswith("log habit: "):
        name = message.replace("log my habit: ", "").replace("log habit: ", "").strip()
        return {"intent": "habit_log", "params": {"name": name}}

    if msg.startswith("i spent ₹") or msg.startswith("spent ₹") or msg.startswith("spent rs "):
        # e.g., i spent ₹200 on coffee
        # Let's extract amount and description using regex
        match = re.search(r'(?:spent\s+[₹rs\.?\s]*)(\d+)(?:\s+on\s+)?(.*)?', msg)
        if match:
            amt = float(match.group(1))
            desc = match.group(2) or ""
            # Simple category detection
            cat = "other"
            for c in ["food", "transport", "entertainment", "shopping", "bills", "rent", "salary"]:
                if c in desc:
                    cat = c
                    break
            return {"intent": "finance_log", "params": {"amount": amt, "category": cat, "description": desc}}

    if "slept " in msg and " last night" in msg:
        match = re.search(r'slept\s+(\d+(?:\.\d+)?)\s*hour', msg)
        if match:
            hours = float(match.group(1))
            return {"intent": "health_log", "params": {"sleep_hours": hours}}

    if msg == "plan my meals" or msg == "plan meals" or msg == "meal plan":
        return {"intent": "meal_plan", "params": {"action": "plan"}}

    if msg.startswith("teach me "):
        topic = message[9:].strip()
        return {"intent": "tutor_learn", "params": {"topic": topic}}

    if msg.startswith("generate an image of ") or msg.startswith("generate image of "):
        prompt = message.replace("generate an image of ", "").replace("generate image of ", "").strip()
        return {"intent": "generate_image", "params": {"prompt": prompt}}

    if msg.startswith("write a blog post about ") or msg.startswith("write a post about "):
        topic = message.replace("write a blog post about ", "").replace("write a post about ", "").strip()
        return {"intent": "creative_writing", "params": {"topic": topic, "format": "blog"}}

    return None


# ─── LOCAL OLLAMA INTENT CLASSIFIER ─────────────────────────────────────────────

async def _classify_with_ollama(message: str) -> dict:
    prompt = f"""You are the intent routing engine for ARIS.
Classify the following user message into one of the available intents.
You MUST output a valid JSON object matching this schema:
{{
  "intent": "intent_name",
  "params": {{}}
}}

Available intents:
- "open_application": Open/launch an app. params: {{"app": "app name"}}
- "close_application": Close/quit an app. params: {{"title": "app name"}}
- "media_control": Control volume or playback. params: {{"action": "mute|vol_up|vol_down|play|next|prev|set_volume", "level": optional_integer}}
- "brightness_control": Adjust screen brightness. params: {{"level": integer}}
- "power_control": Put PC to sleep, lock, shutdown, restart. params: {{"action": "lock|sleep|shutdown|restart|cancel"}}
- "window_snap": Snap window to half screen. params: {{"direction": "left|right"}}
- "take_screenshot": Capture the screen. params: {{}}
- "type_text": Emulate typing text. params: {{"text": "text to type"}}
- "press_hotkey": Press key shortcut. params: {{"keys": "key combo"}}
- "send_notification": Show desktop notification. params: {{"message": "alert message"}}
- "clipboard_read": Read from clipboard. params: {{}}
- "clipboard_write": Copy text to clipboard. params: {{"text": "text"}}
- "get_system_stats": CPU, RAM, disk, battery. params: {{}}
- "list_processes": Show active running processes. params: {{}}
- "kill_process": Kill/stop a process. params: {{"name": "process name"}}
- "network_diagnostics": Wi-Fi, signal, latency ping, public IP. params: {{}}
- "list_files": List files in directory. params: {{"path": "folder path"}}
- "read_file": Read content of a file. params: {{"path": "file path"}}
- "write_file": Write content to a file. params: {{"path": "file path", "content": "text"}}
- "browser_search": Search web/Google. params: {{"query": "search query"}}
- "browser_open": Open a URL. params: {{"url": "url string"}}
- "read_inbox": Read unread email inbox. params: {{}}
- "send_email": Send an email. params: {{}}
- "search_emails": Search email inbox. params: {{}}
- "get_today_events": Show today's calendar events. params: {{}}
- "get_week_events": Show this week's calendar events. params: {{}}
- "create_event": Add event to calendar. params: {{}}
- "get_tasks": Show Google Tasks checklist. params: {{}}
- "create_task": Add task to Google Tasks. params: {{}}
- "complete_task": Mark task as completed. params: {{}}
- "get_person": Query relationship memory details. params: {{"name": "person name"}}
- "get_neglected_contacts": Identify people to reach out to. params: {{}}
- "get_upcoming_birthdays": Check birthdays. params: {{}}
- "knowledge_store": Store fact/note permanently. params: {{"content": "fact", "title": "optional title"}}
- "knowledge_search": Search notes/docs. params: {{"query": "search query"}}
- "code_generate": Write/generate code. params: {{"description": "what code does", "language": "python|js"}}
- "code_debug": Debug code. params: {{"code": "code", "error": "optional error"}}
- "code_execute": Run Python locally. params: {{"code": "python code"}}
- "habit_create": Track a new habit. params: {{"name": "name", "description": "text", "target": "3L"}}
- "habit_log": Log habit done. params: {{"name": "name", "notes": "text"}}
- "habit_streaks": Show habits checklist & streaks. params: {{}}
- "health_log": Log sleep, mood, energy, water, exercise. params: {{"sleep_hours": 7.5, "mood": "good", "water_litres": 2.5, "exercise_mins": 30, "exercise_type": "running", "notes": "text"}}
- "health_trends": View health summary & analysis. params: {{"days": 7}}
- "finance_log": Log transaction in INR (₹). params: {{"amount": 150, "category": "food", "description": "lunch", "type": "expense|income"}}
- "finance_summary": Show budgets, monthly spending, savings goals. params: {{}}
- "meal_plan": Generate meal plan or suggestions. params: {{"action": "plan|suggest|log", "meal_type": "dinner", "meal_name": "text", "calories": 400}}
- "tutor_learn": Start a structured learning lesson. params: {{"topic": "subject", "difficulty": "beginner|medium"}}
- "tutor_quiz": Take a multiple-choice quiz. params: {{"topic": "subject", "difficulty": "easy|medium"}}
- "creative_writing": Write content in user style. params: {{"topic": "prompt", "format": "blog|linkedin_post|email"}}
- "generate_image": Generate an image. params: {{"prompt": "image description"}}
- "general_chat": Conversational greetings, creative tasks, passages, jokes, or any message that doesn't fit a specific tool. params: {{}}

User message: "{message}"

JSON response:"""

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": OLLAMA_CHAT_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {
                        "temperature": 0.0
                    }
                }
            )
            r.raise_for_status()
            res_json = r.json()
            response_text = res_json.get("response", "").strip()
            
            parsed = json.loads(response_text)
            if "intent" in parsed:
                return {
                    "intent": parsed["intent"],
                    "params": parsed.get("params", {})
                }
    except Exception as e:
        print(f"[Router] Local Ollama classification failed: {e}")
        
    return {"intent": "general_chat", "params": {}}


# ─── ROUTER ────────────────────────────────────────────────────────────────────

async def route_message(message: str) -> dict:
    # 1. Local keyword/regex heuristics (0ms)
    matched = _local_heuristics(message)
    if matched:
        print(f"[ARIS Router] Heuristics matched intent: {matched['intent']}")
        return matched

    # 2. Local Ollama intent classification (local model)
    print(f"[ARIS Router] Calling local Ollama intent classifier...")
    return await _classify_with_ollama(message)


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
            app_name = params.get("app", "")
            # Try folder/file/URL first
            from control.pc.software.folder import open_folder
            folder_res = open_folder(app_name)
            if folder_res is not None:
                if folder_res.get("status") == "error":
                    return {"type": "app_not_found", "data": {"app": app_name, "error": folder_res.get("error")}}
                return {"type": "pc_action", "data": folder_res}
            # Fall back to app launcher
            from control.pc.software import open_app
            res = open_app(app_name)
            if res.get("status") == "error":
                return {"type": "app_not_found", "data": {"app": app_name, "error": res.get("error")}}
            return {"type": "pc_action", "data": res}

        elif intent == "close_application":
            from control.pc.software import close_window
            return {"type": "pc_action", "data": close_window(params.get("title", ""))}

        elif intent == "take_screenshot":
            from control.pc.software import take_screenshot
            return {"type": "pc_action", "data": take_screenshot()}

        elif intent == "type_text":
            from control.pc.software import type_text
            return {"type": "pc_action", "data": type_text(params.get("text", ""))}

        elif intent == "press_hotkey":
            from control.pc.software import hotkey
            keys = [k.strip() for k in params.get("keys", "").replace("+", " ").split()]
            return {"type": "pc_action", "data": hotkey(*keys)}

        elif intent == "clipboard_write":
            from control.pc.software import clipboard_write
            return {"type": "pc_action", "data": clipboard_write(params.get("text", ""))}

        elif intent == "clipboard_read":
            from control.pc.software import clipboard_read
            return {"type": "pc_action", "data": clipboard_read()}

        # ── System Monitoring ──────────────────────────────────────────────────
        elif intent == "get_system_stats":
            from control.pc.hardware import get_stats
            return {"type": "system_stats", "data": get_stats()}

        elif intent == "list_processes":
            from control.pc.hardware import list_processes
            return {"type": "system_stats", "data": list_processes(
                sort_by=params.get("sort_by", "cpu"),
                limit=int(params.get("limit", 10))
            )}

        elif intent == "kill_process":
            from control.pc.hardware import kill_process
            # Safety: always require confirmation via chat
            return {"type": "needs_confirmation", "data": {
                "action" : "kill_process",
                "name"   : params.get("name", ""),
                "message": f"Are you sure you want to kill '{params.get('name')}'? Reply 'yes kill it' to confirm."
            }}

        # ── File Management ────────────────────────────────────────────────────
        elif intent == "list_files":
            from control.pc.software import list_directory
            return {"type": "files", "data": list_directory(params.get("path", "~"))}

        elif intent == "create_file":
            from control.pc.software import create_file
            return {"type": "files", "data": create_file(
                path=params.get("path", ""),
                content=params.get("content", "")
            )}

        elif intent == "read_file":
            from control.pc.software import read_file
            return {"type": "files", "data": read_file(params.get("path", ""))}

        elif intent == "search_files":
            from control.pc.software import search_files
            return {"type": "files", "data": search_files(
                query=params.get("query", ""),
                search_path=params.get("search_path", "~"),
                extension=params.get("extension")
            )}

        # ── Browser ────────────────────────────────────────────────────────────
        elif intent == "browser_open":
            from control.pc.software import open_url
            return {"type": "browser", "data": open_url(params.get("url", ""))}

        elif intent == "browser_search":
            from intelligence.search import web_search
            res = await web_search(
                query=params.get("query", ""),
                num_results=int(params.get("max_results", 5))
            )
            return {"type": "browser", "data": res}

        # ── Notifications ──────────────────────────────────────────────────────
        elif intent == "send_notification":
            from control.pc.software import send_notification
            return {"type": "pc_action", "data": send_notification(
                title=params.get("title", "ARIS"),
                message=params.get("message", "")
            )}

        # ── Media Control (New) ────────────────────────────────────────────────
        elif intent == "media_control":
            from control.pc.hardware import media_control
            action = params.get("action", "")
            level = params.get("level")
            return {"type": "pc_action", "data": media_control(action, level)}

        # ── Brightness Control (New) ───────────────────────────────────────────
        elif intent == "brightness_control":
            from control.pc.hardware import set_brightness
            level = params.get("level", 50)
            return {"type": "pc_action", "data": set_brightness(level)}

        # ── Power Control (New) ────────────────────────────────────────────────
        elif intent == "power_control":
            from control.pc.hardware import lock_pc, sleep_pc, shutdown_pc, restart_pc, cancel_shutdown
            action = params.get("action", "").lower().strip()
            confirmed = params.get("confirmed", False)
            if action == "lock":
                return {"type": "pc_action", "data": lock_pc()}
            elif action == "sleep":
                return {"type": "pc_action", "data": sleep_pc()}
            elif action == "shutdown":
                res = shutdown_pc(confirmed)
                if res.get("status") == "needs_confirmation":
                    return {"type": "needs_confirmation", "data": {
                        "action": "power_control",
                        "params": {"action": "shutdown"},
                        "message": "Are you sure you want to shut down your PC? Reply 'yes' to proceed."
                    }}
                return {"type": "pc_action", "data": res}
            elif action == "restart":
                res = restart_pc(confirmed)
                if res.get("status") == "needs_confirmation":
                    return {"type": "needs_confirmation", "data": {
                        "action": "power_control",
                        "params": {"action": "restart"},
                        "message": "Are you sure you want to restart your PC? Reply 'yes' to proceed."
                    }}
                return {"type": "pc_action", "data": res}
            elif action in ("cancel", "abort"):
                return {"type": "pc_action", "data": cancel_shutdown()}
            else:
                return {"type": "pc_action", "data": {"status": "error", "error": f"Unknown power action '{action}'"}}

        # ── Window Snapping (New) ──────────────────────────────────────────────
        elif intent == "window_snap":
            from control.pc.software import snap_window
            direction = params.get("direction", "left")
            return {"type": "pc_action", "data": snap_window(direction)}

        # ── Network Diagnostics (New) ──────────────────────────────────────────
        elif intent == "network_diagnostics":
            from control.pc.hardware import get_network_diagnostics
            return {"type": "network_diagnostics", "data": get_network_diagnostics()}

        # ── Phase 5: Knowledge Base ────────────────────────────────────────────
        elif intent == "knowledge_store":
            from intelligence.knowledge import add_document
            res = await add_document(doc_type="text", content=params.get("content", ""), title=params.get("title", "Remembered Note"))
            return {"type": "knowledge", "data": res}

        elif intent == "knowledge_search":
            from intelligence.knowledge import search_knowledge
            res = await search_knowledge(query=params.get("query", ""))
            return {"type": "knowledge", "data": res}

        # ── Phase 5: Code Assistant ────────────────────────────────────────────
        elif intent == "code_generate":
            from intelligence.code import generate_code
            res = await generate_code(description=params.get("description", ""), language=params.get("language", "python"))
            return {"type": "code", "data": res}

        elif intent == "code_debug":
            from intelligence.code import debug_code
            res = await debug_code(code=params.get("code", ""), error=params.get("error", ""), language=params.get("language", "python"))
            return {"type": "code", "data": res}

        elif intent == "code_execute":
            from intelligence.code import execute_python
            res = execute_python(code=params.get("code", ""))
            return {"type": "code", "data": res}

        # ── Phase 5: Habits & Goals ────────────────────────────────────────────
        elif intent == "habit_create":
            from life.habits import create_habit
            res = create_habit(name=params.get("name", ""), description=params.get("description", ""), target=params.get("target", ""))
            return {"type": "habits", "data": res}

        elif intent == "habit_log":
            from life.habits import log_habit
            res = log_habit(habit_id=params.get("habit_id", 1), notes=params.get("notes", ""))
            return {"type": "habits", "data": res}

        elif intent == "habit_streaks":
            from life.habits import get_all_streaks
            res = get_all_streaks()
            return {"type": "habits", "data": res}

        # ── Phase 5: Health & Wellbeing ────────────────────────────────────────
        elif intent == "health_log":
            from life.health import log_health
            res = log_health(
                sleep_hours=params.get("sleep_hours"),
                mood=params.get("mood"),
                energy=params.get("energy"),
                water_litres=params.get("water_litres"),
                exercise_mins=params.get("exercise_mins"),
                exercise_type=params.get("exercise_type", ""),
                notes=params.get("notes", "")
            )
            return {"type": "health", "data": res}

        elif intent == "health_trends":
            from life.health import get_health_summary, analyze_trends
            summary = await get_health_summary()
            trends = await analyze_trends(days=params.get("days", 7))
            return {"type": "health", "data": {"summary": summary, "trends": trends}}

        # ── Phase 5: Finance Awareness ─────────────────────────────────────────
        elif intent == "finance_log":
            from life.finance import log_transaction
            res = log_transaction(
                amount=params.get("amount"),
                category=params.get("category", "other"),
                description=params.get("description", ""),
                txn_type=params.get("type", "expense")
            )
            return {"type": "finance", "data": res}

        elif intent == "finance_summary":
            from life.finance import get_monthly_summary, get_budgets, list_savings_goals
            summary = get_monthly_summary()
            budgets = get_budgets()
            savings = list_savings_goals()
            return {"type": "finance", "data": {"monthly_summary": summary, "budgets": budgets, "savings": savings}}

        # ── Phase 5: Meal Planning ─────────────────────────────────────────────
        elif intent == "meal_plan":
            action = params.get("action", "plan").lower().strip()
            if action == "plan":
                from life.meals import plan_weekly_meals
                res = await plan_weekly_meals()
            elif action == "suggest":
                from life.meals import suggest_meals
                res = await suggest_meals(meal_type=params.get("meal_type", ""))
            else:
                from life.meals import log_meal
                res = log_meal(name=params.get("meal_name", ""), meal_type=params.get("meal_type", "lunch"), calories=params.get("calories"))
            return {"type": "meals", "data": res}

        # ── Phase 5: Personal Tutor ────────────────────────────────────────────
        elif intent == "tutor_learn":
            from intelligence.tutor import start_lesson
            res = await start_lesson(topic=params.get("topic", ""), difficulty=params.get("difficulty", "beginner"))
            return {"type": "tutor", "data": res}

        elif intent == "tutor_quiz":
            from intelligence.tutor import generate_quiz
            res = await generate_quiz(topic=params.get("topic", ""), difficulty=params.get("difficulty", "medium"))
            return {"type": "tutor", "data": res}

        # ── Phase 5: Creative Writing & Images ────────────────────────────────
        elif intent == "creative_writing":
            from creative.writing import generate_content
            res = await generate_content(topic=params.get("topic", ""), format_type=params.get("format", "blog"))
            return {"type": "writing", "data": res}

        elif intent == "generate_image":
            from creative.images import generate_image
            res = await generate_image(prompt=params.get("prompt", ""))
            return {"type": "image", "data": res}

        # ── Fallback ───────────────────────────────────────────────────────────
        else:
            return {"type": "general_chat", "data": None}

    except Exception as e:
        return {"type": "error", "data": str(e)}