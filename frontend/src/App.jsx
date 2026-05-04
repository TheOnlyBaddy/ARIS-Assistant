import { useState, useEffect, useRef } from 'react'
import axios from 'axios'
import './App.css'

const API_BASE = 'http://localhost:8000'

// ── Typing indicator dots ──────────────────────────────────────────────────────
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

// ── Single chat message ────────────────────────────────────────────────────────
function Message({ msg }) {
  const isUser = msg.role === 'user'
  // Convert markdown-style **bold** to <strong> for display
  const formatText = (text) =>
    text.split('\n').map((line, i) => (
      <span key={i}>
        {line.split(/\*\*(.*?)\*\*/g).map((part, j) =>
          j % 2 === 1 ? <strong key={j}>{part}</strong> : part
        )}
        {i < text.split('\n').length - 1 && <br />}
      </span>
    ))

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
          <span className="meta">{msg.model_used} · {msg.memories_used} mem</span>
        )}
      </div>
      {isUser && <div className="avatar user-avatar">S</div>}
    </div>
  )
}

// ── Main App ──────────────────────────────────────────────────────────────────
export default function App() {
  const [messages,   setMessages]   = useState([])
  const [input,      setInput]      = useState('')
  const [isTyping,   setIsTyping]   = useState(false)
  const [sessionId,  setSessionId]  = useState('session-' + Date.now())
  const [profile,    setProfile]    = useState(null)
  const [status,     setStatus]     = useState('connecting')
  const [confirmed,  setConfirmed]  = useState(false)   // for destructive action confirm
  const bottomRef = useRef(null)
  const inputRef  = useRef(null)

  // ── Load profile & check health on mount ───────────────────────────────────
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
      })
      .catch(() => setStatus('offline'))
  }, [])

  // ── Auto-scroll to latest message ─────────────────────────────────────────
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isTyping])

  // ── Send message ──────────────────────────────────────────────────────────
  const sendMessage = async (overrideConfirmed = false) => {
    const text = input.trim()
    if (!text || isTyping) return

    const userMsg = {
      id: Date.now(),
      role: 'user',
      text,
      safety_status: 'ok'
    }
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
        safety_status: d.safety_status
      }])

      // If ARIS needs confirmation, show confirm button next render
      if (d.safety_status === 'needs_confirmation') {
        setConfirmed(true)
        setInput(text)   // restore the original message so user can re-send confirmed
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

  // ── New chat session ───────────────────────────────────────────────────────
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
          <p>Phase 1 · Core Brain</p>
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

        {/* Messages */}
        <div className="messages-container">
          {messages.map(msg => <Message key={msg.id} msg={msg} />)}
          {isTyping && <TypingIndicator />}
          <div ref={bottomRef} />
        </div>

        {/* Confirm banner (shows when safety needs confirmation) */}
        {confirmed && (
          <div className="confirm-banner">
            <span>⚠️ This action needs confirmation.</span>
            <button onClick={() => sendMessage(true)} className="confirm-btn">
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
            placeholder={`Message ARIS…`}
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