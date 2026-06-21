import { useState, useEffect } from 'react'
import { getAudit } from '../api'

function fmtTime(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

const EVENT_COLORS = {
  TOKEN_ISSUED:   'var(--success)',
  TOKEN_REVOKED:  'var(--danger)',
  APPROVED:       'var(--success)',
  DENIED:         'var(--danger)',
  EXPIRED:        'var(--text-subtle)',
  SCOPE_DERIVED:  'var(--info)',
  SCOPE_DENIED:   'var(--danger)',
  SESSION_ENDED:  'var(--warning)',
  SUBMITTED:      'var(--accent)',
}

export default function AuditFeed() {
  const [events, setEvents] = useState([])
  const [stub, setStub] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getAudit(100)
      .then(d => {
        setEvents(d.events ?? [])
        setStub(d.stub ?? false)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  return (
    <>
      <div className="page-header">
        <div className="page-header__left">
          <h1>Audit Log</h1>
          <p>Append-only record of every access lifecycle event.</p>
        </div>
      </div>

      <div className="page-body">
        {stub && (
          <div className="audit-stub-banner">
            ⚠ Audit log is live in Phase 13 — full event persistence wired then.
          </div>
        )}

        {loading ? (
          <div className="state-loading"><span className="spinner" /> Loading audit log…</div>
        ) : events.length === 0 ? (
          <div className="state-empty">
            <span className="state-empty__icon">📋</span>
            <h3>No audit events yet</h3>
            <p>
              Every access grant, denial, scope derivation, and token revocation
              will be recorded here in Phase 13.
            </p>
            <div style={{ marginTop: 20, fontSize: 12, color: 'var(--text-subtle)', textAlign: 'left', lineHeight: 1.8 }}>
              Planned events:
              {['SUBMITTED', 'SCOPE_DERIVED', 'APPROVED', 'TOKEN_ISSUED',
                'SCOPE_DENIED', 'TOKEN_REVOKED', 'SESSION_ENDED'].map(e => (
                <div key={e} style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4 }}>
                  <span style={{ color: EVENT_COLORS[e] ?? 'var(--info)', fontFamily: 'monospace', fontSize: 11, fontWeight: 700 }}>{e}</span>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="card">
            {events.map((ev, i) => (
              <div key={i} className="audit-row">
                <span className="audit-time">{fmtTime(ev.timestamp ?? ev.created_at)}</span>
                <span className="audit-event" style={{ color: EVENT_COLORS[ev.event] ?? 'var(--info)' }}>
                  {ev.event}
                </span>
                <span className="audit-detail">
                  {ev.agent_id && <span>agent:{ev.agent_id?.slice(0,10)} · </span>}
                  {ev.service && <span>{ev.service} · </span>}
                  {ev.detail ?? ev.message ?? ''}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  )
}
