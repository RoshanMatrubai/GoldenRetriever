import { useState, useEffect, useCallback, useMemo } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  Inbox, Zap, Clock, Globe, Bot, Settings, LogOut,
  Check, X, RefreshCw, Activity, Filter, ChevronDown,
  ChevronRight, CheckCircle2, XCircle, AlertCircle,
  Radio, Wifi, WifiOff, Plus, Fingerprint, Bell, Shield,
  Trash2, Copy, MoreHorizontal, Search,
} from "lucide-react";
import { io } from "socket.io-client";

// ─── Types ────────────────────────────────────────────────────────────────────

type BackendRequest = {
  id: string;
  state: "PENDING" | "APPROVED" | "DENIED" | "EXPIRED";
  tenant_id: string;
  agent_id: string;
  service: string;
  task: string;
  scope: string[];
  created_at: string;
  expires_at: string | null;
  resolved_at: string | null;
  token_id: string | null;
  session_expires_at: string | null;
};

type AuditEvent = {
  id?: string;
  event: string;
  tenant_id: string;
  agent_id: string;
  service: string;
  request_id: string;
  scope: string[];
  detail: string;
  timestamp: string;
  created_at?: string;
};

type Account = {
  id: string;
  service: string;
  username: string;
  tenant_id: string;
  created_at: string;
};

type Screen = "requests" | "sessions" | "audit" | "accounts" | "agents" | "settings";

// ─── Socket ───────────────────────────────────────────────────────────────────

const socket = io("/", {
  transports: ["polling", "websocket"],
  reconnectionDelay: 1000,
  reconnectionAttempts: Infinity,
});

// ─── API ──────────────────────────────────────────────────────────────────────

async function apiFetch(path: string, opts: RequestInit = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  const json = await res.json();
  if (!res.ok) throw new Error(json.error || `HTTP ${res.status}`);
  return json;
}

const api = {
  allRequests: (limit = 60) => apiFetch(`/api/requests/all?limit=${limit}`),
  approve: (id: string, scope?: string[]) =>
    apiFetch(`/api/requests/${id}/approve`, { method: "POST", body: scope ? JSON.stringify({ scope }) : undefined }),
  deny: (id: string) => apiFetch(`/api/requests/${id}/deny`, { method: "POST" }),
  sessions: () => apiFetch("/api/sessions"),
  endSession: (id: string) => apiFetch(`/api/sessions/${id}/end`, { method: "POST" }),
  audit: (limit = 120) => apiFetch(`/api/audit?limit=${limit}`),
  tenants: () => apiFetch("/api/tenants"),
  accounts: (tenantId: string) => apiFetch(`/api/accounts?tenant_id=${tenantId}`),
  demoRequest: (service: string) => apiFetch("/api/demo/request", { method: "POST", body: JSON.stringify({ service }) }),
  demoAction: async (action: string, requestId: string) => {
    const res = await fetch("/api/demo/action", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, request_id: requestId }),
    });
    return res.json();
  },
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

