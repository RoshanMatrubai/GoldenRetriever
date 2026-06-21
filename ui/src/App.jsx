import { useState, useEffect, useCallback } from 'react'
import './styles.css'
import { socket } from './socket'
import { getStatus } from './api'
import DemoControls from './components/DemoControls'
import PendingTile from './components/PendingTile'
import SessionsTile from './components/SessionsTile'
import AuditTile from './components/AuditTile'
import AccountsTile from './components/AccountsTile'
import { useCursorGlow } from './hooks'

function Tile({ area, children }) {
  const { ref, handleMouseMove } = useCursorGlow()
  return (
    <div
      ref={ref}
      className={`tile tile--${area}`}
      onMouseMove={handleMouseMove}
    >
      {children}
    </div>
  )
}

export default function App() {
  const [connected, setConnected]   = useState(false)
  const [pendingCount, setPending]  = useState(0)
  const [sessionCount, setSessions] = useState(0)
  const [version, setVersion]       = useState(null)
  const [toast, setToast]           = useState(null)

  useEffect(() => {
    const onConnect    = () => setConnected(true)
    const onDisconnect = () => setConnected(false)
    socket.on('connect', onConnect)
    socket.on('disconnect', onDisconnect)
    if (socket.connected) setConnected(true)
    return () => { socket.off('connect', onConnect); socket.off('disconnect', onDisconnect) }
  }, [])

  useEffect(() => {
    getStatus()
      .then(d => { setVersion(d.version); setPending(d.pending_count ?? 0); setSessions(d.active_sessions ?? 0) })
      .catch(() => {})
  }, [])

  useEffect(() => {
    const up   = () => setSessions(c => c + 1)
    const down = () => setSessions(c => Math.max(0, c - 1))
    socket.on('session:started', up)
    socket.on('session:ended',   down)
    return () => { socket.off('session:started', up); socket.off('session:ended', down) }
  }, [])

  // Toast for new pending requests
  useEffect(() => {
    function onNew({ request }) {
      setToast(`New request — ${request.service} · agent:${request.agent_id?.slice(0,10)}`)
      setTimeout(() => setToast(null), 4000)
    }
    socket.on('request:new', onNew)
    return () => socket.off('request:new', onNew)
  }, [])

  return (
    <div className="bento-wrap">
      {/* ── Header ── */}
      <header className="bento-header">
        <div className="bento-header__brand">
          <span className="bento-header__logo">🐕</span>
          <div>
            <span className="bento-header__name">Doberman</span>
            <span className="bento-header__sub">Access Broker</span>
          </div>
        </div>

        <DemoControls />

        <div className="bento-header__status">
          <div className={`connection-status connection-status--${connected ? 'live' : 'off'}`}>
            <span className="connection-status__dot"/>
            {connected ? 'Live' : 'Connecting…'}
          </div>
          {version && <span className="sidebar__version">v{version}</span>}
        </div>
      </header>

      {/* ── Bento grid ── */}
      <div className="bento-grid">
        <Tile area="pending">
          <PendingTile onCountChange={setPending} />
        </Tile>

        <Tile area="sessions">
          <SessionsTile onCountChange={setSessions} />
        </Tile>

        <Tile area="audit">
          <AuditTile />
        </Tile>

        <Tile area="accounts">
          <AccountsTile />
        </Tile>
      </div>

      {/* ── Toast ── */}
      {toast && (
        <div className="toast-wrap">
          <div className="toast">
            <span className="toast__dot"/>
            {toast}
          </div>
        </div>
      )}
    </div>
  )
}
