// src/components/SystemDashboard.jsx
import { useState, useEffect, useRef } from "react"
import axios from "axios"

const API_BASE = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
  ? "http://localhost:8000"
  : `http://${window.location.hostname}:8000`

// ── Circular gauge ────────────────────────────────────────────────────────────
function Gauge({ value, max = 100, label, color, unit = "%", subtitle, tooltip }) {
    const pct = Math.min((value / max) * 100, 100)
    const radius = 36
    const circ = 2 * Math.PI * radius
    const offset = circ - (pct / 100) * circ

    return (
        <div className="gauge-wrap">
            <svg width="90" height="90" viewBox="0 0 90 90">
                {/* Track */}
                <circle cx="45" cy="45" r={radius}
                    fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="8" />
                {/* Fill */}
                <circle cx="45" cy="45" r={radius}
                    fill="none" stroke={color} strokeWidth="8"
                    strokeDasharray={circ} strokeDashoffset={offset}
                    strokeLinecap="round"
                    transform="rotate(-90 45 45)"
                    style={{ transition: "stroke-dashoffset 0.6s ease" }}
                />
                {/* Value */}
                <text x="45" y="45" textAnchor="middle" dominantBaseline="middle"
                    fill="#fff" fontSize="13" fontWeight="700">
                    {unit.includes("GB") ? value.toFixed(1) : Math.round(value)}{unit}
                </text>
            </svg>
            <p className="gauge-label">{label}</p>
            {subtitle && <p className="gauge-sub" style={{ fontSize: "10px", color: "#888", marginTop: "-2px", marginBottom: "0" }}>{subtitle}</p>}
            {tooltip}
        </div>
    )
}

// ── Disk bar ──────────────────────────────────────────────────────────────────
function DiskBar({ disk }) {
    const col = disk.percent > 90 ? "#ef4444" : disk.percent > 75 ? "#f59e0b" : "#10b981"
    return (
        <div className="disk-bar-wrap">
            <div className="disk-bar-header">
                <span className="disk-drive">{disk.device} ({disk.type || "SSD"})</span>
                <span className="disk-pct" style={{ color: col }}>{disk.percent}%</span>
            </div>
            <div className="disk-track">
                <div className="disk-fill" style={{ width: `${disk.percent}%`, background: col }} />
            </div>
            <div className="disk-meta">
                {disk.used_gb} GB used / {disk.total_gb} GB total · {disk.free_gb} GB free
            </div>
        </div>
    )
}

// ── Network Icon Helper ───────────────────────────────────────────────────────
const getNetIcon = (type) => {
    if (!type) return "🌐";
    const t = type.toLowerCase();
    if (t.includes("wi-fi") || t.includes("wifi")) return "📶";
    if (t.includes("ethernet")) return "🔌";
    if (t.includes("tether") || t.includes("ndis") || t.includes("usb")) return "📱";
    if (t.includes("bluetooth")) return "🔵";
    if (t.includes("disconnected")) return "⚠️";
    return "🌐";
}

// ── Process row ───────────────────────────────────────────────────────────────
function ProcessRow({ proc }) {
    const cpuCol = proc.cpu > 50 ? "#ef4444" : proc.cpu > 20 ? "#f59e0b" : "#6ee7b7"
    return (
        <div className="proc-row">
            <span className="proc-pid">{proc.pid}</span>
            <span className="proc-name">{proc.name}</span>
            <span className="proc-cpu" style={{ color: cpuCol }}>{proc.cpu}%</span>
            <span className="proc-ram">{proc.ram_mb} MB</span>
            <span className="proc-disk">{proc.disk_mbs > 0 ? `${proc.disk_mbs} MB/s` : "0 MB/s"}</span>
            <span className="proc-net">{proc.net_mbps > 0 ? `${proc.net_mbps} Mbps` : "0 Mbps"}</span>
        </div>
    )
}

