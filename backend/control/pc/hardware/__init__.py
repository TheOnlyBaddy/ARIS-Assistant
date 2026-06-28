# control/pc/hardware/__init__.py
from .system import get_stats, get_cpu, get_ram, get_disk, get_battery, list_processes, kill_process, get_network
from .brightness import set_brightness
from .media import media_control
from .network import get_network_diagnostics
from .power import lock_pc, sleep_pc, shutdown_pc, restart_pc, cancel_shutdown
