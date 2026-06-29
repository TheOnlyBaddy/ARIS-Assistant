import { useState, useEffect, useRef } from 'react'
import axios from 'axios'
import './App.css'
import GoogleAuthButton from "./components/GoogleAuthButton"
import SystemDashboard from "./components/SystemDashboard"
import IntelligenceDashboard from "./components/IntelligenceDashboard"
import LifeDashboard from "./components/LifeDashboard"
import CreativeDashboard from "./components/CreativeDashboard"
import AgentsDashboard from "./components/AgentsDashboard"
import SchedulerUI from "./components/SchedulerUI"
import FinetuneDashboard from "./components/FinetuneDashboard"

const API_BASE = window.location.hostname
  ? `http://${window.location.hostname}:8000`
  : 'http://localhost:8000'

// Install Axios request interceptor to automatically inject X-API-Key header
axios.interceptors.request.use((config) => {
  const apiKey = localStorage.getItem("aris_api_key") || "your_secure_token";
  config.headers["X-API-Key"] = apiKey;
  return config;
}, (error) => {
  return Promise.reject(error);
});

// ── Typing indicator ───────────────────────────────────────────────────────────
function TypingIndicator() {
  return (
    <div className="message aris">
      <div className="avatar">A</div>
      <div className="bubble typing">
        <span /><span /><span />
      </div>
    </div>
  )
}

// ── Format text with bold/newlines ────────────────────────────────────────────
function formatText(text) {
  return text.split('\n').map((line, i, arr) => (
    <span key={i}>
      {line.split(/\*\*(.*?)\*\*/g).map((part, j) =>
        j % 2 === 1 ? <strong key={j}>{part}</strong> : part
      )}
      {i < arr.length - 1 && <br />}
    </span>
  ))
}

// ── Email card ────────────────────────────────────────────────────────────────
function EmailCard({ email }) {
  return (
    <div className="card email-card">
      <div className="card-header">
        <span className="card-icon">📧</span>
        <span className="card-title">{email.subject}</span>
      </div>
      <div className="card-meta">From: {email.from}</div>
      <div className="card-meta">Date: {email.date}</div>
      <div className="card-snippet">{email.snippet}</div>
    </div>
  )
}

// ── Event card ────────────────────────────────────────────────────────────────
function EventCard({ event }) {
  const start = event.start ? new Date(event.start).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''
  const end = event.end ? new Date(event.end).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''
  return (
    <div className="card event-card">
      <div className="card-header">
        <span className="card-icon">📅</span>
        <span className="card-title">{event.title}</span>
      </div>
      {(start || end) && <div className="card-meta">🕐 {start}{end ? ` – ${end}` : ''}</div>}
      {event.location && <div className="card-meta">📍 {event.location}</div>}
      {event.meet_link && <a className="card-link" href={event.meet_link} target="_blank" rel="noreferrer">Join Meet</a>}
    </div>
  )
}

// ── Task card ─────────────────────────────────────────────────────────────────
function TaskCard({ task }) {
  const priorityLabel = { 1: '', 2: '🟡 Medium', 3: '🟠 High', 4: '🔴 Urgent' }
  return (
    <div className="card task-card">
      <div className="card-header">
        <span className="card-icon">✅</span>
        <span className="card-title">{task.content}</span>
      </div>
      {task.due && <div className="card-meta">📆 Due: {task.due}</div>}
      {task.priority > 1 && <div className="card-meta">{priorityLabel[task.priority]}</div>}
    </div>
  )
}

