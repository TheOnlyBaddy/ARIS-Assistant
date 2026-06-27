// src/components/SystemDashboard.jsx
import { useState, useEffect, useRef } from "react"
import axios from "axios"

const API_BASE = "http://localhost:8000"

// ── Circular gauge ────────────────────────────────────────────────────────────
function Gauge({ value, max = 100, label, color, unit = "%" }) {
    const pct = Math.min((value / max) * 100, 100)
    const radius = 36
    const circ = 2 * Math.PI * radius
    const offset = circ - (pct / 100) * circ

    const col = pct > 85 ? "#ef4444" : pct > 60 ? "#f59e0b" : color

    return (
        <div className="gauge-wrap">
            <svg width="90" height="90" viewBox="0 0 90 90">
                {/* Track */}
                <circle cx="45" cy="45" r={radius}
                    fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="8" />
                {/* Fill */}
                <circle cx="45" cy="45" r={radius}
                    fill="none" stroke={col} strokeWidth="8"
                    strokeDasharray={circ} strokeDashoffset={offset}
                    strokeLinecap="round"
                    transform="rotate(-90 45 45)"
                    style={{ transition: "stroke-dashoffset 0.6s ease" }}
                />
                {/* Value */}
                <text x="45" y="45" textAnchor="middle" dominantBaseline="middle"
                    fill="#fff" fontSize="13" fontWeight="700">
                    {Math.round(value)}{unit}
                </text>
            </svg>
            <p className="gauge-label">{label}</p>
        </div>
    )
}

// ── Disk bar ──────────────────────────────────────────────────────────────────
function DiskBar({ disk }) {
    const col = disk.percent > 90 ? "#ef4444" : disk.percent > 75 ? "#f59e0b" : "#10b981"
    return (
        <div className="disk-bar-wrap">
            <div className="disk-bar-header">
                <span className="disk-drive">{disk.device}</span>
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

// ── Process row ───────────────────────────────────────────────────────────────
function ProcessRow({ proc }) {
    const cpuCol = proc.cpu > 50 ? "#ef4444" : proc.cpu > 20 ? "#f59e0b" : "#6ee7b7"
    return (
        <div className="proc-row">
            <span className="proc-pid">{proc.pid}</span>
            <span className="proc-name">{proc.name}</span>
            <span className="proc-cpu" style={{ color: cpuCol }}>{proc.cpu}%</span>
            <span className="proc-ram">{proc.ram_mb} MB</span>
        </div>
    )
}

// ── Main Dashboard ────────────────────────────────────────────────────────────
export default function SystemDashboard({ visible }) {
    const [stats, setStats] = useState(null)
    const [processes, setProcesses] = useState([])
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
            setProcesses(procRes.data.processes || [])
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
        intervalRef.current = setInterval(fetchStats, 3000)
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
                <Gauge value={stats.cpu.percent} label="CPU" color="#6366f1" />
                <Gauge value={stats.ram.percent} label="RAM" color="#10b981" />
                {stats.battery && (
                    <Gauge
                        value={stats.battery.percent}
                        label={stats.battery.plugged_in ? "🔌 Battery" : "🔋 Battery"}
                        color={stats.battery.plugged_in ? "#10b981" : "#f59e0b"}
                    />
                )}
                <div className="gauge-wrap">
                    <div className="sys-text-stat">
                        <p className="sys-stat-val">{stats.ram.used_gb}<span>GB</span></p>
                        <p className="sys-stat-sub">of {stats.ram.total_gb} GB RAM</p>
                    </div>
                    <p className="gauge-label">Memory</p>
                </div>
            </div>

            {/* ── Network ── */}
            <div className="sys-section">
                <p className="sys-section-title">Network</p>
                <div className="sys-network">
                    <div className="net-stat">
                        <span className="net-icon">↑</span>
                        <span>{stats.network.bytes_sent_mb} MB sent</span>
                    </div>
                    <div className="net-stat">
                        <span className="net-icon">↓</span>
                        <span>{stats.network.bytes_recv_mb} MB recv</span>
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
                    <div className="proc-sort-btns">
                        {["cpu", "ram", "name"].map(s => (
                            <button
                                key={s}
                                className={`proc-sort-btn ${procSort === s ? "active" : ""}`}
                                onClick={() => setProcSort(s)}
                            >
                                {s.toUpperCase()}
                            </button>
                        ))}
                    </div>
                </div>
                <div className="proc-table">
                    <div className="proc-row proc-header">
                        <span>PID</span><span>Name</span><span>CPU</span><span>RAM</span>
                    </div>
                    {processes.map((p, i) => <ProcessRow key={i} proc={p} />)}
                </div>
            </div>

        </div>
    )
}