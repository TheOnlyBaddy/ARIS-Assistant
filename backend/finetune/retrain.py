# backend/finetune/retrain.py
"""
Continuous learning pipeline scheduler for ARIS models.
Executes weekly training check, handles model versioning, backup rollbacks, and status logging.
"""

import os
import sys
import sqlite3
import json
import subprocess
from datetime import datetime, timezone

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(BASE_DIR)
DB_PATH = os.path.join(BACKEND_DIR, "aris.db")
METADATA_PATH = os.path.join(BASE_DIR, "metadata.json")

# Default metadata template
DEFAULT_METADATA = {
    "last_trained_timestamp": "1970-01-01T00:00:00Z",
    "examples_at_last_train": 0,
    "model_versions": {
        "qwen3": "aris-qwen-v1",
        "mistral": "aris-mistral-v1",
        "gemma4": "aris-gemma-v1"
    },
    "rollback_versions": {
        "qwen3": [],
        "mistral": [],
        "gemma4": []
    }
}

def load_metadata():
    if os.path.exists(METADATA_PATH):
        try:
            with open(METADATA_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return DEFAULT_METADATA.copy()

def save_metadata(meta):
    with open(METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

def get_new_examples_count(last_trained_ts):
    """Query DB for any messages or feedback logged after the last training session."""
    conn = sqlite3.connect(DB_PATH)
    try:
        # Count feedback corrections
        fb_count = conn.execute(
            "SELECT COUNT(*) FROM user_feedback WHERE timestamp > ?", 
            (last_trained_ts,)
        ).fetchone()[0]
        
        # Count user messages
        msg_count = conn.execute(
            "SELECT COUNT(*) FROM conversation_messages WHERE role='user' AND timestamp > ?", 
            (last_trained_ts,)
        ).fetchone()[0]
        
        return fb_count + msg_count
    except Exception as e:
        print(f"Error querying examples: {e}")
        return 0
    finally:
        conn.close()

def run_retrain_pipeline(force=False, dry_run=False):
    print(f"\n[{datetime.now().isoformat()}] Starting retraining pipeline run (Force={force}, Dry-run={dry_run})...")
    meta = load_metadata()
    last_ts = meta["last_trained_timestamp"]
    new_count = get_new_examples_count(last_ts)
    
    print(f"New examples detected since {last_ts}: {new_count}")
    
    if new_count < 50 and not force:
        print("Pipeline aborted: insufficient new training examples (requires at least 50).")
        return {"status": "skipped", "reason": f"Only {new_count} examples collected. Requires 50."}

    # 1. Update datasets
    print("Regenerating training datasets...")
    python_exe = sys.executable
    prep_res = subprocess.run([python_exe, os.path.join(BASE_DIR, "prepare_data.py")], capture_output=True, text=True, encoding="utf-8")
    if prep_res.returncode != 0:
        print(f"Dataset preparation failed: {prep_res.stderr}")
        return {"status": "failed", "reason": "Dataset preparation failed"}

    # 2. Retrain each model (ordered from smallest to largest parameter size)
    models_to_train = ["gemma4", "qwen3", "mistral"]
    new_versions = {}
    
    for m in models_to_train:
        current_version = meta["model_versions"][m]
        # Versioning: aris-qwen-v1 -> aris-qwen-v2
        base_name = current_version.rsplit("-v", 1)[0]
        version_num = int(current_version.rsplit("-v", 1)[1])
        next_version = f"{base_name}-v{version_num + 1}"
        
        print(f"Retraining model {m}: {current_version} -> {next_version}...")
        
        train_cmd = [python_exe, os.path.join(BASE_DIR, "train.py"), "--model", m]
        if dry_run:
            train_cmd.append("--dry-run")
            
        train_res = subprocess.run(train_cmd, capture_output=True, text=True, encoding="utf-8")
        if train_res.returncode != 0:
            print(f"Training failed for model {m}:\n{train_res.stderr}")
            return {"status": "failed", "reason": f"Training failed for {m}"}

        # Track GGUF registry version tags
        ollama_base_tag = "aris-qwen" if m == "qwen3" else ("aris-mistral" if m == "mistral" else "aris-gemma")
        
        # Tag version in Ollama: aris-qwen:v2
        tag_cmd = ["ollama", "copy", ollama_base_tag, f"{ollama_base_tag}:{version_num + 1}"]
        env = os.environ.copy()
        env["OLLAMA_HOST"] = "127.0.0.1:11434"
        subprocess.run(tag_cmd, capture_output=True, env=env)
        
        new_versions[m] = next_version
        
        # Manage rollback versions (keep last 2 versions)
        rollbacks = meta["rollback_versions"][m]
        rollbacks.append(current_version)
        if len(rollbacks) > 2:
            old_version = rollbacks.pop(0)
            # Remove old version tag from local Ollama to save disk space
            # e.g., ollama rm aris-llama:1
            old_tag = old_version.replace("-v", ":")
            subprocess.run(["ollama", "rm", old_tag], capture_output=True, env=env)
            
        meta["rollback_versions"][m] = rollbacks
        meta["model_versions"][m] = next_version

    # 3. Update metadata
    meta["last_trained_timestamp"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    meta["examples_at_last_train"] = meta["examples_at_last_train"] + new_count
    save_metadata(meta)
    
    print("SUCCESS! Model retraining, tagging, and versioning cycle complete.")
    return {"status": "success", "new_versions": new_versions}

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="ARIS Retrain Pipeline")
    parser.add_argument("--force", action="store_true", help="Force retrain even if under 50 examples")
    parser.add_argument("--dry-run", action="store_true", help="Use tiny base models for fast validation")
    args = parser.parse_args()

    run_retrain_pipeline(force=args.force, dry_run=args.dry_run)
