import os
import tempfile

import pytest

from core.crypto import argon2id_hash, aes_gcm_encrypt
from core.vault import Vault, VaultError

# MOCK: Argon2id m=256 for fast tests; production uses m=65536
_FAST_M = 256


def _fast_vault_create(path: str, password: str = "test-master-pw") -> Vault:
    """Create vault with fast Argon2id params for tests."""
    from core.crypto import aes_gcm_encrypt
    key, salt = argon2id_hash(password, m=_FAST_M)
    v = Vault(path, key)
    sentinel = b"Doberman-vault-v1"
    v._conn.execute("INSERT OR REPLACE INTO vault_meta VALUES (?, ?)", ("argon2_salt", salt))
    v._conn.execute("INSERT OR REPLACE INTO vault_meta VALUES (?, ?)", ("check_blob", aes_gcm_encrypt(key, sentinel)))
    v._conn.commit()
    return v


def _fast_vault_unlock(path: str, password: str = "test-master-pw") -> Vault:
    """Unlock vault with fast Argon2id params for tests."""
    import sqlite3
    tmp = sqlite3.connect(path)
    tmp.row_factory = sqlite3.Row
    salt_row = tmp.execute("SELECT v FROM vault_meta WHERE k='argon2_salt'").fetchone()
    check_row = tmp.execute("SELECT v FROM vault_meta WHERE k='check_blob'").fetchone()
    tmp.close()
    from core.crypto import aes_gcm_decrypt
    key, _ = argon2id_hash(password, bytes(salt_row["v"]), m=_FAST_M)
    plaintext = aes_gcm_decrypt(key, bytes(check_row["v"]))
    assert plaintext == b"Doberman-vault-v1"
    return Vault(path, key)


@pytest.fixture
def vault(tmp_path):
    db = str(tmp_path / "test.db")
    v = _fast_vault_create(db)
    yield v
    v.close()


@pytest.fixture
def vault_path(tmp_path):
    return str(tmp_path / "test.db")


# --- create / unlock ---

def test_create_and_unlock(vault_path):
    v = _fast_vault_create(vault_path, "hunter2")
    v.close()
    v2 = _fast_vault_unlock(vault_path, "hunter2")
    assert v2 is not None
    v2.close()


def test_wrong_password_raises(vault_path):
    v = _fast_vault_create(vault_path, "correct")
    v.close()
    import sqlite3
    from core.crypto import aes_gcm_decrypt
    tmp = sqlite3.connect(vault_path)
    tmp.row_factory = sqlite3.Row
    salt_row = tmp.execute("SELECT v FROM vault_meta WHERE k='argon2_salt'").fetchone()
    check_row = tmp.execute("SELECT v FROM vault_meta WHERE k='check_blob'").fetchone()
    tmp.close()
    key_wrong, _ = argon2id_hash("wrong-password", bytes(salt_row["v"]), m=_FAST_M)
    with pytest.raises(Exception):
        aes_gcm_decrypt(key_wrong, bytes(check_row["v"]))


# --- tenants ---

def test_add_and_get_tenant(vault):
    tid = vault.add_tenant("AcmeCorp")
    t = vault.get_tenant(tid)
    assert t["id"] == tid
    assert t["name"] == "AcmeCorp"
    assert "created_at" in t


def test_list_tenants(vault):
    vault.add_tenant("Alpha")
    vault.add_tenant("Beta")
    tenants = vault.list_tenants()
    names = {t["name"] for t in tenants}
    assert {"Alpha", "Beta"} == names


def test_get_nonexistent_tenant_returns_none(vault):
    assert vault.get_tenant("no-such-id") is None


def test_delete_tenant(vault):
    tid = vault.add_tenant("ToDelete")
    assert vault.delete_tenant(tid) is True
    assert vault.get_tenant(tid) is None


def test_delete_nonexistent_tenant_returns_false(vault):
    assert vault.delete_tenant("ghost") is False


def test_duplicate_tenant_name_raises(vault):
    vault.add_tenant("Unique")
    with pytest.raises(Exception):
        vault.add_tenant("Unique")


# --- service accounts ---

def test_add_and_get_service_account(vault):
    tid = vault.add_tenant("Tenant1")
    creds = {"password": "s3cr3t", "region": "us-east-1"}
    acct_id = vault.add_service_account(tid, "Amazon", "user@amazon.com", creds)
    acct = vault.get_service_account(acct_id)
    assert acct["service"] == "Amazon"
    assert acct["username"] == "user@amazon.com"
    assert acct["tenant_id"] == tid