function fmtTime(iso?: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function fmtDateTime(iso?: string | null) {
  if (!iso) return "—";
  const d = new Date(iso);
  const today = new Date();
  const time = d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  return d.toDateString() === today.toDateString()
    ? `Today ${time}`
    : `${d.toLocaleDateString([], { month: "short", day: "numeric" })} ${time}`;
}

function calcTTL(expiresAt: string | null) {
  if (!expiresAt) return null;
  const d = new Date(expiresAt).getTime() - Date.now();
  if (d <= 0) return "Expired";
  const m = Math.floor(d / 60000), s = Math.floor((d % 60000) / 1000);
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

function useTTL(expiresAt: string | null) {
  const [ttl, setTTL] = useState(() => calcTTL(expiresAt));
  useEffect(() => {
    const t = setInterval(() => setTTL(calcTTL(expiresAt)), 1000);
    return () => clearInterval(t);
  }, [expiresAt]);
  return ttl;
}

function deriveRisk(scope: string[]): "low" | "medium" | "high" {
  if (!scope?.length) return "low";
  if (scope.includes("purchase") || scope.includes("delete")) return "high";
  if (scope.includes("write")) return "medium";
  return "low";
}

// ─── Action catalogs per service ──────────────────────────────────────────────

const SERVICE_ACTIONS: Record<string, { label: string; action: string }[]> = {
  amazon:  [{ label: "Search products", action: "search" }, { label: "View listing", action: "read" }, { label: "Write review", action: "write" }, { label: "Add to cart", action: "purchase" }, { label: "Cancel order", action: "delete" }],
  google:  [{ label: "Search web", action: "search" }, { label: "Read emails", action: "read" }, { label: "Send email", action: "write" }, { label: "Delete email", action: "delete" }],
  github:  [{ label: "Search repos", action: "search" }, { label: "View issues", action: "read" }, { label: "Push commit", action: "write" }, { label: "Delete branch", action: "delete" }],
  slack:   [{ label: "Search messages", action: "search" }, { label: "Read channel", action: "read" }, { label: "Send message", action: "write" }, { label: "Delete message", action: "delete" }],
  jira:    [{ label: "Search tickets", action: "search" }, { label: "View ticket", action: "read" }, { label: "Create ticket", action: "write" }, { label: "Delete issue", action: "delete" }],
};

const ALL_SCOPE_ACTIONS = ["search", "read", "write", "purchase", "delete"];

const DEMO_SERVICES = [
  { id: "amazon", label: "Amazon" },
  { id: "google", label: "Google" },
  { id: "github", label: "GitHub" },
  { id: "slack",  label: "Slack"  },
  { id: "jira",   label: "Jira"   },
];

// ─── Shared UI atoms ──────────────────────────────────────────────────────────

const Badge = ({ children, variant = "default" }: {
  children: React.ReactNode;
  variant?: "default" | "success" | "danger" | "warning" | "neutral";
}) => {
  const cls = {
    default: "bg-primary/10 text-primary",
    success: "bg-green-100 text-green-700",
    danger:  "bg-red-100 text-red-700",
    warning: "bg-amber-100 text-amber-700",
    neutral: "bg-muted text-muted-foreground",
  }[variant];
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold font-['DM_Mono',monospace] ${cls}`}>
      {children}
    </span>
  );
};

const RiskBadge = ({ risk }: { risk: string }) => (
  risk === "high"   ? <Badge variant="danger">high risk</Badge>  :
  risk === "medium" ? <Badge variant="warning">medium risk</Badge> :
                      <Badge variant="neutral">low risk</Badge>
);

const SectionHeader = ({ title, subtitle, action }: {
  title: string; subtitle?: string; action?: React.ReactNode;
}) => (
  <div className="flex items-start justify-between mb-6">
    <div>
      <h1 className="text-xl font-semibold font-['Outfit',sans-serif] text-foreground">{title}</h1>
      {subtitle && <p className="text-sm text-muted-foreground mt-0.5">{subtitle}</p>}
    </div>
    {action && <div>{action}</div>}
  </div>
);

const StatCard = ({ label, value, sub, icon: Icon, color = "text-primary" }: {
  label: string; value: string | number; sub?: string; icon: React.ElementType; color?: string;
}) => (
  <div className="bg-card rounded-lg border border-border p-4 flex items-start gap-3">
    <div className={`p-2 rounded-md bg-primary/10 ${color}`}><Icon size={16} /></div>
    <div>
      <div className="text-2xl font-semibold font-['Outfit',sans-serif] text-foreground leading-none">{value}</div>
      <div className="text-xs text-muted-foreground mt-1">{label}</div>
      {sub && <div className="text-xs text-primary mt-0.5">{sub}</div>}
    </div>
  </div>
);

// ─── Dog logo ─────────────────────────────────────────────────────────────────

const DogLogo = ({ size = 36, className = "" }: { size?: number; className?: string }) => (
  <svg width={size} height={size} viewBox="0 0 64 56" fill="currentColor" xmlns="http://www.w3.org/2000/svg" className={className}>
    <path d="M8,54 C8,40 12,34 18,32 L30,32 C36,32 40,36 40,44 L40,54 Z" />
    <ellipse cx="36" cy="46" rx="7" ry="9" />
    <path d="M30,32 C32,26 34,22 38,20 L42,28 C38,30 34,32 32,34 Z" />
    <ellipse cx="46" cy="20" rx="13" ry="10" transform="rotate(-8 46 20)" />
    <path d="M52,22 C55,20 62,22 62,26 C62,30 58,32 53,31 C48,30 46,27 47,24 Z" />
    <path d="M37,14 C32,14 28,18 28,28 C28,32 30,34 34,32 C34,22 36,16 42,14 Z" />
    <path d="M8,46 Q2,36 6,26 Q10,18 14,22" stroke="currentColor" strokeWidth="5" fill="none" strokeLinecap="round" />
    <rect x="32" y="50" width="7" height="5" rx="2.5" />
    <ellipse cx="61" cy="26" rx="2.5" ry="2" fill="rgba(0,0,0,0.28)" />
  </svg>
);

// ─── Scope editor ─────────────────────────────────────────────────────────────

const ScopeEditor = ({ value, derived, onChange }: {
  value: string[]; derived: string[]; onChange: (s: string[]) => void;
}) => (
  <div className="flex flex-wrap gap-1.5 mt-2">
    {ALL_SCOPE_ACTIONS.map((action) => {
      const on = value.includes(action);
      const isDestructive = action === "purchase" || action === "delete";
      const isWrite = action === "write";
      const colorOn = isDestructive
        ? "bg-red-50 text-red-600 border-red-200"
        : isWrite
        ? "bg-amber-50 text-amber-700 border-amber-200"
        : "bg-blue-50 text-blue-700 border-blue-200";
      const fromPolicy = derived.includes(action);
      return (
        <button
          key={action}
          onClick={() => onChange(on ? value.filter(a => a !== action) : [...value, action])}
          title={fromPolicy ? "Policy derived" : "Not in derived scope"}
          className={`inline-flex items-center gap-1 px-2.5 py-1 rounded text-xs font-semibold font-['DM_Mono',monospace] border transition-all cursor-pointer ${on ? colorOn : "bg-muted text-muted-foreground border-border opacity-50"}`}
        >
          {on ? <Check size={9} /> : <span className="w-[9px]" />}
          {action}
          {fromPolicy && !on && <span className="text-[8px] opacity-50 ml-0.5">policy</span>}
        </button>
      );
    })}
  </div>
);

// ─── Request card ─────────────────────────────────────────────────────────────

const RequestCard = ({ request, onApprove, onDeny }: {
  request: BackendRequest;
  onApprove?: (id: string, scope?: string[]) => Promise<void>;
  onDeny?: (id: string) => Promise<void>;
}) => {
  const [loading, setLoading] = useState<"approve" | "deny" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [scopeDraft, setScopeDraft] = useState<string[]>(request.scope ?? []);
  const isPending = request.state === "PENDING";
  const risk = deriveRisk(request.scope);

  async function handleApprove() {
    setLoading("approve"); setError(null);
    try { await onApprove?.(request.id, editing ? scopeDraft : undefined); }
    catch (e: any) { setError(e.message); }
    finally { setLoading(null); }
  }

  async function handleDeny() {
    setLoading("deny"); setError(null);
    try { await onDeny?.(request.id); }
    catch (e: any) { setError(e.message); }
    finally { setLoading(null); }
  }

  return (
    <motion.div layout initial={{ opacity: 0, y: -12 }} animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.97 }} transition={{ duration: 0.22, ease: "easeOut" }}
      className={`bg-card rounded-lg border overflow-hidden ${
        isPending          ? "border-primary/30 shadow-sm"
        : request.state === "APPROVED" ? "border-green-200"
        : "border-red-200 opacity-75"
      }`}
    >
      <div className="px-4 py-3">
        <div className="flex items-start gap-3">
          {/* Icon */}
          <div className={`mt-0.5 w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${
            isPending ? "bg-primary/10 text-primary"
            : request.state === "APPROVED" ? "bg-green-100 text-green-600"
            : "bg-red-100 text-red-500"
          }`}>
            <Bot size={16} />
          </div>

          <div className="flex-1 min-w-0">
            {/* Header row */}
            <div className="flex items-center gap-2 flex-wrap mb-1">
              <span className="font-semibold text-sm text-foreground font-['DM_Mono',monospace]">
                {request.agent_id.length > 22 ? request.agent_id.slice(0, 22) + "…" : request.agent_id}
              </span>
              <ChevronRight size={12} className="text-muted-foreground" />
              <span className="font-semibold text-sm text-foreground flex items-center gap-1 capitalize">
                <Globe size={12} className="text-muted-foreground" /> {request.service}
              </span>
              <RiskBadge risk={risk} />
            </div>

            {/* Task */}
            <p className="text-sm text-muted-foreground mb-2">"{request.task}"</p>

            {/* Scope section — pending only */}
            {isPending && (
              <div className="mb-2">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">
                    {editing ? "Edit Scope" : "Derived Scope"}
                  </span>
                  <button onClick={() => { setEditing(e => !e); setScopeDraft(request.scope ?? []); }}
                    className="text-[10px] font-semibold text-primary hover:underline">
                    {editing ? "✕ cancel" : "✎ edit"}
                  </button>
                </div>
                {editing
                  ? <ScopeEditor value={scopeDraft} derived={request.scope ?? []} onChange={setScopeDraft} />
                  : (
                    <div className="flex flex-wrap gap-1">
                      {(request.scope ?? []).length > 0
                        ? (request.scope ?? []).map(s => (
                            <span key={s} className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold font-['DM_Mono',monospace] bg-primary/10 text-primary">{s}</span>
                          ))
                        : <span className="text-xs text-muted-foreground italic">No scope yet — policy still running</span>
                      }
                    </div>
                  )
                }
                {editing && scopeDraft.length === 0 && (
                  <p className="text-xs text-amber-600 mt-1">⚠ Empty scope — agent will receive a token with no permissions</p>
                )}
              </div>
            )}

            {/* Footer */}
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Clock size={11} />
              <span className="font-['DM_Mono',monospace]">{fmtTime(request.created_at)}</span>
              {!isPending && (
                <>
                  <span className="w-1 h-1 rounded-full bg-border" />
                  {request.state === "APPROVED"
                    ? <span className="text-green-600 flex items-center gap-1"><CheckCircle2 size={11} /> Approved</span>
                    : request.state === "DENIED"
                    ? <span className="text-red-500 flex items-center gap-1"><XCircle size={11} /> Denied</span>
                    : <span className="text-muted-foreground flex items-center gap-1"><XCircle size={11} /> Expired</span>}
                </>
              )}
            </div>
            {error && <p className="text-xs text-red-500 mt-1">⚠ {error}</p>}
          </div>

          {/* Approve / Deny */}
          {isPending && (
            <div className="flex items-center gap-2 shrink-0 ml-2">
              <button onClick={handleDeny} disabled={!!loading}
                className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-md bg-red-50 text-red-600 hover:bg-red-100 transition-colors font-medium border border-red-100 disabled:opacity-50">
                {loading === "deny" ? <RefreshCw size={11} className="animate-spin" /> : <X size={12} />} Deny
              </button>
              <button onClick={handleApprove} disabled={!!loading}
                className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-md bg-green-50 text-green-700 hover:bg-green-100 transition-colors font-medium border border-green-100 disabled:opacity-50">
                {loading === "approve" ? <RefreshCw size={11} className="animate-spin" /> : <Check size={12} />}
                {editing ? `Approve [${scopeDraft.length}]` : "Approve"}
              </button>
            </div>
          )}
        </div>
      </div>
    </motion.div>
  );
};

// ─── Screen: Requests ─────────────────────────────────────────────────────────

const RequestsScreen = ({ requests, onApprove, onDeny, pendingCount }: {
  requests: BackendRequest[];
  onApprove: (id: string, scope?: string[]) => Promise<void>;
  onDeny: (id: string) => Promise<void>;
  pendingCount: number;
}) => {
  const [simService, setSimService] = useState("amazon");
  const [simLoading, setSimLoading] = useState(false);

  async function simulate() {
    setSimLoading(true);
    try { await api.demoRequest(simService); }
    catch (e) { console.error(e); }
    finally { setSimLoading(false); }
  }

  const approved = requests.filter(r => r.state === "APPROVED").length;
  const denied   = requests.filter(r => r.state === "DENIED").length;

  return (
    <div className="p-8 max-w-3xl">
      <div className="flex items-start justify-between mb-6">
        <div>
          <div className="flex items-center gap-3 mb-0.5">
            <h1 className="text-xl font-semibold font-['Outfit',sans-serif] text-foreground">Requests</h1>
            <span className="inline-flex items-center gap-1.5 px-2 py-0.5 bg-green-100 text-green-700 text-xs font-semibold rounded-full">
              <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" /> LIVE
            </span>
          </div>
          <p className="text-sm text-muted-foreground">
            {pendingCount} pending · {approved} approved · {denied} denied
          </p>
        </div>

        {/* Demo controls */}
        <div className="flex items-center gap-2">
          <div className="relative">
            <select value={simService} onChange={e => setSimService(e.target.value)} disabled={simLoading}
              className="text-xs bg-muted border border-border rounded-md pl-3 pr-7 py-1.5 appearance-none text-muted-foreground focus:outline-none focus:ring-1 ring-primary">
              {DEMO_SERVICES.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}
            </select>
            <ChevronDown size={11} className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
          </div>
          <button onClick={simulate} disabled={simLoading}
            className="flex items-center gap-1.5 text-xs border border-border rounded-md px-3 py-1.5 hover:bg-muted transition-colors text-muted-foreground hover:text-foreground disabled:opacity-50">
            {simLoading ? <RefreshCw size={12} className="animate-spin" /> : <Radio size={12} />}
            Simulate request
          </button>
        </div>
      </div>

      <div className="flex flex-col gap-3">
        <AnimatePresence mode="popLayout">
          {requests.map(req => (
            <RequestCard key={req.id} request={req}
              onApprove={req.state === "PENDING" ? onApprove : undefined}
              onDeny={req.state === "PENDING" ? onDeny : undefined}
            />
          ))}
        </AnimatePresence>
      </div>

      {requests.length === 0 && (
        <div className="py-20 text-center">
          <Inbox size={32} className="mx-auto text-muted-foreground/40 mb-3" />
          <p className="text-sm text-muted-foreground">No requests yet.</p>
          <p className="text-xs text-muted-foreground mt-1">Pick a service above and click <strong>Simulate request</strong>.</p>
        </div>
      )}
    </div>
  );
};

// ─── Session card ─────────────────────────────────────────────────────────────

const SessionCard = ({ session, onEnded }: {
  session: BackendRequest; onEnded: (id: string) => void;
}) => {
  const [ending, setEnding] = useState(false);
  const [actionResults, setActionResults] = useState<Record<string, "allowed" | "denied">>({});
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const ttl = useTTL(session.session_expires_at);
  const actions = SERVICE_ACTIONS[session.service?.toLowerCase()] ?? [];
  const ttlColor = !ttl || ttl === "Expired" ? "text-red-500" : ttl.includes("m") ? "text-muted-foreground" : "text-amber-600";

  async function handleEnd() {
    if (ending) return;
    setEnding(true);
    try { await api.endSession(session.id); onEnded(session.id); }
    catch (e) { console.error(e); setEnding(false); }
  }

  async function tryAction(label: string, action: string) {
    setActionLoading(label);
    try {
      const data = await api.demoAction(action, session.id);
      setActionResults(r => ({ ...r, [label]: data.allowed ? "allowed" : "denied" }));
      setTimeout(() => setActionResults(r => { const n = { ...r }; delete n[label]; return n; }), 3000);
    } catch (e) { console.error(e); }
    finally { setActionLoading(null); }
  }

  return (
    <div className="bg-card rounded-lg border border-green-200 overflow-hidden">
      <div className="px-4 py-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            {/* Header */}
            <div className="flex items-center gap-2.5 mb-2">
              <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse shrink-0" />
              <span className="font-semibold text-sm text-foreground capitalize">{session.service}</span>
              <Badge variant="success">LIVE</Badge>
              {ttl && <span className={`text-xs font-semibold font-['DM_Mono',monospace] ${ttlColor}`}>⏱ {ttl}</span>}
            </div>

            {/* Meta */}
            <div className="text-xs text-muted-foreground font-['DM_Mono',monospace] mb-2">
              agent:{session.agent_id?.slice(0, 16)} · {session.tenant_id}
            </div>

            {/* Scope */}
            <div className="flex flex-wrap gap-1 mb-1">
              {(session.scope ?? []).map(s => (
                <span key={s} className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold font-['DM_Mono',monospace] bg-primary/10 text-primary">{s}</span>
              ))}
            </div>

            {/* Token ID */}
            {session.token_id && (
              <div className="text-[10px] text-muted-foreground font-['DM_Mono',monospace] mt-1">
                token:{session.token_id.slice(0, 16)}…
              </div>
            )}
          </div>

          <button onClick={handleEnd} disabled={ending}
            className="shrink-0 text-xs px-3 py-1.5 rounded-md border border-border hover:bg-muted transition-colors text-muted-foreground hover:text-foreground disabled:opacity-50 flex items-center gap-1">
            {ending ? <RefreshCw size={11} className="animate-spin" /> : <X size={11} />} End Session
          </button>
        </div>

        {/* Action test buttons */}
        {actions.length > 0 && (
          <div className="mt-3 pt-3 border-t border-border">
            <div className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider mb-2">Try an action</div>
            <div className="flex flex-wrap gap-1.5">
              {actions.map(({ label, action }) => {
                const res = actionResults[label];
                const isLoading = actionLoading === label;
                return (
                  <button key={label} onClick={() => tryAction(label, action)} disabled={!!actionLoading}
                    className={`px-2.5 py-1 rounded text-xs font-medium border transition-all disabled:opacity-40 ${
                      res === "allowed" ? "bg-green-50 text-green-700 border-green-200"
                      : res === "denied" ? "bg-red-50 text-red-600 border-red-200"
                      : "bg-muted text-muted-foreground border-border hover:bg-muted/80"
                    }`}>
                    {isLoading ? <RefreshCw size={10} className="animate-spin inline" />
                    : res === "allowed" ? `✓ ${label}`
                    : res === "denied"  ? `✕ ${label}`
                    : label}
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

// ─── Screen: Active Sessions ──────────────────────────────────────────────────

const SessionsScreen = ({ sessions, onEnded, onGoToRequests }: {
  sessions: BackendRequest[];
  onEnded: (id: string) => void;
  onGoToRequests: () => void;
}) => (
  <div className="p-8 max-w-3xl">
    <div className="flex items-start justify-between mb-6">
      <div>
        <div className="flex items-center gap-3 mb-0.5">
          <h1 className="text-xl font-semibold font-['Outfit',sans-serif] text-foreground">Active Sessions</h1>
          {sessions.length > 0 && (
            <span className="inline-flex items-center gap-1.5 px-2 py-0.5 bg-green-100 text-green-700 text-xs font-semibold rounded-full">
              <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" /> {sessions.length} LIVE
            </span>
          )}
        </div>
        <p className="text-sm text-muted-foreground">
          Approved tokens — use "Try an action" to test scope enforcement live
        </p>
      </div>
    </div>

    {sessions.length === 0 && (
      <button onClick={onGoToRequests}
        className="w-full mb-6 flex items-center gap-3 bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 hover:bg-amber-100 transition-colors text-left group">
        <AlertCircle size={16} className="text-amber-500 shrink-0" />
        <span className="text-sm text-amber-800 flex-1">No live sessions yet — approve a request to start one</span>
        <span className="text-xs text-amber-600 flex items-center gap-1 group-hover:gap-2 transition-all">
          Go to Requests <ChevronRight size={12} />
        </span>
      </button>
    )}

    <div className="flex flex-col gap-3">
      <AnimatePresence mode="popLayout">
        {sessions.map(s => (
          <motion.div key={s.id} layout initial={{ opacity: 0, y: -12 }} animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97 }} transition={{ duration: 0.22, ease: "easeOut" }}>
            <SessionCard session={s} onEnded={onEnded} />
          </motion.div>
        ))}
      </AnimatePresence>
    </div>

    {sessions.length === 0 && (
      <div className="py-12 text-center">
        <Zap size={28} className="mx-auto text-muted-foreground/30 mb-3" />
        <p className="text-sm text-muted-foreground">Approve a pending request to see a live session appear here.</p>
      </div>
    )}
  </div>
);

// ─── Screen: Audit Log ────────────────────────────────────────────────────────

const EVENT_RESULT: Record<string, "approved" | "denied" | "revoked"> = {
  APPROVED: "approved", TOKEN_ISSUED: "approved", ACTION_ALLOWED: "approved",
  DENIED: "denied", SCOPE_DENIED: "denied",
  TOKEN_REVOKED: "revoked", SESSION_ENDED: "revoked", EXPIRED: "revoked",
};

const EventBadge = ({ event }: { event: string }) => {
  const r = EVENT_RESULT[event];
  if (r === "approved") return <Badge variant="success"><CheckCircle2 size={10} />{event}</Badge>;
  if (r === "denied")   return <Badge variant="danger"><XCircle size={10} />{event}</Badge>;
  if (r === "revoked")  return <Badge variant="warning"><RefreshCw size={10} />{event}</Badge>;
  return <Badge variant="neutral">{event}</Badge>;
};

const AuditScreen = ({ events }: { events: AuditEvent[] }) => {
  const [filter, setFilter] = useState<"all" | "approved" | "denied" | "revoked">("all");
  const [agentFilter, setAgentFilter] = useState("all");

  const agents = useMemo(() => [...new Set(events.map(e => e.agent_id).filter(Boolean))], [events]);
  const filtered = events.filter(ev => {
    const r = EVENT_RESULT[ev.event] ?? "info";
    return (filter === "all" || r === filter) && (agentFilter === "all" || ev.agent_id === agentFilter);
  });

  const approvedCount = events.filter(e => EVENT_RESULT[e.event] === "approved").length;
  const deniedCount   = events.filter(e => EVENT_RESULT[e.event] === "denied").length;
  const revokedCount  = events.filter(e => EVENT_RESULT[e.event] === "revoked").length;

  return (
    <div className="p-8 max-w-5xl">
      <SectionHeader title="Audit Log"
        subtitle="Append-only event stream for every access lifecycle event"
        action={
          <button className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground border border-border rounded-md px-3 py-1.5 hover:bg-muted transition-colors">
            <Copy size={13} /> Export CSV
          </button>
        }
      />

      <div className="grid grid-cols-4 gap-4 mb-6">
        <StatCard label="Total events" value={events.length} icon={Activity} />
        <StatCard label="Approved / Issued" value={approvedCount} icon={CheckCircle2} color="text-green-600"
          sub={events.length > 0 ? `${Math.round(approvedCount / events.length * 100)}% rate` : undefined} />
        <StatCard label="Denied" value={deniedCount} icon={XCircle} color="text-red-600" />
        <StatCard label="Revoked / Ended" value={revokedCount} icon={RefreshCw} color="text-amber-600" />
      </div>

      <div className="bg-card rounded-lg border border-border overflow-hidden">
        <div className="flex items-center gap-3 px-4 py-3 border-b border-border flex-wrap">
          <div className="flex items-center gap-1 bg-muted rounded-md p-0.5">
            {(["all", "approved", "denied", "revoked"] as const).map(v => (
              <button key={v} onClick={() => setFilter(v)}
                className={`text-xs px-3 py-1 rounded transition-colors font-medium capitalize ${filter === v ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"}`}>
                {v}
              </button>
            ))}
          </div>
          <div className="relative">
            <select value={agentFilter} onChange={e => setAgentFilter(e.target.value)}
              className="text-xs bg-muted border-0 rounded-md pl-3 pr-7 py-1.5 appearance-none text-muted-foreground focus:outline-none focus:ring-1 ring-primary">
              <option value="all">All agents</option>
              {agents.map(a => <option key={a} value={a}>{a.slice(0, 24)}</option>)}
            </select>
            <ChevronDown size={12} className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
          </div>
          <span className="text-xs text-muted-foreground ml-auto">{filtered.length} events</span>
        </div>

        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-muted-foreground font-medium border-b border-border">
              <th className="text-left px-4 py-2.5 font-medium">Time</th>
              <th className="text-left px-4 py-2.5 font-medium">Event</th>
              <th className="text-left px-4 py-2.5 font-medium">Service</th>
              <th className="text-left px-4 py-2.5 font-medium">Agent</th>
              <th className="text-left px-4 py-2.5 font-medium">Scope</th>
              <th className="text-left px-4 py-2.5 font-medium">Detail</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((ev, i) => (
              <tr key={ev.id ?? i} className="border-b border-border last:border-0 hover:bg-muted/40 transition-colors">
                <td className="px-4 py-3 text-xs text-muted-foreground font-['DM_Mono',monospace] whitespace-nowrap">
                  {fmtDateTime(ev.timestamp ?? ev.created_at)}
                </td>
                <td className="px-4 py-3"><EventBadge event={ev.event} /></td>
                <td className="px-4 py-3">
                  <span className="flex items-center gap-1.5 text-sm text-foreground capitalize">
                    <Globe size={12} className="text-muted-foreground" />{ev.service || "—"}
                  </span>
                </td>
                <td className="px-4 py-3 text-xs text-muted-foreground font-['DM_Mono',monospace]">
                  {ev.agent_id?.slice(0, 18) || "—"}
                </td>
                <td className="px-4 py-3">
                  {ev.scope?.length > 0
                    ? <span className="text-xs font-['DM_Mono',monospace] text-muted-foreground">[{ev.scope.join(", ")}]</span>
                    : <span className="text-muted-foreground text-xs">—</span>}
                </td>
                <td className="px-4 py-3 text-xs text-muted-foreground max-w-[220px] truncate" title={ev.detail}>
                  {ev.detail || "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {filtered.length === 0 && (
          <div className="py-16 text-center text-muted-foreground text-sm">
            {events.length === 0
              ? "No events yet — simulate a request and approve it to see the full lifecycle here."
              : "No events match the current filter."}
          </div>
        )}
      </div>
    </div>
  );
};

