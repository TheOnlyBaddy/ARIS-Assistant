"""
ARIS 24/7 Proactive Automation Scheduler
- Uses APScheduler to run background tasks
- Restores jobs from SQLite database on startup
- Event-triggered monitoring (e.g., CPU health checks)
- Exposes schedule creation, listing, deletion, and manual triggering
"""

import os
import sqlite3
import json
import asyncio
import time
import psutil
from datetime import datetime, timezone
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from integrations.router import execute_intent

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(os.path.dirname(BASE_DIR), "aris.db")

scheduler = BackgroundScheduler()
CPU_ALERT_COOLDOWN = 300  # 5 minutes alert cooldown
last_cpu_alert_time = 0


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_scheduler_tables():
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_jobs (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT    NOT NULL,
            trigger_type  TEXT    NOT NULL, -- cron, interval
            expression    TEXT    NOT NULL, -- cron string or interval seconds
            intent        TEXT    NOT NULL,
            params        TEXT    NOT NULL DEFAULT '{}',
            status        TEXT    NOT NULL DEFAULT 'active' -- active, paused
        )
    """)
    conn.commit()
    conn.close()


init_scheduler_tables()


# ─── ACTION EXECUTION WRAPPER ──────────────────────────────────────────────────

def run_job_action(intent: str, params: dict):
    """Bridge sync APScheduler trigger to async execute_intent router."""
    print(f"[ARIS Scheduler] Triggering background job intent: '{intent}' with params: {params}")
    try:
        # Run async execute_intent in new event loop thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        res = loop.run_until_complete(execute_intent(intent, params))
        loop.close()
        print(f"[ARIS Scheduler] Job completed. Output: {res}")
    except Exception as e:
        print(f"[ARIS Scheduler] Job action failed: {e}")


# ─── EVENT-TRIGGERED SYSTEM MONITORING ──────────────────────────────────────────

def check_system_health():
    """Event-triggered monitoring for high CPU usage."""
    global last_cpu_alert_time
    try:
        cpu_pct = psutil.cpu_percent(interval=None)
        if cpu_pct > 90:
            now = time.time()
            if now - last_cpu_alert_time > CPU_ALERT_COOLDOWN:
                last_cpu_alert_time = now
                print(f"[ARIS Monitor] Alert: CPU usage critical at {cpu_pct}%!")
                run_job_action("send_notification", {
                    "title": "⚠️ ARIS System Alert",
                    "message": f"Critical CPU load: {cpu_pct}% usage detected."
                })
    except Exception as e:
        print(f"[ARIS Monitor] Health check failed: {e}")


# ─── SCHEDULER CONTROLLER ─────────────────────────────────────────────────────

def load_jobs_from_db():
    """Load and schedule all active jobs from SQLite."""
    conn = _get_conn()
    jobs = conn.execute("SELECT * FROM scheduled_jobs WHERE status = 'active'").fetchall()
    conn.close()

    # Remove existing jobs from memory scheduler to avoid duplicates
    scheduler.remove_all_jobs()

    # Always add our built-in system monitors
    scheduler.add_job(
        check_system_health,
        trigger="interval",
        seconds=15,
        id="sys_health_monitor",
        replace_existing=True
    )

    for row in jobs:
        job_id = str(row["id"])
        trigger_type = row["trigger_type"]
        expr = row["expression"]
        intent = row["intent"]
        params = json.loads(row["params"])

        try:
            if trigger_type == "cron":
                trigger = CronTrigger.from_crontab(expr)
                scheduler.add_job(
                    run_job_action,
                    trigger=trigger,
                    args=[intent, params],
                    id=job_id,
                    replace_existing=True
                )
            elif trigger_type == "interval":
                scheduler.add_job(
                    run_job_action,
                    trigger="interval",
                    seconds=int(expr),
                    args=[intent, params],
                    id=job_id,
                    replace_existing=True
                )
            print(f"[ARIS Scheduler] Scheduled job '{row['name']}' (ID: {job_id}) successfully.")
        except Exception as e:
            print(f"[ARIS Scheduler] Failed to schedule job {job_id}: {e}")


def start_scheduler():
    """Start the scheduler background thread."""
    if not scheduler.running:
        scheduler.start()
        print("[ARIS Scheduler] APScheduler background engine started.")
    load_jobs_from_db()


def stop_scheduler():
    """Shutdown the scheduler background thread."""
    if scheduler.running:
        scheduler.shutdown()
        print("[ARIS Scheduler] APScheduler background engine stopped.")


# ─── CRUD OPERATION CONTROLLERS ───────────────────────────────────────────────

def create_scheduled_job(name: str, trigger_type: str, expression: str, intent: str, params: dict) -> dict:
    """Save a new automation to DB and schedule it immediately."""
    try:
        conn = _get_conn()
        cur = conn.execute(
            "INSERT INTO scheduled_jobs (name, trigger_type, expression, intent, params, status) VALUES (?, ?, ?, ?, ?, 'active')",
            (name, trigger_type, expression, intent, json.dumps(params))
        )
        job_id = cur.lastrowid
        conn.commit()
        conn.close()

        # Reload database jobs into scheduler memory
        load_jobs_from_db()

        return {
            "status": "success",
            "message": f"Job '{name}' scheduled successfully.",
            "job_id": job_id
        }
    except Exception as e:
        return {"status": "error", "message": f"Failed to create job: {str(e)}"}


def list_scheduled_jobs() -> list:
    """List all scheduled automations."""
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM scheduled_jobs").fetchall()
    conn.close()

    result = []
    for r in rows:
        job_dict = dict(r)
        job_dict["is_running_in_memory"] = scheduler.get_job(str(r["id"])) is not None
        result.append(job_dict)

    # Include built-in monitor info
    result.append({
        "id": "sys_health_monitor",
        "name": "ARIS Health Monitor (CPU Alert)",
        "trigger_type": "interval",
        "expression": "15",
        "intent": "send_notification",
        "params": "{}",
        "status": "active",
        "is_running_in_memory": scheduler.get_job("sys_health_monitor") is not None
    })
    return result


def delete_scheduled_job(job_id: str) -> dict:
    """Delete a scheduled automation."""
    if job_id == "sys_health_monitor":
        return {"status": "error", "message": "Cannot delete built-in system monitor."}
    try:
        conn = _get_conn()
        conn.execute("DELETE FROM scheduled_jobs WHERE id = ?", (job_id,))
        conn.commit()
        conn.close()

        # Remove from scheduler memory
        try:
            scheduler.remove_job(str(job_id))
        except Exception:
            pass

        return {"status": "success", "message": f"Job ID {job_id} deleted."}
    except Exception as e:
        return {"status": "error", "message": f"Delete failed: {str(e)}"}


def trigger_job_now(job_id: str) -> dict:
    """Instantly execute the action of a scheduled job."""
    if job_id == "sys_health_monitor":
        check_system_health()
        return {"status": "success", "message": "Built-in system health monitor triggered."}

    conn = _get_conn()
    job = conn.execute("SELECT * FROM scheduled_jobs WHERE id = ?", (job_id,)).fetchone()
    conn.close()

    if not job:
        return {"status": "error", "message": "Job not found"}

    intent = job["intent"]
    params = json.loads(job["params"])
    
    # Run synchronously to give immediate feedback to user
    run_job_action(intent, params)
    return {"status": "success", "message": f"Job '{job['name']}' triggered successfully."}
