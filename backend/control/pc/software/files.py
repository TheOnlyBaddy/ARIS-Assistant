# ARIS/control/pc/software/files.py
"""
File & Folder Management module for ARIS — Windows 11
Handles: list, create, rename, move, delete, search, read, open
"""

import os
import shutil
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional

# ── Helpers ───────────────────────────────────────────────────────────────────

def _expand(path: str) -> str:
    """Expand ~ and environment variables, return absolute path string, checking OneDrive redirects."""
    p = path.strip().strip('"').strip("'")
    
    try:
        from control.pc.software.folder import FOLDER_MAP
        p_lower = p.lower()
        if p_lower in FOLDER_MAP:
            return FOLDER_MAP[p_lower]
        
        if p.startswith("~"):
            # Split off the ~ prefix
            parts = p.split("/", 1) if "/" in p else p.split("\\", 1)
            if len(parts) > 1:
                sub = parts[1].lower()
                if sub in FOLDER_MAP:
                    return FOLDER_MAP[sub]
    except Exception:
        pass

    return str(Path(os.path.expandvars(os.path.expanduser(p))).resolve())


def _size_label(bytes: int) -> str:
    """Convert bytes to human-readable size."""
    for unit in ["B", "KB", "MB", "GB"]:
        if bytes < 1024:
            return f"{bytes:.1f} {unit}"
        bytes /= 1024
    return f"{bytes:.1f} TB"


def _file_info(path: Path) -> dict:
    """Return a clean info dict for a file or folder."""
    stat = path.stat()
    return {
        "name"    : path.name,
        "path"    : str(path),
        "type"    : "folder" if path.is_dir() else "file",
        "size"    : _size_label(stat.st_size) if path.is_file() else None,
        "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
        "extension": path.suffix.lower() if path.is_file() else None,
    }

# ── List directory ────────────────────────────────────────────────────────────

def list_directory(path: str = "~", show_hidden: bool = False) -> dict:
    """
    List files and folders in a directory.
    Defaults to home directory (~).
    """
    try:
        target = Path(_expand(path))
        if not target.exists():
            return {"status": "error", "error": f"Path not found: {path}"}
        if not target.is_dir():
            return {"status": "error", "error": f"Not a directory: {path}"}

        items = []
        for item in sorted(target.iterdir()):
            if not show_hidden and item.name.startswith("."):
                continue
            try:
                items.append(_file_info(item))
            except PermissionError:
                items.append({"name": item.name, "path": str(item), "type": "unknown", "error": "permission denied"})

        folders = [i for i in items if i["type"] == "folder"]
        files   = [i for i in items if i["type"] == "file"]

        return {
            "action"      : "list_directory",
            "path"        : str(target),
            "folder_count": len(folders),
            "file_count"  : len(files),
            "items"       : folders + files,  # folders first
            "status"      : "ok"
        }

    except PermissionError:
        return {"status": "error", "error": f"Permission denied: {path}"}
    except Exception as e:
        return {"status": "error", "error": str(e)}

# ── Create ────────────────────────────────────────────────────────────────────

def create_file(path: str, content: str = "") -> dict:
    """Create a new file with optional content. Creates parent dirs if needed."""
    try:
        target = Path(_expand(path))
        target.parent.mkdir(parents=True, exist_ok=True)

        if target.exists():
            return {"status": "error", "error": f"File already exists: {path}"}

        target.write_text(content, encoding="utf-8")
        return {
            "action" : "create_file",
            "path"   : str(target),
            "name"   : target.name,
            "size"   : _size_label(target.stat().st_size),
            "status" : "ok"
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def create_folder(path: str) -> dict:
    """Create a folder (and any missing parent folders)."""
    try:
        target = Path(_expand(path))
        if target.exists():
            return {"status": "error", "error": f"Folder already exists: {path}"}
        target.mkdir(parents=True, exist_ok=True)
        return {
            "action": "create_folder",
            "path"  : str(target),
            "name"  : target.name,
            "status": "ok"
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}

# ── Read ──────────────────────────────────────────────────────────────────────

def read_file(path: str, max_chars: int = 5000) -> dict:
    """
    Read text file contents.
    max_chars limits output to avoid flooding — default 5000 chars.
    """
    try:
        target = Path(_expand(path))
        if not target.exists():
            return {"status": "error", "error": f"File not found: {path}"}
        if not target.is_file():
            return {"status": "error", "error": f"Not a file: {path}"}

        content = target.read_text(encoding="utf-8", errors="replace")
        truncated = len(content) > max_chars

        return {
            "action"   : "read_file",
            "path"     : str(target),
            "name"     : target.name,
            "content"  : content[:max_chars],
            "truncated": truncated,
            "total_chars": len(content),
            "status"   : "ok"
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def write_file(path: str, content: str, append: bool = False) -> dict:
    """Write or append content to a file. Creates file if it doesn't exist."""
    try:
        target = Path(_expand(path))
        target.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        with open(target, mode, encoding="utf-8") as f:
            f.write(content)
        return {
            "action"  : "write_file",
            "path"    : str(target),
            "name"    : target.name,
            "append"  : append,
            "size"    : _size_label(target.stat().st_size),
            "status"  : "ok"
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}

# ── Rename ────────────────────────────────────────────────────────────────────

def rename(path: str, new_name: str) -> dict:
    """Rename a file or folder. new_name is just the name, not full path."""
    try:
        target  = Path(_expand(path))
        if not target.exists():
            return {"status": "error", "error": f"Not found: {path}"}

        new_path = target.parent / new_name
        if new_path.exists():
            return {"status": "error", "error": f"Already exists: {new_name}"}

        target.rename(new_path)
        return {
            "action"  : "rename",
            "old_path": str(target),
            "new_path": str(new_path),
            "old_name": target.name,
            "new_name": new_name,
            "status"  : "ok"
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}

# ── Move ──────────────────────────────────────────────────────────────────────

def move(src: str, dst: str) -> dict:
    """Move a file or folder to a new location."""
    try:
        src_path = Path(_expand(src))
        dst_path = Path(_expand(dst))

        if not src_path.exists():
            return {"status": "error", "error": f"Source not found: {src}"}

        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src_path), str(dst_path))

        return {
            "action"  : "move",
            "src"     : str(src_path),
            "dst"     : str(dst_path),
            "status"  : "ok"
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}

