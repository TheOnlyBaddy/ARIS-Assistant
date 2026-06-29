"""
ARIS Self-Tool Creation
Allows ARIS to write, sandbox-test, and register custom Python tools on the fly
when no existing tool matches a task description.
"""

import os
import sys
import json
import subprocess
import httpx
from datetime import datetime, timezone
from google import genai
from google.genai import types

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOOLS_DIR = os.path.join(BASE_DIR, "generated_tools")
REGISTRY_PATH = os.path.join(TOOLS_DIR, "tools_registry.json")

os.makedirs(TOOLS_DIR, exist_ok=True)
if not os.path.exists(REGISTRY_PATH):
    with open(REGISTRY_PATH, "w") as f:
        json.dump({}, f)

gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
MODEL = os.getenv("PRIMARY_MODEL", "gemini-2.5-flash")


async def generate_tool_code(task_description: str, tool_name: str) -> str:
    """Generate Python script using Gemini with Ollama fallback."""
    prompt = (
        f"You are the tool creator core of ARIS. Your task is to write a highly reliable, safe Python script to do the following:\n"
        f"Task Description: '{task_description}'\n"
        f"Tool Name: '{tool_name}'\n\n"
        "Rules for the script:\n"
        "1. It must contain a single main entry point function defined exactly as:\n"
        "   `def run(params: dict) -> dict:`\n"
        "2. The function must unpack parameters from the `params` dictionary, perform the task, and return a dictionary with at least 'status' ('success' or 'error') and 'message'.\n"
        "3. You MUST explicitly write any required import statements (e.g. 'import re', 'import os', 'import math') at the very top of the script. Standard libraries are NOT pre-imported.\n"
        "4. Output ONLY the raw Python code. Do NOT enclose it in markdown blocks or fences (no ```python etc.).\n"
        "5. The code should be production-grade, secure, and handle exceptions cleanly."
    )

    try:
        response = gemini_client.models.generate_content(
            model=MODEL,
            contents=prompt,
        )
        return response.text.strip()
    except Exception as e:
        print(f"[ARIS Tool Creator] Gemini failed: {e}. Falling back to Ollama...")
        ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        ollama_model = os.getenv("OLLAMA_CHAT_MODEL", "llama3.2")
        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                r = await client.post(
                    f"{ollama_url}/api/generate",
                    json={
                        "model": ollama_model,
                        "prompt": prompt,
                        "stream": False,
                    }
                )
                r.raise_for_status()
                return r.json().get("response", "").strip()
        except Exception as ollama_err:
            raise RuntimeError(f"Code generation failed: Gemini ({e}), Ollama ({ollama_err})")