// ── Briefing modal ────────────────────────────────────────────────────────────
function BriefingModal({ briefing, onClose }) {
  if (!briefing) return null
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>🌅 Morning Briefing</h2>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>
        <div className="modal-date">{briefing.date}</div>
        <div className="modal-summary">{briefing.summary}</div>
        {briefing.calendar_events?.length > 0 && (
          <div className="modal-section">
            <h3>📅 Today's Calendar</h3>
            {briefing.calendar_events.map((e, i) => <EventCard key={i} event={e} />)}
          </div>
        )}
        {briefing.tasks_today?.length > 0 && (
          <div className="modal-section">
            <h3>✅ Due Today</h3>
            {briefing.tasks_today.map((t, i) => <TaskCard key={i} task={t} />)}
          </div>
        )}
        {briefing.tasks_overdue?.length > 0 && (
          <div className="modal-section">
            <h3>⚠️ Overdue</h3>
            {briefing.tasks_overdue.map((t, i) => <TaskCard key={i} task={t} />)}
          </div>
        )}
        {briefing.emails?.length > 0 && (
          <div className="modal-section">
            <h3>📧 Recent Emails</h3>
            {briefing.emails.map((e, i) => <EmailCard key={i} email={e} />)}
          </div>
        )}
        {briefing.neglected?.length > 0 && (
          <div className="modal-section">
            <h3>👥 Reach Out</h3>
            {briefing.neglected.map((p, i) => (
              <div key={i} className="card person-card">
                <div className="card-header">
                  <span className="card-icon">👤</span>
                  <span className="card-title">{p.name}</span>
                </div>
                <div className="card-meta">{p.relationship} · Last contact: {p.last_contact || 'never'}</div>
                {p.days_since_contact && <div className="card-meta">⏱ {p.days_since_contact} days ago</div>}
              </div>
            ))}
          </div>
        )}
        {briefing.birthdays?.length > 0 && (
          <div className="modal-section">
            <h3>🎂 Upcoming Birthdays</h3>
            {briefing.birthdays.map((p, i) => (
              <div key={i} className="card birthday-card">
                <div className="card-header">
                  <span className="card-icon">🎂</span>
                  <span className="card-title">{p.name}</span>
                </div>
                <div className="card-meta">In {p.days_until_birthday} days — {p.birthday_this_year}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Single chat message ────────────────────────────────────────────────────────
function Message({ msg }) {
  const isUser = msg.role === 'user'
  return (
    <div className={`message ${isUser ? 'user' : 'aris'}`}>
      {!isUser && <div className="avatar">A</div>}
      <div className={`bubble ${isUser ? 'user-bubble' : 'aris-bubble'}`}>
        {msg.safety_status === 'blocked' && (
          <span className="safety-tag blocked">🛡 Blocked</span>
        )}
        {msg.safety_status === 'needs_confirmation' && (
          <span className="safety-tag warn">⚠️ Confirmation needed</span>
        )}
        {msg.vision_result && (
          <div className="vision-result-card">
            <div className="vision-result-header">
              {msg.vision_type === 'screen' ? '🖥️ Screen Vision' :
                msg.vision_type === 'camera' ? '📷 Camera Vision' : '📝 OCR Result'}
            </div>
            {msg.vision_image && (
              <img
                src={`${API_BASE}/vision/image?path=${encodeURIComponent(msg.vision_image)}`}
                alt="Vision capture"
                className="vision-result-img"
                onError={e => e.target.style.display = 'none'}
              />
            )}
          </div>
        )}
        <p>{formatText(msg.text)}</p>
        {(() => {
          const imgMatch = msg.text?.match(/(\/output\/images\/gen_\d+\.jpg)/);
          if (imgMatch) {
            return (
              <div style={{ marginTop: '10px', textAlign: 'center' }}>
                <img
                  src={`${API_BASE}${imgMatch[0]}`}
                  alt="Generated visual"
                  style={{ maxWidth: '100%', maxHeight: '300px', borderRadius: '6px', border: '1px solid #1e293b' }}
                />
              </div>
            )
          }
          return null;
        })()}
        {msg.model_used && msg.model_used !== 'safety-filter' && (
          <span className="meta">
            {msg.model_used} · {msg.memories_used} mem
            {msg.intent && msg.intent !== 'general_chat' && ` · ${msg.intent}`}
          </span>
        )}
        {!isUser && msg.emotion && msg.emotion !== 'neutral' && (
          <span className="emotion-tag">{msg.emotionEmoji} {msg.emotion}</span>
        )}
      </div>
      {isUser && <div className="avatar user-avatar">S</div>}
    </div>
  )
}

// ── Voice status badge ────────────────────────────────────────────────────────
function VoiceStatusBadge({ status, emotion, emotionEmoji }) {
  const statusConfig = {
    off: { label: 'Voice Off', color: '#666', pulse: false },
    loading: { label: 'Loading...', color: '#f59e0b', pulse: true },
    listening: { label: 'Listening', color: '#10b981', pulse: true },
    wake_detected: { label: 'Wake Word!', color: '#6366f1', pulse: true },
    recording: { label: 'Recording', color: '#ef4444', pulse: true },
    transcribing: { label: 'Transcribing', color: '#f59e0b', pulse: true },
    thinking: { label: 'Thinking', color: '#6366f1', pulse: true },
    speaking: { label: 'Speaking', color: '#3b82f6', pulse: true },
    error: { label: 'Error', color: '#ef4444', pulse: false },
  }
  const cfg = statusConfig[status] || statusConfig.off
  return (
    <div className="voice-status-badge" style={{ '--badge-color': cfg.color }}>
      <span className={`voice-dot ${cfg.pulse ? 'pulse' : ''}`} />
      <span className="voice-label">{cfg.label}</span>
      {emotion && emotion !== 'neutral' && (
        <span className="voice-emotion">{emotionEmoji} {emotion}</span>
      )}
    </div>
  )
}

// ── Vision result modal ───────────────────────────────────────────────────────
function VisionModal({ result, onClose }) {
  if (!result) return null
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal vision-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>
            {result.type === 'screen' ? '🖥️ Screen Vision' :
              result.type === 'camera' ? '📷 Camera Vision' : '📝 OCR Result'}
          </h2>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>
        {result.image && (
          <img src={result.image} alt="Vision capture" className="vision-modal-img" />
        )}
        <div className="vision-modal-text">{result.text}</div>
        <div className="vision-modal-meta">
          {result.resolution && <span>📐 {result.resolution}</span>}
          {result.elapsed_secs && <span>⏱ {result.elapsed_secs}s</span>}
          {result.model_used && <span>🤖 {result.model_used}</span>}
        </div>
      </div>
    </div>
  )
}

// ── Settings Panel Component ──────────────────────────────────────────────────
function SettingsPanel({ visible, apiBase }) {
  const [apiKey, setApiKey] = useState(localStorage.getItem("aris_api_key") || "your_secure_token")
  const [stats, setStats] = useState(null)
  const [privacy, setPrivacy] = useState({ privacy_mode: false, retention_days: 30 })

  const fetchSettingsAndStats = async () => {
    try {
      const token = localStorage.getItem("aris_api_key") || "your_secure_token"
      const headers = { "X-API-Key": token }
      const [statsRes, privRes] = await Promise.all([
        axios.get(`${apiBase}/admin/stats`, { headers }),
        axios.get(`${apiBase}/settings/privacy`, { headers })
      ])
      setStats(statsRes.data)
      setPrivacy(privRes.data)
    } catch (e) {
      console.error("Error fetching settings/stats:", e)
    }
  }

  useEffect(() => {
    if (!visible) return
    fetchSettingsAndStats()
  }, [visible])

  const handleSaveKey = (e) => {
    e.preventDefault()
    localStorage.setItem("aris_api_key", apiKey)
    alert("API Key saved to localStorage!")
    fetchSettingsAndStats()
  }

  const handleSavePrivacy = async (e) => {
    e.preventDefault()
    try {
      const token = localStorage.getItem("aris_api_key") || "your_secure_token"
      const headers = { "X-API-Key": token, "Content-Type": "application/json" }
      const r = await axios.post(`${apiBase}/settings/privacy`, privacy, { headers })
      alert(`Privacy policy updated! Pruned ${r.data.messages_pruned} old messages.`)
      fetchSettingsAndStats()
    } catch (err) {
      alert("Failed to save privacy settings: " + (err.response?.data?.detail || err.message))
    }
  }

  if (!visible) return null

  return (
    <div className="settings-panel" style={{
      color: "#fff",
      padding: "24px",
      background: "rgba(10, 10, 15, 0.2)",
      borderRadius: "16px",
      backdropFilter: "blur(20px)",
      border: "1px solid rgba(255, 255, 255, 0.05)",
      display: "grid",
      gridTemplateColumns: "1fr 1fr",
      gap: "24px"
    }}>
      <style>{`
        .settings-card {
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid rgba(255, 255, 255, 0.06);
          border-radius: 12px;
          padding: 20px;
          backdrop-filter: blur(10px);
        }
        .settings-title {
          font-size: 1.1rem;
          font-weight: 700;
          margin-top: 0;
          margin-bottom: 16px;
          display: flex;
          align-items: center;
          gap: 8px;
          border-bottom: 1px solid rgba(255, 255, 255, 0.08);
          padding-bottom: 10px;
        }
        .form-group {
          margin-bottom: 12px;
          display: flex;
          flex-direction: column;
          gap: 6px;
        }
        .form-label {
          font-size: 0.8rem;
          color: #aaa;
        }
        .form-input {
          background: rgba(255, 255, 255, 0.05);
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 6px;
          padding: 8px 12px;
          color: #fff;
          font-size: 0.9rem;
          width: 100%;
          box-sizing: border-box;
          outline: none;
        }
        .form-input:focus {
          border-color: #6366f1;
        }
        .save-btn {
          background: linear-gradient(135deg, #6366f1, #8b5cf6);
          color: #fff;
          border: none;
          border-radius: 6px;
          padding: 10px 16px;
          font-weight: 600;
          cursor: pointer;
          transition: opacity 0.3s;
        }
        .save-btn:hover {
          opacity: 0.9;
        }
        .stats-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 12px;
        }
        .stat-item {
          background: rgba(0, 0, 0, 0.2);
          padding: 12px;
          border-radius: 6px;
          text-align: center;
        }
        .stat-lbl {
          font-size: 0.75rem;
          color: #888;
        }
        .stat-val {
          font-size: 1.25rem;
          font-weight: 700;
          color: #6366f1;
          margin-top: 4px;
        }
      `}</style>
      
      {/* Left settings column */}
      <div style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
        <div className="settings-card">
          <h3 className="settings-title">🔑 Authentication & API Security</h3>
          <form onSubmit={handleSaveKey} style={{ display: "grid", gap: "12px" }}>
            <div className="form-group">
              <label className="form-label">Client API Key (X-API-Key Header)</label>
              <input
                type="password"
                className="form-input"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
              />
              <span style={{ fontSize: "0.7rem", color: "#888" }}>
                Default: "your_secure_token". Ensure this matches the backend API_KEY env var.
              </span>
            </div>
            <button type="submit" className="save-btn">Save Key</button>
          </form>
        </div>

        <div className="settings-card">
          <h3 className="settings-title">🛡️ Privacy & Containment Policy</h3>
          <form onSubmit={handleSavePrivacy} style={{ display: "grid", gap: "12px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <span style={{ fontWeight: "600", fontSize: "0.9rem", display: "block" }}>Local Offline Privacy Mode</span>
                <span style={{ fontSize: "0.75rem", color: "#888" }}>Blocks external APIs & forces local Ollama</span>
              </div>
              <input
                type="checkbox"
                style={{ width: "18px", height: "18px", cursor: "pointer" }}
                checked={privacy.privacy_mode}
                onChange={(e) => setPrivacy({ ...privacy, privacy_mode: e.target.checked })}
              />
            </div>
            <div className="form-group">
              <label className="form-label">Message Retention Limit (Days)</label>
              <input
                type="number"
                className="form-input"
                min="1"
                max="365"
                value={privacy.retention_days}
                onChange={(e) => setPrivacy({ ...privacy, retention_days: parseInt(e.target.value) || 30 })}
              />
            </div>
            <button type="submit" className="save-btn">Update Policy</button>
          </form>
        </div>
      </div>

      {/* Right admin statistics panel column */}
      <div className="settings-card" style={{ display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
        <div>
          <h3 className="settings-title">📊 Admin & Observability Panel</h3>
          {stats ? (
            <div className="stats-grid" style={{ marginBottom: "20px" }}>
              <div className="stat-item">
                <div className="stat-lbl">System Uptime</div>
                <div className="stat-val" style={{ color: "#10b981" }}>Active</div>
              </div>
              <div className="stat-item">
                <div className="stat-lbl">SQLite Database Size</div>
                <div className="stat-val">{stats.database.db_size_kb.toFixed(1)} KB</div>
              </div>
              <div className="stat-item">
                <div className="stat-lbl">Active Chat Sessions</div>
                <div className="stat-val">{stats.database.total_active_sessions}</div>
              </div>
              <div className="stat-item">
                <div className="stat-lbl">Synthesized Custom Tools</div>
                <div className="stat-val" style={{ color: "#8b5cf6" }}>{stats.agents.registered_tools_count}</div>
              </div>
              <div className="stat-item">
                <div className="stat-lbl">Logged Errors Count</div>
                <div className="stat-val" style={{ color: stats.observability.logged_errors_count > 0 ? "#ef4444" : "#10b981" }}>
                  {stats.observability.logged_errors_count}
                </div>
              </div>
              <div className="stat-item">
                <div className="stat-lbl">Logs File Size</div>
                <div className="stat-val">{stats.observability.log_file_size_kb.toFixed(2)} KB</div>
              </div>
            </div>
          ) : (
            <p style={{ color: "#888", fontSize: "0.85rem", textAlign: "center" }}>Fetching statistics from backend...</p>
          )}
        </div>
        <div style={{ background: "rgba(0,0,0,0.15)", borderRadius: "8px", padding: "12px", fontSize: "0.75rem", color: "#aaa" }}>
          <strong>System Status Summary:</strong>
          <ul style={{ margin: "6px 0 0 0", paddingLeft: "16px" }}>
            <li>Uptime is logged dynamically since application boot.</li>
            <li>Error counts represent non-fatal anomalies detected in logs.</li>
            <li>Custom tools are verified and compiled in sandboxed processes.</li>
          </ul>
        </div>
      </div>
    </div>
  )
}

const formatModelName = (modelId) => {
  if (!modelId) return '';
  const mapping = {
    'gemini-3.5-flash': 'Gemini 3.5 Flash',
    'gemini-2.5-flash': 'Gemini 2.5 Flash',
    'gemini-1.5-flash': 'Gemini 1.5 Flash',
    'gemini-1.5-pro': 'Gemini 1.5 Pro',
    'gemini-2.5-pro': 'Gemini 2.5 Pro',
    'gemini-2.0-flash-exp': 'Gemini 2.0 Flash Exp',
  };
  if (mapping[modelId]) return mapping[modelId];
  return modelId.split('-').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
};

// ── Main App ──────────────────────────────────────────────────────────────────
export default function App() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [isTyping, setIsTyping] = useState(false)
  const [sessionId, setSessionId] = useState('session-' + Date.now())
  const [profile, setProfile] = useState(null)
  const [status, setStatus] = useState('connecting')
  const [confirmed, setConfirmed] = useState(false)
  const [briefing, setBriefing] = useState(null)
  const [briefingOpen, setBriefingOpen] = useState(false)
  const [briefingLoading, setBriefingLoading] = useState(false)
  const [googleConnected, setGoogleConnected] = useState(false)
  const [ollamaStatus, setOllamaStatus] = useState(null) // null=loading, {connected, models}
  const [activeTab, setActiveTab] = useState("chat") // "chat" | "system"

  // Voice & Vision state
  const [voiceOn, setVoiceOn] = useState(false)
  const [voiceStatus, setVoiceStatus] = useState('off')
  const [voiceEmotion, setVoiceEmotion] = useState('neutral')
  const [voiceEmoji, setVoiceEmoji] = useState('😐')
  const [lastHeard, setLastHeard] = useState('')
  const [visionResult, setVisionResult] = useState(null)
  const [visionLoading, setVisionLoading] = useState(null)
  const voicePollRef = useRef(null)

  const bottomRef = useRef(null)
  const inputRef = useRef(null)

  // ── Load profile, health, auth status on mount ────────────────────────────
  useEffect(() => {
    axios.get(`${API_BASE}/health`)
      .then(() => {
        setStatus('online')
        return axios.get(`${API_BASE}/profile`)
      })
      .then(res => {
        setProfile(res.data)
        setMessages([{
          id: Date.now(),
          role: 'aris',
          text: `Hello ${res.data.preferred_name || 'there'}! I'm ARIS, your personal AI assistant. How can I help you today?`,
          model_used: null,
          memories_used: 0,
          safety_status: 'ok'
        }])
        // ✅ Use new /auth/google/status endpoint
        return axios.get(`${API_BASE}/auth/google/status`)
      })
      .then(res => {
        setGoogleConnected(res.data.connected)
      })
      .then(() => {
        return axios.get(`${API_BASE}/control/system/ollama`)
          .then(res => setOllamaStatus(res.data))
          .catch(() => setOllamaStatus({ ollama: { connected: false, models: [], count: 0 }, gemini: { connected: false } }))
      })
      .catch(() => setStatus('offline'))
  }, [])

  // ── Periodic backend health check (Heartbeat) ──────────────────────────────
  useEffect(() => {
    const intervalTime = status === 'offline' ? 3000 : 30000 // 3s when offline, 30s when online

    const pollInterval = setInterval(() => {
      axios.get(`${API_BASE}/health`)
        .then(() => {
          setStatus(prev => {
            if (prev === 'offline') {
              clearInterval(pollInterval)
              window.location.reload()
            }
            return 'online'
          })
        })
        .catch(() => {
          setStatus('offline')
        })
    }, intervalTime)

    return () => clearInterval(pollInterval)
  }, [status])

  // ✅ Callback: re-check Google status when auth button reports connected
  const handleGoogleAuthChange = (connected) => {
    setGoogleConnected(connected)
  }

  // Derived integrations list from googleConnected state
  const integrations = [
    { name: 'Gmail', icon: '📧', connected: googleConnected },
    { name: 'Calendar', icon: '📅', connected: googleConnected },
    { name: 'Todoist', icon: '✅', connected: true },
  ]

  // ── Auto-scroll ───────────────────────────────────────────────────────────
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isTyping])

  // ── Voice pipeline polling ────────────────────────────────────────────────
  useEffect(() => {
    if (!voiceOn) {
      clearInterval(voicePollRef.current)
      setVoiceStatus('off')
      return
    }

    let prevHeard = ''
    let prevReply = ''

    voicePollRef.current = setInterval(async () => {
      try {
        const res = await axios.get(`${API_BASE}/voice/status`)
        const d = res.data

        setVoiceStatus(d.status || 'listening')
        setVoiceEmotion(d.emotion || 'neutral')
        setVoiceEmoji(d.emotion_emoji || '😐')

        if (d.last_heard && d.last_heard !== prevHeard && d.status === 'thinking') {
          prevHeard = d.last_heard
          setLastHeard(d.last_heard)
          setMessages(prev => [...prev, {
            id: Date.now(), role: 'user',
            text: `🎙️ ${d.last_heard}`,
            safety_status: 'ok', fromVoice: true
          }])
        }

        if (d.last_reply && d.last_reply !== prevReply && d.status === 'speaking') {
          prevReply = d.last_reply
          setMessages(prev => [...prev, {
            id: Date.now() + 1, role: 'aris',
            text: d.last_reply,
            model_used: 'voice', memories_used: 0,
            safety_status: 'ok',
            emotion: d.emotion, emotionEmoji: d.emotion_emoji,
            fromVoice: true
          }])
        }
      } catch {
        // ignore poll errors
      }
    }, 1000)

    return () => clearInterval(voicePollRef.current)
  }, [voiceOn])

  // ── Toggle voice pipeline ─────────────────────────────────────────────────
  const toggleVoice = async () => {
    try {
      if (!voiceOn) {
        await axios.post(`${API_BASE}/voice/start`)
        setVoiceOn(true)
        setVoiceStatus('loading')
      } else {
        await axios.post(`${API_BASE}/voice/stop`)
        setVoiceOn(false)
        setVoiceStatus('off')
        setLastHeard('')
      }
    } catch {
      alert('Voice pipeline error. Make sure FastAPI is running.')
    }
  }

  // ── Vision actions ────────────────────────────────────────────────────────
  const runVision = async (type) => {
    setVisionLoading(type)
    try {
      let res, text, image

      if (type === 'screen') {
        res = await axios.get(`${API_BASE}/vision/screen`)
        text = res.data.description
        setMessages(prev => [...prev, {
          id: Date.now(), role: 'aris',
          text: `🖥️ Screen: ${text}`,
          model_used: res.data.model_used, memories_used: 0, safety_status: 'ok',
          vision_result: true, vision_type: 'screen', vision_image: res.data.screenshot
        }])
      } else if (type === 'camera') {
        res = await axios.get(`${API_BASE}/vision/camera`)
        text = res.data.description
        setMessages(prev => [...prev, {
          id: Date.now(), role: 'aris',
          text: `📷 Camera: ${text}`,
          model_used: res.data.model_used, memories_used: 0, safety_status: 'ok',
          vision_result: true, vision_type: 'camera', vision_image: res.data.image_path
        }])
      } else if (type === 'ocr') {
        res = await axios.get(`${API_BASE}/vision/ocr?source=screen&mode=summarize`)
        text = res.data.text
        setMessages(prev => [...prev, {
          id: Date.now(), role: 'aris',
          text: `📝 OCR: ${text}`,
          model_used: res.data.model_used, memories_used: 0, safety_status: 'ok',
          vision_result: true, vision_type: 'ocr'
        }])
      }

      setVisionResult({
        type, text, image,
        resolution: res.data.resolution,
        elapsed_secs: res.data.elapsed_secs,
        model_used: res.data.model_used,
      })
    } catch (err) {
      alert(`Vision error: ${err.response?.data?.detail || err.message}`)
    } finally {
      setVisionLoading(null)
    }
  }

  // ── Send message ──────────────────────────────────────────────────────────
  const sendMessage = async (overrideText = null, overrideConfirmed = false) => {
    const text = overrideText || input.trim()
    if (!text || isTyping) return

    const userMsg = { id: Date.now(), role: 'user', text, safety_status: 'ok' }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setIsTyping(true)
    setConfirmed(false)

    try {
      const res = await axios.post(`${API_BASE}/chat`, {
        message: text,
        session_id: sessionId,
        confirmed: overrideConfirmed
      })
      const d = res.data
      setMessages(prev => [...prev, {
        id: Date.now() + 1, role: 'aris',
        text: d.response,
        model_used: d.model_used,
        memories_used: d.memories_used,
        safety_status: d.safety_status,
        intent: d.intent
      }])
      if (d.safety_status === 'needs_confirmation') {
        setConfirmed(true)
        setInput(text)
      }
    } catch (err) {
      setMessages(prev => [...prev, {
        id: Date.now() + 1, role: 'aris',
        text: '⚠️ Connection error. Please check the backend is running.',
        safety_status: 'ok'
      }])
    } finally {
      setIsTyping(false)
      inputRef.current?.focus()
    }
  }

  // ── Morning briefing ──────────────────────────────────────────────────────
  const fetchBriefing = async () => {
    setBriefingLoading(true)
    try {
      const res = await axios.get(`${API_BASE}/briefing`)
      setBriefing(res.data)
      setBriefingOpen(true)
    } catch {
      alert('Failed to load briefing. Make sure the backend is running.')
    } finally {
      setBriefingLoading(false)
    }
  }

  // ── Quick actions ─────────────────────────────────────────────────────────
  const quickActions = [
    { label: '📧 Check Email', message: 'What emails do I have?' },
    { label: '📅 My Schedule', message: "What's on my calendar today?" },
    { label: '✅ My Tasks', message: 'Show me my tasks' },
    { label: '👥 Reach Out', message: "Who haven't I talked to recently?" },
  ]

  // ── New chat ──────────────────────────────────────────────────────────────
  const newChat = () => {
    const newId = 'session-' + Date.now()
    setSessionId(newId)
    setMessages([{
      id: Date.now(), role: 'aris',
      text: `New session started. How can I help you, ${profile?.preferred_name || 'there'}?`,
      model_used: null, memories_used: 0, safety_status: 'ok'
    }])
    setInput('')
    setConfirmed(false)
    inputRef.current?.focus()
  }

  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="app">

      {briefingOpen && (
        <BriefingModal briefing={briefing} onClose={() => setBriefingOpen(false)} />
      )}

      {visionResult && (
        <VisionModal result={visionResult} onClose={() => setVisionResult(null)} />
      )}

      {/* ── Sidebar ── */}
      <aside className="sidebar">
        <div className="sidebar-logo">
          <div className="logo-icon">A</div>
          <div>
            <h1>ARIS</h1>
            <p>Personal AI</p>
          </div>
        </div>

        <button className="new-chat-btn" onClick={newChat}>+ New Chat</button>

        <button
          className="briefing-btn"
          onClick={fetchBriefing}
          disabled={briefingLoading}
        >
          {briefingLoading ? '⏳ Loading...' : '🌅 Morning Briefing'}
        </button>

        <button
          className={`voice-toggle-btn ${voiceOn ? 'voice-on' : 'voice-off'}`}
          onClick={toggleVoice}
          title={voiceOn ? 'Stop voice pipeline' : 'Start voice pipeline'}
        >
          {voiceOn ? '🎙️ Voice On' : '🎙️ Voice Off'}
        </button>

        {voiceOn && (
          <div className="sidebar-voice-status">
            <VoiceStatusBadge
              status={voiceStatus}
              emotion={voiceEmotion}
              emotionEmoji={voiceEmoji}
            />
            {lastHeard && (
              <div className="last-heard">
                <span className="last-heard-label">Heard:</span>
                <span className="last-heard-text">"{lastHeard}"</span>
              </div>
            )}
          </div>
        )}

        {/* ✅ Google Auth Button — live status + connect/disconnect */}
        <div className="sidebar-section">
          <p className="sidebar-label">Google Account</p>
          <GoogleAuthButton onAuthChange={handleGoogleAuthChange} />
        </div>

        <div className="sidebar-section">
          <p className="sidebar-label">Integrations</p>
          <div className="integrations-list">
            {integrations.map(({ name, icon, connected }) => (
              <div key={name} className={`integration-item ${connected ? 'connected' : 'disconnected'}`}>
                <span>{icon} {name}</span>
                <span className="integration-status-dot">{connected ? '✓' : '✗'}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="sidebar-section">
          <p className="sidebar-label">Status</p>

          {/* Backend pill */}
          <div className={`status-dot ${status}`}>
            <span />
            {status === 'online' ? 'Backend Online' : 'Backend Offline'}
          </div>

          {/* ── Gemini block ── */}
          <div className="llm-group">
            <div className="llm-group-header">
              <span className="llm-group-icon">✦</span>
              <span className="llm-group-name">Gemini</span>
              <span className="llm-group-dot connected" />
            </div>
            <div className="llm-pills">
              {ollamaStatus?.gemini ? (
                <>
                  <span className="llm-pill gemini" title="Primary / Fallback model">
                    {ollamaStatus.gemini.model?.replace('gemini-', '').replace('-', ' ')}
                  </span>
                </>
              ) : (
                <span className="llm-pill-loading">loading…</span>
              )}
            </div>
          </div>

          {/* ── Ollama block ── */}
          <div className="llm-group">
            <div className="llm-group-header">
              <span className="llm-group-icon">🦙</span>
              <span className="llm-group-name">Ollama</span>
              <span className={`llm-group-dot ${ollamaStatus?.ollama?.connected ? 'connected' : 'disconnected'}`} />
            </div>

            {ollamaStatus === null && (
              <span className="llm-pill-loading">checking…</span>
            )}

            {ollamaStatus?.ollama?.connected === false && (
              <span className="llm-pill-offline">Offline</span>
            )}

            {ollamaStatus?.ollama?.connected && (
              <div className="llm-pills">
                {ollamaStatus.ollama.models.map(m => {
                  const name     = m.split(':')[0]
                  const isChat   = name === ollamaStatus.gemini?.chat_model?.split(':')[0]
                  const isWrite  = name === ollamaStatus.gemini?.write_model?.split(':')[0]
                  const isReason = name === ollamaStatus.gemini?.reason_model?.split(':')[0]
                  const role     = isChat ? 'chat' : isWrite ? 'write' : isReason ? 'reason' : null

                  return (
                    <span
                      key={m}
                      className={`llm-pill ollama ${role || ''}`}
                      title={
                        role === 'chat'   ? 'Used for: chat & reads' :
                        role === 'write'  ? 'Used for: emails & summaries' :
                        role === 'reason' ? 'Used for: reasoning & scheduling' :
                        name
                      }
                    >
                      {name}
                      {role && <span className="llm-pill-role">{role}</span>}
                    </span>
                  )
                })}
              </div>
            )}
          </div>
        </div>

        {profile && (
          <div className="sidebar-section">
            <p className="sidebar-label">Profile</p>
            <div className="profile-card">
              <div className="profile-avatar">{profile.preferred_name?.[0] || 'U'}</div>
              <div>
                <p className="profile-name">{profile.preferred_name}</p>
                <p className="profile-role">{profile.occupation}</p>
              </div>
            </div>
          </div>
        )}

        <div className="sidebar-section">
          <p className="sidebar-label">Session</p>
          <p className="session-id">{sessionId.slice(0, 20)}…</p>
        </div>

        <div className="sidebar-footer">
          <p>Phase 3 · Voice &amp; Vision</p>
        </div>
      </aside>

      {/* ── Chat area ── */}
      <main className="chat-area">

        <header className="chat-header">
          <div>
            <h2>ARIS</h2>
            <p>Autonomous Reasoning &amp; Intelligence System</p>
          </div>
          {voiceOn && (
            <VoiceStatusBadge
              status={voiceStatus}
              emotion={voiceEmotion}
              emotionEmoji={voiceEmoji}
            />
          )}
          <div className={`header-status ${status}`}>
            {status === 'online' ? '● Online' : '○ Offline'}
          </div>
        </header>

        {/* Tab switcher */}
        <div className="tab-bar" style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
          <button
            className={`tab-btn ${activeTab === "chat" ? "active" : ""}`}
            onClick={() => setActiveTab("chat")}
          >
            💬 Chat
          </button>
          <button
            className={`tab-btn ${activeTab === "intelligence" ? "active" : ""}`}
            onClick={() => setActiveTab("intelligence")}
          >
            💡 Intelligence
          </button>
          <button
            className={`tab-btn ${activeTab === "life" ? "active" : ""}`}
            onClick={() => setActiveTab("life")}
          >
            🏥 Life
          </button>
          <button
            className={`tab-btn ${activeTab === "creative" ? "active" : ""}`}
            onClick={() => setActiveTab("creative")}
          >
            🎨 Creative
          </button>
          <button
            className={`tab-btn ${activeTab === "agents" ? "active" : ""}`}
            onClick={() => setActiveTab("agents")}
          >
            🤖 Agents
          </button>
          <button
            className={`tab-btn ${activeTab === "scheduler" ? "active" : ""}`}
            onClick={() => setActiveTab("scheduler")}
          >
            ⏰ Scheduler
          </button>
          <button
            className={`tab-btn ${activeTab === "finetune" ? "active" : ""}`}
            onClick={() => setActiveTab("finetune")}
          >
            🎯 Fine-Tuning
          </button>
          <button
            className={`tab-btn ${activeTab === "system" ? "active" : ""}`}
            onClick={() => setActiveTab("system")}
          >
            🖥️ System
          </button>
          <button
            className={`tab-btn ${activeTab === "settings" ? "active" : ""}`}
            onClick={() => setActiveTab("settings")}
          >
            ⚙️ Settings
          </button>
        </div>

        {/* Dashboards */}
        <IntelligenceDashboard visible={activeTab === "intelligence"} apiBase={API_BASE} />
        <LifeDashboard visible={activeTab === "life"} apiBase={API_BASE} />
        <CreativeDashboard visible={activeTab === "creative"} apiBase={API_BASE} />
        <AgentsDashboard visible={activeTab === "agents"} />
        <SchedulerUI visible={activeTab === "scheduler"} />
        <FinetuneDashboard visible={activeTab === "finetune"} apiBase={API_BASE} />
        <SystemDashboard visible={activeTab === "system"} />
        <SettingsPanel visible={activeTab === "settings"} apiBase={API_BASE} />

        {/* Wrap existing chat content so it hides when system tab is open */}
        {activeTab === "chat" && (
          <>
            <div className="quick-actions">
              {quickActions.map(({ label, message }) => (
                <button
                  key={label}
                  className="quick-btn"
                  onClick={() => sendMessage(message)}
                  disabled={isTyping}
                >
                  {label}
                </button>
              ))}
            </div>

            <div className="vision-bar">
              <span className="vision-bar-label">👁️ Vision</span>
              <button
                className={`vision-btn ${visionLoading === 'screen' ? 'loading' : ''}`}
                onClick={() => runVision('screen')}
                disabled={!!visionLoading}
                title="Capture and describe your screen"
              >
                {visionLoading === 'screen' ? '⏳' : '🖥️'} See Screen
              </button>
              <button
                className={`vision-btn ${visionLoading === 'camera' ? 'loading' : ''}`}
                onClick={() => runVision('camera')}
                disabled={!!visionLoading}
                title="Capture and describe camera view"
              >
                {visionLoading === 'camera' ? '⏳' : '📷'} Use Camera
              </button>
              <button
                className={`vision-btn ${visionLoading === 'ocr' ? 'loading' : ''}`}
                onClick={() => runVision('ocr')}
                disabled={!!visionLoading}
                title="Read text from screen"
              >
                {visionLoading === 'ocr' ? '⏳' : '📝'} Scan Text
              </button>
            </div>

            <div className="messages-container">
              {messages.map(msg => <Message key={msg.id} msg={msg} />)}
              {isTyping && <TypingIndicator />}
              <div ref={bottomRef} />
            </div>

            {confirmed && (
              <div className="confirm-banner">
                <span>⚠️ This action needs confirmation.</span>
                <button onClick={() => sendMessage(null, true)} className="confirm-btn">
                  Yes, proceed
                </button>
                <button onClick={() => { setConfirmed(false); setInput('') }} className="cancel-btn">
                  Cancel
                </button>
              </div>
            )}

            <div className="input-area">
              <textarea
                ref={inputRef}
                className="input-box"
                placeholder="Message ARIS…"
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKey}
                rows={1}
              />
              <button
                className={`mic-btn ${voiceOn ? 'mic-on' : ''}`}
                onClick={toggleVoice}
                title={voiceOn ? 'Stop listening' : 'Start voice mode'}
              >
                🎙️
              </button>
              <button
                className="send-btn"
                onClick={() => sendMessage()}
                disabled={!input.trim() || isTyping}
              >
                {isTyping ? '…' : '↑'}
              </button>
            </div>
            <p className="input-hint">Enter to send · Shift+Enter for new line · 🎙️ for voice</p>
          </>
        )}
      </main>
    </div>
  )
}