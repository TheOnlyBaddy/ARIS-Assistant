# ARIS/control/pc/hardware/system.py
"""
System Monitoring module for ARIS — Windows 11
Handles: CPU, RAM, disk, battery, processes, network, kill process
"""

import psutil
import os
import platform
from datetime import datetime
from typing import Optional
import subprocess
import shutil

import json
import re
import copy
import threading
import time
import win32pdh
import win32gui
import win32process

# ── Helpers ───────────────────────────────────────────────────────────────────

def _size_gb(bytes: int) -> float:
    return round(bytes / (1024 ** 3), 2)

def _size_mb(bytes: int) -> float:
    return round(bytes / (1024 ** 2), 2)

def _os_name() -> str:
    if platform.system() == "Windows":
        try:
            build = int(platform.version().split(".")[-1])
            if build >= 22000:
                return "Windows 11"
            else:
                return "Windows 10"
        except Exception:
            pass
    return f"{platform.system()} {platform.release()}"


_STATIC_DISKS_MAP = None

def get_disk_media_types() -> dict[str, str]:
    """Map drive letters (e.g. C, D) to physical media types (SSD, HDD, USB) on Windows."""
    global _STATIC_DISKS_MAP
    if _STATIC_DISKS_MAP is not None:
        return _STATIC_DISKS_MAP

    mapping = {}
    if platform.system() != "Windows":
        return mapping
    try:
        # Get partitions: DiskNumber -> DriveLetter
        out_part = subprocess.check_output([
            "powershell", "-Command",
            "Get-Partition | Where-Object DriveLetter | Select-Object DiskNumber, DriveLetter | ConvertTo-Json"
        ], text=True, timeout=5.0).strip()
        
        parts_data = []
        if out_part:
            parts_data = json.loads(out_part)
            if not isinstance(parts_data, list):
                parts_data = [parts_data]
                
        # Get physical disks: DeviceId -> MediaType, Model
        out_phys = subprocess.check_output([
            "powershell", "-Command",
            "Get-PhysicalDisk | Select-Object DeviceId, MediaType, Model | ConvertTo-Json"
        ], text=True, timeout=5.0).strip()
        
        phys_data = []
        if out_phys:
            phys_data = json.loads(out_phys)
            if not isinstance(phys_data, list):
                phys_data = [phys_data]
                
        for p in parts_data:
            letter = p.get("DriveLetter")
            disk_num = str(p.get("DiskNumber"))
            if letter:
                media_type = "SSD" # default
                for d in phys_data:
                    if str(d.get("DeviceId")) == disk_num:
                        m_type = d.get("MediaType", "SSD")
                        if m_type == "Unspecified":
                            m_type = "USB" if "storage" in d.get("Model", "").lower() or "usb" in d.get("Model", "").lower() else "SSD"
                        media_type = m_type
                        break
                mapping[letter.upper()] = media_type
    except Exception:
        pass
    _STATIC_DISKS_MAP = mapping
    return mapping


# Cache LUID mapping dynamically between boots
_GPU_LUID_CACHE = {}
_STATIC_GPUS_BASE = None

