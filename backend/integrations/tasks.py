# ARIS/integrations/tasks.py
# Todoist integration — create, read, update, complete tasks

import os
from todoist_api_python.api import TodoistAPI
from datetime import date
from dotenv import load_dotenv

load_dotenv()

TODOIST_API_TOKEN = os.getenv("TODOIST_API_TOKEN")


def _get_client() -> TodoistAPI:
    """Get an authenticated Todoist API client."""
    if not TODOIST_API_TOKEN:
        raise Exception("TODOIST_API_TOKEN not set in .env")
    return TodoistAPI(TODOIST_API_TOKEN)


def _paginate(paginator) -> list:
    """Convert a ResultsPaginator into a plain list."""
    results = []
    for page in paginator:
        results.extend(page)
    return results


def _format_task(task) -> dict:
    """Convert Todoist task dict/object to clean dict — always returns due_date as string."""
    if isinstance(task, dict):
        due = task.get("due") or {}
        raw_date = due.get("date") if due else None
        return {
            "id":           task.get("id", ""),
            "content":      task.get("content", ""),
            "description":  task.get("description", ""),
            "priority":     task.get("priority", 1),
            "due":          due.get("string") if due else None,
            "due_date":     str(raw_date) if raw_date else None,  # always string
            "project_id":   task.get("project_id", ""),
            "labels":       task.get("labels", []),
            "is_completed": task.get("is_completed", False),
            "url":          task.get("url", ""),
        }
    else:
        due      = getattr(task, "due", None)
        raw_date = due.date if due and hasattr(due, "date") else None
        return {
            "id":           getattr(task, "id", ""),
            "content":      getattr(task, "content", ""),
            "description":  getattr(task, "description", ""),
            "priority":     getattr(task, "priority", 1),
            "due":          due.string if due and hasattr(due, "string") else None,
            "due_date":     str(raw_date) if raw_date else None,  # always string
            "project_id":   getattr(task, "project_id", ""),
            "labels":       getattr(task, "labels", []),
            "is_completed": getattr(task, "is_completed", False),
            "url":          getattr(task, "url", ""),
        }


def _format_project(project) -> dict:
    """Convert Todoist project dict/object to clean dict."""
    if isinstance(project, dict):
        return {
            "id":    project.get("id", ""),
            "name":  project.get("name", ""),
            "color": project.get("color", ""),
        }
    else:
        return {
            "id":    getattr(project, "id", ""),
            "name":  getattr(project, "name", ""),
            "color": getattr(project, "color", ""),
        }


# ─── READ TASKS ────────────────────────────────────────────────────────────────

def get_all_tasks(filter_str: str = None) -> list[dict]:
    """Fetch all active tasks with optional client-side filter."""
    api       = _get_client()
    paginator = api.get_tasks()
    raw_tasks = _paginate(paginator)
    result    = [_format_task(t) for t in raw_tasks]

    today_str = date.today().isoformat()  # always "2026-05-05" string

    if filter_str == "today":
        result = [
            t for t in result
            if t.get("due_date") and str(t["due_date"]) == today_str
        ]
    elif filter_str == "overdue":
        result = [
            t for t in result
            if t.get("due_date") and str(t["due_date"]) < today_str
        ]
    elif filter_str == "p1":
        result = [t for t in result if t["priority"] == 4]
    elif filter_str == "p2":
        result = [t for t in result if t["priority"] == 3]

    return result


def get_today_tasks() -> list[dict]:
    return get_all_tasks(filter_str="today")


def get_overdue_tasks() -> list[dict]:
    return get_all_tasks(filter_str="overdue")


# ─── CREATE TASK ───────────────────────────────────────────────────────────────

def create_task(
    content: str,
    description: str = "",
    due_string: str = None,
    priority: int = 1,
    labels: list[str] = None,
    project_id: str = None
) -> dict:
    """Create a new Todoist task."""
    api = _get_client()

    kwargs = {
        "content":     content,
        "description": description,
        "priority":    priority,
    }
    if due_string:  kwargs["due_string"]  = due_string
    if labels:      kwargs["labels"]      = labels
    if project_id:  kwargs["project_id"]  = project_id

    task = api.add_task(**kwargs)
    return {"status": "created", "task": _format_task(task)}


# ─── UPDATE TASK ───────────────────────────────────────────────────────────────

def update_task(
    task_id: str,
    content: str = None,
    description: str = None,
    due_string: str = None,
    priority: int = None
) -> dict:
    """Update an existing task."""
    api = _get_client()

    kwargs = {}
    if content:     kwargs["content"]     = content
    if description: kwargs["description"] = description
    if due_string:  kwargs["due_string"]  = due_string
    if priority:    kwargs["priority"]    = priority

    api.update_task(task_id=task_id, **kwargs)
    return {"status": "updated", "task_id": task_id}


# ─── COMPLETE & DELETE ─────────────────────────────────────────────────────────

def complete_task(task_id: str) -> dict:
    """Mark a task as complete."""
    api = _get_client()
    api.close_task(task_id=task_id)
    return {"status": "completed", "task_id": task_id}


def delete_task(task_id: str) -> dict:
    """Permanently delete a task."""
    api = _get_client()
    api.delete_task(task_id=task_id)
    return {"status": "deleted", "task_id": task_id}


# ─── PROJECTS ──────────────────────────────────────────────────────────────────

def get_projects() -> list[dict]:
    """Fetch all Todoist projects."""
    api       = _get_client()
    paginator = api.get_projects()
    raw_projects = _paginate(paginator)
    return [_format_project(p) for p in raw_projects]


# ─── TASK SUMMARY ──────────────────────────────────────────────────────────────

def get_task_summary() -> dict:
    """Get task overview for ARIS morning briefing."""
    all_tasks = get_all_tasks()
    today     = get_today_tasks()
    overdue   = get_overdue_tasks()

    return {
        "total_active":  len(all_tasks),
        "due_today":     len(today),
        "overdue":       len(overdue),
        "today_tasks":   today,
        "overdue_tasks": overdue,
    }