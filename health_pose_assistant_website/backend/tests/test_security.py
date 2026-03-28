"""Unit tests for core/security.py — JWT, password hashing, device tokens."""

from datetime import timedelta

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
    generate_device_token,
    hash_device_token,
)


class TestPasswordHashing:
    def test_hash_and_verify(self):
        hashed = hash_password("secret123")
        assert hashed != "secret123"
        assert verify_password("secret123", hashed)

    def test_wrong_password(self):
        hashed = hash_password("secret123")
        assert not verify_password("wrong", hashed)

    def test_different_hashes(self):
        h1 = hash_password("same")
        h2 = hash_password("same")
        # bcrypt salts should differ
        assert h1 != h2


class TestJWT:
    def test_create_and_decode(self):
        token = create_access_token({"sub": "42"})
        payload = decode_access_token(token)
        assert payload is not None
        assert payload["sub"] == "42"
        assert "exp" in payload

    def test_expired_token(self):
        token = create_access_token({"sub": "1"}, expires_delta=timedelta(seconds=-1))
        assert decode_access_token(token) is None

    def test_invalid_token(self):
        assert decode_access_token("garbage.token.value") is None

    def test_empty_token(self):
        assert decode_access_token("") is None


class TestDeviceToken:
    def test_generate_returns_pair(self):
        plain, hashed = generate_device_token()
        assert len(plain) > 20
        assert len(hashed) == 64  # SHA-256 hex

    def test_hash_deterministic(self):
        assert hash_device_token("abc") == hash_device_token("abc")

    def test_hash_matches_generated(self):
        plain, hashed = generate_device_token()
        assert hash_device_token(plain) == hashed

    def test_different_tokens(self):
        p1, _ = generate_device_token()
        p2, _ = generate_device_token()
        assert p1 != p2