def _query_pdh_metrics() -> dict:
    """Natively query Windows Performance Counters via win32pdh (0ms overhead)."""
    metrics = {
        "cpu_utility": None,
        "cpu_performance": None,
        "gpu_util": {},
        "gpu_vram": {},
    }
    
    hQuery = None
    try:
        hQuery = win32pdh.OpenQuery()
        hCpuUtil = win32pdh.AddCounter(hQuery, "\\Processor Information(_Total)\\% Processor Utility")
        hCpuPerf = win32pdh.AddCounter(hQuery, "\\Processor Information(_Total)\\% Processor Performance")
        
        gpu_engine_paths = []
        try:
            expanded = win32pdh.ExpandCounterPath("\\GPU Engine(*)\\Utilization Percentage")
            gpu_engine_paths = [p for p in expanded if "engtype_3d" in p.lower()]
        except Exception:
            pass
            
        hGpuEngines = {}
        for p in gpu_engine_paths:
            try:
                hGpuEngines[p] = win32pdh.AddCounter(hQuery, p)
            except Exception:
                pass
                
        gpu_mem_paths = []
        try:
            gpu_mem_paths += win32pdh.ExpandCounterPath("\\GPU Adapter Memory(*)\\Dedicated Usage")
            gpu_mem_paths += win32pdh.ExpandCounterPath("\\GPU Adapter Memory(*)\\Shared Usage")
        except Exception:
            pass
            
        hGpuMems = {}
        for p in gpu_mem_paths:
            try:
                hGpuMems[p] = win32pdh.AddCounter(hQuery, p)
            except Exception:
                pass
                
        # Sample rate delta counters
        win32pdh.CollectQueryData(hQuery)
        time.sleep(0.05)
        win32pdh.CollectQueryData(hQuery)
        
        try:
            _, val = win32pdh.GetFormattedCounterValue(hCpuUtil, win32pdh.PDH_FMT_DOUBLE)
            metrics["cpu_utility"] = val
        except Exception:
            pass
        try:
            _, val = win32pdh.GetFormattedCounterValue(hCpuPerf, win32pdh.PDH_FMT_DOUBLE)
            metrics["cpu_performance"] = val
        except Exception:
            pass
            
        for p, hC in hGpuEngines.items():
            try:
                _, val = win32pdh.GetFormattedCounterValue(hC, win32pdh.PDH_FMT_DOUBLE)
                match = re.search(r"luid_(0x[0-9a-fA-F]+_0x[0-9a-fA-F]+)", p)
                if match:
                    luid = match.group(0).lower()
                    metrics["gpu_util"][luid] = metrics["gpu_util"].get(luid, 0.0) + val
            except Exception:
                pass
                
        for p, hC in hGpuMems.items():
            try:
                _, val = win32pdh.GetFormattedCounterValue(hC, win32pdh.PDH_FMT_DOUBLE)
                match = re.search(r"luid_(0x[0-9a-fA-F]+_0x[0-9a-fA-F]+)", p)
                if match:
                    luid = match.group(0).lower()
                    if luid not in metrics["gpu_vram"]:
                        metrics["gpu_vram"][luid] = {"dedicated": 0.0, "shared": 0.0}
                    if "dedicated usage" in p.lower():
                        metrics["gpu_vram"][luid]["dedicated"] = val
                    elif "shared usage" in p.lower():
                        metrics["gpu_vram"][luid]["shared"] = val
            except Exception:
                pass
    except Exception:
        pass
    finally:
        if hQuery:
            try:
                win32pdh.CloseQuery(hQuery)
            except Exception:
                pass
                
    return metrics


_LAST_NVIDIA_SMI_TIME = 0.0
_CACHED_NVIDIA_TEMP = None
_CACHED_NVIDIA_TOTAL_VRAM = None
_LAST_GPU_PERCENTS = {}

