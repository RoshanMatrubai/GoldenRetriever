import os

# Server ports
DASHBOARD_PORT = 5001
AGENT_API_PORT = 5002

# Database
DB_PATH = os.path.join(os.path.dirname(__file__), "vault.db")

# Token / request lifetimes (seconds)
TOKEN_TTL_SECONDS = 900   # 15 min — never renewable, always re-request
REQUEST_TTL_SECONDS = 60  # pending request expires if not acted on

# Per-agent rate limiting for access requests
RATE_LIMIT_REQUESTS = 10   # max requests per agent per window
RATE_LIMIT_WINDOW_SECONDS = 60  # sliding window duration

# Ed25519 identity key (never commit this file)
TOKEN_KEY_FILE = os.path.join(os.path.dirname(__file__), ".gr_identity.key")

# OAuth redirect base (fill in real values before running OAuth flow)
OAUTH_REDIRECT_URI = "http://localhost:5001/auth/callback"

# OAuth service configs — populate client_id/secret from your app registrations
OAUTH_SERVICES = {
    "google": {
        "client_id": "PLACEHOLDER_GOOGLE_CLIENT_ID",         # MOCK
        "client_secret": "PLACEHOLDER_GOOGLE_CLIENT_SECRET", # MOCK
        "scope": "openid email https://www.googleapis.com/auth/gmail.readonly",
    },
    "github": {
        "client_id": "PLACEHOLDER_GITHUB_CLIENT_ID",         # MOCK
        "client_secret": "PLACEHOLDER_GITHUB_CLIENT_SECRET", # MOCK
        "scope": "repo read:user",
    },
}

# Encrypted cookie cache TTL for headless sessions (6 hours)
COOKIE_CACHE_TTL_SECONDS = 21600

# Adapter type per service name — drives auth/adapters/ dispatch
SERVICE_ADAPTERS: dict = {
    "google": "oauth",
    "github": "oauth",
    "amazon": "headless",
}

# Vault master password — used to derive the AES-256-GCM vault key (MOCK for dev)
VAULT_MASTER_PASSWORD = "gr-dev-master-password"  # MOCK — replace before any real deployment

# MCP server defaults — used when running python main.py --mcp
MCP_AGENT_API_URL = f"http://localhost:{AGENT_API_PORT}"  # connects to the running backend
MCP_DEFAULT_TENANT = "demo"          # tenant ID injected into MCP tool calls
MCP_DEFAULT_AGENT = "claude-mcp"     # agent ID injected into MCP tool calls
MCP_POLL_TIMEOUT = 300               # seconds to wait for admin approval (5 min)

# Build-completion ping key (Claude Code only — not a product feature)
BARK_KEY = os.environ.get("BARK_KEY", "Ty6uAVeqkSq5D2u35yMotQ")
