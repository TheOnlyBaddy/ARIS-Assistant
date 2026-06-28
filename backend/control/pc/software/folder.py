# ARIS/control/pc/software/folder.py
"""
Folder / File / URL Opening module for ARIS — Windows 11
Opens known user folders, searches for folders across the PC, and opens URLs.
Uses Windows Shell API (KnownFolders) to resolve actual paths,
handling OneDrive redirects correctly.
"""

import os
import subprocess
import string
import ctypes

# ── Resolve actual user folder paths via Windows Shell API ────────────────────

def _get_known_folder(folder_id):
    """Use SHGetKnownFolderPath to get the real path of a Windows known folder."""
    try:
        buf = ctypes.c_wchar_p()
        ctypes.windll.shell32.SHGetKnownFolderPath(
            ctypes.byref(folder_id), 0, None, ctypes.byref(buf)
        )
        path = buf.value
        ctypes.windll.ole32.CoTaskMemFree(buf)
        return path
    except Exception:
        return None

class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]

def _guid(s):
    import uuid
    u = uuid.UUID(s)
    return _GUID(u.time_low, u.time_mid, u.time_hi_version,
                 (ctypes.c_ubyte * 8)(*u.bytes[8:]))

# Standard Windows Known Folder IDs
_FOLDERID_PICTURES     = _guid("{33E28130-4E1E-4676-835A-98395C3BC3BB}")
_FOLDERID_DOCUMENTS    = _guid("{FDD39AD0-238F-46AF-ADB4-6C85480369C7}")
_FOLDERID_DOWNLOADS    = _guid("{374DE290-123F-4565-9164-39C4925E467B}")
_FOLDERID_DESKTOP      = _guid("{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}")
_FOLDERID_MUSIC        = _guid("{4BD8D571-6D19-48D3-BE97-422220080E43}")
_FOLDERID_VIDEOS       = _guid("{18989B1D-99B5-455B-841C-AB7C74E4DDFC}")

def _resolve_user_folders():
    """Build the FOLDER_MAP using the Windows Shell API for correct OneDrive-redirected paths."""
    user = os.path.expanduser("~")

    pictures  = _get_known_folder(_FOLDERID_PICTURES)  or os.path.join(user, "Pictures")
    documents = _get_known_folder(_FOLDERID_DOCUMENTS) or os.path.join(user, "Documents")
    downloads = _get_known_folder(_FOLDERID_DOWNLOADS) or os.path.join(user, "Downloads")
    desktop   = _get_known_folder(_FOLDERID_DESKTOP)   or os.path.join(user, "Desktop")
    music     = _get_known_folder(_FOLDERID_MUSIC)     or os.path.join(user, "Music")
    videos    = _get_known_folder(_FOLDERID_VIDEOS)    or os.path.join(user, "Videos")

    return {
        "pictures"      : pictures,
        "my pictures"   : pictures,
        "photos"        : pictures,
        "documents"     : documents,
        "my documents"  : documents,
        "docs"          : documents,
        "downloads"     : downloads,
        "download"      : downloads,
        "desktop"       : desktop,
        "music"         : music,
        "my music"      : music,
        "videos"        : videos,
        "my videos"     : videos,
        "home"          : user,
        "user folder"   : user,
        "recycle bin"   : "shell:RecycleBinFolder",
        "trash"         : "shell:RecycleBinFolder",
        "startup"       : os.path.join(user, "AppData", "Roaming", "Microsoft", "Windows", "Start Menu", "Programs", "Startup"),
        "appdata"       : os.path.join(user, "AppData"),
        "temp"          : os.environ.get("TEMP", os.path.join(user, "AppData", "Local", "Temp")),
        "onedrive"      : os.path.join(user, "OneDrive"),
    }

FOLDER_MAP = _resolve_user_folders()


# ── Dynamic folder search across the PC ───────────────────────────────────────

def _get_all_drives():
    """Get all available drive letters on the system."""
    drives = []
    for letter in string.ascii_uppercase:
        drive = f"{letter}:\\"
        if os.path.exists(drive):
            drives.append(drive)
    return drives


