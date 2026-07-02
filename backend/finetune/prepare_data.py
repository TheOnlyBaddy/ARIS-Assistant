# backend/finetune/prepare_data.py
"""
Prepares training datasets for fine-tuning ARIS's local Ollama models.
Extracts data from SQLite database, applies user profile style guides, and formats as JSONL.
"""

import os
import sqlite3
import json
import re

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(BASE_DIR)
DB_PATH = os.path.join(BACKEND_DIR, "aris.db")
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

PROFILE_PATH = os.path.join(BACKEND_DIR, "user_profile.json")

# Default system prompts matching Shubh's profile style markers
DEFAULT_STYLE = {
    "tone": "friendly",
    "verbosity": "concise",
    "technical_level": "advanced",
    "use_emojis": False
}

def load_user_profile():
    if os.path.exists(PROFILE_PATH):
        try:
            with open(PROFILE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Failed to load user profile: {e}")
    return {"communication_style": DEFAULT_STYLE}

def clean_response(text, style):
    """
    Ensures response matches Shubh's preferred style markers.
    - Removes emojis if use_emojis is False.
    - Trims response to be concise if verbosity is concise.
    """
    cleaned = text
    # Remove emojis if profile forbids them
    if not style.get("use_emojis", True):
        cleaned = re.sub(r'[\u2700-\u27BF]|[\uE000-\uF8FF]|\uD83C[\uDC00-\uDFFF]|\uD83D[\uDC00-\uDFFF]|[\u2011-\u26FF]|\uD83E[\uDC00-\uDFFF]', '', cleaned)
    
    # Trim leading/trailing whitespace
    return cleaned.strip()

def build_system_prompt(model_role, profile):
    style = profile.get("communication_style", DEFAULT_STYLE)
    persona = profile.get("aris_persona", {})
    
    prompt = f"You are ARIS, Shubh's personal AI assistant. "
    prompt += f"Personality: {persona.get('personality', 'professional yet warm')}. "
    prompt += f"Tone: {style.get('tone', 'friendly')}. "
    prompt += f"Verbosity: {style.get('verbosity', 'concise')}. "
    prompt += f"Technical Level: {style.get('technical_level', 'advanced')}. "
    
    if model_role == "chat":
        prompt += "Your role is general chat, chitchat, and general assistance. Be helpful, concise, and clear."
    elif model_role == "writing":
        prompt += "Your role is professional writing, summarization, and email drafting. Keep emails structured, clear, and focused."
    elif model_role == "reasoning":
        prompt += "Your role is task planning, reasoning, scheduling, and structured data queries. Always break down complex tasks into clear steps."
        
    return prompt

# Seed/Synthetic examples to guarantee high-quality dataset initialization
SEED_DATA = {
    "chat": [
        {"prompt": "Hello ARIS", "completion": "Hello Shubh. I'm ready to assist you today. What can I do for you?"},
        {"prompt": "how is the weather in Delhi?", "completion": "Delhi is experiencing typical warm summer weather today. Would you like me to pull the exact forecast?"},
        {"prompt": "What are you?", "completion": "I am ARIS, your autonomous assistant. I handle PC control, task management, and data synthesis locally."}
    ],
    "writing": [
        {"prompt": "Draft an email to client about project delay", "completion": "Subject: Project Timeline Update - ARIS Assistant\n\nDear Client,\n\nWe are currently finalizing the core integration modules of the assistant. To ensure stability, we are adjusting the delivery timeline by one week. The new target release date is next Monday.\n\nThank you for your patience.\n\nBest regards,\nShubh"},
        {"prompt": "summarize CPU logs show high usage at 9 PM", "completion": "Summary of CPU Log Anomaly:\n- Timestamp: 9:00 PM\n- Severity: Warning\n- Event: CPU utilization peaked at 92% due to background database consolidation processes."},
        {"prompt": "write a summary of our meeting about database schemas", "completion": "Meeting Summary: Database Schema Finalization\n- Discussed SQLite indexes for conversation storage.\n- Resolved to map job_id to string type to support built-in monitors.\n- Agreed to run weekly data retention pruning jobs."}
    ],
    "reasoning": [
        {"prompt": "Create a task list to build fine-tuning dashboard", "completion": "Task Breakdown:\n1. Create backend `/finetune/status` endpoint to track versions.\n2. Design React dashboard component (`FinetuneDashboard.jsx`) with rollback triggers.\n3. Integrate the dashboard as an active tab in the main layout."},
        {"prompt": "Plan my schedule for tomorrow morning", "completion": "Schedule Plan:\n- 09:00 AM: Team standup and status updates.\n- 10:00 AM: Code review and refactoring.\n- 11:30 AM: Database schema optimization checks."},
        {"prompt": "verify network latency and public IP address", "completion": "Diagnostics Action Plan:\n1. Query network status adapters.\n2. Measure ICMP ping round-trip times.\n3. Fetch external public IP address from lookup API."}
    ]
}

def extract_and_prepare():
    profile = load_user_profile()
    style = profile.get("communication_style", DEFAULT_STYLE)
    
    print("Connecting to database...")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    # 1. Fetch conversations
    messages = conn.execute("SELECT id, session_id, role, text, model_used FROM conversation_messages ORDER BY session_id, id").fetchall()
    
    # 2. Fetch user feedback/corrections to construct positive/corrected examples
    corrections = conn.execute("SELECT session_id, user_correction, model_response FROM user_feedback").fetchall()
    corrections_map = {c["session_id"]: c for c in corrections}

    # Group message pairs by target role
    model_pairs = {
        "chat": [],      # qwen3:8b
        "writing": [],   # mistral
        "reasoning": []  # gemma4:12b
    }

    # Process DB conversation turns
    for i in range(len(messages) - 1):
        msg_current = messages[i]
        msg_next = messages[i+1]
        
        if (msg_current["role"] == "user" and 
            msg_next["role"] == "model" and 
            msg_current["session_id"] == msg_next["session_id"]):
            
            prompt = msg_current["text"].strip()
            completion = msg_next["text"].strip()
            model_used = msg_next["model_used"] or ""
            session_id = msg_current["session_id"]

            if len(prompt) < 5 or len(completion) < 10:
                continue

            # Apply correction overrides if user corrected this session
            if session_id in corrections_map:
                corr = corrections_map[session_id]
                # Replace output with corrected style/content guidelines
                completion = f"Corrected response: {corr['user_correction']}"

            completion = clean_response(completion, style)

            # Map to model roles based on classification prefix or intent
            if "llama3.2" in model_used.lower() or "llama3.1" in model_used.lower() or "qwen3" in model_used.lower() or "general_chat" in model_used.lower():
                model_pairs["chat"].append({"prompt": prompt, "completion": completion})
            elif "mistral" in model_used.lower() or "creative_writing" in model_used.lower():
                model_pairs["writing"].append({"prompt": prompt, "completion": completion})
            elif "gemma3:4b" in model_used.lower() or "gemma4" in model_used.lower() or "reasoning" in model_used.lower() or "network_diagnostics" in model_used.lower():
                model_pairs["reasoning"].append({"prompt": prompt, "completion": completion})
            else:
                # Default fallback based on triggers
                if any(k in prompt.lower() for k in ["email", "draft", "write a", "summarize"]):
                    model_pairs["writing"].append({"prompt": prompt, "completion": completion})
                elif any(k in prompt.lower() for k in ["schedule", "plan", "task", "stats"]):
                    model_pairs["reasoning"].append({"prompt": prompt, "completion": completion})
                else:
                    model_pairs["chat"].append({"prompt": prompt, "completion": completion})

    conn.close()

    # Save to JSONL files (ensuring we include seed data so we have a solid dataset)
    output_files = {
        "chat": "qwen3_train.jsonl",
        "writing": "mistral_train.jsonl",
        "reasoning": "gemma4_train.jsonl"
    }

    for role, filename in output_files.items():
        filepath = os.path.join(DATA_DIR, filename)
        
        # Merge database pairs and seed templates
        db_pairs = model_pairs[role]
        seeds = SEED_DATA[role]
        all_pairs = seeds + db_pairs
        
        # Format as system/user/assistant instruction sets
        system_prompt = build_system_prompt(role, profile)
        
        with open(filepath, "w", encoding="utf-8") as f:
            for pair in all_pairs:
                entry = {
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": pair["prompt"]},
                        {"role": "assistant", "content": pair["completion"]}
                    ]
                }
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                
        print(f"Dataset generated: {filename} with {len(all_pairs)} training pairs.")

if __name__ == "__main__":
    extract_and_prepare()
