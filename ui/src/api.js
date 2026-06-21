// All dashboard API calls — vite proxies /api → http://localhost:5001

async function _fetch(path, opts = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  })
  const json = await res.json()
  if (!res.ok) throw new Error(json.error || `HTTP ${res.status}`)
  return json
}

export const getStatus       = ()          => _fetch('/api/status')
export const getPending      = ()          => _fetch('/api/requests?state=PENDING')
export const getAllRequests   = (limit=100) => _fetch(`/api/requests/all?limit=${limit}`)
export const approve         = (id)        => _fetch(`/api/requests/${id}/approve`, { method: 'POST' })
export const deny            = (id)        => _fetch(`/api/requests/${id}/deny`,    { method: 'POST' })
export const revoke          = (id)        => _fetch(`/api/requests/${id}`,         { method: 'DELETE' })
export const getTenants      = ()          => _fetch('/api/tenants')
export const getAccounts     = (tenantId)  => _fetch(`/api/accounts?tenant_id=${tenantId}`)
export const getAudit        = (limit=50)  => _fetch(`/api/audit?limit=${limit}`)
