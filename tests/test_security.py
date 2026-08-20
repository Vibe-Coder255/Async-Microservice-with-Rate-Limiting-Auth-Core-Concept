from datetime import datetime, timezone
from uuid import uuid4

from app.core.security import create_access_token, decode_token, hash_password, verify_password
from app.services.rate_limiter import generate_api_key, hash_api_key


def test_password_hash_roundtrip():
    hashed = hash_password("s3cret-pass")
    assert hashed != "s3cret-pass"
    assert verify_password("s3cret-pass", hashed)
    assert not verify_password("wrong", hashed)


def test_jwt_contains_role_and_scopes():
    user_id = str(uuid4())
    token = create_access_token(subject=user_id, role="ingest_writer")
    payload = decode_token(token)
    assert payload["sub"] == user_id
    assert payload["role"] == "ingest_writer"
    assert "ingest_writer" in payload["scopes"]
    assert "viewer" in payload["scopes"]
    assert "admin" not in payload["scopes"]
    exp = payload["exp"]
    assert datetime.fromtimestamp(exp, tz=timezone.utc) > datetime.now(timezone.utc)


def test_api_key_hash_is_sha256_hex():
    raw = generate_api_key()
    digest = hash_api_key(raw)
    assert raw.startswith("eik_")
    assert len(digest) == 64
    assert hash_api_key(raw) == digest
    assert hash_api_key(raw + "x") != digest
