import { useState, useEffect, useCallback } from 'react'
import './styles.css'
import { socket } from './socket'
import { getStatus } from './api'
import PendingQueue from './components/PendingQueue'
import AllRequests from './components/AllRequests'
import AccountsManager from './components/AccountsManager'
import AuditFeed from './components/AuditFeed'

const NAV = [
  { id: 'pending',  icon: '🔔', label: 'Pending' },
  { id: 'all',      icon: '📋', label: 'All Requests' },
  { id: 'accounts', icon: '🗄️', label: 'Accounts' },
  { id: 'audit',    icon: '📊', label: 'Audit Log' },
]

export default function App() {
  const [page, setPage] = useState('pending')
  const [connected, setConnected] = useState(false)
  const [pendingCount, setPendingCount] = useState(0)
  const [version, setVersion] = useState(null)
  const [toast, setToast] = useState(null)

  // Socket connection status
  useEffect(() => {
    const onConnect    = () => setConnected(true)
    const onDisconnect = () => setConnected(false)
    socket.on('connect', onConnect)
    socket.on('disconnect', onDisconnect)
    if (socket.connected) setConnected(true)
    return () => { socket.off('connect', onConnect); socket.off('disconnect', onDisconnect) }
  }, [])

  // Initial status fetch
  useEffect(() => {
    getStatus()
      .then(d => { setVersion(d.version); setPendingCount(d.pending_count ?? 0) })
      .catch(() => {})
  }, [])

  const showToast = useCallback((msg) => {
    setToast(msg)
    const t = setTimeout(() => setToast(null), 4500)
    return () => clearTimeout(t)
  }, [])

  const handleCountChange = useCallback((val) => {
    setPendingCount(typeof val === 'function' ? val : () => val)
  }, [])

  return (
    <div className="app">
      {/* ─── Sidebar ─── */}
      <aside className="sidebar">
        <div className="sidebar__logo">
          <span className="sidebar__logo-icon">🐕</span>
          <span>GoldenRetriever</span>
        </div>

        <nav className="sidebar__nav">
          {NAV.map(item => (
            <button
              key={item.id}
              className={`nav-item${page === item.id ? ' nav-item--active' : ''}`}
              onClick={() => setPage(item.id)}
            >
              <span className="nav-icon">{item.icon}</span>
              <span className="nav-label">{item.label}</span>
              {item.id === 'pending' && pendingCount > 0 && (
                <span className="badge badge--warning">{pendingCount}</span>
              )}
            </button>
          ))}
        </nav>

        <div className="sidebar__footer">
          <div className={`connection-status connection-status--${connected ? 'live' : 'off'}`}>
            <span className="connection-status__dot" />
            {connected ? 'Live' : 'Connecting…'}
          </div>
          {version && <div className="sidebar__version">v{version}</div>}
        </div>
      </aside>

      {/* ─── Main content ─── */}
      <main className="main">
        {page === 'pending' && (
          <PendingQueue
            onCountChange={handleCountChange}
            showToast={showToast}
          />
        )}
        {page === 'all'      && <AllRequests />}
        {page === 'accounts' && <AccountsManager />}
        {page === 'audit'    && <AuditFeed />}
      </main>

      {/* ─── Toast ─── */}
      {toast && <div className="toast">🔔 {toast}</div>}
    </div>
  )
}