// ── Main Dashboard ────────────────────────────────────────────────────────────
export default function SystemDashboard({ visible }) {
    const [stats, setStats] = useState(null)
    const [apps, setApps] = useState([])
    const [background, setBackground] = useState([])
    const [totalApps, setTotalApps] = useState(0)
    const [totalBg, setTotalBg] = useState(0)
    const [appsExpanded, setAppsExpanded] = useState(true)
    const [bgExpanded, setBgExpanded] = useState(true)
    const [loading, setLoading] = useState(true)
    const [lastUpdate, setLastUpdate] = useState(null)
    const [procSort, setProcSort] = useState("cpu")
    const intervalRef = useRef(null)

    const fetchStats = async () => {
        try {
            const [statsRes, procRes] = await Promise.all([
                axios.get(`${API_BASE}/control/system`),
                axios.post(`${API_BASE}/control/system/processes`,
                    { sort_by: procSort, limit: 15 },
                    { headers: { "Content-Type": "application/json" } }
                )
            ])
            setStats(statsRes.data)
            setApps(procRes.data.apps || [])
            setBackground(procRes.data.background || [])
            setTotalApps(procRes.data.total_apps || 0)
            setTotalBg(procRes.data.total_background || 0)
            setLastUpdate(new Date().toLocaleTimeString())
            setLoading(false)
        } catch (e) {
            console.error("System stats error:", e)
            setLoading(false)
        }
    }

    useEffect(() => {
        if (!visible) return
        fetchStats()
        intervalRef.current = setInterval(fetchStats, 500)
        return () => clearInterval(intervalRef.current)
    }, [visible, procSort])

    if (!visible) return null

    if (loading) return (
        <div className="sys-dashboard loading">
            <div className="sys-spinner" />
            <p>Loading system stats…</p>
        </div>
    )

    if (!stats) return (
        <div className="sys-dashboard error">
            <p>⚠️ Could not reach backend</p>
        </div>
    )

    return (
        <div className="sys-dashboard">

            {/* ── Header ── */}
            <div className="sys-header">
                <h3>🖥️ System Dashboard</h3>
                <div className="sys-meta">
                    <span>{stats.os}</span>
                    <span>⏱ Up {stats.uptime}</span>
                    {lastUpdate && <span>🔄 {lastUpdate}</span>}
                </div>
            </div>

            {/* ── Gauges row ── */}
            <div className="sys-gauges">
                <Gauge 
                    value={stats.cpu.percent} 
                    label="CPU" 
                    color="#6366f1" 
                    subtitle={stats.cpu.freq_mhz ? `${(stats.cpu.freq_mhz / 1000).toFixed(2)} GHz` : undefined}
                    tooltip={
                        <div className="gauge-tooltip align-left" style={{ '--accent-color': '#6366f1' }}>
                            <div className="gauge-tooltip-title">CPU Specifications</div>
                            <div className="gauge-tooltip-row">
                                <span className="tooltip-key">Logical Cores</span>
                                <span className="tooltip-val">{stats.cpu.cores_logical}</span>
                            </div>
                            <div className="gauge-tooltip-row">
                                <span className="tooltip-key">Physical Cores</span>
                                <span className="tooltip-val">{stats.cpu.cores_physical}</span>
                            </div>
                            <div className="gauge-tooltip-row">
                                <span className="tooltip-key">Active Speed</span>
                                <span className="tooltip-val">{(stats.cpu.freq_mhz / 1000).toFixed(2)} GHz</span>
                            </div>
                        </div>
                    }
                />
                <Gauge 
                    value={stats.ram.percent} 
                    label="RAM" 
                    color="#10b981" 
                    tooltip={
                        <div className="gauge-tooltip" style={{ '--accent-color': '#10b981' }}>
                            <div className="gauge-tooltip-title">Memory Details</div>
                            <div className="gauge-tooltip-row">
                                <span className="tooltip-key">Used</span>
                                <span className="tooltip-val">{stats.ram.used_gb} GB</span>
                            </div>
                            <div className="gauge-tooltip-row">
                                <span className="tooltip-key">Available</span>
                                <span className="tooltip-val">{stats.ram.free_gb} GB</span>
                            </div>
                            <div className="gauge-tooltip-row">
                                <span className="tooltip-key">Total Size</span>
                                <span className="tooltip-val">{stats.ram.total_gb} GB</span>
                            </div>
                        </div>
                    }
                />
                {stats.gpus && stats.gpus.map((gpu, idx) => {
                    const isLastGpu = idx === stats.gpus.length - 1 && !stats.battery
                    return (
                        <Gauge 
                            key={`gpu-gauge-${idx}`}
                            value={gpu.percent} 
                            label={gpu.type === "integrated" ? "Integrated GPU" : "Discrete GPU"} 
                            color="#ec4899" 
                            subtitle={gpu.temp !== null ? `${gpu.temp}°C` : undefined}
                            tooltip={
                                <div className={`gauge-tooltip ${isLastGpu ? 'align-right' : ''}`} style={{ '--accent-color': '#ec4899' }}>
                                    <div className="gauge-tooltip-title">{gpu.name}</div>
                                    <div className="gauge-tooltip-row">
                                        <span className="tooltip-key">Type</span>
                                        <span className="tooltip-val">{gpu.type === "integrated" ? "Integrated" : "Discrete"}</span>
                                    </div>
                                    {gpu.total_vram && (
                                        <div className="gauge-tooltip-row">
                                            <span className="tooltip-key">{gpu.type === "integrated" ? "Shared VRAM" : "Dedicated VRAM"}</span>
                                            <span className="tooltip-val">{gpu.used_vram} / {gpu.total_vram} GB</span>
                                        </div>
                                    )}
                                    {gpu.temp !== null && (
                                        <div className="gauge-tooltip-row">
                                            <span className="tooltip-key">Temperature</span>
                                            <span className="tooltip-val">{gpu.temp}°C</span>
                                        </div>
                                    )}
                                </div>
                            }
                        />
                    )
                })}
                {stats.battery && (
                    <Gauge
                        value={stats.battery.percent}
                        label={stats.battery.plugged_in ? "🔌 Battery" : "🔋 Battery"}
                        color={stats.battery.plugged_in ? "#10b981" : "#f59e0b"}
                        tooltip={
                            <div className="gauge-tooltip align-right" style={{ '--accent-color': stats.battery.plugged_in ? '#10b981' : '#f59e0b' }}>
                                <div className="gauge-tooltip-title">Battery Status</div>
                                <div className="gauge-tooltip-row">
                                    <span className="tooltip-key">Charge</span>
                                    <span className="tooltip-val">{stats.battery.percent}%</span>
                                </div>
                                <div className="gauge-tooltip-row">
                                    <span className="tooltip-key">Status</span>
                                    <span className="tooltip-val">{stats.battery.status}</span>
                                </div>
                                {stats.battery.plugged_in ? (
                                    <div className="gauge-tooltip-row">
                                        <span className="tooltip-key">Power Source</span>
                                        <span className="tooltip-val" style={{ color: '#10b981' }}>AC Power</span>
                                    </div>
                                ) : (
                                    <div className="gauge-tooltip-row">
                                        <span className="tooltip-key">Time Left</span>
                                        <span className="tooltip-val">{stats.battery.time_left}</span>
                                    </div>
                                )}
                            </div>
                        }
                    />
                )}
            </div>

            {/* ── Network ── */}
            <div className="sys-section">
                <p className="sys-section-title">Network</p>
                <div className="sys-network" style={{ display: "flex", gap: "24px", flexWrap: "wrap" }}>
                    <div className="net-stat">
                        <span className="net-icon">{getNetIcon(stats.network.type)}</span>
                        <span>Connection: <strong>{stats.network.type || "Unknown"}</strong>{stats.network.name && <span style={{ color: "#777", fontSize: "11px" }}> ({stats.network.name})</span>}</span>
                    </div>
                    <div className="net-stat">
                        <span className="net-icon">↑</span>
                        <span>Send: <strong>{stats.network.sent_kbps > 1000 ? `${(stats.network.sent_kbps / 1000).toFixed(2)} Mbps` : `${stats.network.sent_kbps} Kbps`}</strong> <span style={{ color: "#777", fontSize: "11px" }}>({stats.network.bytes_sent_mb} MB total)</span></span>
                    </div>
                    <div className="net-stat">
                        <span className="net-icon">↓</span>
                        <span>Receive: <strong>{stats.network.recv_kbps > 1000 ? `${(stats.network.recv_kbps / 1000).toFixed(2)} Mbps` : `${stats.network.recv_kbps} Kbps`}</strong> <span style={{ color: "#777", fontSize: "11px" }}>({stats.network.bytes_recv_mb} MB total)</span></span>
                    </div>
                </div>
            </div>

            {/* ── Disks ── */}
            <div className="sys-section">
                <p className="sys-section-title">Disk Usage</p>
                {stats.disks.map((d, i) => <DiskBar key={i} disk={d} />)}
            </div>

            {/* ── Processes ── */}
            <div className="sys-section">
                <div className="sys-proc-header">
                    <p className="sys-section-title">Processes</p>
                </div>
                <div className="proc-table">
                    <div className="proc-row proc-header">
                        <span className="proc-pid">PID</span>
                        <span className={`proc-name sortable ${procSort === 'name' ? 'active' : ''}`} onClick={() => setProcSort('name')}>Name</span>
                        <span className={`proc-cpu sortable ${procSort === 'cpu' ? 'active' : ''}`} onClick={() => setProcSort('cpu')}>CPU</span>
                        <span className={`proc-ram sortable ${procSort === 'ram' ? 'active' : ''}`} onClick={() => setProcSort('ram')}>Memory</span>
                        <span className={`proc-disk sortable ${procSort === 'disk' ? 'active' : ''}`} onClick={() => setProcSort('disk')}>Disk</span>
                        <span className={`proc-net sortable ${procSort === 'network' ? 'active' : ''}`} onClick={() => setProcSort('network')}>Network</span>
                    </div>
                    
                    {/* Apps Section */}
                    <div className="proc-category-header" onClick={() => setAppsExpanded(!appsExpanded)}>
                        <span className="category-arrow">{appsExpanded ? "▼" : "▶"}</span>
                        <span>Apps ({totalApps})</span>
                    </div>
                    {appsExpanded && apps.map((p, i) => <ProcessRow key={`app-${i}`} proc={p} />)}

                    {/* Background Processes Section */}
                    <div className="proc-category-header" onClick={() => setBgExpanded(!bgExpanded)}>
                        <span className="category-arrow">{bgExpanded ? "▼" : "▶"}</span>
                        <span>Background processes ({totalBg})</span>
                    </div>
                    {bgExpanded && background.map((p, i) => <ProcessRow key={`bg-${i}`} proc={p} />)}
                </div>
            </div>

        </div>
    )
}