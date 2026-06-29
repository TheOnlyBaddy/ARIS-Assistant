// src/components/AgentsDashboard.jsx
import { useState, useEffect, useRef } from "react"
import axios from "react"

const API_BASE = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
    ? "http://localhost:8000"
    : `http://${window.location.hostname}:8000`

export default function AgentsDashboard({ visible }) {
    const [tasks, setTasks] = useState([])
    const [newGoal, setNewGoal] = useState("")
    const [multiGoal, setMultiGoal] = useState("")
    const [multiResult, setMultiResult] = useState(null)
    const [multiRunning, setMultiRunning] = useState(false)
    const [tools, setTools] = useState([])
    const [toolName, setToolName] = useState("")
    const [toolDesc, setToolDesc] = useState("")
    const [learningSummary, setLearningSummary] = useState(null)
    const [predictions, setPredictions] = useState([])
    const [taskLoading, setTaskLoading] = useState(false)
    const [toolCreating, setToolCreating] = useState(false)
    const [learningTriggering, setLearningTriggering] = useState(false)
    const [expandedTaskId, setExpandedTaskId] = useState(null)

    const fetchTasks = async () => {
        try {
            const apiKey = localStorage.getItem("aris_api_key") || ""
            const r = await axios.get(`${API_BASE}/agents/tasks`, {
                headers: { "X-API-Key": apiKey }
            })
            setTasks(r.data.tasks || [])
        } catch (e) {
            console.error("Error fetching tasks:", e)
        }
    }

    const fetchTools = async () => {
        try {
            const apiKey = localStorage.getItem("aris_api_key") || ""
            const r = await axios.get(`${API_BASE}/agents/tools`, {
                headers: { "X-API-Key": apiKey }
            })
            setTools(r.data.tools || [])
        } catch (e) {
            console.error("Error fetching tools:", e)
        }
    }

    const fetchLearningAndPredictions = async () => {
        try {
            const apiKey = localStorage.getItem("aris_api_key") || ""
            const [learningRes, predictRes] = await Promise.all([
                axios.get(`${API_BASE}/agents/learning/summary`, { headers: { "X-API-Key": apiKey } }),
                axios.get(`${API_BASE}/agents/predict`, { headers: { "X-API-Key": apiKey } })
            ])
            setLearningSummary(learningRes.data)
            setPredictions(predictRes.data.suggestions || [])
        } catch (e) {
            console.error("Error fetching learning/predictions:", e)
        }
    }

    const handleCreateTask = async (e) => {
        e.preventDefault()
        if (!newGoal.trim()) return
        setTaskLoading(true)
        try {
            const apiKey = localStorage.getItem("aris_api_key") || ""
            const r = await axios.post(`${API_BASE}/agents/task`, 
                { goal: newGoal },
                { headers: { "X-API-Key": apiKey, "Content-Type": "application/json" } }
            )
            setNewGoal("")
            setExpandedTaskId(r.data.task_id)
            fetchTasks()
        } catch (err) {
            alert("Failed to spawn task: " + (err.response?.data?.detail || err.message))
        } finally {
            setTaskLoading(false)
        }
    }

    const handleRunMultiAgent = async (e) => {
        e.preventDefault()
        if (!multiGoal.trim()) return
        setMultiRunning(true)
        setMultiResult(null)
        try {
            const apiKey = localStorage.getItem("aris_api_key") || ""
            const r = await axios.post(`${API_BASE}/agents/multi`,
                { goal: multiGoal },
                { headers: { "X-API-Key": apiKey, "Content-Type": "application/json" } }
            )
            setMultiResult(r.data)
        } catch (err) {
            alert("Multi-agent run failed: " + (err.response?.data?.detail || err.message))
        } finally {
            setMultiRunning(false)
        }
    }

    const handleCreateTool = async (e) => {
        e.preventDefault()
        if (!toolName.trim() || !toolDesc.trim()) return
        setToolCreating(true)
        try {
            const apiKey = localStorage.getItem("aris_api_key") || ""
            await axios.post(`${API_BASE}/agents/create-tool`,
                { tool_name: toolName, task_description: toolDesc, test_params: {} },
                { headers: { "X-API-Key": apiKey, "Content-Type": "application/json" } }
            )
            setToolName("")
            setToolDesc("")
            fetchTools()
            alert("Tool created and verified successfully!")
        } catch (err) {
            alert("Tool creation failed: " + (err.response?.data?.detail || err.message))
        } finally {
            setToolCreating(false)
        }
    }

    const handleTriggerLearning = async () => {
        setLearningTriggering(true)
        try {
            const apiKey = localStorage.getItem("aris_api_key") || ""
            const r = await axios.post(`${API_BASE}/agents/learning/trigger`, {}, {
                headers: { "X-API-Key": apiKey }
            })
            alert(r.data.message || "Prompt updated successfully based on user correction rules!")
            fetchLearningAndPredictions()
        } catch (err) {
            alert("Self-learning consolidation failed: " + (err.response?.data?.detail || err.message))
        } finally {
            setLearningTriggering(false)
        }
    }

    useEffect(() => {
        if (!visible) return
        fetchTasks()
        fetchTools()
        fetchLearningAndPredictions()

        const t = setInterval(fetchTasks, 5000)
        return () => clearInterval(t)
    }, [visible])

    if (!visible) return null

    return (
        <div className="agents-dashboard" style={{
            color: "#fff",
            fontFamily: "inherit",
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: "24px",
            padding: "24px",
            background: "rgba(10, 10, 15, 0.2)",
            borderRadius: "16px",
            backdropFilter: "blur(20px)",
            border: "1px solid rgba(255, 255, 255, 0.05)"
        }}>
            <style>{`
                .agents-card {
                    background: rgba(255, 255, 255, 0.03);
                    border: 1px solid rgba(255, 255, 255, 0.06);
                    border-radius: 12px;
                    padding: 20px;
                    margin-bottom: 24px;
                    backdrop-filter: blur(10px);
                }
                .agents-card-title {
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
                .status-badge {
                    padding: 3px 8px;
                    border-radius: 20px;
                    font-size: 0.75rem;
                    font-weight: 600;
                    text-transform: uppercase;
                }
                .status-pending { background: rgba(245, 158, 11, 0.15); color: #f59e0b; border: 1px solid rgba(245, 158, 11, 0.3); }
                .status-running { background: rgba(99, 102, 241, 0.15); color: #6366f1; border: 1px solid rgba(99, 102, 241, 0.3); }
                .status-done { background: rgba(16, 185, 129, 0.15); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.3); }
                .status-failed { background: rgba(239, 68, 68, 0.15); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.3); }
                
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
                .task-item-row {
                    padding: 10px;
                    border-bottom: 1px solid rgba(255, 255, 255, 0.03);
                    cursor: pointer;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                }
                .task-item-row:hover {
                    background: rgba(255, 255, 255, 0.02);
                }
                .subtask-list {
                    margin-top: 10px;
                    background: rgba(0, 0, 0, 0.15);
                    border-radius: 6px;
                    padding: 12px;
                }
                .subtask-item {
                    display: flex;
                    align-items: flex-start;
                    gap: 10px;
                    font-size: 0.85rem;
                    padding: 6px 0;
                    border-bottom: 1px dashed rgba(255, 255, 255, 0.05);
                }
                .subtask-item:last-child {
                    border-bottom: none;
                }
                .subtask-dot {
                    width: 8px;
                    height: 8px;
                    border-radius: 50%;
                    margin-top: 5px;
                }
                .dot-pending { background: #f59e0b; box-shadow: 0 0 6px #f59e0b; }
                .dot-running { background: #6366f1; box-shadow: 0 0 6px #6366f1; }
                .dot-done { background: #10b981; box-shadow: 0 0 6px #10b981; }
                .dot-failed { background: #ef4444; box-shadow: 0 0 6px #ef4444; }
            `}</style>

            {/* LEFT COLUMN: TASK ORCHESTRATION & PERSISTENCE */}
            <div className="left-column">
                {/* 1. Spawning Tasks Card */}
                <div className="agents-card">
                    <h3 className="agents-card-title">🤖 Task Orchestrator</h3>
                    <form onSubmit={handleCreateTask} style={{ display: "flex", gap: "10px" }}>
                        <input
                            type="text"
                            placeholder="Enter a complex goal (e.g. Gather system metrics & write report)"
                            className="form-input"
                            style={{ flex: 1 }}
                            value={newGoal}
                            onChange={(e) => setNewGoal(e.target.value)}
                        />
                        <button type="submit" className="submit-btn" disabled={taskLoading || !newGoal.trim()}>
                            {taskLoading ? "Spawning..." : "Spawn Plan"}
                        </button>
                    </form>
                </div>

                {/* 2. Tasks Persistence / Active Status Card */}
                <div className="agents-card">
                    <h3 className="agents-card-title">📋 Active Agent Plans</h3>
                    {tasks.length === 0 ? (
                        <p style={{ color: "#888", fontSize: "0.9rem", textAlign: "center" }}>No active plans in SQLite.</p>
                    ) : (
                        <div style={{ maxHeight: "350px", overflowY: "auto", borderRadius: "8px" }}>
                            {tasks.map((t) => (
                                <div key={t.id} style={{ borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
                                    <div className="task-item-row" onClick={() => setExpandedTaskId(expandedTaskId === t.id ? null : t.id)}>
                                        <div style={{ flex: 1 }}>
                                            <span style={{ fontSize: "0.9rem", fontWeight: "600" }}>{t.goal}</span>
                                            <div style={{ fontSize: "0.75rem", color: "#888", marginTop: "3px" }}>
                                                ID: #{t.id} · {t.created_at}
                                            </div>
                                        </div>
                                        <span className={`status-badge status-${t.status.toLowerCase()}`}>{t.status}</span>
                                    </div>
                                    {expandedTaskId === t.id && (
                                        <div className="subtask-list">
                                            <h4 style={{ margin: "0 0 8px 0", fontSize: "0.85rem", color: "#6366f1" }}>Decomposed Steps:</h4>
                                            {t.subtasks && t.subtasks.length > 0 ? (
                                                t.subtasks.map((st, i) => (
                                                    <div key={i} className="subtask-item">
                                                        <div className={`subtask-dot dot-${st.status.toLowerCase()}`} />
                                                        <div style={{ flex: 1 }}>
                                                            <div style={{ fontWeight: "600", fontSize: "0.8rem" }}>Step {st.step}: {st.description}</div>
                                                            {st.result && <div style={{ fontSize: "0.75rem", color: "#aaa", background: "rgba(0,0,0,0.2)", padding: "4px 8px", borderRadius: "4px", marginTop: "4px", whiteSpace: "pre-wrap" }}>{st.result}</div>}
                                                            {st.error && <div style={{ fontSize: "0.75rem", color: "#ef4444", marginTop: "4px" }}>Error: {st.error}</div>}
                                                        </div>
                                                        <span style={{ fontSize: "0.7rem", color: "#888" }}>{st.status}</span>
                                                    </div>
                                                ))
                                            ) : (
                                                <p style={{ color: "#777", fontSize: "0.8rem", margin: 0 }}>Generating plan steps...</p>
                                            )}
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    )}
                </div>

                {/* 3. Learning & Predictions Sidebar */}
                <div className="agents-card">
                    <h3 className="agents-card-title">💡 Proactive Self-Learning</h3>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
                        <div>
                            <h4 style={{ margin: "0 0 8px 0", fontSize: "0.85rem", color: "#10b981" }}>Learned Rules:</h4>
                            {learningSummary?.rules ? (
                                <ul style={{ margin: 0, paddingLeft: "16px", fontSize: "0.8rem", color: "#ddd" }}>
                                    {learningSummary.rules.split("\n").filter(l => l.trim()).map((rule, idx) => (
                                        <li key={idx} style={{ marginBottom: "6px" }}>{rule.replace(/^[•\-\*]\s*/, "")}</li>
                                    ))}
                                </ul>
                            ) : (
                                <p style={{ color: "#777", fontSize: "0.8rem", margin: 0 }}>No corrections logged yet.</p>
                            )}
                            <button className="submit-btn" style={{ marginTop: "12px", width: "100%", fontSize: "0.8rem", padding: "6px 12px" }} onClick={handleTriggerLearning} disabled={learningTriggering}>
                                {learningTriggering ? "Consolidating..." : "Consolidate Rules"}
                            </button>
                        </div>
                        <div>
                            <h4 style={{ margin: "0 0 8px 0", fontSize: "0.85rem", color: "#06b6d4" }}>Proactive Suggestions:</h4>
                            {predictions.length > 0 ? (
                                <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                                    {predictions.slice(0, 3).map((pred, i) => (
                                        <div key={i} style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.05)", borderRadius: "6px", padding: "8px", fontSize: "0.75rem", color: "#bbb" }}>
                                            💡 {pred}
                                        </div>
                                    ))}
                                </div>
                            ) : (
                                <p style={{ color: "#777", fontSize: "0.8rem", margin: 0 }}>No suggestions available.</p>
                            )}
                        </div>
                    </div>
                </div>
            </div>

            {/* RIGHT COLUMN: MULTI-AGENT & SELF-TOOL CREATOR */}
            <div className="right-column">
                {/* 1. LangGraph Multi-Agent Workflow */}
                <div className="agents-card">
                    <h3 className="agents-card-title">🤝 Multi-Agent Collaboration</h3>
                    <form onSubmit={handleRunMultiAgent} style={{ display: "flex", gap: "10px", marginBottom: "16px" }}>
                        <input
                            type="text"
                            placeholder="Enter a task (e.g. Write a python script to analyze CPU usage)"
                            className="form-input"
                            style={{ flex: 1 }}
                            value={multiGoal}
                            onChange={(e) => setMultiGoal(e.target.value)}
                        />
                        <button type="submit" className="submit-btn" disabled={multiRunning || !multiGoal.trim()}>
                            {multiRunning ? "Collaborating..." : "Launch Team"}
                        </button>
                    </form>

                    {multiRunning && (
                        <div style={{ padding: "16px", background: "rgba(0,0,0,0.15)", borderRadius: "8px", textAlign: "center" }}>
                            <div className="status-badge status-running" style={{ display: "inline-block", marginBottom: "8px" }}>LangGraph Supervisor Active</div>
                            <p style={{ fontSize: "0.85rem", color: "#aaa", margin: 0 }}>Researcher, Writer, Executor, and Verifier collaborating...</p>
                        </div>
                    )}

                    {multiResult && (
                        <div style={{ background: "rgba(0,0,0,0.25)", borderRadius: "8px", padding: "12px", maxHeight: "250px", overflowY: "auto" }}>
                            <div style={{ fontSize: "0.85rem", fontWeight: "700", color: "#10b981", marginBottom: "8px" }}>Final Output:</div>
                            <pre style={{ margin: 0, fontSize: "0.8rem", color: "#ccc", whiteSpace: "pre-wrap", fontFamily: "monospace" }}>
                                {multiResult.output || JSON.stringify(multiResult, null, 2)}
                            </pre>
                        </div>
                    )}
                </div>

                {/* 2. Self-Tool Creator */}
                <div className="agents-card">
                    <h3 className="agents-card-title">🛠️ Self-Tool Generator</h3>
                    <form onSubmit={handleCreateTool} style={{ display: "grid", gap: "12px", marginBottom: "20px" }}>
                        <div className="form-group">
                            <label className="form-label">Tool Name</label>
                            <input
                                type="text"
                                placeholder="e.g. disk_wipe_temp"
                                className="form-input"
                                value={toolName}
                                onChange={(e) => setToolName(e.target.value)}
                            />
                        </div>
                        <div className="form-group">
                            <label className="form-label">Task Description</label>
                            <textarea
                                placeholder="Describe what the tool should do (Python will be written, verified, and dynamically imported into registry)"
                                className="form-input"
                                style={{ minHeight: "60px", resize: "vertical" }}
                                value={toolDesc}
                                onChange={(e) => setToolDesc(e.target.value)}
                            />
                        </div>
                        <button type="submit" className="submit-btn" disabled={toolCreating || !toolName.trim() || !toolDesc.trim()}>
                            {toolCreating ? "Synthesizing & Sandbox Verifying..." : "Synthesize Tool"}
                        </button>
                    </form>

                    <h4 style={{ margin: "0 0 10px 0", fontSize: "0.85rem", color: "#8b5cf6" }}>Registered Tools Directory:</h4>
                    {tools.length === 0 ? (
                        <p style={{ color: "#777", fontSize: "0.8rem", margin: 0 }}>No custom tools synthesized yet.</p>
                    ) : (
                        <div style={{ display: "flex", flexDirection: "column", gap: "8px", maxHeight: "200px", overflowY: "auto" }}>
                            {tools.map((tool, idx) => (
                                <div key={idx} style={{
                                    background: "rgba(255,255,255,0.02)",
                                    border: "1px solid rgba(255,255,255,0.05)",
                                    borderRadius: "8px",
                                    padding: "10px",
                                    fontSize: "0.8rem"
                                }}>
                                    <div style={{ display: "flex", justifyContent: "space-between", fontWeight: "600", color: "#fff" }}>
                                        <span>🛠️ {tool.name}</span>
                                        <span style={{ fontSize: "0.7rem", color: "#888" }}>v1.0</span>
                                    </div>
                                    <div style={{ color: "#aaa", fontSize: "0.75rem", marginTop: "4px" }}>{tool.description}</div>
                                    <div style={{ color: "#666", fontSize: "0.7rem", marginTop: "4px", fontFamily: "monospace" }}>File: {tool.script_path?.split("/").pop() || "dynamic"}</div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>
        </div>
    )
}