def get_all_gpus(pdh: dict) -> list[dict]:
    """Get active GPUs using the pre-queried pdh dictionary on Windows."""
    global _GPU_LUID_CACHE, _STATIC_GPUS_BASE, _LAST_NVIDIA_SMI_TIME, _CACHED_NVIDIA_TEMP, _CACHED_NVIDIA_TOTAL_VRAM, _LAST_GPU_PERCENTS
    
    # 1. Query WMI adapters via PowerShell for baseline name/AdapterRAM (run once and cache)
    if _STATIC_GPUS_BASE is None:
        _STATIC_GPUS_BASE = []
        if platform.system() == "Windows":
            try:
                cmd = ["powershell", "-Command", "Get-CimInstance Win32_VideoController | Select-Object Name, AdapterRAM | ConvertTo-Json"]
                out = subprocess.check_output(cmd, text=True, timeout=5.0).strip()
                if out:
                    data = json.loads(out)
                    if not isinstance(data, list):
                        data = [data]
                    
                    idx = 0
                    for item in data:
                        name = item.get("Name", "")
                        if not name or "spacedesk" in name.lower() or "virtual" in name.lower():
                            continue
                        
                        ram_bytes = item.get("AdapterRAM")
                        total_vram = round(ram_bytes / (1024 ** 3), 1) if ram_bytes else None
                        
                        _STATIC_GPUS_BASE.append({
                            "id"        : idx,
                            "name"      : name,
                            "percent"   : 0,
                            "temp"      : None,
                            "used_vram" : None,
                            "total_vram": total_vram,
                            "type"      : "integrated" if "intel" in name.lower() or "amd" in name.lower() else "discrete"
                        })
                        idx += 1
            except Exception:
                pass

    # Make a copy of baseline config to update dynamically on this poll
    gpus = copy.deepcopy(_STATIC_GPUS_BASE)

    # 2. Query Nvidia smi GPU temperature & true total VRAM (run at most once every 5.0 seconds to avoid process spawn overhead)
    now = time.time()
    if now - _LAST_NVIDIA_SMI_TIME > 5.0:
        _LAST_NVIDIA_SMI_TIME = now
        smi = shutil.which("nvidia-smi")
        if smi:
            try:
                out = subprocess.check_output([
                    smi,
                    "--query-gpu=temperature.gpu,memory.total",
                    "--format=csv,noheader,nounits"
                ], text=True, timeout=2.0).strip()
                if out:
                    parts = [p.strip() for p in out.splitlines()[0].split(",")]
                    if len(parts) >= 2:
                        _CACHED_NVIDIA_TEMP = int(parts[0])
                        _CACHED_NVIDIA_TOTAL_VRAM = round(int(parts[1]) / 1024.0, 1)
            except Exception:
                pass

    # 3. Resolve Discrete and Integrated LUIDs using pdh memory metrics
    if platform.system() == "Windows" and pdh:
        discrete_luid = _GPU_LUID_CACHE.get("discrete")
        integrated_luid = _GPU_LUID_CACHE.get("integrated")
        
        if not discrete_luid or not integrated_luid:
            for l, m in pdh.get("gpu_vram", {}).items():
                if m["dedicated"] > 100 * 1024 * 1024:
                    _GPU_LUID_CACHE["discrete"] = l
                    discrete_luid = l
                elif m["shared"] > 10 * 1024 * 1024:
                    _GPU_LUID_CACHE["integrated"] = l
                    integrated_luid = l

        # Update GPU utilization percentages and VRAM usage natively from pdh with EMA smoothing
        for g in gpus:
            if g["type"] == "discrete":
                g["temp"] = _CACHED_NVIDIA_TEMP
                if _CACHED_NVIDIA_TOTAL_VRAM is not None:
                    g["total_vram"] = _CACHED_NVIDIA_TOTAL_VRAM
                if discrete_luid in pdh.get("gpu_util", {}):
                    raw_val = min(round(pdh["gpu_util"][discrete_luid]), 100)
                    old_val = _LAST_GPU_PERCENTS.get(discrete_luid, 0.0)
                    smoothed = round(0.4 * raw_val + 0.6 * old_val)
                    _LAST_GPU_PERCENTS[discrete_luid] = smoothed
                    g["percent"] = smoothed
                if discrete_luid in pdh.get("gpu_vram", {}):
                    g["used_vram"] = round(pdh["gpu_vram"][discrete_luid]["dedicated"] / (1024 ** 3), 1)
            elif g["type"] == "integrated":
                if integrated_luid in pdh.get("gpu_util", {}):
                    raw_val = min(round(pdh["gpu_util"][integrated_luid]), 100)
                    old_val = _LAST_GPU_PERCENTS.get(integrated_luid, 0.0)
                    smoothed = round(0.4 * raw_val + 0.6 * old_val)
                    _LAST_GPU_PERCENTS[integrated_luid] = smoothed
                    g["percent"] = smoothed
                if integrated_luid in pdh.get("gpu_vram", {}):
                    g["used_vram"] = round(pdh["gpu_vram"][integrated_luid]["shared"] / (1024 ** 3), 1)
                                
    return gpus

# ── Full system stats ─────────────────────────────────────────────────────────

