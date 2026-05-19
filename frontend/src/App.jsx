import { useState, useEffect, useRef } from 'react'
import axios from 'axios'
import './App.css'

const API_BASE = 'http://localhost:8000'

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
  const end   = event.end   ? new Date(event.end).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''
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
        {/* Vision result card inside message */}
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
        {msg.model_used && msg.model_used !== 'safety-filter' && (
          <span className="meta">
            {msg.model_used} · {msg.memories_used} mem
            {msg.intent && msg.intent !== 'general_chat' && ` · ${msg.intent}`}
          </span>
        )}
        {/* Emotion tag on ARIS messages */}
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
    off          : { label: 'Voice Off',    color: '#666',   pulse: false },
    loading      : { label: 'Loading...',   color: '#f59e0b', pulse: true  },
    listening    : { label: 'Listening',    color: '#10b981', pulse: true  },
    wake_detected: { label: 'Wake Word!',   color: '#6366f1', pulse: true  },
    recording    : { label: 'Recording',    color: '#ef4444', pulse: true  },
    transcribing : { label: 'Transcribing', color: '#f59e0b', pulse: true  },
    thinking     : { label: 'Thinking',     color: '#6366f1', pulse: true  },
    speaking     : { label: 'Speaking',     color: '#3b82f6', pulse: true  },
    error        : { label: 'Error',        color: '#ef4444', pulse: false },
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

// ── Integration status bar ────────────────────────────────────────────────────
function IntegrationStatus({ integrations }) {
  return (
    <div className="integration-bar">
      {integrations.map(({ name, icon, connected }) => (
        <div key={name} className={`integration-pill ${connected ? 'connected' : 'disconnected'}`}>
          <span>{icon}</span>
          <span>{name}</span>
          <span>{connected ? '✓' : '✗'}</span>
        </div>
      ))}
    </div>
  )
}

