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

# Headless-login site adapters (stub — populated in Phase 14)
SERVICE_ADAPTERS: dict = {}

# Vault master password — used to derive the AES-256-GCM vault key (MOCK for dev)
VAULT_MASTER_PASSWORD = "gr-dev-master-password"  # MOCK — replace before any real deployment

# Build-completion ping key (Claude Code only — not a product feature)
BARK_KEY = os.environ.get("BARK_KEY", "Ty6uAVeqkSq5D2u35yMotQ")