def _detect_connection_type_and_name() -> tuple:
    """Detects active network connection type and profile name (SSID)."""
    try:
        # 1. Get active connection profiles (SSID / Profile Name)
        cmd_profile = 'powershell.exe -NoProfile -Command "Get-NetConnectionProfile | Select-Object Name, InterfaceAlias | ConvertTo-Json"'
        res_profile = subprocess.check_output(cmd_profile, shell=True, text=True, stderr=subprocess.DEVNULL).strip()
        if not res_profile:
            return "Disconnected", ""
            
        import json
        profiles = json.loads(res_profile)
        if not isinstance(profiles, list):
            profiles = [profiles]
            
        # 2. Get adapters to check descriptions
        cmd_adapter = 'powershell.exe -NoProfile -Command "Get-NetAdapter | Select-Object Name, InterfaceDescription | ConvertTo-Json"'
        res_adapter = subprocess.check_output(cmd_adapter, shell=True, text=True, stderr=subprocess.DEVNULL).strip()
        adapters = []
        if res_adapter:
            adapters = json.loads(res_adapter)
            if not isinstance(adapters, list):
                adapters = [adapters]
                
        adapter_map = {a.get("Name"): a.get("InterfaceDescription", "") for a in adapters}
        
        # 3. Find active profile
        for prof in profiles:
            alias = prof.get("InterfaceAlias")
            net_name = prof.get("Name", "")
            
            desc = adapter_map.get(alias, "").lower()
            alias_lower = alias.lower() if alias else ""
            
            if "ndis" in desc or "tether" in desc or "rndis" in desc or "sharing" in desc:
                return "USB Tethering", net_name
            elif "wi-fi" in desc or "wifi" in desc or "wireless" in desc or "wlan" in desc or "802.11" in desc or "wi-fi" in alias_lower or "wifi" in alias_lower:
                return "Wi-Fi", net_name
            elif "bluetooth" in desc or "bluetooth" in alias_lower:
                return "Bluetooth", net_name
            elif "ethernet" in desc or "ethernet" in alias_lower:
                return "Ethernet", net_name
                
        return "Connected", ""
    except Exception:
        try:
            for name, stats in psutil.net_if_stats().items():
                if stats.isup and name != "Loopback Pseudo-Interface 1":
                    n = name.lower()
                    if "wi-fi" in n or "wifi" in n or "wireless" in n or "wlan" in n:
                        return "Wi-Fi", name
                    elif "bluetooth" in n:
                        return "Bluetooth", name
                    elif "ethernet" in n:
                        return "Ethernet", name
            return "Disconnected", ""
        except Exception:
            return "Unknown", ""

# Global cache for system stats snapshot
_SYSTEM_STATS_CACHE = {}
_CACHE_LOCK = threading.Lock()

_CONN_TYPE_CACHE, _CONN_NAME_CACHE = _detect_connection_type_and_name()
_CONN_TYPE_COUNTER = 0

# Global cache for processes listing
_PROCESSES_CACHE = []
_PROCESSES_LOCK = threading.Lock()

_WORKER_STARTED = False

def _stats_worker_loop():
    global _SYSTEM_STATS_CACHE, _CONN_TYPE_CACHE, _CONN_NAME_CACHE, _CONN_TYPE_COUNTER
    while True:
        try:
            # Poll connection type profile every 10 runs (5.0 seconds)
            _CONN_TYPE_COUNTER += 1
            if _CONN_TYPE_COUNTER >= 10:
                _CONN_TYPE_COUNTER = 0
                _CONN_TYPE_CACHE, _CONN_NAME_CACHE = _detect_connection_type_and_name()
                
            snapshot = _collect_stats_snapshot()
            with _CACHE_LOCK:
                _SYSTEM_STATS_CACHE = snapshot
        except Exception:
            pass
        time.sleep(0.5) # Poll system stats every 0.5 seconds in background

def _procs_worker_loop():
    global _PROCESSES_CACHE
    while True:
        try:
            snapshot = _collect_processes_snapshot()
            with _PROCESSES_LOCK:
                _PROCESSES_CACHE = snapshot
        except Exception:
            pass
        time.sleep(1.0) # Poll process details every 1.0 second in background

_PROCESS_OBJECTS_CACHE = {}

