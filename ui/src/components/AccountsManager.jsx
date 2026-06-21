import { useState, useEffect } from 'react'
import { getTenants, getAccounts } from '../api'

const SVC_ICONS = {
  amazon: '🛒', google: '🔍', github: '🐱',
  slack: '💬', jira: '📋',
}

function fmtDate(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' })
}

function TenantSection({ tenant }) {
  const [accounts, setAccounts] = useState(null)

  useEffect(() => {
    getAccounts(tenant.id)
      .then(d => setAccounts(d.accounts ?? []))
      .catch(() => setAccounts([]))
  }, [tenant.id])

  return (
    <div className="tenant-section">
      <div className="tenant-header">
        <span className="tenant-name">{tenant.name}</span>
        <span className="tenant-id">{tenant.id}</span>
        {accounts !== null && (
          <span className="badge badge--muted">{accounts.length} account{accounts.length !== 1 ? 's' : ''}</span>
        )}
      </div>

      {accounts === null ? (
        <div className="state-loading" style={{ padding: '16px 0' }}>
          <span className="spinner" />
        </div>
      ) : accounts.length === 0 ? (
        <div style={{ fontSize: 13, color: 'var(--text-subtle)', padding: '8px 4px' }}>
          No service accounts configured for this tenant.
        </div>
      ) : (
        accounts.map(acct => (
          <div key={acct.id} className="account-row">
            <span className="account-svc-icon">
              {SVC_ICONS[acct.service?.toLowerCase()] ?? '🔑'}
            </span>
            <div className="account-info">
              <div className="account-service">{acct.service}</div>
              <div className="account-username">{acct.username}</div>
            </div>
            <span className="account-date">{fmtDate(acct.created_at)}</span>
          </div>
        ))
      )}
    </div>
  )
}

export default function AccountsManager() {
  const [tenants, setTenants] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    getTenants()
      .then(d => setTenants(d.tenants ?? []))
      .catch(e => setError(e.message))
  }, [])

  return (
    <>
      <div className="page-header">
        <div className="page-header__left">
          <h1>Accounts</h1>
          <p>Tenants and their encrypted service accounts.</p>
        </div>
      </div>

      <div className="page-body">
        {error && (
          <div style={{ color: 'var(--danger)', fontSize: 13, marginBottom: 16 }}>
            ⚠ {error}
          </div>
        )}

        {tenants === null && !error ? (
          <div className="state-loading"><span className="spinner" /> Loading tenants…</div>
        ) : tenants?.length === 0 ? (
          <div className="state-empty">
            <span className="state-empty__icon">🗄️</span>
            <h3>No tenants yet</h3>
            <p>
              Tenants and service accounts are added via the vault API.
              They'll appear here once created.
            </p>
          </div>
        ) : (
          tenants?.map(t => <TenantSection key={t.id} tenant={t} />)
        )}
      </div>
    </>
  )
}
