// src/components/SchedulerUI.jsx
import { useState, useEffect, useRef } from "react"
import axios from "axios"

const API_BASE = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
    ? "http://localhost:8000"
    : `http://${window.location.hostname}:8000`

export default function SchedulerUI({ visible }) {
    const [schedules, setSchedules] = useState([])
    const [stats, setStats] = useState(null)
    const [privacy, setPrivacy] = useState({ privacy_mode: false, retention_days: 30 })
    const [loading, setLoading] = useState(true)

    // Form states
    const [jobName, setJobName] = useState("")
    const [triggerType, setTriggerType] = useState("interval")
    const [expression, setExpression] = useState("60")
    const [intent, setIntent] = useState("send_notification")
    const [paramsStr, setParamsStr] = useState('{"title": "ARIS Alert", "message": "Proactive job fired!"}')
    const [formSubmitting, setFormSubmitting] = useState(false)

    const fetchAllData = async () => {
        try {
            const apiKey = localStorage.getItem("aris_api_key") || ""
            const headers = { "X-API-Key": apiKey }

            const [schedRes, statsRes, privRes] = await Promise.all([
                axios.get(`${API_BASE}/agents/schedules`, { headers }),
                axios.get(`${API_BASE}/admin/stats`, { headers }),
                axios.get(`${API_BASE}/settings/privacy`, { headers })
            ])

            setSchedules(schedRes.data.schedules || [])
            setStats(statsRes.data)
            setPrivacy(privRes.data)
            setLoading(false)
        } catch (e) {
            console.error("Error fetching scheduler/admin data:", e)
            setLoading(false)
        }
    }

    const handleCreateSchedule = async (e) => {
        e.preventDefault()
        if (!jobName.trim() || !expression.trim() || !intent.trim()) return
        setFormSubmitting(true)

        let parsedParams = {}
        try {
            if (paramsStr.trim()) {
                parsedParams = JSON.parse(paramsStr)
            }
        } catch (err) {
            alert("Invalid JSON format in Parameters field.")
            setFormSubmitting(false)
            return
        }

        try {
            const apiKey = localStorage.getItem("aris_api_key") || ""
            await axios.post(`${API_BASE}/agents/schedule`,
                {
                    name: jobName,
                    trigger_type: triggerType,
                    expression: expression,
                    intent: intent,
                    params: parsedParams
                },
                { headers: { "X-API-Key": apiKey, "Content-Type": "application/json" } }
            )
            setJobName("")
            setExpression(triggerType === "interval" ? "60" : "0 9 * * *")
            fetchAllData()
            alert("Automation schedule created successfully!")
        } catch (err) {
            alert("Failed to create schedule: " + (err.response?.data?.detail || err.message))
        } finally {
            setFormSubmitting(false)
        }
    }

    const handleDeleteSchedule = async (jobId) => {
        if (!confirm("Are you sure you want to delete this schedule?")) return
        try {
            const apiKey = localStorage.getItem("aris_api_key") || ""
            await axios.delete(`${API_BASE}/agents/schedule/${jobId}`, {
                headers: { "X-API-Key": apiKey }
            })
            fetchAllData()
        } catch (err) {
            alert("Failed to delete schedule: " + (err.response?.data?.detail || err.message))
        }
    }

    const handleTriggerSchedule = async (jobId) => {
        try {
            const apiKey = localStorage.getItem("aris_api_key") || ""
            const r = await axios.post(`${API_BASE}/agents/schedule/${jobId}/trigger`, {}, {
                headers: { "X-API-Key": apiKey }
            })
            alert(r.data.message || "Job triggered successfully!")
            fetchAllData()
        } catch (err) {
            alert("Failed to trigger job: " + (err.response?.data?.detail || err.message))
        }
    }

    const handleSavePrivacy = async (e) => {
        e.preventDefault()
        try {
            const apiKey = localStorage.getItem("aris_api_key") || ""
            const r = await axios.post(`${API_BASE}/settings/privacy`,
                privacy,
                { headers: { "X-API-Key": apiKey, "Content-Type": "application/json" } }
            )
            alert(`Privacy settings updated! Pruned ${r.data.messages_pruned} messages exceeding retention policy.`)
            fetchAllData()
        } catch (err) {
            alert("Failed to save privacy settings: " + (err.response?.data?.detail || err.message))
        }
    }

    useEffect(() => {
        if (!visible) return
        fetchAllData()
        const t = setInterval(fetchAllData, 10000)
        return () => clearInterval(t)
    }, [visible])

    if (!visible) return null

    return (
        <div className="scheduler-ui" style={{
            color: "#fff",
            fontFamily: "inherit",
            display: "flex",
            flexDirection: "column",
            gap: "24px",
            padding: "24px",
            background: "rgba(10, 10, 15, 0.2)",
            borderRadius: "16px",
            backdropFilter: "blur(20px)",
            border: "1px solid rgba(255, 255, 255, 0.05)"
        }}>
            <style>{`
                .sched-grid {
                    display: grid;
                    grid-template-columns: 1.2fr 0.8fr;
                    gap: 24px;
                }
                .sched-card {
                    background: rgba(255, 255, 255, 0.03);
                    border: 1px solid rgba(255, 255, 255, 0.06);
                    border-radius: 12px;
                    padding: 20px;
                    backdrop-filter: blur(10px);
                }
                .sched-card-title {
                    font-size: 1.1rem;
                    font-weight: 700;
                    margin-top: 0;
                    margin-bottom: 16px;
                    display: flex;
                    align-items: center;
                    gap: 8px;
                    color: #fff;
                    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
                    padding-bottom: 10px;
                }
                .trigger-badge {
                    padding: 2px 6px;
                    border-radius: 4px;
                    font-size: 0.7rem;
                    font-weight: 600;
                    text-transform: uppercase;
                }
                .trigger-interval { background: rgba(6, 182, 212, 0.15); color: #06b6d4; border: 1px solid rgba(6, 182, 212, 0.3); }
                .trigger-cron { background: rgba(139, 92, 246, 0.15); color: #8b5cf6; border: 1px solid rgba(139, 92, 246, 0.3); }
                
                .form-group {
                    margin-bottom: 12px;
                    display: flex;
                    flex-direction: column;
                    gap: 6px;
                }
                .form-label {
                    font-size: 0.8rem;
                    color: #aaa;
                    font-weight: 500;
                }
                .form-input {
                    background: rgba(255, 255, 255, 0.05);
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    border-radius: 6px;
                    padding: 8px 12px;
                    color: #fff;
                    font-family: inherit;
                    font-size: 0.9rem;
                    outline: none;
                    transition: border 0.3s;
                    width: 100%;
                    box-sizing: border-box;
                }
                .form-input:focus {
                    border-color: #6366f1;
                }
                .submit-btn {
                    background: linear-gradient(135deg, #6366f1, #8b5cf6);
                    color: #fff;
                    border: none;
                    border-radius: 6px;
                    padding: 10px 16px;
                    font-weight: 600;
                    cursor: pointer;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    gap: 8px;
                    transition: opacity 0.3s, transform 0.2s;
                }
                .submit-btn:hover {
                    opacity: 0.9;
                }
                .submit-btn:active {
                    transform: scale(0.98);
                }
                .submit-btn:disabled {
                    background: #555;
                    cursor: not-allowed;
                    opacity: 0.5;
                }
                .action-icon-btn {
                    background: rgba(255, 255, 255, 0.05);
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    color: #fff;
                    border-radius: 4px;
                    padding: 4px 8px;
                    cursor: pointer;
                    font-size: 0.8rem;
                    transition: background 0.3s;
                }
                .action-icon-btn:hover {
                    background: rgba(255, 255, 255, 0.1);
                }
                .btn-delete:hover {
                    background: rgba(239, 68, 68, 0.2);
                    border-color: rgba(239, 68, 68, 0.4);
                    color: #ef4444;
                }
                
                .stat-box {
                    background: rgba(255, 255, 255, 0.02);
                    border: 1px solid rgba(255, 255, 255, 0.05);
                    border-radius: 8px;
                    padding: 12px;
                    text-align: center;
                }
                .stat-val {
                    font-size: 1.4rem;
                    font-weight: 700;
                    color: #6366f1;
                    margin-top: 4px;
                }
                .stat-desc {
                    font-size: 0.75rem;
                    color: #888;
                    margin-top: 2px;
                }
            `}</style>

            {/* TOP BAR: ADMIN PANEL STATUS & METRICS */}
            <div className="sched-card" style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "16px" }}>
                <div className="stat-box">
                    <span style={{ fontSize: "1.2rem" }}>🖥️ CPU Load</span>
                    <div className="stat-val" style={{ color: (stats?.system?.cpu_load_percent > 70) ? "#ef4444" : "#10b981" }}>
                        {stats ? `${stats.system.cpu_load_percent.toFixed(1)}%` : "—"}
                    </div>
                    <div className="stat-desc">Processor load</div>
                </div>
                <div className="stat-box">
                    <span style={{ fontSize: "1.2rem" }}>💾 Memory Load</span>
                    <div className="stat-val" style={{ color: (stats?.system?.memory_utilization_percent > 80) ? "#f59e0b" : "#6366f1" }}>
                        {stats ? `${stats.system.memory_utilization_percent.toFixed(1)}%` : "—"}
                    </div>
                    <div className="stat-desc">RAM utilization</div>
                </div>
                <div className="stat-box">
                    <span style={{ fontSize: "1.2rem" }}>🗃️ DB Info</span>
                    <div className="stat-val" style={{ color: "#06b6d4" }}>
                        {stats ? `${stats.database.db_size_kb.toFixed(1)} KB` : "—"}
                    </div>
                    <div className="stat-desc">{stats ? `${stats.database.total_active_sessions} Sessions` : "—"}</div>
                </div>
                <div className="stat-box">
                    <span style={{ fontSize: "1.2rem" }}>⚠️ Observability</span>
                    <div className="stat-val" style={{ color: (stats?.observability?.logged_errors_count > 0) ? "#ef4444" : "#10b981" }}>
                        {stats ? stats.observability.logged_errors_count : "—"}
                    </div>
                    <div className="stat-desc">{stats ? `Log: ${stats.observability.log_file_size_kb.toFixed(2)} KB` : "—"}</div>
                </div>
            </div>

            <div className="sched-grid">
                {/* LEFT COLUMN: ACTIVE SCHEDULES LIST */}
                <div style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
                    <div className="sched-card">
                        <h3 className="sched-card-title">⏰ Active Background Automatons</h3>
                        {schedules.length === 0 ? (
                            <p style={{ color: "#888", fontSize: "0.9rem", textAlign: "center", padding: "20px 0" }}>No background schedules active.</p>
                        ) : (
                            <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                                {schedules.map((s) => (
                                    <div key={s.id} style={{
                                        background: "rgba(255, 255, 255, 0.02)",
                                        border: "1px solid rgba(255, 255, 255, 0.05)",
                                        borderRadius: "8px",
                                        padding: "16px",
                                        display: "flex",
                                        justifyContent: "space-between",
                                        alignItems: "center"
                                    }}>
                                        <div>
                                            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                                                <span style={{ fontWeight: "700", fontSize: "0.95rem" }}>{s.name}</span>
                                                <span className={`trigger-badge trigger-${s.trigger_type.toLowerCase()}`}>{s.trigger_type}</span>
                                            </div>
                                            <div style={{ fontSize: "0.8rem", color: "#aaa", marginTop: "4px" }}>
                                                Expression: <code style={{ color: "#a5b4fc" }}>{s.expression}</code> · Action: <code style={{ color: "#f472b6" }}>{s.intent}</code>
                                            </div>
                                            {s.params && s.params !== "{}" && (
                                                <div style={{ fontSize: "0.75rem", color: "#888", marginTop: "4px", fontFamily: "monospace" }}>
                                                    Params: {s.params}
                                                </div>
                                            )}
                                        </div>
                                        <div style={{ display: "flex", gap: "8px" }}>
                                            <button className="action-icon-btn" onClick={() => handleTriggerSchedule(s.id)}>⚡ Run Now</button>
                                            <button className="action-icon-btn btn-delete" onClick={() => handleDeleteSchedule(s.id)}>🗑️ Delete</button>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </div>

                {/* RIGHT COLUMN: CREATE SCHEDULE & PRIVACY */}
                <div style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
                    {/* Add Schedule Form */}
                    <div className="sched-card">
                        <h3 className="sched-card-title">➕ Add New Schedule</h3>
                        <form onSubmit={handleCreateSchedule} style={{ display: "grid", gap: "10px" }}>
                            <div className="form-group">
                                <label className="form-label">Job Name</label>
                                <input
                                    type="text"
                                    placeholder="e.g. morning_brief_check"
                                    className="form-input"
                                    value={jobName}
                                    onChange={(e) => setJobName(e.target.value)}
                                    required
                                />
                            </div>
                            <div className="form-group" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" }}>
                                <div>
                                    <label className="form-label">Trigger Type</label>
                                    <select
                                        className="form-input"
                                        style={{ background: "#222" }}
                                        value={triggerType}
                                        onChange={(e) => {
                                            setTriggerType(e.target.value)
                                            setExpression(e.target.value === "interval" ? "60" : "0 9 * * *")
                                        }}
                                    >
                                        <option value="interval">Interval</option>
                                        <option value="cron">Cron</option>
                                    </select>
                                </div>
                                <div>
                                    <label className="form-label">Expression</label>
                                    <input
                                        type="text"
                                        placeholder={triggerType === "interval" ? "seconds (e.g. 60)" : "cron (e.g. 0 9 * * *)"}
                                        className="form-input"
                                        value={expression}
                                        onChange={(e) => setExpression(e.target.value)}
                                        required
                                    />
                                </div>
                            </div>
                            <div className="form-group">
                                <label className="form-label">Automation Intent</label>
                                <select
                                    className="form-input"
                                    style={{ background: "#222" }}
                                    value={intent}
                                    onChange={(e) => setIntent(e.target.value)}
                                >
                                    <option value="send_notification">Send Notification</option>
                                    <option value="general_chat">Trigger Proactive Chat</option>
                                    <option value="web_search">Run Scheduled Web Search</option>
                                    <option value="system_stats">Check System Health</option>
                                </select>
                            </div>
                            <div className="form-group">
                                <label className="form-label">Parameters (JSON)</label>
                                <textarea
                                    className="form-input"
                                    style={{ fontFamily: "monospace", fontSize: "0.8rem", minHeight: "50px" }}
                                    value={paramsStr}
                                    onChange={(e) => setParamsStr(e.target.value)}
                                />
                            </div>
                            <button type="submit" className="submit-btn" disabled={formSubmitting || !jobName.trim()}>
                                {formSubmitting ? "Scheduling..." : "Schedule Job"}
                            </button>
                        </form>
                    </div>

                    {/* Privacy & Retention Panel */}
                    <div className="sched-card">
                        <h3 className="sched-card-title">🛡️ Privacy & Retention Policy</h3>
                        <form onSubmit={handleSavePrivacy} style={{ display: "grid", gap: "16px" }}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                <div>
                                    <span style={{ fontWeight: "600", fontSize: "0.9rem", display: "block" }}>Local Privacy Mode</span>
                                    <span style={{ fontSize: "0.75rem", color: "#888" }}>Force local Ollama offline execution</span>
                                </div>
                                <input
                                    type="checkbox"
                                    style={{ width: "20px", height: "20px", cursor: "pointer" }}
                                    checked={privacy.privacy_mode}
                                    onChange={(e) => setPrivacy({ ...privacy, privacy_mode: e.target.checked })}
                                />
                            </div>
                            <div className="form-group">
                                <label className="form-label">Chat Data Retention (Days)</label>
                                <input
                                    type="number"
                                    className="form-input"
                                    min="1"
                                    max="365"
                                    value={privacy.retention_days}
                                    onChange={(e) => setPrivacy({ ...privacy, retention_days: parseInt(e.target.value) || 30 })}
                                />
                                <span style={{ fontSize: "0.7rem", color: "#888" }}>Prunes database messages older than this limit on save</span>
                            </div>
                            <button type="submit" className="submit-btn">
                                Save Policy
                            </button>
                        </form>
                    </div>
                </div>
            </div>
        </div>
    )
}
