"""
ARIS Personal Tutor
- Teach any subject using Socratic questioning & spaced repetition
- Create and store flashcards
- Adaptive quiz mode (tracks score & adapts difficulty)
- Stored in SQLite (backend/aris.db)
"""

import os
import sqlite3
import json
from datetime import datetime, timezone
from google import genai
from google.genai import types

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(os.path.dirname(BASE_DIR), "aris.db")

gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
MODEL = os.getenv("PRIMARY_MODEL", "gemini-2.5-flash")


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_tables():
    """Create tutoring database tables if they do not exist."""
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tutor_lessons (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            topic       TEXT    NOT NULL,
            content     TEXT    NOT NULL,
            difficulty  TEXT    DEFAULT 'beginner',
            created_at  TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tutor_flashcards (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            topic       TEXT    NOT NULL,
            front       TEXT    NOT NULL,
            back        TEXT    NOT NULL,
            box         INTEGER DEFAULT 1, -- Spaced repetition Leitner system box
            next_review TEXT    DEFAULT NULL,
            created_at  TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tutor_quizzes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            topic       TEXT    NOT NULL,
            questions   TEXT    NOT NULL, -- JSON string of questions/answers
            score       INTEGER DEFAULT 0,
            total       INTEGER DEFAULT 0,
            difficulty  TEXT    DEFAULT 'medium',
            created_at  TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tutor_progress (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            topic       TEXT    NOT NULL UNIQUE,
            mastery     REAL    DEFAULT 0.0, -- progress level (0.0 to 100.0)
            lessons_read INTEGER DEFAULT 0,
            quizzes_taken INTEGER DEFAULT 0,
            avg_score   REAL    DEFAULT 0.0,
            updated_at  TEXT    NOT NULL
        );
    """)
    conn.commit()
    conn.close()


init_tables()


# ── Lessons ──────────────────────────────────────────────────────────────────

async def start_lesson(topic: str, difficulty: str = "beginner") -> dict:
    """Generate a structured lesson on a topic using Gemini."""
    prompt = (
        f"You are ARIS, an expert personal tutor. Create a structured lesson on the topic: '{topic}'.\n"
        f"Target audience level: {difficulty}.\n\n"
        "Please structured the response into:\n"
        "1. **Core Concept**: Explain the concept simply using analogies.\n"
        "2. **Key Details**: 3-4 bullet points detailing the mechanism/rules.\n"
        "3. **Example/Use Case**: A real-world example or practical code snippet (if technical).\n"
        "4. **Socratic Question**: Ask one open-ended question to test the student's understanding.\n\n"
        "Keep it concise, engaging, and under 350 words."
    )

    try:
        response = gemini_client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=1024)
            )
        )
        content = response.text.strip()
        now = datetime.now(timezone.utc).isoformat()

        # Save to DB
        conn = _get_conn()
        conn.execute(
            "INSERT INTO tutor_lessons (topic, content, difficulty, created_at) VALUES (?, ?, ?, ?)",
            (topic, content, difficulty, now)
        )
        # Update progress entry
        conn.execute(
            """INSERT INTO tutor_progress (topic, mastery, lessons_read, updated_at)
               VALUES (?, 10.0, 1, ?)
               ON CONFLICT(topic) DO UPDATE SET 
                  lessons_read = lessons_read + 1,
                  mastery = MIN(mastery + 10.0, 100.0),
                  updated_at = ?""",
            (topic, now, now)
        )
        conn.commit()
        conn.close()

        return {
            "status": "success",
            "topic": topic,
            "difficulty": difficulty,
            "lesson": content
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ── Flashcards ───────────────────────────────────────────────────────────────

async def generate_flashcards(topic: str, count: int = 5) -> dict:
    """Generate flashcards using Gemini and save them."""
    prompt = (
        f"You are ARIS, a personal tutor. Generate {count} flashcards for the topic '{topic}'.\n"
        "Format your output as a valid JSON array of objects. Do not include any markdown formatting, wrappers, or fences outside the JSON. "
        "Each object MUST have exactly two keys: 'front' (the question or term) and 'back' (the short answer or definition).\n\n"
        "Example output structure:\n"
        '[\n  {"front": "Term 1", "back": "Definition 1"}\n]'
    )

    try:
        response = gemini_client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=1024)
            )
        )
        raw_text = response.text.strip()

        # Clean text in case models still outputs markdown blocks
        if raw_text.startswith("```"):
            lines = raw_text.split("\n")
            if lines[-1].strip() == "```":
                lines = lines[1:-1]
            else:
                lines = lines[1:]
            raw_text = "\n".join(lines).strip()
            if raw_text.startswith("json"):
                raw_text = raw_text[4:].strip()

        cards = json.loads(raw_text)
        now = datetime.now(timezone.utc).isoformat()

        conn = _get_conn()
        saved = []
        for card in cards:
            front = card.get("front", "").strip()
            back = card.get("back", "").strip()
            if front and back:
                cur = conn.execute(
                    "INSERT INTO tutor_flashcards (topic, front, back, created_at) VALUES (?, ?, ?, ?)",
                    (topic, front, back, now)
                )
                saved.append({
                    "id": cur.lastrowid,
                    "front": front,
                    "back": back
                })
        conn.commit()
        conn.close()

        return {
            "status": "success",
            "topic": topic,
            "count": len(saved),
            "flashcards": saved
        }
    except Exception as e:
        return {"status": "error", "message": f"Failed to generate flashcards: {e}. Raw response: {response.text if 'response' in locals() else ''}"}


def list_flashcards(topic: str = "") -> list:
    """List all saved flashcards, optionally filtered by topic."""
    conn = _get_conn()
    if topic:
        rows = conn.execute("SELECT * FROM tutor_flashcards WHERE topic = ? ORDER BY id DESC", (topic,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM tutor_flashcards ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Quizzes ──────────────────────────────────────────────────────────────────

async def generate_quiz(topic: str, difficulty: str = "medium", count: int = 3) -> dict:
    """Generate a quiz with questions, multiple-choice options, and correct answers using Gemini."""
    prompt = (
        f"You are ARIS, an expert tutor. Create a {count}-question multiple-choice quiz on the topic '{topic}' at a '{difficulty}' level.\n"
        "Format your output as a valid JSON array of objects. Do not include any markdown wrappers or fences outside the JSON.\n"
        "Each object MUST have exactly these keys:\n"
        "- 'question': The question text\n"
        "- 'options': A list of exactly 4 strings (possible choices)\n"
        "- 'correct': The exact string from the options list that is correct\n\n"
        "Example output structure:\n"
        '[\n  {"question": "Q1", "options": ["A", "B", "C", "D"], "correct": "A"}\n]'
    )

    try:
        response = gemini_client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=1024)
            )
        )
        raw_text = response.text.strip()

        if raw_text.startswith("```"):
            lines = raw_text.split("\n")
            if lines[-1].strip() == "```":
                lines = lines[1:-1]
            else:
                lines = lines[1:]
            raw_text = "\n".join(lines).strip()
            if raw_text.startswith("json"):
                raw_text = raw_text[4:].strip()

        questions = json.loads(raw_text)
        now = datetime.now(timezone.utc).isoformat()

        # Save to DB
        conn = _get_conn()
        cur = conn.execute(
            "INSERT INTO tutor_quizzes (topic, questions, total, difficulty, created_at) VALUES (?, ?, ?, ?, ?)",
            (topic, json.dumps(questions), len(questions), difficulty, now)
        )
        quiz_id = cur.lastrowid
        conn.commit()
        conn.close()

        # Return questions without the answers directly visible in the question object (to allow backend evaluation)
        clean_questions = []
        for i, q in enumerate(questions):
            clean_questions.append({
                "index": i,
                "question": q["question"],
                "options": q["options"]
            })

        return {
            "status": "success",
            "quiz_id": quiz_id,
            "topic": topic,
            "difficulty": difficulty,
            "questions": clean_questions
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def submit_quiz_answers(quiz_id: int, user_answers: list) -> dict:
    """Evaluate submitted quiz answers, store the score, and update topic mastery."""
    conn = _get_conn()
    quiz = conn.execute("SELECT * FROM tutor_quizzes WHERE id = ?", (quiz_id,)).fetchone()
    if not quiz:
        conn.close()
        return {"status": "error", "message": "Quiz not found"}

    questions = json.loads(quiz["questions"])
    score = 0
    feedback = []

    for i, q in enumerate(questions):
        user_ans = user_answers[i] if i < len(user_answers) else ""
        correct = q["correct"]
        is_correct = (user_ans.strip().lower() == correct.strip().lower())
        if is_correct:
            score += 1
        feedback.append({
            "question": q["question"],
            "user_answer": user_ans,
            "correct_answer": correct,
            "is_correct": is_correct
        })

    now = datetime.now(timezone.utc).isoformat()
    # Update quiz score
    conn.execute(
        "UPDATE tutor_quizzes SET score = ? WHERE id = ?",
        (score, quiz_id)
    )

    # Calculate mastery adjustment based on score percentage
    pct = (score / len(questions)) * 100.0
    mastery_change = (pct - 50.0) / 2.0  # 100% score = +25% mastery; 0% score = -25% mastery

    conn.execute(
        """INSERT INTO tutor_progress (topic, mastery, quizzes_taken, avg_score, updated_at)
           VALUES (?, ?, 1, ?, ?)
           ON CONFLICT(topic) DO UPDATE SET
              quizzes_taken = quizzes_taken + 1,
              avg_score = ((avg_score * (quizzes_taken)) + ?) / (quizzes_taken + 1),
              mastery = MIN(MAX(mastery + ?, 0.0), 100.0),
              updated_at = ?""",
        (quiz["topic"], max(0.0, pct), float(pct), now, float(pct), mastery_change, now)
    )
    conn.commit()
    conn.close()

    # Suggest next difficulty
    next_difficulty = "medium"
    if pct >= 80:
        next_difficulty = "hard"
    elif pct < 50:
        next_difficulty = "beginner"

    return {
        "status": "success",
        "quiz_id": quiz_id,
        "topic": quiz["topic"],
        "score": score,
        "total": len(questions),
        "percentage": pct,
        "suggested_next_difficulty": next_difficulty,
        "feedback": feedback
    }


# ── Progress ─────────────────────────────────────────────────────────────────

def get_tutor_progress() -> list:
    """Get learning progress across all topics."""
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM tutor_progress ORDER BY mastery DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]