def _collect_processes_snapshot() -> list:
    """Collects list of processes with CPU, RAM, Disk, Net, and App categorization."""
    global _PROCESS_OBJECTS_CACHE
    procs = []
    num_cores = psutil.cpu_count() or 1
    now = time.time()

    current_pids = set(psutil.pids())
    
    # Prune cached process objects for dead PIDs
    dead_pids = set(_PROCESS_OBJECTS_CACHE.keys()) - current_pids
    for pid in dead_pids:
        _PROCESS_OBJECTS_CACHE.pop(pid, None)

    # Enumerate visible windows to tag App processes
    visible_pids = set()
    def enum_windows_callback(hwnd, extra):
        try:
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title:
                    _, win_pid = win32process.GetWindowThreadProcessId(hwnd)
                    visible_pids.add(win_pid)
        except Exception:
            pass
        return True

    try:
        win32gui.EnumWindows(enum_windows_callback, None)
    except Exception:
        pass

    # Fallback if window enumeration returns nothing (e.g. running in background/service session)
    use_fallback = len(visible_pids) == 0
    fallback_apps = {
        "chrome.exe", "brave.exe", "msedge.exe", "notepad.exe", "taskmgr.exe",
        "discord.exe", "explorer.exe", "code.exe", "python.exe", "antigravity.exe",
        "antigravity ide.exe", "spacedesk.exe", "spacedeskservice.exe", "spacedeskservicetray.exe"
    }

    for pid in current_pids:
        try:
            # Instantiate process object on its first discovery
            if pid not in _PROCESS_OBJECTS_CACHE:
                p = psutil.Process(pid)
                p.cpu_percent() # Initialize cpu ticks
                _PROCESS_OBJECTS_CACHE[pid] = {
                    "process": p,
                    "last_io": p.io_counters(),
                    "last_time": now
                }
                continue

            entry = _PROCESS_OBJECTS_CACHE[pid]
            p = entry["process"]
                
            with p.oneshot():
                name = p.name()
                if pid == 0 or (name and name.lower() == "system idle process"):
                    continue

                cpu_percent = p.cpu_percent()
                mem_info = p.memory_info()
                status = p.status()

                disk_mbs = 0.0
                net_mbps = 0.0
                try:
                    io = p.io_counters()
                    prev_io = entry["last_io"]
                    dt = now - entry["last_time"]
                    
                    if prev_io and io and dt > 0.1:
                        read_delta = io.read_bytes - prev_io.read_bytes
                        write_delta = io.write_bytes - prev_io.write_bytes
                        other_delta = io.other_bytes - prev_io.other_bytes

                        disk_mbs = round(((read_delta + write_delta) / dt) / (1024 * 1024), 2)
                        net_mbps = round(((other_delta / dt) * 8) / (1000 * 1000), 2)
                        
                    entry["last_io"] = io
                    entry["last_time"] = now
                except Exception:
                    pass

                is_app = (pid in visible_pids) or (use_fallback and name.lower() in fallback_apps)

                procs.append({
                    "pid"     : pid,
                    "name"    : name,
                    "cpu"     : round(cpu_percent / num_cores, 1),
                    "ram_mb"  : _size_mb(mem_info.rss) if mem_info else 0,
                    "disk_mbs": disk_mbs,
                    "net_mbps": net_mbps,
                    "status"  : status,
                    "is_app"  : is_app,
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
            
    return procs

def start_stats_worker():
    global _WORKER_STARTED
    if _WORKER_STARTED:
        return
    _WORKER_STARTED = True
    
    t_stats = threading.Thread(target=_stats_worker_loop, daemon=True)
    t_stats.start()
    
    t_procs = threading.Thread(target=_procs_worker_loop, daemon=True)
    t_procs.start()

def get_stats() -> dict:
    """Returns the latest cached system health snapshot instantly."""
    global _SYSTEM_STATS_CACHE
    start_stats_worker()
    with _CACHE_LOCK:
        if _SYSTEM_STATS_CACHE:
            return _SYSTEM_STATS_CACHE
            
    # Fallback for the very first request: collect stats synchronously
    snapshot = _collect_stats_snapshot()
    with _CACHE_LOCK:
        _SYSTEM_STATS_CACHE = snapshot
    return snapshot

_PREV_NET_COUNTERS = None
_PREV_NET_TIMESTAMP = None
_LAST_CPU_PERCENT = 0.0

def _collect_stats_snapshot() -> dict:
    """Collects system stats synchronously using native win32pdh performance queries."""
    global _PREV_NET_COUNTERS, _PREV_NET_TIMESTAMP, _LAST_CPU_PERCENT

    # 1. Query all PDH counters natively (takes ~50ms sleep delta inside)
    pdh = _query_pdh_metrics()

    # 2. Network Rates (Zero-Sleep Calculation)
    net_now = psutil.net_io_counters()
    time_now = time.time()
    
    sent_kbps = 0.0
    recv_kbps = 0.0
    
    if _PREV_NET_COUNTERS is not None and _PREV_NET_TIMESTAMP is not None:
        dt = time_now - _PREV_NET_TIMESTAMP
        if dt > 0.1:
            sent_delta = net_now.bytes_sent - _PREV_NET_COUNTERS.bytes_sent
            recv_delta = net_now.bytes_recv - _PREV_NET_COUNTERS.bytes_recv
            sent_kbps = round(((sent_delta / dt) * 8) / 1000, 1)
            recv_kbps = round(((recv_delta / dt) * 8) / 1000, 1)
            
    _PREV_NET_COUNTERS = net_now
    _PREV_NET_TIMESTAMP = time_now
    
    network = {
        "bytes_sent_mb" : _size_mb(net_now.bytes_sent),
        "bytes_recv_mb" : _size_mb(net_now.bytes_recv),
        "sent_kbps"     : sent_kbps,
        "recv_kbps"     : recv_kbps,
        "type"          : _CONN_TYPE_CACHE,
        "name"          : _CONN_NAME_CACHE,
    }

    # 3. CPU Metrics (Damped via Exponential Moving Average)
    raw_cpu = psutil.cpu_percent(interval=None)
    cpu_percent = round(0.4 * raw_cpu + 0.6 * _LAST_CPU_PERCENT, 1)
    _LAST_CPU_PERCENT = cpu_percent
    
    cpu_count       = psutil.cpu_count(logical=True)
    cpu_count_phys  = psutil.cpu_count(logical=False)
    
    # Calculate active overclocked CPU frequency (matches Task Manager exactly)
    cpu_freq_mhz = 2400
    try:
        base_mhz = 2400
        freq_info = psutil.cpu_freq()
        if freq_info and freq_info.max:
            base_mhz = freq_info.max
            
        if pdh.get("cpu_performance") is not None:
            cpu_freq_mhz = round(base_mhz * (pdh["cpu_performance"] / 100.0))
        elif freq_info:
            cpu_freq_mhz = round(freq_info.current)
    except Exception:
        pass

    # ── RAM ───────────────────────────────────────────────────────────────────
    ram             = psutil.virtual_memory()
    ram_total_gb    = _size_gb(ram.total)
    ram_used_gb     = _size_gb(ram.used)
    ram_free_gb     = _size_gb(ram.available)
    ram_percent     = ram.percent

    # ── Disk (With Media Type SSD/HDD/USB) ─────────────────────────────────────
    disk_types = get_disk_media_types()
    disks = []
    for part in psutil.disk_partitions():
        try:
            usage = psutil.disk_usage(part.mountpoint)
            drive_letter = part.mountpoint.split(":")[0].upper() if ":" in part.mountpoint else ""
            m_type = disk_types.get(drive_letter, "SSD") if drive_letter else "SSD"
            
            disks.append({
                "device"    : part.device,
                "mountpoint": part.mountpoint,
                "fstype"    : part.fstype,
                "total_gb"  : _size_gb(usage.total),
                "used_gb"   : _size_gb(usage.used),
                "free_gb"  : _size_gb(usage.free),
                "percent"   : usage.percent,
                "type"      : m_type,
            })
        except (PermissionError, OSError):
            continue

    # ── Battery ───────────────────────────────────────────────────────────────
    battery = None
    try:
        bat = psutil.sensors_battery()
        if bat:
            battery = {
                "percent"   : round(bat.percent, 1),
                "plugged_in": bat.power_plugged,
                "status"    : "Charging" if bat.power_plugged else "Discharging",
                "time_left" : str(datetime.fromtimestamp(bat.secsleft).strftime("%H:%M")) if bat.secsleft > 0 and not bat.power_plugged else "N/A",
            }
    except Exception:
        pass

    # ── GPUs (All controllers mapped natively via pdh) ───────────────────────
    gpus = get_all_gpus(pdh)

    # ── Uptime ────────────────────────────────────────────────────────────────
    boot_time   = psutil.boot_time()
    uptime_secs = (datetime.now().timestamp() - boot_time)
    uptime_hrs  = int(uptime_secs // 3600)
    uptime_mins = int((uptime_secs % 3600) // 60)

    return {
        "action"   : "get_stats",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "cpu": {
            "percent"       : cpu_percent,
            "cores_logical" : cpu_count,
            "cores_physical": cpu_count_phys,
            "freq_mhz"      : cpu_freq_mhz,
            "status"        : "high" if cpu_percent > 80 else "normal",
        },
        "ram": {
            "total_gb"  : ram_total_gb,
            "used_gb"   : ram_used_gb,
            "free_gb"   : ram_free_gb,
            "percent"   : ram_percent,
            "status"    : "high" if ram_percent > 85 else "normal",
        },
        "gpus"   : gpus,
        "disks"  : disks,
        "battery": battery,
        "network": network,
        "uptime" : f"{uptime_hrs}h {uptime_mins}m",
        "os"     : _os_name(),
        "status" : "ok",
    }

# ── CPU only ──────────────────────────────────────────────────────────────────

def get_cpu() -> dict:
    """Quick CPU usage check."""
    percent = psutil.cpu_percent(interval=0.5)
    return {
        "action" : "get_cpu",
        "percent": percent,
        "cores"  : psutil.cpu_count(logical=True),
        "status" : "high" if percent > 80 else "normal",
    }

# ── RAM only ──────────────────────────────────────────────────────────────────

def get_ram() -> dict:
    """Quick RAM usage check."""
    ram = psutil.virtual_memory()
    return {
        "action"   : "get_ram",
        "total_gb" : _size_gb(ram.total),
        "used_gb"  : _size_gb(ram.used),
        "free_gb"  : _size_gb(ram.available),
        "percent"  : ram.percent,
        "status"   : "high" if ram.percent > 85 else "normal",
    }

# ── Disk only ─────────────────────────────────────────────────────────────────

def get_disk() -> dict:
    """Disk usage for all drives."""
    disks = []
    for part in psutil.disk_partitions():
        try:
            usage = psutil.disk_usage(part.mountpoint)
            disks.append({
                "device"   : part.device,
                "total_gb" : _size_gb(usage.total),
                "used_gb"  : _size_gb(usage.used),
                "free_gb"  : _size_gb(usage.free),
                "percent"  : usage.percent,
                "status"   : "low" if usage.percent > 90 else "ok",
            })
        except (PermissionError, OSError):
            continue
    return {"action": "get_disk", "disks": disks, "status": "ok"}

# ── Battery only ──────────────────────────────────────────────────────────────

def get_battery() -> dict:
    """Battery level and charging status."""
    try:
        bat = psutil.sensors_battery()
        if not bat:
            return {"action": "get_battery", "available": False, "status": "ok"}
        return {
            "action"    : "get_battery",
            "available" : True,
            "percent"   : round(bat.percent, 1),
            "plugged_in": bat.power_plugged,
            "charging"  : bat.power_plugged,
            "status"    : "ok",
        }
    except Exception as e:
        return {"action": "get_battery", "status": "error", "error": str(e)}

# ── Process list ──────────────────────────────────────────────────────────────

def list_processes(sort_by: str = "cpu", limit: int = 20) -> dict:
    """
    List running processes sorted by CPU, RAM, Disk, or Network usage.
    Returns instantly from the background cache, categorized into Apps and Background processes.
    """
    global _PROCESSES_CACHE
    start_stats_worker()
    
    with _PROCESSES_LOCK:
        # Fallback if cache is not populated yet
        if not _PROCESSES_CACHE:
            _PROCESSES_CACHE = _collect_processes_snapshot()
        procs = list(_PROCESSES_CACHE)

    # Group processes by name (case-insensitive base name)
    grouped = {}
    for p in procs:
        name_clean = p["name"]
        if name_clean.lower().endswith(".exe"):
            name_clean = name_clean[:-4]
            
        key = name_clean.lower()
        if key not in grouped:
            grouped[key] = {
                "name": name_clean,
                "cpu": 0.0,
                "ram_mb": 0.0,
                "disk_mbs": 0.0,
                "net_mbps": 0.0,
                "pids": [],
                "count": 0,
                "is_app": False
            }
        
        grouped[key]["cpu"] += p["cpu"]
        grouped[key]["ram_mb"] += p["ram_mb"]
        grouped[key]["disk_mbs"] += p["disk_mbs"]
        grouped[key]["net_mbps"] += p["net_mbps"]
        grouped[key]["pids"].append(p["pid"])
        grouped[key]["count"] += 1
        grouped[key]["is_app"] = grouped[key]["is_app"] or p.get("is_app", False)

    apps = []
    background = []
    
    for k, item in grouped.items():
        display_name = item["name"]
        if item["count"] > 1:
            display_name = f"{item['name']} ({item['count']})"
            
        proc_data = {
            "pid": item["pids"][0] if item["pids"] else 0,
            "name": display_name,
            "cpu": round(item["cpu"], 1),
            "ram_mb": round(item["ram_mb"], 1),
            "disk_mbs": round(item["disk_mbs"], 2),
            "net_mbps": round(item["net_mbps"], 2),
            "status": "running"
        }
        
        if item["is_app"]:
            apps.append(proc_data)
        else:
            background.append(proc_data)

    # Sort helper
    def sort_list(lst):
        if sort_by == "ram":
            lst.sort(key=lambda x: x["ram_mb"], reverse=True)
        elif sort_by == "disk":
            lst.sort(key=lambda x: x["disk_mbs"], reverse=True)
        elif sort_by == "network":
            lst.sort(key=lambda x: x["net_mbps"], reverse=True)
        elif sort_by == "name":
            lst.sort(key=lambda x: x["name"].lower())
        else:  # cpu (default)
            lst.sort(key=lambda x: x["cpu"], reverse=True)

    sort_list(apps)
    sort_list(background)

    return {
        "action"          : "list_processes",
        "sort_by"         : sort_by,
        "total_apps"      : len(apps),
        "total_background": len(background),
        "apps"            : apps[:limit],
        "background"      : background[:limit],
        "status"          : "ok",
    }

# ── Kill process ──────────────────────────────────────────────────────────────

def kill_process(name: str = None, pid: int = None, confirmed: bool = False) -> dict:
    """
    Kill a process by name or PID.
    confirmed=True required — safety guard.
    """
    if not confirmed:
        target = name or str(pid)
        return {
            "status" : "needs_confirmation",
            "message": f"Are you sure you want to kill '{target}'? Pass confirmed=true to proceed.",
            "target" : target,
        }

    if not name and not pid:
        return {"status": "error", "error": "Provide name or pid"}

    killed = []
    not_found = True

    for proc in psutil.process_iter(["pid", "name"]):
        try:
            match = (
                (name and name.lower() in proc.info["name"].lower()) or
                (pid and proc.info["pid"] == pid)
            )
            if match:
                not_found = False
                proc.kill()
                killed.append({"pid": proc.info["pid"], "name": proc.info["name"]})
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            killed.append({"pid": proc.info.get("pid"), "name": proc.info.get("name"), "error": str(e)})

    if not_found:
        return {"action": "kill_process", "status": "not_found", "target": name or pid}

    return {
        "action" : "kill_process",
        "killed" : killed,
        "count"  : len(killed),
        "status" : "ok",
    }

# ── Network stats ─────────────────────────────────────────────────────────────

def get_network() -> dict:
    """Network I/O stats and active connections count."""
    net = psutil.net_io_counters()
    try:
        connections = len(psutil.net_connections())
    except Exception:
        connections = None

    return {
        "action"          : "get_network",
        "bytes_sent_mb"   : _size_mb(net.bytes_sent),
        "bytes_recv_mb"   : _size_mb(net.bytes_recv),
        "packets_sent"    : net.packets_sent,
        "packets_recv"    : net.packets_recv,
        "active_connections": connections,
        "status"          : "ok",
    }

# Start background monitoring worker immediately when the module is imported
start_stats_worker()
