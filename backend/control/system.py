# ARIS/control/system.py
"""
System Monitoring module for ARIS — Windows 11
Handles: CPU, RAM, disk, battery, processes, network, kill process
"""

import psutil
import os
import platform
from datetime import datetime
from typing import Optional

# ── Helpers ───────────────────────────────────────────────────────────────────

def _size_gb(bytes: int) -> float:
    return round(bytes / (1024 ** 3), 2)

def _size_mb(bytes: int) -> float:
    return round(bytes / (1024 ** 2), 2)

# ── Full system stats ─────────────────────────────────────────────────────────

def get_stats() -> dict:
    """
    Returns a full system health snapshot:
    CPU, RAM, disk, battery, network, uptime.
    """
    # ── CPU ───────────────────────────────────────────────────────────────────
    cpu_percent     = psutil.cpu_percent(interval=0.5)
    cpu_count       = psutil.cpu_count(logical=True)
    cpu_count_phys  = psutil.cpu_count(logical=False)
    try:
        cpu_freq    = psutil.cpu_freq()
        cpu_freq_mhz = round(cpu_freq.current) if cpu_freq else None
    except Exception:
        cpu_freq_mhz = None

    # ── RAM ───────────────────────────────────────────────────────────────────
    ram             = psutil.virtual_memory()
    ram_total_gb    = _size_gb(ram.total)
    ram_used_gb     = _size_gb(ram.used)
    ram_free_gb     = _size_gb(ram.available)
    ram_percent     = ram.percent

    # ── Disk ──────────────────────────────────────────────────────────────────
    disks = []
    for part in psutil.disk_partitions():
        try:
            usage = psutil.disk_usage(part.mountpoint)
            disks.append({
                "device"    : part.device,
                "mountpoint": part.mountpoint,
                "fstype"    : part.fstype,
                "total_gb"  : _size_gb(usage.total),
                "used_gb"   : _size_gb(usage.used),
                "free_gb"   : _size_gb(usage.free),
                "percent"   : usage.percent,
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

    # ── Network ───────────────────────────────────────────────────────────────
    net = psutil.net_io_counters()
    network = {
        "bytes_sent_mb"   : _size_mb(net.bytes_sent),
        "bytes_recv_mb"   : _size_mb(net.bytes_recv),
        "packets_sent"    : net.packets_sent,
        "packets_recv"    : net.packets_recv,
    }

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
        "disks"  : disks,
        "battery": battery,
        "network": network,
        "uptime" : f"{uptime_hrs}h {uptime_mins}m",
        "os"     : f"{platform.system()} {platform.release()}",
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
    List running processes sorted by CPU or RAM usage.
    sort_by: "cpu" | "ram" | "name"
    """
    procs = []
    for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info", "status"]):
        try:
            info = proc.info
            procs.append({
                "pid"    : info["pid"],
                "name"   : info["name"],
                "cpu"    : round(info["cpu_percent"] or 0, 1),
                "ram_mb" : _size_mb(info["memory_info"].rss) if info["memory_info"] else 0,
                "status" : info["status"],
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    # Sort
    if sort_by == "ram":
        procs.sort(key=lambda x: x["ram_mb"], reverse=True)
    elif sort_by == "name":
        procs.sort(key=lambda x: x["name"].lower())
    else:  # cpu (default)
        procs.sort(key=lambda x: x["cpu"], reverse=True)

    return {
        "action"       : "list_processes",
        "sort_by"      : sort_by,
        "total_running": len(procs),
        "processes"    : procs[:limit],
        "status"       : "ok",
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