// ── Main App ──────────────────────────────────────────────────────────────────
export default function App() {
  const [messages,    setMessages]    = useState([])
  const [input,       setInput]       = useState('')
  const [isTyping,    setIsTyping]    = useState(false)
  const [sessionId,   setSessionId]   = useState('session-' + Date.now())
  const [profile,     setProfile]     = useState(null)
  const [status,      setStatus]      = useState('connecting')
  const [confirmed,   setConfirmed]   = useState(false)
  const [briefing,    setBriefing]    = useState(null)
  const [briefingOpen,setBriefingOpen]= useState(false)
  const [briefingLoading, setBriefingLoading] = useState(false)
  const [integrations, setIntegrations] = useState([
    { name: 'Gmail',    icon: '📧', connected: false },
    { name: 'Calendar', icon: '📅', connected: false },
    { name: 'Todoist',  icon: '✅', connected: false },
  ])

  // ── NEW: Voice & Vision state ─────────────────────────────────────────────
  const [voiceOn,        setVoiceOn]        = useState(false)
  const [voiceStatus,    setVoiceStatus]    = useState('off')
  const [voiceEmotion,   setVoiceEmotion]   = useState('neutral')
  const [voiceEmoji,     setVoiceEmoji]     = useState('😐')
  const [lastHeard,      setLastHeard]      = useState('')
  const [visionResult,   setVisionResult]   = useState(null)   // modal data
  const [visionLoading,  setVisionLoading]  = useState(null)   // 'screen'|'camera'|'ocr'|null
  const voicePollRef = useRef(null)

  const bottomRef = useRef(null)
  const inputRef  = useRef(null)

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
        return axios.get(`${API_BASE}/auth/status`)
      })
      .then(res => {
        const googleConnected = res.data.google_connected
        setIntegrations([
          { name: 'Gmail',    icon: '📧', connected: googleConnected },
          { name: 'Calendar', icon: '📅', connected: googleConnected },
          { name: 'Todoist',  icon: '✅', connected: true },
        ])
      })
      .catch(() => setStatus('offline'))
  }, [])

  // ── Auto-scroll ───────────────────────────────────────────────────────────
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isTyping])

  // ── Voice pipeline polling ────────────────────────────────────────────────
  // Polls /voice/status every second when voice is on
  // Updates status badge, emotion, and shows transcriptions in chat
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
        const d   = res.data

        setVoiceStatus(d.status || 'listening')
        setVoiceEmotion(d.emotion || 'neutral')
        setVoiceEmoji(d.emotion_emoji || '😐')

        // Show what ARIS heard as a user message in chat
        if (d.last_heard && d.last_heard !== prevHeard && d.status === 'thinking') {
          prevHeard = d.last_heard
          setLastHeard(d.last_heard)
          setMessages(prev => [...prev, {
            id        : Date.now(),
            role      : 'user',
            text      : `🎙️ ${d.last_heard}`,
            safety_status: 'ok',
            fromVoice : true
          }])
        }

        // Show ARIS reply in chat when it comes back
        if (d.last_reply && d.last_reply !== prevReply && d.status === 'speaking') {
          prevReply = d.last_reply
          setMessages(prev => [...prev, {
            id          : Date.now() + 1,
            role        : 'aris',
            text        : d.last_reply,
            model_used  : 'voice',
            memories_used: 0,
            safety_status: 'ok',
            emotion     : d.emotion,
            emotionEmoji: d.emotion_emoji,
            fromVoice   : true
          }])
        }
      } catch {
        // Backend might be busy — ignore poll errors
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
        res   = await axios.get(`${API_BASE}/vision/screen`)
        text  = res.data.description
        image = null
        // Add to chat
        setMessages(prev => [...prev, {
          id: Date.now(), role: 'aris',
          text: `🖥️ Screen: ${text}`,
          model_used: res.data.model_used,
          memories_used: 0, safety_status: 'ok',
          vision_result: true, vision_type: 'screen',
          vision_image: res.data.screenshot
        }])

      } else if (type === 'camera') {
        res   = await axios.get(`${API_BASE}/vision/camera`)
        text  = res.data.description
        // Add to chat
        setMessages(prev => [...prev, {
          id: Date.now(), role: 'aris',
          text: `📷 Camera: ${text}`,
          model_used: res.data.model_used,
          memories_used: 0, safety_status: 'ok',
          vision_result: true, vision_type: 'camera',
          vision_image: res.data.image_path
        }])

      } else if (type === 'ocr') {
        res  = await axios.get(`${API_BASE}/vision/ocr?source=screen&mode=summarize`)
        text = res.data.text
        // Add to chat
        setMessages(prev => [...prev, {
          id: Date.now(), role: 'aris',
          text: `📝 OCR: ${text}`,
          model_used: res.data.model_used,
          memories_used: 0, safety_status: 'ok',
          vision_result: true, vision_type: 'ocr'
        }])
      }

      // Show result in modal
      setVisionResult({
        type,
        text,
        image,
        resolution  : res.data.resolution,
        elapsed_secs: res.data.elapsed_secs,
        model_used  : res.data.model_used,
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
        id: Date.now() + 1,
        role: 'aris',
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
        id: Date.now() + 1,
        role: 'aris',
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
    } catch (err) {
      alert('Failed to load briefing. Make sure the backend is running.')
    } finally {
      setBriefingLoading(false)
    }
  }

  // ── Quick actions ─────────────────────────────────────────────────────────
  const quickActions = [
    { label: '📧 Check Email',   message: 'What emails do I have?' },
    { label: '📅 My Schedule',   message: "What's on my calendar today?" },
    { label: '✅ My Tasks',      message: 'Show me my tasks' },
    { label: '👥 Reach Out',     message: "Who haven't I talked to recently?" },
  ]

  // ── New chat ──────────────────────────────────────────────────────────────
  const newChat = () => {
    const newId = 'session-' + Date.now()
    setSessionId(newId)
    setMessages([{
      id: Date.now(),
      role: 'aris',
      text: `New session started. How can I help you, ${profile?.preferred_name || 'there'}?`,
      model_used: null,
      memories_used: 0,
      safety_status: 'ok'
    }])
    setInput('')
    setConfirmed(false)
    inputRef.current?.focus()
  }

  // ── Key handler ───────────────────────────────────────────────────────────
  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="app">

      {/* Briefing modal */}
      {briefingOpen && (
        <BriefingModal briefing={briefing} onClose={() => setBriefingOpen(false)} />
      )}

      {/* Vision result modal */}
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

        <button className="new-chat-btn" onClick={newChat}>
          + New Chat
        </button>

        {/* Morning briefing button */}
        <button
          className="briefing-btn"
          onClick={fetchBriefing}
          disabled={briefingLoading}
        >
          {briefingLoading ? '⏳ Loading...' : '🌅 Morning Briefing'}
        </button>

        {/* ── NEW: Voice toggle in sidebar ── */}
        <button
          className={`voice-toggle-btn ${voiceOn ? 'voice-on' : 'voice-off'}`}
          onClick={toggleVoice}
          title={voiceOn ? 'Stop voice pipeline' : 'Start voice pipeline'}
        >
          {voiceOn ? '🎙️ Voice On' : '🎙️ Voice Off'}
        </button>

        {/* Voice status when on */}
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

        {/* Integration status */}
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
          <div className={`status-dot ${status}`}>
            <span />
            {status === 'online' ? 'Backend Online' : 'Backend Offline'}
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

        {/* Header */}
        <header className="chat-header">
          <div>
            <h2>ARIS</h2>
            <p>Autonomous Reasoning &amp; Intelligence System</p>
          </div>
          {/* Voice status badge in header when voice is on */}
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

        {/* Quick action buttons */}
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

        {/* ── NEW: Vision action bar ── */}
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

        {/* Messages */}
        <div className="messages-container">
          {messages.map(msg => <Message key={msg.id} msg={msg} />)}
          {isTyping && <TypingIndicator />}
          <div ref={bottomRef} />
        </div>

        {/* Confirm banner */}
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

        {/* Input area */}
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
          {/* ── NEW: Mic button next to send ── */}
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
      </main>
    </div>
  )
}