"""
ARIS Finance Awareness
- Manual expense/income logging (natural language friendly)
- Budget categories: food, transport, entertainment, etc.
- Monthly summary and overspend alerts
- Savings goal tracking
- Currency: INR (₹)
- Stored in SQLite (backend/aris.db)
"""

import os
import sqlite3
from datetime import datetime, date, timedelta, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(os.path.dirname(BASE_DIR), "aris.db")

CATEGORIES = [
    "food", "transport", "entertainment", "shopping", "bills",
    "health", "education", "groceries", "subscriptions", "rent",
    "salary", "freelance", "gift", "investment", "other"
]


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_tables():
    """Create finance tables if they don't exist."""
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS transactions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            type        TEXT    NOT NULL DEFAULT 'expense',
            amount      REAL    NOT NULL,
            category    TEXT    NOT NULL DEFAULT 'other',
            description TEXT    DEFAULT '',
            txn_date    TEXT    NOT NULL,
            logged_at   TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS budgets (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            category    TEXT    NOT NULL UNIQUE,
            monthly_limit REAL  NOT NULL,
            updated_at  TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS savings_goals (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL,
            target_amount REAL  NOT NULL,
            current_amount REAL DEFAULT 0,
            target_date TEXT    DEFAULT '',
            created_at  TEXT    NOT NULL,
            completed   INTEGER DEFAULT 0
        );
    """)
    conn.commit()
    conn.close()


init_tables()


# ── Transaction Logging ──────────────────────────────────────────────────────

def log_transaction(
    amount: float,
    category: str = "other",
    description: str = "",
    txn_type: str = "expense",
    txn_date: str = ""
) -> dict:
    """Log an expense or income transaction."""
    if not txn_date:
        txn_date = date.today().isoformat()
    now = datetime.now(timezone.utc).isoformat()
    category = category.lower().strip()
    if category not in CATEGORIES:
        category = "other"

    conn = _get_conn()
    cur = conn.execute(
        """INSERT INTO transactions (type, amount, category, description, txn_date, logged_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (txn_type, amount, category, description, txn_date, now)
    )
    conn.commit()
    txn_id = cur.lastrowid
    conn.close()

    # Check budget overspend
    alert = _check_budget_alert(category, txn_date) if txn_type == "expense" else None

    result = {
        "status": "success",
        "id": txn_id,
        "type": txn_type,
        "amount": amount,
        "category": category,
        "date": txn_date
    }
    if alert:
        result["budget_alert"] = alert
    return result


def get_transactions(days: int = 30, category: str = "") -> list:
    """Get recent transactions, optionally filtered by category."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    conn = _get_conn()
    if category:
        rows = conn.execute(
            "SELECT * FROM transactions WHERE txn_date >= ? AND category = ? ORDER BY txn_date DESC",
            (cutoff, category.lower())
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM transactions WHERE txn_date >= ? ORDER BY txn_date DESC",
            (cutoff,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_transaction(txn_id: int) -> dict:
    """Delete a transaction by ID."""
    conn = _get_conn()
    conn.execute("DELETE FROM transactions WHERE id = ?", (txn_id,))
    conn.commit()
    conn.close()
    return {"status": "success", "id": txn_id}


# ── Monthly Summary ──────────────────────────────────────────────────────────

def get_monthly_summary(year: int = 0, month: int = 0) -> dict:
    """Get expense/income breakdown for a given month (default: current month)."""
    today = date.today()
    if not year:
        year = today.year
    if not month:
        month = today.month

    month_start = f"{year}-{month:02d}-01"
    if month == 12:
        month_end = f"{year + 1}-01-01"
    else:
        month_end = f"{year}-{month + 1:02d}-01"

    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM transactions WHERE txn_date >= ? AND txn_date < ?",
        (month_start, month_end)
    ).fetchall()
    conn.close()

    total_expense = 0.0
    total_income = 0.0
    by_category = {}

    for r in rows:
        row = dict(r)
        if row["type"] == "expense":
            total_expense += row["amount"]
            cat = row["category"]
            by_category[cat] = by_category.get(cat, 0.0) + row["amount"]
        else:
            total_income += row["amount"]

    # Sort categories by spend (descending)
    sorted_cats = sorted(by_category.items(), key=lambda x: x[1], reverse=True)

    return {
        "month": f"{year}-{month:02d}",
        "total_expense": round(total_expense, 2),
        "total_income": round(total_income, 2),
        "net": round(total_income - total_expense, 2),
        "by_category": [
            {"category": cat, "amount": round(amt, 2)}
            for cat, amt in sorted_cats
        ],
        "transaction_count": len(rows)
    }


# ── Budget Management ────────────────────────────────────────────────────────

def set_budget(category: str, monthly_limit: float) -> dict:
    """Set or update a monthly budget limit for a category."""
    category = category.lower().strip()
    now = datetime.now(timezone.utc).isoformat()
    conn = _get_conn()
    conn.execute(
        """INSERT INTO budgets (category, monthly_limit, updated_at) 
           VALUES (?, ?, ?)
           ON CONFLICT(category) DO UPDATE SET monthly_limit = ?, updated_at = ?""",
        (category, monthly_limit, now, monthly_limit, now)
    )
    conn.commit()
    conn.close()
    return {"status": "success", "category": category, "monthly_limit": monthly_limit}


def get_budgets() -> list:
    """List all budget limits with current month spending."""
    conn = _get_conn()
    budgets = conn.execute("SELECT * FROM budgets ORDER BY category").fetchall()

    today = date.today()
    month_start = f"{today.year}-{today.month:02d}-01"
    if today.month == 12:
        month_end = f"{today.year + 1}-01-01"
    else:
        month_end = f"{today.year}-{today.month + 1:02d}-01"

    results = []
    for b in budgets:
        b = dict(b)
        spent_row = conn.execute(
            """SELECT COALESCE(SUM(amount), 0) as spent FROM transactions 
               WHERE category = ? AND type = 'expense' AND txn_date >= ? AND txn_date < ?""",
            (b["category"], month_start, month_end)
        ).fetchone()
        spent = spent_row["spent"]
        remaining = b["monthly_limit"] - spent
        results.append({
            "category": b["category"],
            "monthly_limit": b["monthly_limit"],
            "spent": round(spent, 2),
            "remaining": round(remaining, 2),
            "over_budget": remaining < 0
        })
    conn.close()
    return results


def _check_budget_alert(category: str, txn_date: str) -> dict | None:
    """Check if a category is over or near budget after a transaction."""
    conn = _get_conn()
    budget = conn.execute(
        "SELECT * FROM budgets WHERE category = ?", (category,)
    ).fetchone()
    if not budget:
        conn.close()
        return None

    today = date.today()
    month_start = f"{today.year}-{today.month:02d}-01"
    if today.month == 12:
        month_end = f"{today.year + 1}-01-01"
    else:
        month_end = f"{today.year}-{today.month + 1:02d}-01"

    spent_row = conn.execute(
        """SELECT COALESCE(SUM(amount), 0) as spent FROM transactions 
           WHERE category = ? AND type = 'expense' AND txn_date >= ? AND txn_date < ?""",
        (category, month_start, month_end)
    ).fetchone()
    conn.close()

    spent = spent_row["spent"]
    limit = budget["monthly_limit"]
    pct = (spent / limit * 100) if limit > 0 else 0

    if spent > limit:
        return {"level": "over", "message": f"⚠️ Over budget! ₹{spent:.0f}/₹{limit:.0f} ({pct:.0f}%)"}
    elif pct >= 80:
        return {"level": "warning", "message": f"⚡ Nearing limit! ₹{spent:.0f}/₹{limit:.0f} ({pct:.0f}%)"}
    return None


# ── Savings Goals ────────────────────────────────────────────────────────────

def create_savings_goal(name: str, target_amount: float, target_date: str = "") -> dict:
    """Create a savings goal."""
    now = datetime.now(timezone.utc).isoformat()
    conn = _get_conn()
    cur = conn.execute(
        "INSERT INTO savings_goals (name, target_amount, target_date, created_at) VALUES (?, ?, ?, ?)",
        (name, target_amount, target_date, now)
    )
    conn.commit()
    goal_id = cur.lastrowid
    conn.close()
    return {"status": "success", "id": goal_id, "name": name, "target": target_amount}


def add_to_savings(goal_id: int, amount: float) -> dict:
    """Add money to a savings goal."""
    conn = _get_conn()
    goal = conn.execute("SELECT * FROM savings_goals WHERE id = ?", (goal_id,)).fetchone()
    if not goal:
        conn.close()
        return {"status": "error", "message": "Goal not found"}

    new_amount = goal["current_amount"] + amount
    completed = 1 if new_amount >= goal["target_amount"] else 0
    conn.execute(
        "UPDATE savings_goals SET current_amount = ?, completed = ? WHERE id = ?",
        (new_amount, completed, goal_id)
    )
    conn.commit()
    conn.close()
    return {
        "status": "success",
        "id": goal_id,
        "current": round(new_amount, 2),
        "target": goal["target_amount"],
        "progress_pct": round(new_amount / goal["target_amount"] * 100, 1),
        "completed": bool(completed)
    }


def list_savings_goals() -> list:
    """List all savings goals with progress."""
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM savings_goals ORDER BY created_at DESC").fetchall()
    conn.close()
    results = []
    for r in rows:
        r = dict(r)
        pct = round(r["current_amount"] / r["target_amount"] * 100, 1) if r["target_amount"] > 0 else 0
        r["progress_pct"] = pct
        results.append(r)
    return results