def sandbox_test_tool(file_path: str, test_params: dict) -> dict:
    """Run the tool in a sandboxed Python subprocess to verify correct execution."""
    file_path_clean = file_path.replace("\\", "/")
    test_harness_code = f"""
import sys
import json
import os

# Import the tool
sys.path.append(os.path.dirname('{file_path_clean}'))
module_name = os.path.basename('{file_path_clean}').replace('.py', '')
tool_module = __import__(module_name)

params = json.loads('''{json.dumps(test_params)}''')
try:
    result = tool_module.run(params)
    print("RESULT:" + json.dumps(result))
except Exception as e:
    print("ERROR:" + str(e))
    sys.exit(1)
"""

    temp_test_file = os.path.join(TOOLS_DIR, "temp_test_harness.py")
    with open(temp_test_file, "w") as f:
        f.write(test_harness_code)

    try:
        # Run subprocess with timeout to avoid infinite loops
        proc = subprocess.run(
            [sys.executable, temp_test_file],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        # Clean up harness
        if os.path.exists(temp_test_file):
            os.remove(temp_test_file)

        if proc.returncode != 0:
            return {"status": "error", "message": f"Subprocess exited with code {proc.returncode}. Output: {proc.stderr.strip()}"}

        output = proc.stdout.strip()
        if "ERROR:" in output:
            return {"status": "error", "message": output.replace("ERROR:", "")}
        
        # Find RESULT block
        result_prefix = "RESULT:"
        for line in output.split("\n"):
            if line.startswith(result_prefix):
                result_json = line[len(result_prefix):]
                return {"status": "success", "data": json.loads(result_json)}

        return {"status": "error", "message": f"Tool executed but returned no result output. Stdout: {output}"}

    except subprocess.TimeoutExpired:
        if os.path.exists(temp_test_file):
            os.remove(temp_test_file)
        return {"status": "error", "message": "Tool execution timed out (potential infinite loop)."}
    except Exception as e:
        if os.path.exists(temp_test_file):
            os.remove(temp_test_file)
        return {"status": "error", "message": f"Sandbox setup failed: {str(e)}"}


async def create_self_tool(task_description: str, tool_name: str, test_params: dict) -> dict:
    """Generate, test, and register a new tool."""
    clean_name = "".join([c if c.isalnum() else "_" for c in tool_name.lower()])
    file_name = f"tool_{clean_name}.py"
    file_path = os.path.join(TOOLS_DIR, file_name)

    try:
        # 1. Code Generation
        code = await generate_tool_code(task_description, clean_name)
        
        # Clean markdown fences
        if code.startswith("```"):
            lines = code.split("\n")
            if lines[-1].strip() == "```":
                lines = lines[1:-1]
            else:
                lines = lines[1:]
            code = "\n".join(lines).strip()
            if code.startswith("python"):
                code = code[6:].strip()

        # 2. Write file
        with open(file_path, "w") as f:
            f.write(code)

        # 3. Sandbox verify
        test_res = sandbox_test_tool(file_path, test_params)
        is_val_err = False
        val_msg = ""
        if test_res["status"] == "error":
            is_val_err = True
            val_msg = test_res["message"]
        elif isinstance(test_res.get("data"), dict) and test_res["data"].get("status") == "error":
            is_val_err = True
            val_msg = test_res["data"].get("message", "Tool reported an internal error during test execution.")

        if is_val_err:
            # Clean up failed script
            if os.path.exists(file_path):
                os.remove(file_path)
            return {
                "status": "error",
                "message": f"Sandbox validation failed: {val_msg}",
                "generated_code": code
            }

        # 4. Register tool
        with open(REGISTRY_PATH, "r") as f:
            registry = json.load(f)

        registry[clean_name] = {
            "description": task_description,
            "file_path": file_path,
            "parameters": list(test_params.keys()),
            "registered_at": datetime.now(timezone.utc).isoformat()
        }

        with open(REGISTRY_PATH, "w") as f:
            json.dump(registry, f, indent=4)

        return {
            "status": "success",
            "message": f"Tool '{clean_name}' successfully created, validated, and registered.",
            "file_path": file_path,
            "test_output": test_res["data"]
        }

    except Exception as e:
        return {"status": "error", "message": f"Tool creation failed: {str(e)}"}


def list_registered_tools() -> dict:
    """Return all currently active self-created tools."""
    with open(REGISTRY_PATH, "r") as f:
        return json.load(f)


def execute_self_tool(tool_name: str, params: dict) -> dict:
    """Dynamically import and run a self-created tool from the registry."""
    with open(REGISTRY_PATH, "r") as f:
        registry = json.load(f)

    if tool_name not in registry:
        return {"status": "error", "message": f"Tool '{tool_name}' is not registered."}

    file_path = registry[tool_name]["file_path"]
    
    # Sandbox test runs it safely in a separate process, which is also best for production execution!
    # Or import dynamically. Since we want safe executions, running in subprocess is great, 
    # but direct import is faster. Let's do dynamic import.
    try:
        sys.path.append(TOOLS_DIR)
        module_name = f"tool_{tool_name}"
        # Force reload in case the tool was updated
        if module_name in sys.modules:
            import importlib
            tool_module = importlib.reload(sys.modules[module_name])
        else:
            tool_module = __import__(module_name)
            
        res = tool_module.run(params)
        return {"status": "success", "result": res}
    except Exception as e:
        return {"status": "error", "message": f"Execution failed: {str(e)}"}
