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

        {/* Calendar */}
        {briefing.calendar_events?.length > 0 && (
          <div className="modal-section">
            <h3>📅 Today's Calendar</h3>
            {briefing.calendar_events.map((e, i) => <EventCard key={i} event={e} />)}
          </div>
        )}

        {/* Tasks today */}
        {briefing.tasks_today?.length > 0 && (
          <div className="modal-section">
            <h3>✅ Due Today</h3>
            {briefing.tasks_today.map((t, i) => <TaskCard key={i} task={t} />)}
          </div>
        )}

        {/* Overdue tasks */}
        {briefing.tasks_overdue?.length > 0 && (
          <div className="modal-section">
            <h3>⚠️ Overdue</h3>
            {briefing.tasks_overdue.map((t, i) => <TaskCard key={i} task={t} />)}
          </div>
        )}

        {/* Emails */}
        {briefing.emails?.length > 0 && (
          <div className="modal-section">
            <h3>📧 Recent Emails</h3>
            {briefing.emails.map((e, i) => <EmailCard key={i} email={e} />)}
          </div>
        )}

        {/* Neglected contacts */}
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

        {/* Birthdays */}
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
        <p>{formatText(msg.text)}</p>
        {msg.model_used && msg.model_used !== 'safety-filter' && (
          <span className="meta">
            {msg.model_used} · {msg.memories_used} mem
            {msg.intent && msg.intent !== 'general_chat' && ` · ${msg.intent}`}
          </span>
        )}
      </div>
      {isUser && <div className="avatar user-avatar">S</div>}
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
        // Check Google auth status
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
          <p>Phase 2 · Communication Layer</p>
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
          <button
            className="send-btn"
            onClick={() => sendMessage()}
            disabled={!input.trim() || isTyping}
          >
            {isTyping ? '…' : '↑'}
          </button>
        </div>
        <p className="input-hint">Enter to send · Shift+Enter for new line</p>
      </main>
    </div>
  )
}