import { useState } from 'react'
import { ScopeList } from './ScopeBadge'
import { approve, deny, revoke } from '../api'

const SVC_ICONS = {
  amazon: '🛒', google: '🔍', github: '🐱',
  slack: '💬', jira: '📋',
}

const STATE_BADGE = {
  PENDING:  { cls: 'badge--warning', label: 'Pending' },
  APPROVED: { cls: 'badge--success', label: 'Approved' },
  DENIED:   { cls: 'badge--danger',  label: 'Denied' },
  EXPIRED:  { cls: 'badge--muted',   label: 'Expired' },
}

function fmt(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function fmtDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export default function RequestCard({ request: initial, flash = false, onResolved }) {
  const [req, setReq] = useState(initial)
  const [loading, setLoading] = useState(null) // 'approve'|'deny'|'revoke'
  const [error, setError] = useState(null)

  const stateInfo = STATE_BADGE[req.state] ?? { cls: 'badge--muted', label: req.state }
  const icon = SVC_ICONS[req.service?.toLowerCase()] ?? '🔑'

  async function act(action, apiFn) {
    setLoading(action)
    setError(null)
    try {
      const data = await apiFn(req.id)
      const updated = data.request ?? { ...req, state: action === 'revoke' ? 'EXPIRED' : action.toUpperCase() }
      setReq(updated)
      onResolved?.(updated)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(null)
    }
  }

  return (
    <div className={`card card--${req.state}${flash ? ' card--flash' : ''}`}>
      <div className="card__header">
        <div className="card__service">
          <span className="card__svc-icon">{icon}</span>
          <div>
            <div className="card__svc-name">{req.service}</div>
            <div className="card__svc-agent">agent:{req.agent_id?.slice(0, 12)}</div>
          </div>
        </div>
        <div className="card__header-right">
          <span className={`badge ${stateInfo.cls}`}>{stateInfo.label}</span>
        </div>
      </div>

      <div className="card__body">
        <div className="card__task">"{req.task}"</div>

        <div className="card__scope-label">Derived Scope</div>
        <ScopeList scope={req.scope} />

        <div className="card__meta">
          <div className="card__meta-item">
            <span className="card__meta-label">Request ID</span>
            <span className="card__meta-value">{req.id?.slice(0, 14)}…</span>
          </div>
          <div className="card__meta-item">
            <span className="card__meta-label">Tenant</span>
            <span className="card__meta-value">{req.tenant_id?.slice(0, 12)}…</span>
          </div>
          <div className="card__meta-item">
            <span className="card__meta-label">Submitted</span>
            <span className="card__meta-value">{fmtDate(req.created_at)}</span>
          </div>
          {req.state === 'PENDING' && (
            <div className="card__meta-item">
              <span className="card__meta-label">Expires</span>
              <span className="card__meta-value">{fmt(req.expires_at)}</span>
            </div>
          )}
          {req.resolved_at && (
            <div className="card__meta-item">
              <span className="card__meta-label">Resolved</span>
              <span className="card__meta-value">{fmtDate(req.resolved_at)}</span>
            </div>
          )}
          {req.token_id && (
            <div className="card__meta-item">
              <span className="card__meta-label">Token</span>
              <span className="card__meta-value">{req.token_id?.slice(0, 14)}…</span>
            </div>
          )}
        </div>

        {error && (
          <div style={{ marginTop: 10, fontSize: 12, color: 'var(--danger)' }}>
            ⚠ {error}
          </div>
        )}
      </div>

      {req.state === 'PENDING' && (
        <div className="card__actions">
          <button
            className="btn btn--success"
            disabled={!!loading}
            onClick={() => act('approve', approve)}
          >
            {loading === 'approve' ? <><span className="spinner" /> Approving…</> : '✓ Approve'}
          </button>
          <button
            className="btn btn--danger"
            disabled={!!loading}
            onClick={() => act('deny', deny)}
          >
            {loading === 'deny' ? <><span className="spinner" /> Denying…</> : '✕ Deny'}
          </button>
        </div>
      )}

      {req.state === 'APPROVED' && (
        <div className="card__actions">
          <button
            className="btn btn--ghost"
            disabled={!!loading}
            onClick={() => act('revoke', revoke)}
          >
            {loading === 'revoke' ? <><span className="spinner" /> Revoking…</> : '⊘ Revoke Token'}
          </button>
        </div>
      )}
    </div>
  )
}