def test_credentials_masked_by_default(vault):
    tid = vault.add_tenant("T")
    acct_id = vault.add_service_account(tid, "svc", "u", {"password": "top-secret", "region": "eu"})
    acct = vault.get_service_account(acct_id)
    assert acct["credentials"]["password"] == "***"
    assert acct["credentials"]["region"] == "eu"  # non-sensitive field is visible


def test_credentials_revealed_with_flag(vault):
    tid = vault.add_tenant("T2")
    acct_id = vault.add_service_account(tid, "svc", "u", {"password": "real-pass"})
    acct = vault.get_service_account(acct_id, reveal=True)
    assert acct["credentials"]["password"] == "real-pass"


def test_list_service_accounts_masked(vault):
    tid = vault.add_tenant("ListTenant")
    vault.add_service_account(tid, "AWS", "a@a.com", {"password": "pw1", "key": "k1"})
    vault.add_service_account(tid, "GCP", "b@b.com", {"password": "pw2"})
    accounts = vault.list_service_accounts(tid)
    assert len(accounts) == 2
    for a in accounts:
        assert a["credentials"]["password"] == "***"


def test_list_service_accounts_tenant_isolation(vault):
    tid1 = vault.add_tenant("Corp1")
    tid2 = vault.add_tenant("Corp2")
    vault.add_service_account(tid1, "AWS", "a@corp1.com", {"password": "pw"})
    vault.add_service_account(tid2, "AWS", "b@corp2.com", {"password": "pw"})
    assert len(vault.list_service_accounts(tid1)) == 1
    assert len(vault.list_service_accounts(tid2)) == 1


def test_update_service_account_credentials(vault):
    tid = vault.add_tenant("UpdTenant")
    acct_id = vault.add_service_account(tid, "svc", "u", {"password": "old"})
    vault.update_service_account_credentials(acct_id, {"password": "new", "token": "tok"})
    acct = vault.get_service_account(acct_id, reveal=True)
    assert acct["credentials"]["password"] == "new"
    assert acct["credentials"]["token"] == "tok"


def test_delete_service_account(vault):
    tid = vault.add_tenant("DelTenant")
    acct_id = vault.add_service_account(tid, "svc", "u", {"password": "pw"})
    assert vault.delete_service_account(acct_id) is True
    assert vault.get_service_account(acct_id) is None


def test_delete_nonexistent_account_returns_false(vault):
    assert vault.delete_service_account("ghost") is False


def test_get_nonexistent_account_returns_none(vault):
    assert vault.get_service_account("nope") is None


def test_various_sensitive_keys_masked(vault):
    tid = vault.add_tenant("SensitiveTenant")
    creds = {
        "password": "p",
        "client_secret": "s",
        "access_token": "a",
        "refresh_token": "r",
        "api_key": "k",
        "cookie": "c",
        "region": "us",
        "url": "https://example.com",
    }
    acct_id = vault.add_service_account(tid, "svc", "u", creds)
    acct = vault.get_service_account(acct_id)
    masked = acct["credentials"]
    assert masked["password"] == "***"
    assert masked["client_secret"] == "***"
    assert masked["access_token"] == "***"
    assert masked["refresh_token"] == "***"
    assert masked["api_key"] == "***"
    assert masked["cookie"] == "***"
    assert masked["region"] == "us"
    assert masked["url"] == "https://example.com"


# --- revoked tokens ---

def test_revoke_and_check_token(vault):
    tid = vault.add_tenant("RevokeTenant")
    token_id = "tok-abc-123"
    assert not vault.is_token_revoked(token_id)
    vault.revoke_token(token_id, tid)
    assert vault.is_token_revoked(token_id)


def test_revoke_same_token_twice_is_idempotent(vault):
    tid = vault.add_tenant("Idempotent")
    vault.revoke_token("tok-x", tid)
    vault.revoke_token("tok-x", tid)  # should not raise
    assert vault.is_token_revoked("tok-x")


def test_list_revoked_tokens(vault):
    tid = vault.add_tenant("ListRevoke")
    vault.revoke_token("tok-1", tid)
    vault.revoke_token("tok-2", tid)
    revoked = vault.list_revoked_tokens(tid)
    ids = {r["token_id"] for r in revoked}
    assert ids == {"tok-1", "tok-2"}


def test_revoked_tokens_tenant_isolation(vault):
    tid1 = vault.add_tenant("RevokeC1")
    tid2 = vault.add_tenant("RevokeC2")
    vault.revoke_token("tok-t1", tid1)
    vault.revoke_token("tok-t2", tid2)
    assert len(vault.list_revoked_tokens(tid1)) == 1
    assert vault.list_revoked_tokens(tid1)[0]["token_id"] == "tok-t1"


def test_non_revoked_token_not_in_list(vault):
    tid = vault.add_tenant("NRTenant")
    assert vault.list_revoked_tokens(tid) == []
