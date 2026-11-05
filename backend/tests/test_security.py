"""Security tests."""


from app.core.security import create_access_token, decode_token, hash_password, verify_password


def test_password_hashing():
    hashed = hash_password("secret123")
    assert hashed != "secret123"
    assert verify_password("secret123", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_jwt_token_roundtrip():
    token = create_access_token(subject="42", extra_claims={"role": "admin"})
    payload = decode_token(token)
    assert payload is not None
    assert payload["sub"] == "42"
    assert payload["role"] == "admin"
    assert payload["type"] == "access"


def test_jwt_invalid_token():
    assert decode_token("not.a.valid.token") is None