// ─── Screen: Connected Accounts ───────────────────────────────────────────────

const FALLBACK_ACCOUNTS = [
  { id: "fa1", service: "amazon", username: "agent@acme.co", tenant_id: "demo-tenant", created_at: "" },
  { id: "fa2", service: "google", username: "agent@acme.co", tenant_id: "demo-tenant", created_at: "" },
  { id: "fa3", service: "github", username: "ci@acme.co",    tenant_id: "demo-tenant", created_at: "" },
  { id: "fa4", service: "slack",  username: "bot@acme.co",   tenant_id: "demo-tenant", created_at: "" },
  { id: "fa5", service: "jira",   username: "pm@acme.co",    tenant_id: "demo-tenant", created_at: "" },
];

const AccountsScreen = ({ accounts }: { accounts: Account[] }) => {
  const [search, setSearch] = useState("");
  const display = accounts.length > 0 ? accounts : FALLBACK_ACCOUNTS;
  const filtered = display.filter(a =>
    a.service.toLowerCase().includes(search.toLowerCase()) ||
    a.username.toLowerCase().includes(search.toLowerCase()) ||
    a.tenant_id.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="p-8 max-w-4xl">
      <SectionHeader title="Connected Accounts"
        subtitle="Service accounts stored in the encrypted vault — agents request scoped access to these"
        action={
          <button className="flex items-center gap-2 bg-primary text-primary-foreground text-sm font-medium px-4 py-2 rounded-md hover:bg-primary/90 transition-colors">
            <Plus size={15} /> Add Account
          </button>
        }
      />

      <div className="grid grid-cols-3 gap-4 mb-6">
        <StatCard label="Total accounts" value={display.length} icon={Globe} sub={`${new Set(display.map(a => a.tenant_id)).size} tenant(s)`} />
        <StatCard label="Unique services" value={new Set(display.map(a => a.service)).size} icon={Zap} color="text-blue-600" />
        <StatCard label="Vault status" value="Locked" icon={Shield} color="text-green-600" sub="AES-256-GCM" />
      </div>

      <div className="bg-card rounded-lg border border-border overflow-hidden">
        <div className="flex items-center gap-3 px-4 py-3 border-b border-border">
          <div className="relative flex-1 max-w-xs">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input type="text" placeholder="Search accounts…" value={search} onChange={e => setSearch(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 text-sm bg-muted rounded-md outline-none focus:ring-1 ring-primary placeholder:text-muted-foreground/70" />
          </div>
          <button className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors px-3 py-1.5 rounded-md hover:bg-muted">
            <Filter size={13} /> Filter
          </button>
        </div>

        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-muted-foreground font-medium border-b border-border">
              <th className="text-left px-4 py-2.5 font-medium">Service</th>
              <th className="text-left px-4 py-2.5 font-medium">Username</th>
              <th className="text-left px-4 py-2.5 font-medium">Tenant</th>
              <th className="text-left px-4 py-2.5 font-medium">Credentials</th>
              <th className="text-left px-4 py-2.5 font-medium">Status</th>
              <th className="px-4 py-2.5" />
            </tr>
          </thead>
          <tbody>
            {filtered.map((acc, i) => (
              <tr key={acc.id}
                className={`border-b border-border last:border-0 hover:bg-muted/50 transition-colors group ${i % 2 === 0 ? "" : "bg-muted/20"}`}>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2.5">
                    <div className="w-7 h-7 rounded bg-muted flex items-center justify-center text-xs font-bold text-muted-foreground">
                      {acc.service[0]?.toUpperCase()}
                    </div>
                    <span className="font-medium text-foreground capitalize">{acc.service}</span>
                  </div>
                </td>
                <td className="px-4 py-3 font-['DM_Mono',monospace] text-xs text-foreground">{acc.username}</td>
                <td className="px-4 py-3 text-xs text-muted-foreground font-['DM_Mono',monospace]">{acc.tenant_id}</td>
                <td className="px-4 py-3">
                  <span className="font-['DM_Mono',monospace] text-xs text-muted-foreground">••••••••••••</span>
                </td>
                <td className="px-4 py-3">
                  <span className="inline-flex items-center gap-1.5 text-xs font-medium font-['DM_Mono',monospace] text-green-700">
                    <span className="w-2 h-2 rounded-full bg-green-500 inline-block" /> active
                  </span>
                </td>
                <td className="px-4 py-3">
                  <button className="opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded hover:bg-muted text-muted-foreground hover:text-foreground">
                    <MoreHorizontal size={15} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {filtered.length === 0 && (
          <div className="py-12 text-center text-muted-foreground text-sm">No accounts match your search.</div>
        )}
        {accounts.length === 0 && (
          <div className="px-4 py-2 text-center text-xs text-muted-foreground/50 border-t border-border">
            Showing demo data — add real accounts to the vault to see them here
          </div>
        )}
      </div>
    </div>
  );
};

// ─── Screen: Agent Overview ───────────────────────────────────────────────────

const AgentsScreen = ({ requests, pendingCount, onGoToRequests }: {
  requests: BackendRequest[];
  pendingCount: number;
  onGoToRequests: () => void;
}) => {
  const agents = useMemo(() => {
    const map = new Map<string, {
      id: string; requests: number; services: Set<string>; lastSeen: string;
      approved: number; denied: number;
    }>();
    for (const req of requests) {
      const ex = map.get(req.agent_id);
      if (ex) {
        ex.requests++;
        ex.services.add(req.service);
        if (req.created_at > ex.lastSeen) ex.lastSeen = req.created_at;
        if (req.state === "APPROVED") ex.approved++;
        if (req.state === "DENIED") ex.denied++;
      } else {
        map.set(req.agent_id, {
          id: req.agent_id, requests: 1, services: new Set([req.service]),
          lastSeen: req.created_at,
          approved: req.state === "APPROVED" ? 1 : 0,
          denied: req.state === "DENIED" ? 1 : 0,
        });
      }
    }
    return Array.from(map.values()).sort((a, b) => b.requests - a.requests);
  }, [requests]);

  return (
    <div className="p-8 max-w-4xl">
      <SectionHeader title="Agent Overview"
        subtitle="All agents observed making requests — derived from live request history"
      />

      {pendingCount > 0 && (
        <button onClick={onGoToRequests}
          className="w-full mb-6 flex items-center gap-3 bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 hover:bg-amber-100 transition-colors text-left group">
          <AlertCircle size={16} className="text-amber-500 shrink-0" />
          <span className="text-sm text-amber-800 flex-1">
            <span className="font-semibold">{pendingCount} request{pendingCount !== 1 ? "s" : ""}</span> awaiting your review
          </span>
          <span className="text-xs text-amber-600 flex items-center gap-1 group-hover:gap-2 transition-all">
            Go to Requests <ChevronRight size={12} />
          </span>
        </button>
      )}

      <div className="grid grid-cols-3 gap-4 mb-6">
        <StatCard label="Unique agents" value={agents.length} icon={Bot} />
        <StatCard label="Total requests" value={requests.length} icon={Activity} color="text-blue-600" />
        <StatCard label="Approved" value={requests.filter(r => r.state === "APPROVED").length} icon={CheckCircle2} color="text-green-600"
          sub={requests.length > 0 ? `${Math.round(requests.filter(r => r.state === "APPROVED").length / requests.length * 100)}% rate` : undefined} />
      </div>

      <div className="bg-card rounded-lg border border-border overflow-hidden">
        <div className="px-4 py-3 border-b border-border">
          <span className="text-sm font-medium text-foreground">All Agents</span>
        </div>
        {agents.length === 0 ? (
          <div className="py-16 text-center">
            <Bot size={28} className="mx-auto text-muted-foreground/30 mb-3" />
            <p className="text-sm text-muted-foreground">No agent activity yet.</p>
            <p className="text-xs text-muted-foreground mt-1">Simulate a request on the Requests screen to see agents here.</p>
          </div>
        ) : (
          <div className="divide-y divide-border">
            {agents.map(agent => (
              <div key={agent.id} className="px-4 py-4 hover:bg-muted/40 transition-colors">
                <div className="flex items-start gap-4">
                  <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center text-primary shrink-0">
                    <Bot size={18} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-medium text-sm text-foreground font-['DM_Mono',monospace]">{agent.id}</span>
                      <span className="inline-block w-2 h-2 rounded-full bg-green-500" />
                    </div>
                    <div className="text-xs text-muted-foreground mb-2">Last seen {fmtDateTime(agent.lastSeen)}</div>
                    <div className="flex items-center gap-1.5 flex-wrap">
                      {Array.from(agent.services).map(s => (
                        <span key={s} className="inline-flex items-center gap-1 px-2 py-0.5 bg-muted rounded text-xs text-muted-foreground capitalize">
                          <Globe size={10} /> {s}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="text-right shrink-0">
                    <div className="text-lg font-semibold font-['Outfit',sans-serif] text-foreground">{agent.requests}</div>
                    <div className="text-xs text-muted-foreground">requests</div>
                    <div className="text-xs mt-0.5">
                      <span className="text-green-600">{agent.approved} ✓</span>
                      {agent.denied > 0 && <span className="text-red-500 ml-1">{agent.denied} ✕</span>}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

// ─── Screen: Settings ─────────────────────────────────────────────────────────

const SettingsScreen = () => {
  const [notifications, setNotifications] = useState({ accessRequests: true, deniedAttempts: true, weeklyDigest: true });
  const [integrations, setIntegrations] = useState({ claude: true, openai: true, gemini: false, autogpt: true });

  const Toggle = ({ on, onToggle }: { on: boolean; onToggle: () => void }) => (
    <button onClick={onToggle}
      className={`relative rounded-full transition-colors focus:outline-none focus:ring-2 ring-primary ring-offset-1 ${on ? "bg-primary" : "bg-muted"}`}
      style={{ width: "38px", height: "22px" }}>
      <span className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${on ? "translate-x-[16px]" : "translate-x-0"}`} />
    </button>
  );

  return (
    <div className="p-8 max-w-2xl space-y-6">
      <SectionHeader title="Settings" subtitle="Security, notifications, and AI platform integrations" />

      <div className="bg-card rounded-lg border border-border overflow-hidden">
        <div className="px-5 py-3 border-b border-border"><span className="text-sm font-semibold text-foreground">Profile</span></div>
        <div className="p-5 flex items-center gap-5">
          <div className="w-14 h-14 rounded-full bg-primary/15 flex items-center justify-center">
            <DogLogo size={32} className="text-primary" />
          </div>
          <div className="flex-1">
            <div className="text-base font-semibold text-foreground">Jordan Lee</div>
            <div className="text-sm text-muted-foreground">jordan@acme.co</div>
            <div className="text-xs text-muted-foreground mt-1">Workspace Admin · Acme Corp</div>
          </div>
          <button className="text-sm text-primary hover:underline">Edit</button>
        </div>
      </div>

      <div className="bg-card rounded-lg border border-border overflow-hidden">
        <div className="px-5 py-3 border-b border-border"><span className="text-sm font-semibold text-foreground">Security</span></div>
        <div className="divide-y divide-border">
          {[
            { icon: Fingerprint, label: "Two-factor authentication", desc: "Protect your account with 2FA", right: <Badge variant="success"><Check size={10} /> Enabled</Badge> },
            { icon: Clock, label: "Audit log retention", desc: "How long to keep access history", right: <span className="flex items-center gap-2 text-sm"><span className="font-['DM_Mono',monospace] text-foreground">90 days</span><button className="text-xs text-primary hover:underline">Change</button></span> },
            { icon: Shield, label: "Master vault key", desc: "AES-256-GCM · Argon2id KDF", right: <Badge variant="success"><Check size={10} /> Active</Badge> },
          ].map(({ icon: Icon, label, desc, right }) => (
            <div key={label} className="px-5 py-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Icon size={15} className="text-muted-foreground" />
                <div>
                  <div className="text-sm font-medium text-foreground">{label}</div>
                  <div className="text-xs text-muted-foreground">{desc}</div>
                </div>
              </div>
              {right}
            </div>
          ))}
        </div>
      </div>

      <div className="bg-card rounded-lg border border-border overflow-hidden">
        <div className="px-5 py-3 border-b border-border"><span className="text-sm font-semibold text-foreground">Notifications</span></div>
        <div className="divide-y divide-border">
          {[
            { key: "accessRequests", label: "New access requests", desc: "When an agent submits a request" },
            { key: "deniedAttempts",  label: "Denied / blocked actions", desc: "When an agent is scope-blocked" },
            { key: "weeklyDigest",   label: "Weekly digest", desc: "Summary of all agent activity" },
          ].map(({ key, label, desc }) => (
            <div key={key} className="px-5 py-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Bell size={15} className="text-muted-foreground" />
                <div>
                  <div className="text-sm font-medium text-foreground">{label}</div>
                  <div className="text-xs text-muted-foreground">{desc}</div>
                </div>
              </div>
              <Toggle on={notifications[key as keyof typeof notifications]}
                onToggle={() => setNotifications(n => ({ ...n, [key]: !n[key as keyof typeof n] }))} />
            </div>
          ))}
        </div>
      </div>

      <div className="bg-card rounded-lg border border-border overflow-hidden">
        <div className="px-5 py-3 border-b border-border"><span className="text-sm font-semibold text-foreground">AI Platform Integrations</span></div>
        <div className="divide-y divide-border">
          {[
            { key: "claude",   label: "Anthropic Claude",     desc: "Allow Claude agents via MCP" },
            { key: "openai",   label: "OpenAI GPT",           desc: "Allow GPT agents via SDK" },
            { key: "gemini",   label: "Google Gemini",        desc: "Allow Gemini agents via SDK" },
            { key: "autogpt",  label: "AutoGPT / Open-source",desc: "Allow open-source agents" },
          ].map(({ key, label, desc }) => (
            <div key={key} className="px-5 py-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-7 h-7 rounded bg-primary/10 flex items-center justify-center">
                  <Zap size={13} className="text-primary" />
                </div>
                <div>
                  <div className="text-sm font-medium text-foreground">{label}</div>
                  <div className="text-xs text-muted-foreground">{desc}</div>
                </div>
              </div>
              <Toggle on={integrations[key as keyof typeof integrations]}
                onToggle={() => setIntegrations(n => ({ ...n, [key]: !n[key as keyof typeof n] }))} />
            </div>
          ))}
        </div>
      </div>

      <div className="bg-card rounded-lg border border-red-200 overflow-hidden">
        <div className="px-5 py-3 border-b border-red-200"><span className="text-sm font-semibold text-red-600">Danger Zone</span></div>
        <div className="p-5 flex items-center justify-between">
          <div>
            <div className="text-sm font-medium text-foreground">Delete workspace</div>
            <div className="text-xs text-muted-foreground">Permanently remove all accounts, tokens, and audit history</div>
          </div>
          <button className="text-xs text-red-600 border border-red-200 hover:bg-red-50 transition-colors px-3 py-1.5 rounded font-medium flex items-center gap-1">
            <Trash2 size={12} /> Delete
          </button>
        </div>
      </div>
    </div>
  );
};

// ─── Sidebar ──────────────────────────────────────────────────────────────────

const NAV: { id: Screen; label: string; icon: React.ElementType }[] = [
  { id: "requests", label: "Requests",           icon: Inbox   },
  { id: "sessions", label: "Active Sessions",    icon: Zap     },
  { id: "audit",    label: "Audit Log",          icon: Activity},
  { id: "accounts", label: "Connected Accounts", icon: Globe   },
  { id: "agents",   label: "Agent Overview",     icon: Bot     },
];

const Sidebar = ({ screen, setScreen, pendingCount, sessionCount, connected }: {
  screen: Screen; setScreen: (s: Screen) => void;
  pendingCount: number; sessionCount: number; connected: boolean;
}) => (
  <aside className="w-56 shrink-0 flex flex-col h-full bg-sidebar text-sidebar-foreground border-r border-sidebar-border">
    {/* Logo */}
    <div className="px-5 pt-6 pb-4 flex items-center gap-3">
      <div className="text-primary"><DogLogo size={34} /></div>
      <div>
        <div className="font-['Outfit',sans-serif] font-bold text-base tracking-tight text-sidebar-foreground leading-none">Doberman</div>
        <div className="text-[10px] text-sidebar-foreground/40 mt-0.5 font-['DM_Mono',monospace] leading-none">v0.15.0</div>
      </div>
    </div>

    <div className="mx-4 h-px bg-sidebar-border mb-3" />

    <nav className="flex-1 px-3 space-y-0.5 overflow-y-auto scrollbar-none">
      <div className="text-[10px] font-semibold text-sidebar-foreground/40 uppercase tracking-widest px-2 py-2 font-['DM_Mono',monospace]">
        Workspace
      </div>
      {NAV.map(({ id, label, icon: Icon }) => {
        const isActive = screen === id;
        const badge = id === "requests" ? pendingCount : id === "sessions" ? sessionCount : 0;
        return (
          <button key={id} onClick={() => setScreen(id)}
            className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-md text-sm transition-colors text-left ${
              isActive ? "bg-primary text-primary-foreground font-medium"
              : "text-sidebar-foreground/65 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
            }`}>
            <Icon size={15} />
            <span className="flex-1 font-['Figtree',sans-serif]">{label}</span>
            {badge > 0 && (
              <span className={`text-[10px] font-bold min-w-[18px] h-[18px] px-1 rounded-full flex items-center justify-center ${
                isActive ? "bg-white text-primary" : "bg-primary text-white"
              }`}>{badge}</span>
            )}
          </button>
        );
      })}

      <div className="text-[10px] font-semibold text-sidebar-foreground/40 uppercase tracking-widest px-2 py-2 mt-2 font-['DM_Mono',monospace]">
        Account
      </div>
      <button onClick={() => setScreen("settings")}
        className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-md text-sm transition-colors text-left ${
          screen === "settings" ? "bg-primary text-primary-foreground font-medium"
          : "text-sidebar-foreground/65 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
        }`}>
        <Settings size={15} />
        <span className="font-['Figtree',sans-serif]">Settings</span>
      </button>
    </nav>

    <div className="mx-4 h-px bg-sidebar-border mb-3" />

    {/* Footer */}
    <div className="px-4 pb-5">
      <div className="flex items-center gap-1.5 mb-3 px-1">
        {connected
          ? <Wifi size={12} className="text-green-500" />
          : <WifiOff size={12} className="text-muted-foreground" />}
        <span className={`text-[11px] font-['DM_Mono',monospace] ${connected ? "text-green-600" : "text-muted-foreground"}`}>
          {connected ? "Live" : "Connecting…"}
        </span>
      </div>
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center text-primary text-xs font-bold">JL</div>
        <div className="flex-1 min-w-0">
          <div className="text-xs font-medium text-sidebar-foreground truncate">Jordan Lee</div>
          <div className="text-[11px] text-sidebar-foreground/40 truncate">Admin</div>
        </div>
        <button className="text-sidebar-foreground/40 hover:text-sidebar-foreground transition-colors">
          <LogOut size={14} />
        </button>
      </div>
    </div>
  </aside>
);

// ─── App root ─────────────────────────────────────────────────────────────────

export default function App() {
  const [screen, setScreen]         = useState<Screen>("requests");
  const [connected, setConnected]   = useState(false);
  const [requests, setRequests]     = useState<BackendRequest[]>([]);
  const [sessions, setSessions]     = useState<BackendRequest[]>([]);
  const [auditEvents, setAudit]     = useState<AuditEvent[]>([]);
  const [accounts, setAccounts]     = useState<Account[]>([]);

  // ── Initial fetch ──────────────────────────────────────────────────────────
  const reload = useCallback(async () => {
    try {
      const [reqData, sessData, auditData] = await Promise.all([
        api.allRequests(60), api.sessions(), api.audit(120),
      ]);
      setRequests(reqData.requests ?? []);
      setSessions(sessData.sessions ?? []);
      setAudit(auditData.events ?? []);
    } catch (e) { console.error("[App] load:", e); }

    try {
      const { tenants } = await api.tenants();
      const all: Account[] = [];
      for (const t of (tenants ?? [])) {
        try {
          const { accounts: accs } = await api.accounts(t.id);
          for (const a of (accs ?? [])) all.push(a);
        } catch { /* skip */ }
      }
      setAccounts(all);
    } catch { /* vault cold start */ }
  }, []);

  useEffect(() => { reload(); }, [reload]);

  // ── Socket connection ──────────────────────────────────────────────────────
  useEffect(() => {
    const on = () => setConnected(true);
    const off = () => setConnected(false);
    socket.on("connect", on);
    socket.on("disconnect", off);
    if (socket.connected) setConnected(true);
    return () => { socket.off("connect", on); socket.off("disconnect", off); };
  }, []);

  // ── Socket: new request ────────────────────────────────────────────────────
  useEffect(() => {
    const fn = ({ request }: { request: BackendRequest }) =>
      setRequests(prev => prev.find(r => r.id === request.id) ? prev : [request, ...prev]);
    socket.on("request:new", fn);
    return () => { socket.off("request:new", fn); };
  }, []);

  // ── Socket: request resolved / revoked ────────────────────────────────────
  useEffect(() => {
    const onResolved = ({ request }: { request: BackendRequest }) =>
      setRequests(prev => prev.map(r => r.id === request.id ? request : r));
    const onRevoked = ({ request_id, state }: { request_id: string; state: string }) =>
      setRequests(prev => prev.map(r => r.id === request_id ? { ...r, state: state as any } : r));
    socket.on("request:resolved", onResolved);
    socket.on("token:revoked", onRevoked);
    return () => { socket.off("request:resolved", onResolved); socket.off("token:revoked", onRevoked); };
  }, []);

  // ── Socket: sessions ───────────────────────────────────────────────────────
  useEffect(() => {
    const onStarted = ({ request }: { request: BackendRequest }) => {
      if (!request?.token_id) return;
      setSessions(prev => prev.find(s => s.id === request.id) ? prev : [request, ...prev]);
    };
    const onEnded = ({ request_id }: { request_id: string }) =>
      setSessions(prev => prev.filter(s => s.id !== request_id));
    socket.on("session:started", onStarted);
    socket.on("session:ended", onEnded);
    return () => { socket.off("session:started", onStarted); socket.off("session:ended", onEnded); };
  }, []);

  // ── Socket: audit events ───────────────────────────────────────────────────
  useEffect(() => {
    const fn = (ev: AuditEvent) => setAudit(prev => [ev, ...prev].slice(0, 500));
    socket.on("audit:event", fn);
    return () => { socket.off("audit:event", fn); };
  }, []);

  // ── Approve / Deny ─────────────────────────────────────────────────────────
  const handleApprove = useCallback(async (id: string, scope?: string[]) => {
    const data = await api.approve(id, scope);
    if (data.request) setRequests(prev => prev.map(r => r.id === id ? data.request : r));
  }, []);

  const handleDeny = useCallback(async (id: string) => {
    const data = await api.deny(id);
    if (data.request) setRequests(prev => prev.map(r => r.id === id ? data.request : r));
  }, []);

  const handleSessionEnded = useCallback((id: string) =>
    setSessions(prev => prev.filter(s => s.id !== id)), []);

  const pendingCount = requests.filter(r => r.state === "PENDING").length;

  const renderScreen = () => {
    switch (screen) {
      case "requests": return <RequestsScreen requests={requests} onApprove={handleApprove} onDeny={handleDeny} pendingCount={pendingCount} />;
      case "sessions": return <SessionsScreen sessions={sessions} onEnded={handleSessionEnded} onGoToRequests={() => setScreen("requests")} />;
      case "audit":    return <AuditScreen events={auditEvents} />;
      case "accounts": return <AccountsScreen accounts={accounts} />;
      case "agents":   return <AgentsScreen requests={requests} pendingCount={pendingCount} onGoToRequests={() => setScreen("requests")} />;
      case "settings": return <SettingsScreen />;
    }
  };

  return (
    <div className="h-screen w-screen flex bg-background font-['Figtree',sans-serif] overflow-hidden">
      <Sidebar screen={screen} setScreen={setScreen}
        pendingCount={pendingCount} sessionCount={sessions.length} connected={connected} />
      <main className="flex-1 overflow-y-auto scrollbar-none">
        <motion.div key={screen} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.2, ease: [0.25, 0.1, 0.25, 1] }}>
          {renderScreen()}
        </motion.div>
      </main>
    </div>
  );
}
