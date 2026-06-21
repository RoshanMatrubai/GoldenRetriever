import { useState, useEffect, useCallback } from 'react'
import { getPending } from '../api'
import { socket } from '../socket'
import RequestCard from './RequestCard'

export default function PendingQueue({ onCountChange, showToast }) {
  const [requests, setRequests] = useState([])
  const [loading, setLoading] = useState(true)
  const [flashIds, setFlashIds] = useState(new Set())

  const load = useCallback(async () => {
    try {
      const data = await getPending()
      setRequests(data.requests ?? [])
      onCountChange?.(data.requests?.length ?? 0)
    } catch (e) {
      console.error('[PendingQueue] load error', e)
    } finally {
      setLoading(false)
    }
  }, [onCountChange])

  useEffect(() => { load() }, [load])

  // Live: new request arrives → prepend + flash
  useEffect(() => {
    function onNew({ request }) {
      setRequests(prev => {
        if (prev.find(r => r.id === request.id)) return prev
        return [request, ...prev]
      })
      setFlashIds(prev => new Set([...prev, request.id]))
      setTimeout(() => setFlashIds(prev => { const s = new Set(prev); s.delete(request.id); return s }), 900)
      onCountChange?.(c => c + 1)
      showToast?.(`New request — ${request.service} · agent:${request.agent_id?.slice(0,10)}`)
    }

    // Resolved (approved/denied/expired) → remove from pending list
    function onResolved({ request }) {
      if (request.state === 'PENDING') return
      setRequests(prev => prev.filter(r => r.id !== request.id))
      onCountChange?.(c => Math.max(0, c - 1))
    }

    socket.on('request:new', onNew)
    socket.on('request:resolved', onResolved)
    socket.on('token:revoked', onResolved)
    return () => {
      socket.off('request:new', onNew)
      socket.off('request:resolved', onResolved)
      socket.off('token:revoked', onResolved)
    }
  }, [onCountChange, showToast])

  function handleResolved(updated) {
    setRequests(prev => prev.filter(r => r.id !== updated.id))
    onCountChange?.(c => Math.max(0, c - 1))
  }

  return (
    <>
      <div className="page-header">
        <div className="page-header__left">
          <h1>Pending Approvals</h1>
          <p>Review and approve or deny agent access requests in real time.</p>
        </div>
        <div className="page-header__right">
          <button className="icon-btn" onClick={load} title="Refresh">↻</button>
        </div>
      </div>

      <div className="page-body">
        {loading ? (
          <div className="state-loading"><span className="spinner" /> Loading requests…</div>
        ) : requests.length === 0 ? (
          <div className="state-empty">
            <span className="state-empty__icon">✅</span>
            <h3>No pending requests</h3>
            <p>When an agent requests access, the card will appear here live.</p>
          </div>
        ) : (
          <div className="request-grid">
            {requests.map(r => (
              <RequestCard
                key={r.id}
                request={r}
                flash={flashIds.has(r.id)}
                onResolved={handleResolved}
              />
            ))}
          </div>
        )}
      </div>
    </>
  )
}
