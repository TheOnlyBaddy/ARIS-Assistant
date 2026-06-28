# ARIS/control/pc/hardware/network.py
"""
Network Diagnostics and Statistics module for ARIS — Windows 11
"""

import subprocess
import httpx
import re

def get_network_diagnostics() -> dict:
    """
    Gather network statistics including Wi-Fi SSID, signal quality, latency ping, and public IP address.
    """
    ssid = "N/A"
    signal = "N/A"
    interface_type = "Ethernet/Other"

    # 1. Check Wi-Fi SSID and signal via netsh
    try:
        res = subprocess.run(["netsh", "wlan", "show", "interfaces"], capture_output=True, text=True, errors="ignore")
        if res.returncode == 0:
            for line in res.stdout.split("\n"):
                line_stripped = line.strip()
                if line_stripped.startswith("SSID"):
                    parts = line_stripped.split(":", 1)
                    if len(parts) > 1:
                        ssid = parts[1].strip()
                        interface_type = "Wi-Fi"
                elif line_stripped.startswith("Signal"):
                    parts = line_stripped.split(":", 1)
                    if len(parts) > 1:
                        signal = parts[1].strip()
    except Exception:
        pass

    # 2. Get Public IP via ipify API
    public_ip = "Offline / Unknown"
    try:
        r = httpx.get("https://api.ipify.org?format=json", timeout=2.0)
        if r.status_code == 200:
            public_ip = r.json().get("ip", "N/A")
    except Exception:
        pass

    # 3. Ping Google DNS (8.8.8.8) to measure latency
    latency = "N/A"
    try:
        # Pinging once (Windows syntax: ping -n 1)
        ping_res = subprocess.run(["ping", "-n", "1", "8.8.8.8"], capture_output=True, text=True, errors="ignore")
        if ping_res.returncode == 0:
            match = re.search(r"time[=<](\d+)ms", ping_res.stdout)
            if match:
                latency = f"{match.group(1)} ms"
            else:
                match_avg = re.search(r"Average = (\d+)ms", ping_res.stdout)
                if match_avg:
                    latency = f"{match_avg.group(1)} ms"
    except Exception:
        pass

    return {
        "action"        : "get_network_diagnostics",
        "interface_type": interface_type,
        "wifi_ssid"     : ssid,
        "wifi_signal"   : signal,
        "public_ip"     : public_ip,
        "ping_latency"  : latency,
        "status"        : "ok"
    }
