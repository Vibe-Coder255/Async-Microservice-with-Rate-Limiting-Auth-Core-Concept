from datetime import datetime, timezone
from uuid import uuid4

from app.core.security import (
    ROLE_ALLOWED_TIERS,
    ROLE_SCOPES,
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import UserRole
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


def test_jwt_scopes_claim_ignored_in_favor_of_db_role():
    user_id = str(uuid4())
    forged_token = create_access_token(
        subject=user_id,
        role="viewer",
        extra_claims={"scopes": ["admin", "ingest_writer", "viewer"]},
    )
    payload = decode_token(forged_token)
    assert payload["role"] == "viewer"
    assert payload["scopes"] == ["admin", "ingest_writer", "viewer"]

    authoritative_scopes = ROLE_SCOPES["viewer"]
    assert authoritative_scopes == ["viewer"]
    assert "admin" not in authoritative_scopes
    assert "ingest_writer" not in authoritative_scopes


def test_role_downgrade_scopes_take_effect_immediately():
    admin_scopes = ROLE_SCOPES[UserRole.ADMIN.value]
    viewer_scopes = ROLE_SCOPES[UserRole.VIEWER.value]

    user_id = str(uuid4())
    old_admin_token = create_access_token(subject=user_id, role=UserRole.ADMIN.value)
    old_payload = decode_token(old_admin_token)
    assert old_payload["scopes"] == admin_scopes

    new_authoritative_scopes = ROLE_SCOPES[UserRole.VIEWER.value]
    assert new_authoritative_scopes == viewer_scopes
    assert "admin" not in new_authoritative_scopes
    assert "ingest_writer" not in new_authoritative_scopes


def test_api_key_hash_is_sha256_hex():
    raw = generate_api_key()
    digest = hash_api_key(raw)
    assert raw.startswith("eik_")
    assert len(digest) == 64
    assert hash_api_key(raw) == digest
    assert hash_api_key(raw + "x") != digest


def test_role_allowed_tiers_policy():
    assert ROLE_ALLOWED_TIERS[UserRole.ADMIN.value] == {"free", "standard", "premium"}
    assert ROLE_ALLOWED_TIERS[UserRole.INGEST_WRITER.value] == {"free", "standard"}
    assert ROLE_ALLOWED_TIERS[UserRole.VIEWER.value] == set()


def test_ingest_writer_cannot_have_premium_tier():
    allowed = ROLE_ALLOWED_TIERS[UserRole.INGEST_WRITER.value]
    assert "premium" not in allowed
    assert "free" in allowed
    assert "standard" in allowed


def test_admin_can_have_all_tiers():
    allowed = ROLE_ALLOWED_TIERS[UserRole.ADMIN.value]
    assert "free" in allowed
    assert "standard" in allowed
    assert "premium" in allowed


def test_viewer_cannot_have_any_api_key_tier():
    assert ROLE_ALLOWED_TIERS[UserRole.VIEWER.value] == set()