# ── Copy ──────────────────────────────────────────────────────────────────────

def copy(src: str, dst: str) -> dict:
    """Copy a file or folder to a new location."""
    try:
        src_path = Path(_expand(src))
        dst_path = Path(_expand(dst))

        if not src_path.exists():
            return {"status": "error", "error": f"Source not found: {src}"}

        dst_path.parent.mkdir(parents=True, exist_ok=True)

        if src_path.is_dir():
            shutil.copytree(str(src_path), str(dst_path))
        else:
            shutil.copy2(str(src_path), str(dst_path))

        return {
            "action": "copy",
            "src"   : str(src_path),
            "dst"   : str(dst_path),
            "status": "ok"
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}

# ── Delete ────────────────────────────────────────────────────────────────────

def delete(path: str, confirmed: bool = False) -> dict:
    """
    Delete a file or folder.
    confirmed=True required — safety guard against accidental deletion.
    """
    if not confirmed:
        return {
            "status" : "needs_confirmation",
            "message": f"Are you sure you want to delete '{path}'? Pass confirmed=true to proceed.",
            "path"   : path
        }

    try:
        target = Path(_expand(path))
        if not target.exists():
            return {"status": "error", "error": f"Not found: {path}"}

        if target.is_dir():
            shutil.rmtree(str(target))
            item_type = "folder"
        else:
            target.unlink()
            item_type = "file"

        return {
            "action"   : "delete",
            "path"     : str(target),
            "name"     : target.name,
            "item_type": item_type,
            "status"   : "ok"
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}

# ── Search ────────────────────────────────────────────────────────────────────

def search_files(
    query: str,
    search_path: str = "~",
    extension: str = None,
    max_results: int = 50
) -> dict:
    """
    Search for files by name (case-insensitive partial match).
    Optional: filter by extension (e.g. ".txt", ".py")
    """
    try:
        root    = Path(_expand(search_path))
        query_l = query.lower()
        results = []

        for item in root.rglob("*"):
            if len(results) >= max_results:
                break
            try:
                name_l = item.name.lower()
                if query_l not in name_l:
                    continue
                if extension and item.suffix.lower() != extension.lower():
                    continue
                results.append(_file_info(item))
            except (PermissionError, OSError):
                continue

        return {
            "action"     : "search_files",
            "query"      : query,
            "search_path": str(root),
            "extension"  : extension,
            "count"      : len(results),
            "results"    : results,
            "status"     : "ok"
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}

# ── Open with default app ─────────────────────────────────────────────────────

def open_file(path: str) -> dict:
    """Open a file with its default application (like double-clicking in Explorer)."""
    try:
        target = Path(_expand(path))
        if not target.exists():
            return {"status": "error", "error": f"File not found: {path}"}

        os.startfile(str(target))  # Windows: opens with default app
        return {
            "action": "open_file",
            "path"  : str(target),
            "name"  : target.name,
            "status": "ok"
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def open_in_explorer(path: str) -> dict:
    """Open a folder in Windows File Explorer."""
    try:
        target = Path(_expand(path))
        subprocess.Popen(f'explorer "{target}"')
        return {
            "action": "open_in_explorer",
            "path"  : str(target),
            "status": "ok"
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def get_file_info(path: str) -> dict:
    """Get detailed info about a file or folder."""
    try:
        target = Path(_expand(path))
        if not target.exists():
            return {"status": "error", "error": f"Not found: {path}"}
        info = _file_info(target)
        info["action"] = "get_file_info"
        info["status"] = "ok"
        return info
    except Exception as e:
        return {"status": "error", "error": str(e)}
