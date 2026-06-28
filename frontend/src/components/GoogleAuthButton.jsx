// src/components/GoogleAuthButton.jsx
import { useEffect, useState } from "react"

const API_BASE = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
  ? "http://localhost:8000"
  : `http://${window.location.hostname}:8000`

export default function GoogleAuthButton({ onAuthChange }) {
  const [connected, setConnected] = useState(null)

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    if (params.get("google_auth") === "success") {
      setConnected(true)
      onAuthChange?.(true)
      window.history.replaceState({}, "", "/")
      return
    }
    checkStatus()
  }, [])

  const checkStatus = async () => {
    try {
      const res  = await fetch(`${API_BASE}/auth/google/status`)
      const data = await res.json()
      setConnected(data.connected)
      onAuthChange?.(data.connected)
    } catch {
      setConnected(false)
      onAuthChange?.(false)
    }
  }

  const handleLogin = () => {
    window.location.href = `${API_BASE}/auth/google/login`
  }

  const handleLogout = async () => {
    try {
      await fetch(`${API_BASE}/auth/google/logout`, { method: "POST" })
    } catch {
      // even if endpoint fails, clear frontend state
    }
    setConnected(false)
    onAuthChange?.(false)
  }

  // Loading
  if (connected === null) {
    return (
      <div className="integration-item disconnected">
        <span>🔄 Checking...</span>
      </div>
    )
  }

  // Connected — show same style as Gmail/Calendar rows + disconnect button
  if (connected) {
    return (
      <div className="google-auth-connected">
        <div className="integration-item connected">
          <span><GoogleIcon /> Google</span>
          <span className="integration-status-dot">✓</span>
        </div>
        <button className="google-logout-btn" onClick={handleLogout}>
          Disconnect
        </button>
      </div>
    )
  }

  // Not connected — dark button matching sidebar style
  return (
    <button className="google-connect-btn" onClick={handleLogin}>
      <GoogleIcon />
      Connect Google
    </button>
  )
}

function GoogleIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" style={{ flexShrink: 0 }}>
      <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
      <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
      <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"/>
      <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
    </svg>
  )
}