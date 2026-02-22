import { useEffect, useMemo, useState } from 'react'

const WS_SCHEME = window.location.protocol === 'https:' ? 'wss' : 'ws'
const WS_BASE =
  import.meta.env.VITE_WS_URL || `${WS_SCHEME}://${window.location.hostname}:8000/ws/notifications/`

export default function App() {
  const [status, setStatus] = useState('connecting')
  const [messages, setMessages] = useState([])

  const wsUrl = useMemo(() => WS_BASE, [])

  useEffect(() => {
    const socket = new WebSocket(wsUrl)

    socket.onopen = () => setStatus('connected')
    socket.onclose = () => setStatus('closed')
    socket.onerror = () => setStatus('error')
    socket.onmessage = (event) => {
      const payload = JSON.parse(event.data)
      setMessages((prev) => [payload, ...prev].slice(0, 20))
    }

    return () => socket.close()
  }, [wsUrl])

  return (
    <main className="layout">
      <header className="hero">
        <p className="badge">Tenant Feed</p>
        <h1>Live Notifications</h1>
        <p className="status">Socket status: {status}</p>
        <p className="status">Authentication required on tenant domain session.</p>
      </header>
      <ul>
        {messages.map((item, idx) => (
          <li key={`${item.created_at}-${idx}`}>
            <strong>{item.message}</strong>
            <span>{new Date(item.created_at).toLocaleString()}</span>
          </li>
        ))}
      </ul>
    </main>
  )
}
