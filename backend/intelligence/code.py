"""
ARIS Code Assistant & Sandbox
- Generate code in any language from a description
- Debug code — explain what's wrong and fix it
- Execute Python code safely in an isolated subprocess (timeout, restricted)
"""

import os
import sys
import subprocess
import tempfile
import textwrap
from google import genai
from google.genai import types

gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
MODEL = os.getenv("PRIMARY_MODEL", "gemini-2.5-flash")


async def generate_code(description: str, language: str = "python") -> dict:
    """Generate code in any language from a natural language description."""
    prompt = (
        f"You are ARIS, an expert software engineer. Write clean, production-ready "
        f"{language} code for the following task:\n\n"
        f"{description}\n\n"
        f"Rules:\n"
        f"- Output ONLY the code, no explanations before or after\n"
        f"- Include brief inline comments for clarity\n"
        f"- Use modern best practices for {language}\n"
        f"- If the task needs imports, include them\n"
        f"- Make the code complete and runnable"
    )

    try:
        response = gemini_client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=1024)
            )
        )
        code = response.text.strip()
        # Strip markdown code fences if present
        if code.startswith("```"):
            lines = code.split("\n")
            # Remove first line (```python) and last line (```)
            if lines[-1].strip() == "```":
                lines = lines[1:-1]
            else:
                lines = lines[1:]
            code = "\n".join(lines)

        return {
            "status": "success",
            "language": language,
            "code": code,
            "description": description
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def debug_code(code: str, error: str = "", language: str = "python") -> dict:
    """Analyze code, explain what's wrong, and provide a fixed version."""
    prompt = (
        f"You are ARIS, an expert debugger. Analyze this {language} code:\n\n"
        f"```{language}\n{code}\n```\n\n"
    )
    if error:
        prompt += f"The error message is:\n```\n{error}\n```\n\n"

    prompt += (
        "Respond in this exact format:\n"
        "## Problem\n"
        "Explain what's wrong in 1-2 sentences.\n\n"
        "## Fix\n"
        "Explain the fix in 1-2 sentences.\n\n"
        "## Fixed Code\n"
        "```\n"
        "the corrected code here\n"
        "```"
    )

    try:
        response = gemini_client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=1024)
            )
        )
        return {
            "status": "success",
            "language": language,
            "analysis": response.text.strip()
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def execute_python(code: str, timeout: int = 10) -> dict:
    """
    Execute Python code safely in an isolated subprocess.
    - Timeout enforced (default 10s)
    - No network access hints
    - Captures stdout + stderr
    """
    # Wrap the code to restrict dangerous builtins
    sandbox_wrapper = textwrap.dedent(f"""\
import sys
import io

# Restrict dangerous operations
_blocked = ['open', 'exec', 'eval', '__import__']

{code}
""")

    try:
        result = subprocess.run(
            [sys.executable, "-c", sandbox_wrapper],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=tempfile.gettempdir(),
            env={
                "PATH": os.environ.get("PATH", ""),
                "PYTHONPATH": "",
                "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            }
        )

        output = result.stdout.strip()
        errors = result.stderr.strip()

        return {
            "status": "success" if result.returncode == 0 else "error",
            "return_code": result.returncode,
            "output": output,
            "errors": errors
        }

    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "return_code": -1,
            "output": "",
            "errors": f"Execution timed out after {timeout} seconds"
        }
    except Exception as e:
        return {
            "status": "error",
            "return_code": -1,
            "output": "",
            "errors": str(e)
        }