def _search_folder(name: str, max_depth: int = 3) -> str:
    """
    Search for a folder by name across the PC.
    Searches in priority order for speed:
      1. User home & OneDrive (depth 3)
      2. Desktop, Documents, Downloads (depth 2)
      3. All drive roots (depth 2)
    Returns the first matching path or None.
    """
    target = name.lower()
    user = os.path.expanduser("~")

    # Priority search locations (searched first, deeper)
    priority_roots = [
        user,
        os.path.join(user, "OneDrive"),
    ]
    # Secondary locations (searched with less depth)
    secondary_roots = [
        FOLDER_MAP.get("desktop", ""),
        FOLDER_MAP.get("documents", ""),
        FOLDER_MAP.get("downloads", ""),
    ]

    # Search priority roots first (depth 3)
    for root in priority_roots:
        if root and os.path.isdir(root):
            result = _walk_search(root, target, max_depth=max_depth)
            if result:
                return result

    # Search secondary roots (depth 2)
    for root in secondary_roots:
        if root and os.path.isdir(root):
            result = _walk_search(root, target, max_depth=2)
            if result:
                return result

    # Search all drive roots (depth 2) — skip already searched user drive
    user_drive = os.path.splitdrive(user)[0] + "\\"
    for drive in _get_all_drives():
        if drive == user_drive:
            # Search drive root but skip user folder (already searched)
            result = _walk_search(drive, target, max_depth=2, skip_dirs={user})
            if result:
                return result
        else:
            result = _walk_search(drive, target, max_depth=2)
            if result:
                return result

    return None


def _walk_search(root: str, target: str, max_depth: int = 2, skip_dirs: set = None) -> str:
    """Walk a directory tree up to max_depth looking for a folder matching target name."""
    skip_dirs = skip_dirs or set()
    skip_names = {"$Recycle.Bin", "System Volume Information", "Windows",
                  "ProgramData", "Recovery", "$WinREAgent", "node_modules",
                  ".git", "__pycache__", "venv", ".venv"}

    root_depth = root.rstrip(os.sep).count(os.sep)

    try:
        for dirpath, dirnames, _ in os.walk(root, topdown=True):
            current_depth = dirpath.rstrip(os.sep).count(os.sep) - root_depth

            # Prune depth
            if current_depth >= max_depth:
                dirnames.clear()
                continue

            # Prune system/skip directories
            dirnames[:] = [
                d for d in dirnames
                if d not in skip_names
                and not d.startswith(".")
                and os.path.join(dirpath, d) not in skip_dirs
            ]

            # Check each subfolder name
            for d in dirnames:
                if d.lower() == target:
                    return os.path.join(dirpath, d)
    except PermissionError:
        pass

    return None


def open_folder(name: str) -> dict:
    """
    Open a known folder, search for a folder by name, open a file path, or URL.
    Returns a result dict with status 'ok' on success, or None if nothing matched.
    """
    name_lower = name.lower().strip()

    # Clean up common trailing words like "folder" or "directory"
    name_clean = name_lower
    for suffix in (" folder", " directory", " folders", " directories"):
        if name_clean.endswith(suffix):
            name_clean = name_clean[:-len(suffix)].strip()

    try:
        # 1. Known folder names (instant) - check clean name first, then original
        folder_path = FOLDER_MAP.get(name_clean) or FOLDER_MAP.get(name_lower)
        if folder_path:
            subprocess.Popen(["explorer.exe", folder_path])
            return {"action": "open_folder", "name": name, "path": folder_path, "status": "ok"}

        # 2. Direct file/folder path on disk
        for n in (name_clean, name.strip()):
            expanded = os.path.expanduser(n)
            if os.path.exists(expanded):
                abs_path = os.path.abspath(expanded)
                kind = "open_folder" if os.path.isdir(abs_path) else "open_file"
                if os.path.isdir(abs_path):
                    subprocess.Popen(["explorer.exe", abs_path])
                else:
                    os.startfile(abs_path)
                return {"action": kind, "name": name, "path": abs_path, "status": "ok"}

        # 3. URL detection
        if any(name.startswith(p) for p in ("http://", "https://", "www.")):
            url = name if name.startswith("http") else f"https://{name}"
            os.startfile(url)
            return {"action": "open_url", "url": url, "status": "ok"}

        # 4. Search the PC for a folder with this name
        found = _search_folder(name_clean) or _search_folder(name_lower)
        if found:
            subprocess.Popen(["explorer.exe", found])
            return {"action": "open_folder", "name": name, "path": found, "status": "ok"}

    except Exception as e:
        return {"action": "open_folder", "name": name, "status": "error", "error": str(e)}

    # Not a folder, file, or URL — return None so caller falls back to app.py
    return None

