import { useState, useEffect, useCallback } from 'react'
import { getAllRequests } from '../api'
import { socket } from '../socket'
import RequestCard from './RequestCard'

const STATES = ['ALL', 'PENDING', 'APPROVED', 'DENIED', 'EXPIRED']

export default function AllRequests() {
  const [requests, setRequests] = useState([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('ALL')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await getAllRequests(200)
      setRequests(data.requests ?? [])
    } catch (e) {
      console.error('[AllRequests] load error', e)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  // Live sync — update or insert request when state changes
  useEffect(() => {
    function onUpdate({ request }) {
      setRequests(prev => {
        const idx = prev.findIndex(r => r.id === request.id)
        if (idx >= 0) {
          const next = [...prev]
          next[idx] = request
          return next
        }
        return [request, ...prev]
      })
    }

    function onNew({ request }) { onUpdate({ request }) }

    function onRevoke({ request_id, state }) {
      setRequests(prev => prev.map(r =>
        r.id === request_id ? { ...r, state } : r
      ))
    }

    socket.on('request:new', onNew)
    socket.on('request:resolved', onUpdate)
    socket.on('token:revoked', onRevoke)
    return () => {
      socket.off('request:new', onNew)
      socket.off('request:resolved', onUpdate)
      socket.off('token:revoked', onRevoke)
    }
  }, [])

  const counts = STATES.reduce((acc, s) => {
    acc[s] = s === 'ALL' ? requests.length : requests.filter(r => r.state === s).length
    return acc
  }, {})

  const visible = filter === 'ALL' ? requests : requests.filter(r => r.state === filter)

  return (
    <>
      <div className="page-header">
        <div className="page-header__left">
          <h1>All Requests</h1>
          <p>Full request history — newest first.</p>
        </div>
        <div className="page-header__right">
          <button className="icon-btn" onClick={load} title="Refresh">↻</button>
        </div>
      </div>

      <div className="page-body">
        <div className="filter-bar">
          {STATES.map(s => (
            <button
              key={s}
              className={`filter-btn${filter === s ? ' filter-btn--active' : ''}`}
              onClick={() => setFilter(s)}
            >
              {s} {counts[s] > 0 && <span style={{ opacity: .7 }}>({counts[s]})</span>}
            </button>
          ))}
        </div>

        {loading ? (
          <div className="state-loading"><span className="spinner" /> Loading…</div>
        ) : visible.length === 0 ? (
          <div className="state-empty">
            <span className="state-empty__icon">📭</span>
            <h3>No requests yet</h3>
            <p>Access requests submitted by agents will appear here.</p>
          </div>
        ) : (
          <div className="request-grid">
            {visible.map(r => (
              <RequestCard key={r.id} request={r} />
            ))}
          </div>
        )}
      </div>
    </>
  )
}
