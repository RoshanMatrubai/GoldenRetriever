import datetime
import json
import sqlite3

from core.crypto import aes_gcm_decrypt, aes_gcm_encrypt, argon2id_hash, random_id

_SENTINEL = b"Doberman-vault-v1"
_MASK = "***"
_SENSITIVE = {"password", "secret", "token", "cookie", "key", "access_token",
              "refresh_token", "client_secret"}


class VaultError(Exception):
    pass


class Vault:
    def __init__(self, db_path: str, key: bytes):
        self._key = key
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS vault_meta (
                k TEXT PRIMARY KEY,
                v BLOB NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tenants (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS service_accounts (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL REFERENCES tenants(id),
                service TEXT NOT NULL,
                username TEXT NOT NULL,
                creds_blob BLOB NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS revoked_tokens (
                token_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                revoked_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS cookie_cache (
                id TEXT PRIMARY KEY,
                service TEXT NOT NULL,
                username TEXT NOT NULL,
                cookies_blob BLOB NOT NULL,
                cached_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                UNIQUE(service, username)
            );
        """)
        self._conn.commit()

    @staticmethod
    def create(db_path: str, master_password: str) -> "Vault":
        """Create a new vault; derives key via Argon2id, stores salt + check blob."""
        key, salt = argon2id_hash(master_password)
        v = Vault(db_path, key)
        check = aes_gcm_encrypt(key, _SENTINEL)
        v._conn.execute("INSERT OR REPLACE INTO vault_meta VALUES (?, ?)", ("argon2_salt", salt))
        v._conn.execute("INSERT OR REPLACE INTO vault_meta VALUES (?, ?)", ("check_blob", check))
        v._conn.commit()
        return v

    @staticmethod
    def unlock(db_path: str, master_password: str) -> "Vault":
        """Open existing vault; re-derives key, verifies password via check blob."""
        tmp = sqlite3.connect(db_path)
        tmp.row_factory = sqlite3.Row
        try:
            salt_row = tmp.execute("SELECT v FROM vault_meta WHERE k='argon2_salt'").fetchone()
            if not salt_row:
                raise VaultError("Not a Doberman vault database")
            check_row = tmp.execute("SELECT v FROM vault_meta WHERE k='check_blob'").fetchone()
        finally:
            tmp.close()

        key, _ = argon2id_hash(master_password, bytes(salt_row["v"]))
        try:
            plaintext = aes_gcm_decrypt(key, bytes(check_row["v"]))
        except Exception:
            raise VaultError("Wrong master password")
        if plaintext != _SENTINEL:
            raise VaultError("Vault integrity check failed")
        return Vault(db_path, key)

    def get_key(self) -> bytes:
        """Expose vault key as master secret for per-hint HMAC derivation."""
        return self._key

    def close(self):
        self._conn.close()

    # --- Tenants ---

    def add_tenant(self, name: str) -> str:
        tid = random_id()
        self._conn.execute(
            "INSERT INTO tenants (id, name, created_at) VALUES (?, ?, ?)",
            (tid, name, _now()),
        )
        self._conn.commit()
        return tid

    def get_tenant(self, tenant_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT id, name, created_at FROM tenants WHERE id=?", (tenant_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_tenants(self) -> list[dict]:
        rows = self._conn.execute("SELECT id, name, created_at FROM tenants").fetchall()
        return [dict(r) for r in rows]

    def delete_tenant(self, tenant_id: str) -> bool:
        cur = self._conn.execute("DELETE FROM tenants WHERE id=?", (tenant_id,))
        self._conn.commit()
        return cur.rowcount > 0

    # --- Service accounts ---

    def add_service_account(
        self, tenant_id: str, service: str, username: str, credentials: dict
    ) -> str:
        """Encrypt credentials with AES-GCM and store. Returns account id."""
        acct_id = random_id()
        blob = aes_gcm_encrypt(self._key, json.dumps(credentials).encode())
        self._conn.execute(
            "INSERT INTO service_accounts (id, tenant_id, service, username, creds_blob, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (acct_id, tenant_id, service, username, blob, _now()),
        )
        self._conn.commit()
        return acct_id

    def get_service_account(self, account_id: str, *, reveal: bool = False) -> dict | None:
        """Return account dict. Sensitive credential fields masked unless reveal=True."""
        row = self._conn.execute(
            "SELECT id, tenant_id, service, username, creds_blob, created_at"
            " FROM service_accounts WHERE id=?",
            (account_id,),
        ).fetchone()
        return _format_account(row, self._key, reveal=reveal) if row else None

    def list_service_accounts(self, tenant_id: str, *, reveal: bool = False) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, tenant_id, service, username, creds_blob, created_at"
            " FROM service_accounts WHERE tenant_id=?",
            (tenant_id,),
        ).fetchall()
        return [_format_account(r, self._key, reveal=reveal) for r in rows]

    def update_service_account_credentials(self, account_id: str, credentials: dict) -> bool:
        blob = aes_gcm_encrypt(self._key, json.dumps(credentials).encode())
        cur = self._conn.execute(
            "UPDATE service_accounts SET creds_blob=? WHERE id=?", (blob, account_id)
        )
        self._conn.commit()
        return cur.rowcount > 0

    def delete_service_account(self, account_id: str) -> bool:
        cur = self._conn.execute("DELETE FROM service_accounts WHERE id=?", (account_id,))
        self._conn.commit()
        return cur.rowcount > 0

    # --- Revoked tokens ---

    def revoke_token(self, token_id: str, tenant_id: str) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO revoked_tokens (token_id, tenant_id, revoked_at)"
            " VALUES (?, ?, ?)",
            (token_id, tenant_id, _now()),
        )
        self._conn.commit()

    def is_token_revoked(self, token_id: str) -> bool:
        return self._conn.execute(
            "SELECT 1 FROM revoked_tokens WHERE token_id=?", (token_id,)
        ).fetchone() is not None

    def list_revoked_tokens(self, tenant_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT token_id, tenant_id, revoked_at FROM revoked_tokens WHERE tenant_id=?",
            (tenant_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # --- Cookie cache (headless session reuse) ---

    def set_cookie_cache(self, service: str, username: str, cookies: list) -> None:
        """Encrypt and store cookies with a 6 h TTL (overwrite any existing entry)."""
        import config
        expires = (
            datetime.datetime.now(datetime.UTC)
            + datetime.timedelta(seconds=config.COOKIE_CACHE_TTL_SECONDS)
        ).isoformat()
        blob = aes_gcm_encrypt(self._key, json.dumps(cookies).encode())
        self._conn.execute(
            "INSERT OR REPLACE INTO cookie_cache"
            " (id, service, username, cookies_blob, cached_at, expires_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (random_id(), service, username, blob, _now(), expires),
        )
        self._conn.commit()

    def get_cookie_cache(self, service: str, username: str) -> list | None:
        """Return decrypted cookies if the cache entry is still fresh; None otherwise."""
        row = self._conn.execute(
            "SELECT cookies_blob, expires_at FROM cookie_cache WHERE service=? AND username=?",
            (service, username),
        ).fetchone()
        if not row:
            return None
        expires_at = datetime.datetime.fromisoformat(row["expires_at"])
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=datetime.UTC)
        if datetime.datetime.now(datetime.UTC) > expires_at:
            return None
        return json.loads(aes_gcm_decrypt(self._key, bytes(row["cookies_blob"])))


# --- helpers ---

def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def _mask_credentials(creds: dict) -> dict:
    return {
        k: _MASK if any(s in k.lower() for s in _SENSITIVE) else v
        for k, v in creds.items()
    }


def _format_account(row: sqlite3.Row, key: bytes, *, reveal: bool) -> dict:
    creds = json.loads(aes_gcm_decrypt(key, bytes(row["creds_blob"])))
    return {
        "id": row["id"],
        "tenant_id": row["tenant_id"],
        "service": row["service"],
        "username": row["username"],
        "credentials": creds if reveal else _mask_credentials(creds),
        "created_at": row["created_at"],
    }
