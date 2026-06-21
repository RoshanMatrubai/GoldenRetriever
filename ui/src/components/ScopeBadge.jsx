// Classifies scope actions from the policy engine into visual tiers.
const DESTRUCTIVE = new Set([
  'purchase', 'delete', 'review', 'write',
  'email_send', 'calendar_write', 'drive_write',
  'issue_write', 'pr_write', 'repo_write',
  'send_message', 'create_channel',
])

function classify(action) {
  if (DESTRUCTIVE.has(action) || action.endsWith('_write') || action.endsWith('_send'))
    return 'destructive'
  return 'read'
}

export function ScopeBadge({ action }) {
  const tier = classify(action)
  return <span className={`scope-badge scope-badge--${tier}`}>{action}</span>
}

export function ScopeList({ scope }) {
  if (!scope?.length) return <span className="badge badge--muted">no scope</span>
  return (
    <div className="scope-list">
      {scope.map(a => <ScopeBadge key={a} action={a} />)}
    </div>
  )
}
